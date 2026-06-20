# -*- coding: utf-8 -*-
"""
Visual Word Splitter — 对公式密集型 Word(.docx) 走"整页视觉 OCR"补全题面。

背景
----
化学/物理/数学高考 Word 卷的公式是 MathType OLE/VML 对象（``<w:object>`` →
``<v:imagedata>`` → WMF），python-docx 只读 ``w:t`` 会把公式、化学式、离子式、
电子排布式、Ksp 表格全部丢掉 → DeepSeek 收到 ``options_length=0`` 的残题，判
"硬伤/未评估"。

本模块在 native ``word_splitter`` 之外做**加法式增强**，绝不替换主路径：

1. 默认行为与 native 完全一致（生物 / 叙述卷 / 非目标学科零触发、零额外延迟）。
2. 仅对"目标学科(化/物/数) 且 公式密集" 或 "native 拆题质量异常" 的卷，
   走 docx → PDF(LibreOffice) → 页面图(fitz) → Qwen-VL 逐页 OCR(试卷专用 prompt)
   → 按主题号混合回填（只在 OCR 比 native 更完整时替换 ``content``）。
3. 任意环节失败一律 **fail-open 回 native**，绝不让整卷分析失败。

与 native ``WordSplitter.split`` 返回结构完全一致：
``{"questions": [...], "method": ..., "confidence": ..., "warnings": [...]}``
"""
from __future__ import annotations

import os
import re
import base64
import hashlib
import asyncio
import zipfile
import tempfile
import subprocess
from typing import Dict, Any, List, Optional, Tuple

from logger import get_logger
from word_splitter import WordQuestionSplitter

logger = get_logger()

# ── 试卷专用 OCR Prompt（不可复用教材 prompt）────────────────────────────
EXAM_OCR_PROMPT = """你是高考试卷数字化专家。请把这张试卷图片中的全部文字**原样**转写为纯文本，严格遵守：
1. 完整保留题号（如"4."、"12."、"16."）、小题号（如"（1）""（2）"）和选项标号（A. B. C. D.）。
2. 化学式、离子符号、电子排布式、化学方程式、离子方程式必须按原样转写：下标用 ₀₁₂₃₄₅₆₇₈₉，上标用 ⁰¹²³⁺⁻，例如 Na₂SO₄、(NH₄)₂CO₃、Mn²⁺、HCO₃⁻、Ksp、3d⁸4s²。
3. 表格转写为 Markdown 表格，保留全部数据（如 Ksp 数值 8.0×10⁻²⁷、pH 数值）。
4. 数学/物理公式按原样转写，保留上下标、根号、分数、单位。
5. 流程图/装置图：用一行文字描述其中的物质和箭头流向，不要遗漏物质名称。
6. 去除页眉、页脚、页码、密封线、"第X页共X页"等无关内容。
7. 按阅读顺序输出。**不要解释、不要作答、不要改写题意**，只输出题目原文。"""

# ── 触发阈值 ──────────────────────────────────────────────────────────
# 目标学科：仅这些学科在"公式密集"时才走视觉。生物等叙述卷显式排除。
_VISUAL_SUBJECT_TOKENS = ("chem", "phys", "math", "化学", "物理", "数学")
_NON_VISUAL_SUBJECT_TOKENS = (
    "biolog", "生物", "english", "英语", "chinese", "语文",
    "history", "历史", "geo", "地理", "politic", "政治", "道德",
)
# 公式对象密度阈值：真化学卷 VML≈157；生物卷 VML≈15（不触发）。
_OLE_ABS_THRESHOLD = 30          # 绝对数量
_OLE_PER_Q_THRESHOLD = 2.0       # 每题平均
# 渲染与并发
_RENDER_DPI = 2.1                # fitz Matrix 缩放（72*2.1≈151dpi，已在真卷验证）
_OCR_CONCURRENCY = 3
_OCR_MAX_TOKENS = 8000
_LIBREOFFICE_TIMEOUT = 90
# OCR 结果缓存（按文件内容 hash），容量很小，仅防同文件重试重复 OCR
_OCR_CACHE: "Dict[str, List[Optional[str]]]" = {}
_OCR_CACHE_MAX = 8


# ─────────────────────────────────────────────────────────────────────
# 公式对象密度检测
# ─────────────────────────────────────────────────────────────────────
def count_formula_objects(docx_path: str) -> Dict[str, int]:
    """解包 docx，统计 MathType/VML 公式对象与 WMF 渲染图数量。"""
    res = {"vml": 0, "ole": 0, "wmf": 0, "omml": 0}
    try:
        with zipfile.ZipFile(docx_path) as z:
            names = z.namelist()
            res["wmf"] = sum(
                1 for n in names if n.lower().endswith((".wmf", ".emf"))
            )
            blob_parts = []
            for n in names:
                if n.startswith("word/") and n.endswith(".xml"):
                    try:
                        blob_parts.append(z.read(n).decode("utf-8", "ignore"))
                    except Exception:
                        pass
            blob = "".join(blob_parts)
            res["vml"] = blob.count("<v:imagedata")
            res["ole"] = blob.count("OLEObject")
            res["omml"] = blob.count("<m:oMath")
    except Exception as e:  # 损坏/非 zip 文档：返回全 0，不触发视觉
        logger.warning(f"[VisualSplit] 解包统计公式对象失败: {e}")
    return res


def _subject_class(subject: Optional[str]) -> Optional[bool]:
    """True=目标学科(化/物/数)，False=明确非目标(生物等)，None=未知。"""
    if not subject:
        return None
    s = str(subject).strip().lower()
    if any(t in s for t in _NON_VISUAL_SUBJECT_TOKENS):
        return False
    if any(t in s for t in _VISUAL_SUBJECT_TOKENS):
        return True
    return None


def assess_native_quality(questions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """评估 native 拆题质量。题面普遍异常短 → 疑似公式被掏空。"""
    n = len(questions)
    if n == 0:
        return {"bad": False, "reason": "no_questions", "short_ratio": 0.0}
    short = 0
    for q in questions:
        content = str(q.get("content") or "")
        # 去掉题号前缀后的有效正文长度
        body = re.sub(r"^\s*\d{1,3}[.、．]\s*", "", content).strip()
        if len(body) < 25:
            short += 1
    short_ratio = short / n
    bad = short_ratio >= 0.25
    return {"bad": bad, "reason": "short_stems" if bad else "ok",
            "short_ratio": round(short_ratio, 3), "n": n}


def should_use_visual(
    docx_path: str, subject: Optional[str], questions: List[Dict[str, Any]]
) -> Tuple[bool, Dict[str, Any]]:
    """组合触发判定。返回 (是否走视觉, 诊断信息)。"""
    subj_cls = _subject_class(subject)
    ole = count_formula_objects(docx_path)
    qual = assess_native_quality(questions)
    q_count = max(1, len(questions))
    density_high = (
        ole["vml"] >= _OLE_ABS_THRESHOLD
        or (ole["vml"] / q_count) >= _OLE_PER_Q_THRESHOLD
    )
    diag = {"subject": subject, "subject_class": subj_cls, "ole": ole,
            "quality": qual, "density_high": density_high}

    # 明确非目标学科（生物/语文/英语…）：永不走视觉，零触碰快路径。
    if subj_cls is False:
        diag["decision"] = "native_non_target_subject"
        return False, diag

    # 目标学科 或 未知学科：公式密集 或 native 质量异常 → 走视觉
    use = density_high or qual["bad"]
    diag["decision"] = "visual" if use else "native_low_density"
    return use, diag


# ─────────────────────────────────────────────────────────────────────
# docx → pdf → 页面 OCR
# ─────────────────────────────────────────────────────────────────────
def docx_to_pdf(docx_path: str, out_dir: str) -> str:
    """用 LibreOffice 把 docx 转为 pdf，返回 pdf 路径。失败抛异常。"""
    result = subprocess.run(
        ["libreoffice", "--headless", "--convert-to", "pdf",
         "--outdir", out_dir, docx_path],
        capture_output=True, text=True, timeout=_LIBREOFFICE_TIMEOUT,
    )
    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice 转 PDF 失败: {result.stderr[:200]}")
    stem = os.path.splitext(os.path.basename(docx_path))[0]
    pdf_path = os.path.join(out_dir, f"{stem}.pdf")
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"转换后 PDF 未找到: {pdf_path}")
    return pdf_path


async def _ocr_pdf_pages(pdf_path: str) -> List[Optional[str]]:
    """逐页 OCR，返回每页 markdown（失败页为 None）。并发限流。"""
    import fitz  # 局部导入，避免模块加载期硬依赖
    from vision_processor import VisionProcessor

    vp = VisionProcessor()
    doc = fitz.open(pdf_path)
    try:
        total = doc.page_count
        sem = asyncio.Semaphore(_OCR_CONCURRENCY)

        async def one(page_num: int) -> Optional[str]:
            async with sem:
                try:
                    img_b64 = vp.pdf_page_to_image(doc, page_num, dpi=_RENDER_DPI)
                except Exception as e:
                    logger.warning(f"[VisualSplit] P{page_num} 渲染失败，降级跳过: {e}")
                    return None
                # 单次重试：应对瞬时空响应 / 限流 / 超时
                for attempt in range(2):
                    try:
                        md = await vp.extract_page_markdown(
                            img_b64, page_num,
                            prompt=EXAM_OCR_PROMPT, max_tokens=_OCR_MAX_TOKENS,
                        )
                        if md:
                            return md
                    except Exception as e:
                        logger.warning(f"[VisualSplit] P{page_num} OCR 异常(attempt {attempt}): {e}")
                    if attempt == 0:
                        await asyncio.sleep(2)
                logger.warning(f"[VisualSplit] P{page_num} OCR 两次失败，降级跳过")
                return None

        return await asyncio.gather(*[one(p) for p in range(1, total + 1)])
    finally:
        doc.close()


def _ocr_with_cache(docx_path: str) -> List[Optional[str]]:
    """docx → pdf → 逐页 OCR（带文件 hash 缓存）。同步入口，内部 asyncio.run。"""
    try:
        with open(docx_path, "rb") as f:
            file_hash = hashlib.sha1(f.read()).hexdigest()
    except Exception:
        file_hash = None

    if file_hash and file_hash in _OCR_CACHE:
        logger.info("[VisualSplit] 命中 OCR 缓存")
        return _OCR_CACHE[file_hash]

    tmp_dir = tempfile.mkdtemp(prefix="vsplit_")
    try:
        pdf_path = docx_to_pdf(docx_path, tmp_dir)
        pages = asyncio.run(_ocr_pdf_pages(pdf_path))
    finally:
        try:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass

    if file_hash is not None:
        if len(_OCR_CACHE) >= _OCR_CACHE_MAX:
            _OCR_CACHE.pop(next(iter(_OCR_CACHE)))
        _OCR_CACHE[file_hash] = pages
    return pages


# ─────────────────────────────────────────────────────────────────────
# OCR markdown → {主题号: 题面文本}
# ─────────────────────────────────────────────────────────────────────
# 严格主题号：行首仅允许空白 + 1~2 位数字 + 分隔符 + 空白。
# 显式排除括号小题号"（4）/(4)"（不以数字开头）；排除"1.5"（点后非空白）。
_MAIN_QNUM_RE = re.compile(r"^\s*(\d{1,2})[.、．]\s")
# 考试注意事项噪音（与 native _detect_question_number 同源）：试卷开头的
# "1.答卷前…准考证号" / "2.回答选择题…答题卡" / "3.考试结束后…" 这些编号项
# 不是题目，必须跳过，否则会顶高单调递增计数器导致真 Q1/Q2/Q3 被吞。
_NOISE_QNUM_RE = [
    re.compile(r"^\s*\d{1,2}[.、．]\s*(答卷前|答题前|请按|选择题用|考试结束|注意事项|填涂|核对)"),
    re.compile(r"^\s*\d{1,2}[.、．].*(答题卡|试题卷|试卷|草稿纸|准考证|条形码|铅笔|签字笔)"),
]


def _detect_main_qnum(line: str) -> Optional[int]:
    m = _MAIN_QNUM_RE.match(line)
    if not m:
        return None
    for noise in _NOISE_QNUM_RE:
        if noise.match(line):
            return None  # 注意事项编号项，非题号
    return int(m.group(1))


def parse_ocr_questions(
    pages: List[Optional[str]], valid_ids: Optional[set] = None
) -> Dict[int, str]:
    """把逐页 OCR markdown 按主题号重组为 {题号: 整题文本}。

    防串题三重约束（OCR 常把"（4）"子问转写成"4."而与主题号撞号）：
    1. 严格行首主题号（非括号、点后必须空白）；
    2. **单调递增**——主题号必须 > 已见最大主题号，故大题之后出现的小号被拒；
    3. **白名单**——仅接受 native 真实存在的主题号。
    跨页续行自动归到当前题；不满足约束的行并入当前题正文。
    """
    result: Dict[int, List[str]] = {}
    current: Optional[int] = None
    last_main = 0
    for md in pages:
        if not md:
            continue
        for raw_line in md.splitlines():
            line = raw_line.rstrip()
            qid = _detect_main_qnum(line)
            accept = (
                qid is not None
                and qid > last_main
                and (valid_ids is None or qid in valid_ids)
            )
            if accept:
                current = qid
                last_main = qid
                result.setdefault(qid, [])
                result[qid].append(line)
            elif current is not None:
                result[current].append(line)
    return {qid: "\n".join(lines).strip() for qid, lines in result.items()}


# ─────────────────────────────────────────────────────────────────────
# 混合回填
# ─────────────────────────────────────────────────────────────────────
def _merge_ocr_into_native(
    native: Dict[str, Any], ocr_map: Dict[int, str]
) -> Dict[str, Any]:
    """把 OCR 题面回填进 native 题目。只在 OCR 更完整时替换，逐题 fail-open。"""
    questions = native.get("questions", [])
    native_ids = [q.get("id") for q in questions if isinstance(q.get("id"), int)]
    ocr_ids = set(ocr_map)
    overlap = [i for i in native_ids if i in ocr_ids]

    native.setdefault("warnings", [])

    # 题号序列对不上（OCR 拆题不可信）→ 整卷 fail-open 回 native
    if native_ids and len(overlap) < 0.6 * len(native_ids):
        logger.warning(
            f"[VisualSplit] 题号匹配率过低 {len(overlap)}/{len(native_ids)}，"
            f"fail-open 回 native"
        )
        native["warnings"].append("visual_ocr_split_mismatch")
        native.setdefault("visual_ocr", {})
        native["visual_ocr"].update(
            {"used": True, "filled": 0, "reason": "id_mismatch",
             "native_ids": len(native_ids), "matched": len(overlap)}
        )
        return native

    filled, missing = 0, 0
    for q in questions:
        qid = q.get("id")
        if not isinstance(qid, int):
            continue
        ocr_text = ocr_map.get(qid)
        if not ocr_text or len(ocr_text) < 15:
            missing += 1
            continue
        native_content = str(q.get("content") or "")
        body = re.sub(r"^\s*\d{1,3}[.、．]\s*", "", native_content).strip()
        # 仅在 OCR 明显更完整（更长）或 native 题面被掏空（短）时替换
        if len(ocr_text) > len(native_content) or len(body) < 25:
            q["content"] = ocr_text
            warns = q.setdefault("warnings", [])
            if "visual_ocr_filled" not in warns:
                warns.append("visual_ocr_filled")
            filled += 1

    native["warnings"].append("visual_ocr_applied")
    native.setdefault("visual_ocr", {})
    native["visual_ocr"].update(
        {"used": True, "filled": filled, "missing": missing,
         "native_ids": len(native_ids), "ocr_ids": len(ocr_ids)}
    )
    native["method"] = (native.get("method") or "word_native") + "+visual_ocr"
    logger.info(
        f"[VisualSplit] 视觉回填完成: 替换 {filled} 题 / 共 {len(native_ids)} 题"
    )
    return native


# ─────────────────────────────────────────────────────────────────────
# 顶层统一入口
# ─────────────────────────────────────────────────────────────────────
def split_word_with_visual(file_path: str, subject: Optional[str] = None) -> Dict[str, Any]:
    """统一 Word 拆题入口：native 拆题 +（按需）视觉 OCR 回填。

    - native 拆题异常**照常抛出**（上游错误映射保持不变）。
    - 视觉增强全程 try/except，失败一律 fail-open 回 native。
    - 替代 ``word_splitter.split(file_path)`` 的全部调用点。
    """
    native = WordQuestionSplitter().split(file_path)  # 异常透传，保留上游 400 错误映射

    try:
        questions = native.get("questions", [])
        use_visual, diag = should_use_visual(file_path, subject, questions)
        logger.info(f"[VisualSplit] 触发判定: {diag.get('decision')} | "
                    f"subject={subject} ole={diag['ole']} "
                    f"quality={diag['quality']}")
        if not use_visual:
            return native

        pages = _ocr_with_cache(file_path)
        ok_pages = sum(1 for p in pages if p)
        if ok_pages == 0:
            logger.warning("[VisualSplit] 全部页面 OCR 失败，fail-open 回 native")
            native.setdefault("warnings", []).append("visual_ocr_all_pages_failed")
            return native

        native_ids = {q.get("id") for q in questions if isinstance(q.get("id"), int)}
        ocr_map = parse_ocr_questions(pages, valid_ids=native_ids)
        merged = _merge_ocr_into_native(native, ocr_map)
        merged.setdefault("visual_ocr", {})
        merged["visual_ocr"].update(
            {"pages_total": len(pages), "pages_ok": ok_pages, "diag": diag}
        )
        return merged

    except Exception as e:
        logger.error(f"[VisualSplit] 视觉增强失败，fail-open 回 native: {e}",
                     exc_info=True)
        native.setdefault("warnings", []).append("visual_ocr_pipeline_error")
        return native
