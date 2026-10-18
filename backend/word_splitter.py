"""
Word文档题目拆分器
基于python-docx提取结构化内容，准确识别题目、图片和表格
"""

import re
import base64
import io
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from docx import Document
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph as DocxParagraph
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from PIL import Image, ImageDraw, ImageFont
from logger import get_logger

logger = get_logger()


@dataclass
class Question:
    """题目数据结构"""
    id: int
    content: str
    images: List[Dict[str, Any]]  # 图片列表
    tables: List[Dict[str, Any]]  # 表格列表
    media: List[Dict[str, Any]]  # 按文档顺序保存图片和表格
    warnings: List[str]
    section_header: Optional[str] = None  # 分节标题


class WordQuestionSplitter:
    """Word文档题目拆分器"""

    # 题号正则模式（优先级从高到低）
    QUESTION_PATTERNS = [
        (r'^(\d+)[.、]\s*', 1.0, 'standard'),       # 1. 或 1、
        (r'^\((\d+)\)\s*', 0.9, 'parenthesis'),    # (1)
        (r'^([一二三四五六七八九十]+)[.、]\s*', 0.8, 'chinese'),  # 一、
    ]
    TABLE_CUE_PATTERN = re.compile(r"(如下表|下表|结果如下表|表中|表格|表\s*\d+|table)", re.IGNORECASE)
    IMAGE_CUE_PATTERN = re.compile(r"(如下图|下图|如图|图中|图\s*\d+|曲线|电泳|figure|fig)", re.IGNORECASE)

    # OOXML 命名空间（Clark 记法，与 lxml element.tag 对齐）
    WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    MATH_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
    # OMML 上/下标 → Unicode（化学式/离子符号/电子排布式还原；无法映射时退回 _x / ^x 文本）
    SUBSCRIPT_MAP = {
        "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄",
        "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉",
        "+": "₊", "-": "₋", "=": "₌", "(": "₍", ")": "₎",
        "a": "ₐ", "e": "ₑ", "h": "ₕ", "i": "ᵢ", "j": "ⱼ", "k": "ₖ",
        "l": "ₗ", "m": "ₘ", "n": "ₙ", "o": "ₒ", "p": "ₚ", "r": "ᵣ",
        "s": "ₛ", "t": "ₜ", "u": "ᵤ", "v": "ᵥ", "x": "ₓ",
    }
    SUPERSCRIPT_MAP = {
        "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
        "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
        "+": "⁺", "-": "⁻", "=": "⁼", "(": "⁽", ")": "⁾",
        "n": "ⁿ", "i": "ⁱ",
    }

    def __init__(self):
        logger.info("[Word拆分器] 初始化完成")

    # ── OMML（Word 公式编辑器）文本还原 ──────────────────────────
    # python-docx 的 para.text / cell.text 只读 w:t，会丢弃 m:oMath（化学式、
    # 离子符号、电子排布式、Ksp、反应方程式等公式对象）。下列方法按文档顺序把
    # OMML 文本回填到题面原位置，避免化学/物理/数学题面被掏空（治本：根因①）。

    def _paragraph_text_with_omml(self, para: DocxParagraph) -> str:
        """段落文本 = 普通 w:t + 原位置回填的 OMML 公式文本（文档顺序）。"""
        try:
            return self._node_text_in_order(para._p)
        except Exception as e:
            logger.warning(f"[OMML提取] 段落解析失败，回退 para.text: {e}")
            return para.text

    def _cell_text_with_omml(self, cell) -> str:
        """表格单元格文本（含 OMML 还原），按段落拼接。"""
        try:
            text = "\n".join(
                self._paragraph_text_with_omml(p) for p in cell.paragraphs
            )
            # OMML 走查无文本（无段落结构 / 异常 mock 等）→ 退回 cell.text，避免掏空
            return text if text.strip() else cell.text
        except Exception as e:
            logger.warning(f"[OMML提取] 单元格解析失败，回退 cell.text: {e}")
            return cell.text

    def _node_text_in_order(self, node) -> str:
        """按文档顺序递归取文本：w:t 原文 + m:oMath 公式还原；m:oMath 作为整体处理不再下钻。"""
        W, M = self.WORD_NS, self.MATH_NS
        tag = node.tag
        if not isinstance(tag, str):
            return ""  # 注释 / ProcessingInstruction 节点
        if tag == M + "oMath":
            return self._omml_to_text(node)
        if tag == W + "t":
            return node.text or ""
        if tag == W + "tab":
            return "\t"
        if tag in (W + "br", W + "cr"):
            return "\n"
        if tag == W + "delText":
            return ""  # 修订删除的文本，不计入
        return "".join(self._node_text_in_order(c) for c in node)

    def _omml_to_text(self, el) -> str:
        """把单个 OMML 子树还原为线性文本，处理常见结构（上下标/分式/根式/定界）。"""
        M = self.MATH_NS
        tag = el.tag
        if not isinstance(tag, str):
            return ""
        local = tag.split("}")[-1]
        if local == "t":
            return el.text or ""
        if local == "sSub":  # 下标（H₂O 的 ₂、SO₄ 的 ₄）
            base = self._omml_child_text(el, M + "e")
            return base + self._fmt_script(self._omml_child_text(el, M + "sub"), True)
        if local == "sSup":  # 上标（Fe³⁺ 的 ³⁺、电荷）
            base = self._omml_child_text(el, M + "e")
            return base + self._fmt_script(self._omml_child_text(el, M + "sup"), False)
        if local == "sSubSup":  # 上下标兼有（SO₄²⁻）
            base = self._omml_child_text(el, M + "e")
            sub = self._fmt_script(self._omml_child_text(el, M + "sub"), True)
            sup = self._fmt_script(self._omml_child_text(el, M + "sup"), False)
            return base + sub + sup
        if local == "f":  # 分式
            num = self._omml_child_text(el, M + "num")
            den = self._omml_child_text(el, M + "den")
            return f"({num})/({den})" if (num or den) else ""
        if local == "rad":  # 根式
            return "√(" + self._omml_child_text(el, M + "e") + ")"
        # m:d（括号定界）/ m:nary / m:func 等：默认按文档顺序线性展开子节点
        return "".join(self._omml_to_text(c) for c in el)

    def _omml_child_text(self, el, child_tag: str) -> str:
        """取 el 下指定标签（如 m:e / m:sub / m:num）直接子节点的 OMML 文本。"""
        out = []
        for c in el:
            if isinstance(c.tag, str) and c.tag == child_tag:
                out.append("".join(self._omml_to_text(g) for g in c))
        return "".join(out)

    def _fmt_script(self, s: str, sub: bool) -> str:
        """上/下标还原：能整体映射 Unicode 就映射（Cu₂S、SO₄²⁻），否则退回 _x / ^x 文本。"""
        s = (s or "").strip()
        if not s:
            return ""
        table = self.SUBSCRIPT_MAP if sub else self.SUPERSCRIPT_MAP
        if all(ch in table for ch in s):
            return "".join(table[ch] for ch in s)
        prefix = "_" if sub else "^"
        return prefix + (s if len(s) == 1 else "{" + s + "}")

    def split(self, docx_path: str) -> Dict[str, Any]:
        """
        拆分Word文档为题目列表

        返回:
        {
            "questions": [...],
            "method": "word_native",
            "confidence": 1.0,
            "total_pages": None  # Word没有页码概念
        }
        """
        logger.info(f"[Word拆分] 开始处理文档: {docx_path}")

        try:
            doc = Document(docx_path)

            # 提取所有块元素（段落和表格，按顺序）
            elements = self._extract_elements(doc)
            logger.info(f"[Word拆分] 提取到{len(elements)}个元素")

            # 识别题目边界
            questions = self._split_questions(elements)
            logger.info(f"[Word拆分] 识别到{len(questions)}道题目")

            # 转为字典格式
            result = {
                "questions": [self._question_to_dict(q) for q in questions],
                "method": "word_native",
                "confidence": 1.0,  # Word结构化，置信度100%
                "warnings": []
            }

            logger.info(f"[Word拆分] 完成，识别到{len(questions)}道题目")
            return result

        except Exception as e:
            logger.error(f"[Word拆分] 失败: {str(e)}")
            raise

    def _extract_elements(self, doc: Document) -> List[Dict]:
        """
        按顺序提取文档中的所有元素（段落和表格）
        """
        elements = []

        for element in doc.element.body:
            if isinstance(element, CT_P):
                # 段落
                para = DocxParagraph(element, doc)
                text = self._paragraph_text_with_omml(para).strip()

                # 提取段落中的图片
                images, image_warnings = self._extract_images_from_paragraph(para, doc)

                if not text and not images:
                    continue

                elements.append({
                    "type": "paragraph",
                    "text": text,
                    "images": images,
                    "warnings": image_warnings,
                    "element": para
                })

            elif isinstance(element, CT_Tbl):
                # 表格
                table = DocxTable(element, doc)
                table_image = self._table_to_image(table)
                table_text = self._table_to_markdown(table)
                table_warnings = []
                if table_text and not table_image:
                    table_warnings.append("table_media_render_failed")

                elements.append({
                    "type": "table",
                    "image_base64": table_image,
                    "text": table_text,
                    "warnings": table_warnings,
                    "element": table
                })

        return elements

    def _extract_images_from_paragraph(self, para: DocxParagraph, doc: Document) -> Tuple[List[str], List[str]]:
        """
        从段落中提取图片的base64编码
        """
        images = []
        warnings = []

        for run in para.runs:
            # 查找drawing元素（图片）
            drawings = run.element.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing')

            for drawing in drawings:
                # 查找图片关系ID
                blips = drawing.findall('.//{http://schemas.openxmlformats.org/drawingml/2006/main}blip')

                for blip in blips:
                    rId = blip.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')

                    if rId:
                        try:
                            # 获取图片二进制数据
                            image_part = doc.part.related_parts[rId]
                            image_bytes = image_part.blob

                            # 验证是否为有效图片格式（过滤MathType对象）
                            if not self._is_valid_image(image_bytes):
                                # 根因④：非标准图片多为 MathType/OLE 公式对象。OMML 已被
                                # _paragraph_text_with_omml 还原；此处剩下的是无法转文本的
                                # 公式真图，不再静默丢弃——记一个告警计入"未提取"（供目标C消费）。
                                logger.debug(f"[图片提取] 跳过非标准图片格式（可能是公式对象）")
                                warnings.append("formula_image_unextracted")
                                continue

                            image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                            images.append(image_base64)
                            logger.debug(f"[图片提取] 提取图片，大小={len(image_base64)}字节")
                        except Exception as e:
                            logger.warning(f"[图片提取] 失败: {str(e)}")
                            warnings.append("image_media_extract_failed")

        return images, list(dict.fromkeys(warnings))

    def _is_valid_image(self, image_bytes: bytes) -> bool:
        """
        验证是否为有效的图片格式（PNG/JPEG/GIF/BMP/WEBP）
        过滤掉MathType对象和其他非标准格式
        """
        if len(image_bytes) < 12:
            return False

        # 检查常见图片格式的magic number
        magic_numbers = {
            b'\x89PNG\r\n\x1a\n': 'PNG',
            b'\xff\xd8\xff': 'JPEG',
            b'GIF87a': 'GIF',
            b'GIF89a': 'GIF',
            b'BM': 'BMP',
            b'RIFF': 'WEBP',  # WEBP格式
        }

        for magic, format_name in magic_numbers.items():
            if image_bytes.startswith(magic):
                logger.debug(f"[图片验证] 识别为{format_name}格式")
                return True

        # 如果不是标准图片格式，记录前几个字节用于调试
        logger.debug(f"[图片验证] 未知格式，magic bytes: {image_bytes[:16].hex()}")
        return False

    def _table_to_markdown(self, table: DocxTable) -> str:
        """将 Word 表格转为 Markdown 文本。"""
        if not table.rows:
            return ""
        rows_data = []
        for row in table.rows:
            row_data = []
            prev_tc = None
            for cell in row.cells:
                if cell._tc is prev_tc:
                    continue  # skip merged cell duplicate
                prev_tc = cell._tc
                row_data.append(self._cell_text_with_omml(cell).strip().replace("\n", " "))
            rows_data.append(row_data)
        if not rows_data:
            return ""
        max_cols = max(len(r) for r in rows_data)
        for row in rows_data:
            while len(row) < max_cols:
                row.append("")
        lines = []
        lines.append("| " + " | ".join(rows_data[0]) + " |")
        lines.append("|" + "|".join(["---" for _ in rows_data[0]]) + "|")
        for row in rows_data[1:]:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    def _table_to_image(self, table: DocxTable) -> str:
        """
        将Word表格转为图片（截图方式）
        """
        try:
            # 提取表格文本数据（含 OMML 还原 → 合成表格图不再因公式被掏空而空白；根因②/约束③）
            rows_data = []
            for row in table.rows:
                row_data = [self._cell_text_with_omml(cell).strip() for cell in row.cells]
                rows_data.append(row_data)

            # 使用PIL绘制表格图片
            return self._render_table_as_image(rows_data)

        except Exception as e:
            logger.warning(f"[表格转图] 失败: {str(e)}")
            return ""

    def _render_table_as_image(self, rows_data: List[List[str]]) -> str:
        """
        使用PIL将表格数据渲染为图片
        """
        if not rows_data:
            return ""

        # 计算表格尺寸
        num_rows = len(rows_data)
        num_cols = len(rows_data[0]) if rows_data else 0

        cell_width = 120
        cell_height = 40
        padding = 10

        img_width = num_cols * cell_width + padding * 2
        img_height = num_rows * cell_height + padding * 2

        # 创建白色背景图片
        img = Image.new('RGB', (img_width, img_height), 'white')
        draw = ImageDraw.Draw(img)

        # 尝试加载中文字体
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 14)
        except:
            font = ImageFont.load_default()

        # 绘制表格
        for i, row in enumerate(rows_data):
            for j, cell_text in enumerate(row):
                x = padding + j * cell_width
                y = padding + i * cell_height

                # 绘制单元格边框
                draw.rectangle(
                    [x, y, x + cell_width, y + cell_height],
                    outline='black',
                    width=1
                )

                # 绘制文本（居中）
                if cell_text:
                    # 简单截断过长文本
                    display_text = cell_text[:10]
                    text_bbox = draw.textbbox((0, 0), display_text, font=font)
                    text_width = text_bbox[2] - text_bbox[0]
                    text_height = text_bbox[3] - text_bbox[1]

                    text_x = x + (cell_width - text_width) // 2
                    text_y = y + (cell_height - text_height) // 2

                    draw.text((text_x, text_y), display_text, fill='black', font=font)

        # 转base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        logger.debug(f"[表格转图] 成功，尺寸={num_rows}x{num_cols}, base64长度={len(img_base64)}")
        return img_base64

    def _split_questions(self, elements: List[Dict]) -> List[Question]:
        """
        根据题号识别拆分题目
        """
        questions = []
        current_question = None
        current_section_header = None  # 当前分节标题

        for element in elements:
            if element["type"] == "paragraph":
                text = element["text"]

                # 检测是否为分节标题
                section_header = self._detect_section_header(text)
                if section_header:
                    current_section_header = section_header
                    logger.info(f"[分节检测] 识别到分节标题: {section_header}")
                    continue

                # 检测是否为题号
                question_id, pattern_type = self._detect_question_number(text)

                if question_id is not None:
                    # 新题目开始
                    if current_question:
                        questions.append(current_question)

                    current_question = Question(
                        id=question_id,
                        content=text,
                        images=element["images"].copy(),
                        tables=[],
                        media=[
                            {"type": "image", "base64": img_base64}
                            for img_base64 in element["images"]
                        ],
                        warnings=list(element.get("warnings", [])),
                        section_header=current_section_header  # 附加分节标题
                    )
                    logger.debug(f"[题号检测] 识别到题目{question_id}，模式={pattern_type}")
                else:
                    # 题目内容追加
                    if current_question:
                        if text:
                            current_question.content += "\n" + text
                        for warning in element.get("warnings", []):
                            if warning not in current_question.warnings:
                                current_question.warnings.append(warning)
                        current_question.images.extend(element["images"])
                        current_question.media.extend(
                            {"type": "image", "base64": img_base64}
                            for img_base64 in element["images"]
                        )

            elif element["type"] == "table":
                # 表格归属到当前题目
                if current_question:
                    for warning in element.get("warnings", []):
                        if warning not in current_question.warnings:
                            current_question.warnings.append(warning)
                    current_question.tables.append({
                        "image_base64": element["image_base64"]
                    })
                    current_question.media.append({
                        "type": "table",
                        "base64": element["image_base64"]
                    })
                    # Append table markdown text to content
                    table_text = element.get("text", "")
                    if table_text:
                        current_question.content += "\n" + table_text

        # 添加最后一道题
        if current_question:
            questions.append(current_question)

        return questions

    def _detect_section_header(self, text: str) -> Optional[str]:
        """
        检测文本是否为分节标题

        返回: 分节标题文本 或 None

        示例匹配：
        - "一、单选题（1-15题，每题2分，共30分）"
        - "二、多选题：本题共5小题，每小题3分，共15分"
        - "三、非选择题（本题包括必考题和选考题两部分）"
        """
        section_patterns = [
            r'^[一二三四五六七八九十]+[.、]\s*.*(选择题|非选择题|实验题|综合题|填空题|简答题)',
            r'^[一二三四五六七八九十]+[.、]\s*本题共\d+小题',
        ]

        for pattern in section_patterns:
            if re.search(pattern, text[:100]):  # 检查前100字符
                logger.debug(f"[分节检测] 匹配到分节标题: {text[:50]}")
                return text.strip()

        return None

    def _detect_question_number(self, text: str) -> Tuple[Optional[int], Optional[str]]:
        """
        检测文本是否为题号

        返回: (题号, 模式类型) 或 (None, None)
        """
        # 过滤考试注意事项（保留，不是分节标题）
        noise_patterns = [
            r'^[0-9]+[.、]\s*(答题前|请按|选择题用|考试结束|注意事项|填涂|核对)',
            r'^[0-9]+[.、].*(答题卡|试卷|草稿纸|准考证|条形码|铅笔|签字笔)',
        ]

        for noise_pattern in noise_patterns:
            if re.search(noise_pattern, text[:50]):
                logger.debug(f"[题号检测] 过滤噪音: {text[:30]}")
                return None, None

        for pattern, confidence, pattern_type in self.QUESTION_PATTERNS:
            match = re.match(pattern, text)
            if match:
                num_str = match.group(1)

                # 转为阿拉伯数字
                if pattern_type == 'chinese':
                    question_id = self._chinese_to_num(num_str)
                else:
                    question_id = int(num_str)

                return question_id, pattern_type

        return None, None

    def _chinese_to_num(self, chinese: str) -> int:
        """中文数字转阿拉伯数字"""
        chinese_num_map = {
            '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9, '十': 10
        }

        if chinese in chinese_num_map:
            return chinese_num_map[chinese]

        # 处理"十一"、"十二"等
        if chinese.startswith('十'):
            if len(chinese) == 1:
                return 10
            else:
                return 10 + chinese_num_map.get(chinese[1], 0)

        return 0

    def _question_to_dict(self, question: Question) -> Dict[str, Any]:
        """
        将Question对象转为字典

        前端接收：id, content, warnings
        后端AI使用：_media_for_ai, _section_header
        """
        # 组装media数据（仅供AI分析）
        media_for_ai = []

        for item in question.media:
            if item.get("type") in ("image", "table") and item.get("base64"):
                media_for_ai.append({
                    "type": item["type"],
                    "base64": item["base64"]
                })

        table_count = sum(1 for item in media_for_ai if item["type"] == "table")
        image_count = sum(1 for item in media_for_ai if item["type"] == "image")
        expected_table = bool(self.TABLE_CUE_PATTERN.search(question.content or ""))
        expected_image = bool(self.IMAGE_CUE_PATTERN.search(question.content or ""))
        integrity_warnings = []
        if expected_table and table_count == 0:
            integrity_warnings.append("table_media_missing")
        if expected_image and image_count == 0:
            integrity_warnings.append("image_media_missing")
        for warning in question.warnings:
            if warning in {"table_media_render_failed", "image_media_extract_failed"}:
                integrity_warnings.append(warning)
        integrity_warnings = list(dict.fromkeys(integrity_warnings))
        for warning in integrity_warnings:
            if warning not in question.warnings:
                question.warnings.append(warning)

        return {
            "id": question.id,
            "content": question.content,
            "confidence": 1.0,  # Word结构化，置信度100%
            "warnings": question.warnings,
            "has_options": False,  # Word不自动检测选项
            "cross_page": False,  # Word没有页面概念

            # 内部使用，不发给前端
            "_media_for_ai": media_for_ai,
            "media_integrity": {
                "status": "ok" if not integrity_warnings else "failed",
                "expected_table": expected_table,
                "expected_image": expected_image,
                "actual_tables": table_count,
                "actual_images": image_count,
                "warnings": integrity_warnings,
            },
            "_section_header": question.section_header  # 分节标题（如"一、单选题（1-15题，每题2分，共30分）"）
        }
