"""LLM 特征提取 v3 — 难度预测模型（工作记忆 + 推理耦合 + 陷阱密度）。

设计文档: docs/plans/2026-03-28-difficulty-v3-design.md
v3 核心变化：bloom 降为报告标签，新增 working_memory/chain_coupling/trap_density。
"""
import json
import re
from claude_client import send_message_gpt
from prompt_loader import PromptLoader
from logger import get_logger

logger = get_logger()

# === 评分维度（参与难度计算）===
SCORING_RANGES = {
    "working_memory": (1, 5),
    "reasoning_steps": (1, 10),
    "chain_coupling": (1, 3),
    "trap_density": (1, 3),
    "novelty": (1, 3),
    "knowledge_breadth": (1, 3),
}

# === 报告维度（不参与评分）===
REPORT_RANGES = {
    "bloom": (1, 6),
    "info_density": (1, 3),
    "representation_complexity": (1, 3),
}

# 合并：解析时全部提取
FEATURE_RANGES = {**SCORING_RANGES, **REPORT_RANGES}

# 解析失败时的默认值
DEFAULT_FEATURES = {
    "working_memory": 3,
    "reasoning_steps": 4,
    "chain_coupling": 2,
    "trap_density": 2,
    "novelty": 2,
    "knowledge_breadth": 2,
    "bloom": 3,
    "info_density": 2,
    "representation_complexity": 1,
}

# reason 字段
_REASON_KEYS = [
    "bloom_reason", "steps_detail", "breadth_reason",
    "density_reason", "novelty_reason", "representation_reason",
    "working_memory_reason", "coupling_reason", "trap_reason",
]

# 质量审查 + 教师点评字段
_QUALITY_KEYS = [
    "quality_scientific", "quality_normative", "quality_language",
    "quality_context", "quality_sensitivity", "teacher_comment",
]

# Bloom 中文标签
_BLOOM_LABELS = {"识记", "理解", "应用", "分析", "评价", "创造"}


def build_feature_prompt(question_text: str, options: str = "",
                         correct_answer: str = "", question_type: str = "") -> str:
    """构建特征提取 prompt（v3: 难度预测 + 质量审查 + 教学点评）。"""
    parts = [question_text]
    if options:
        parts.append(f"选项：{options}")
    if correct_answer:
        parts.append(f"正确答案：{correct_answer}")
    question_block = "\n".join(parts)

    qtype_hint = f"\n题型：{question_type}" if question_type else ""

    return f"""你是一名资深高中生物命题审查专家。请从难度预测、命题质量、教学价值三个层面严格分析这道题目。

题目：
{question_block}{qtype_hint}

请输出严格 JSON（不要多余解释）：
{{
  "working_memory": 1-5（解题关键步骤中需同时在脑中保持的信息元素数量。1=直接匹配（读题→回忆→作答），2=单一比较（两个概念对比），3=多条件筛选（3-4个条件同时考虑），4=多要素联立（4-5个信息交叉推理），5=复杂系统推理（5+要素同时操控，如多基因+环境+系谱联合分析）），
  "working_memory_reason": "列出关键步骤需同时处理的具体信息元素(≤40字)",
  "reasoning_steps": 正整数（从题目信息到答案的最少认知操作数，不含读题/看选项），
  "steps_detail": "简述推理链(≤50字)",
  "chain_coupling": 1-3（推理链各步骤的依赖关系。1=独立：各步可单独完成，错一步不影响其他（如选择题四个选项独立判断），2=部分依赖：部分步骤依赖前步结论但有独立分支，3=全链依赖：前一步错后续全错（如连续遗传推理、多步代谢通路、基因工程构建→转化→筛选→验证全链条）），
  "coupling_reason": "说明为什么是该耦合度(≤30字)",
  "trap_density": 1-3（看似正确但实际错误的推理路径或选项数量。1=低（0-1个有效干扰，答案一眼可见），2=中（2-3个选项/路径有迷惑性，需仔细排除），3=高（4+个看似合理的错误路径，或存在经典易混淆概念陷阱）），
  "trap_reason": "指出主要陷阱是什么(≤30字)",
  "novelty": 1-3（1教材原文/常见原题 2变式/改编 3全新情境/陌生素材），
  "novelty_reason": "一句话(≤20字)",
  "knowledge_breadth": 1-3（1单知识点 2跨考点 3跨模块），
  "breadth_reason": "一句话(≤20字)",
  "bloom": 1-6（该题所需的最高认知层级。注意：此字段仅用于教学报告，不影响难度评分），
  "bloom_distribution": {{"识记": 0, "理解": 0, "应用": 0, "分析": 0, "评价": 0, "创造": 0}}（各层级出现次数。选择题按选项计，非选择题按小问计），
  "bloom_reason": "描述最高层级对应的具体认知操作(≤30字)",
  "info_density": 1-3（1低≤2条 2中3-5条 3高>5条或含图表），
  "density_reason": "一句话(≤20字)",
  "representation_complexity": 1-3（1纯文字 2简单图表 3复杂系谱图/多图联读/装置图），
  "representation_reason": "一句话(≤20字)",
  "quality_score": 1-5（1=严重缺陷 2=明显问题 3=基本合格 4=较好 5=优秀。5分极少——大多数试题都有改进空间），
  "quality_scientific": "先指出问题，再给评价。检查：知识准确性、答案唯一性、有无歧义或事实错误。无问题写'无明显问题'(≤60字)",
  "quality_normative": "先指出问题，再给评价。检查：题干完整性、选项平行性、分值合理性、干扰项有效性。(≤60字)",
  "quality_language": "先指出问题，再给评价。检查：有无冗余/口语化/歧义/术语错误/表述过绝对。(≤60字)",
  "quality_context": "先指出问题，再给评价。检查：素材真实性、与考查内容关联度、背景知识门槛。(≤60字)",
  "quality_sensitivity": "先指出问题，再给评价。检查：是否涉及政治敏感话题、民族宗教争议、不当伦理情境（如人体实验、基因编辑争议性表述）、可能引发家长或社会舆论的内容。无问题写'无舆情风险'(≤60字)",
  "teacher_comment": "教师视角深度点评(≤150字)：考查目的、各小问难点归因、学生典型错误路径（具体写出学生会怎么错）、针对性教学建议"
}}

**working_memory 判例：**
- 1：直接回忆单一概念（"线粒体的功能是什么"）
- 2：两个概念比较（"有丝分裂和减数分裂的区别"）
- 3：3-4个条件同时筛选（"根据实验条件、自变量、因变量判断正确选项"）
- 4：4-5个信息交叉（"根据基因型+显隐性+连锁关系+杂交后代比例推导"）
- 5：5+要素系统推理（"多基因+多代系谱+电泳数据+概率计算联合分析"）

**chain_coupling 判例：**
- 1（独立）：选择题四个选项各自判断对错，错一个不影响其他
- 2（部分依赖）：先判断遗传方式再推基因型，但表现型分析独立
- 3（全链依赖）：基因工程"设计引物→构建载体→转化→筛选→检测"任一步错后续全偏；遗传系谱"判断显隐性→确定基因位置→推基因型→算概率"链式推理

**trap_density 判例：**
- 1：选择题只有1个有效干扰项，或填空题答案路径唯一
- 2：选择题2-3个选项都有一定迷惑性，或推理中存在1-2个常见误区
- 3：选择题所有选项都"看起来对"（如概念辨析题的细微差别），或推理中存在多个经典混淆点（如基因频率vs基因型频率、转录方向vs翻译方向）

**Bloom 判定规则（仅用于报告标签）：**
1. 选择题按选项、非选择题按小问独立判 bloom 层级
2. bloom 填最高层级，bloom_distribution 填各层级计数
3. bloom=5: "评价/论证/判断是否合理" bloom=6: "设计实验/提出方案"
"""


def parse_features(raw: str) -> dict:
    """从 LLM 原始输出解析特征，带容错和范围裁剪。"""
    data = None

    if not isinstance(raw, str):
        logger.warning(f"特征解析输入非字符串: {type(raw)}")
        return dict(DEFAULT_FEATURES)

    # 策略 1: 直接解析
    try:
        data = json.loads(raw.strip())
    except (json.JSONDecodeError, TypeError):
        pass

    # 策略 2: code block
    if data is None:
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

    # 策略 3: 第一个 JSON object（支持一层嵌套）
    if data is None:
        m = re.search(r'\{(?:[^{}]|\{[^{}]*\})*\}', raw)
        if m:
            try:
                data = json.loads(m.group())
            except json.JSONDecodeError:
                pass

    # 截断检测
    if data is None and raw.count('{') > raw.count('}'):
        logger.warning(f"[特征提取] 疑似截断：{{ 数={raw.count('{')}, }} 数={raw.count('}')}, 原始长度={len(raw)}")
        last_brace = raw.rfind('}')
        if last_brace > 0:
            try:
                candidate = raw[:last_brace + 1]
                candidate = re.sub(r',\s*"[^"]*":\s*"?[^"{}]*$', '', candidate)
                if not candidate.endswith('}'):
                    candidate += '}'
                data = json.loads(candidate)
                logger.info(f"[特征提取] 截断修复成功，恢复了 {len(data)} 个字段")
            except (json.JSONDecodeError, Exception):
                pass

    # 全部失败
    if not isinstance(data, dict):
        logger.warning(f"特征解析失败，使用默认值。原始输出: {raw[:200]}")
        return dict(DEFAULT_FEATURES)

    # 补全缺失字段 + 范围裁剪
    result = {}
    for key, (lo, hi) in FEATURE_RANGES.items():
        val = data.get(key, DEFAULT_FEATURES[key])
        try:
            val = int(val)
        except (ValueError, TypeError):
            val = DEFAULT_FEATURES[key]
        result[key] = max(lo, min(hi, val))

    # 保留 reason 字段
    for reason_key in _REASON_KEYS:
        if reason_key in data:
            result[reason_key] = str(data[reason_key])[:50]

    # bloom_distribution
    bloom_dist = data.get("bloom_distribution")
    if isinstance(bloom_dist, dict):
        cleaned = {}
        for label, count in bloom_dist.items():
            if label in _BLOOM_LABELS:
                try:
                    cleaned[label] = max(0, int(count))
                except (ValueError, TypeError):
                    pass
        if sum(cleaned.values()) > 0:
            result["bloom_distribution"] = cleaned

    # quality_score
    qs = data.get("quality_score")
    if qs is not None:
        try:
            result["quality_score"] = max(1, min(5, int(qs)))
        except (ValueError, TypeError):
            pass

    # 质量审查 + 教师点评
    missing_quality = []
    for qkey in _QUALITY_KEYS:
        if qkey in data:
            limit = 200 if qkey == "teacher_comment" else 80
            result[qkey] = str(data[qkey])[:limit]
        else:
            missing_quality.append(qkey)
    if missing_quality:
        logger.warning(f"[特征提取] 质量字段缺失: {missing_quality}")

    return result


async def extract_features(question_text: str, options: str = "",
                           correct_answer: str = "",
                           question_type: str = "",
                           subject: str = "biology") -> dict:
    """调用 LLM 提取题目特征（v3: 难度预测维度 + 报告维度 + 质量审查）。"""
    # 尝试从 PromptLoader 加载学科专用 prompt
    loader = PromptLoader(subject)
    if loader.exists("feature_extractor"):
        parts = [question_text]
        if options:
            parts.append(f"选项：{options}")
        if correct_answer:
            parts.append(f"正确答案：{correct_answer}")
        question_block = "\n".join(parts)
        qtype_hint = f"\n题型：{question_type}" if question_type else ""
        prompt = loader.load("feature_extractor",
                            question_block=question_block, qtype_hint=qtype_hint)
    else:
        prompt = build_feature_prompt(question_text, options, correct_answer, question_type)
    try:
        raw = await send_message_gpt(
            prompt,
            max_tokens=1500,
            temperature=0,
        )
        result = parse_features(raw)

        # 完整性评分：评分9 + 报告3 + reason9 + quality6 + bloom_dist1 + quality_score1 = 29 满分
        completeness = len([k for k in FEATURE_RANGES if k in result])
        completeness += len([k for k in _REASON_KEYS if k in result])
        completeness += len([k for k in _QUALITY_KEYS if k in result])
        completeness += (1 if "bloom_distribution" in result else 0)
        completeness += (1 if "quality_score" in result else 0)

        if completeness >= 25:
            logger.info(f"[特征提取] 完整度={completeness}/29, wm={result.get('working_memory')}, "
                        f"steps={result.get('reasoning_steps')}, coupling={result.get('chain_coupling')}, "
                        f"trap={result.get('trap_density')}, qs={result.get('quality_score')}")
        elif completeness >= 18:
            logger.warning(f"[特征提取] 部分缺失 完整度={completeness}/29")
        else:
            logger.error(f"[特征提取] 严重不完整 完整度={completeness}/29, 原始长度={len(raw)}")

        return result
    except Exception as e:
        logger.error(f"特征提取 API 调用失败: {e}")
        return dict(DEFAULT_FEATURES)


# ── 大题结构化特征提取 v3.1 ────────────────────────────────────

def build_big_question_prompt(question_text: str, options: str = "",
                              correct_answer: str = "",
                              question_type: str = "") -> str:
    """构建大题结构化特征提取 prompt（v3.1）。"""
    parts = [question_text]
    if options:
        parts.append(f"选项：{options}")
    if correct_answer:
        parts.append(f"正确答案/参考答案：{correct_answer}")
    question_block = "\n".join(parts)
    qtype_hint = f"\n题型：{question_type}" if question_type else ""

    return f"""你是一名资深高中生物命题审查专家。这是一道非选择题（大题），请按小问拆分分析。

题目：
{question_block}{qtype_hint}

请输出严格 JSON（不要多余解释），格式如下：
{{
  "subquestions": [
    {{
      "id": 1,
      "points": 该小问分值(整数),
      "working_memory": 1-5（该小问解题时需同时在脑中保持的信息元素数），
      "reasoning_steps": 正整数（该小问最少认知操作数），
      "trap_density": 1-3（看似正确但实际错误的推理路径数），
      "novelty": 1-3（知识/方法新颖度），
      "knowledge_breadth": 1-3（跨知识模块程度），
      "brief": "核心任务(<=20字)"
    }}
  ],
  "dependencies": [
    {{
      "from": 源小问id,
      "to": 目标小问id,
      "strength": "weak"或"strong",
      "reason": "依赖内容(<=30字)"
    }}
  ],
  "global_features": {{
    "shared_context_load": 1-3（跨问保持负担。1=各问独立 2=共享背景 3=围绕复杂系统），
    "shared_context_reason": "<=20字",
    "global_method_novelty": 1-3（教材外方法。1=全教材内 2=部分外 3=核心方法外），
    "method_novelty_reason": "<=20字"
  }},
  "bloom": 1-6, "bloom_distribution": {{}}, "bloom_reason": "<=30字",
  "info_density": 1-3, "density_reason": "<=20字",
  "representation_complexity": 1-3, "representation_reason": "<=20字",
  "quality_score": 1-5,
  "quality_scientific": "<=60字", "quality_normative": "<=60字",
  "quality_language": "<=60字", "quality_context": "<=60字",
  "quality_sensitivity": "<=60字", "teacher_comment": "<=150字"
}}

**dependencies 判定规则（关键！）：**
- "strong"：前一问的结论/产物是后一问的前提。不知道前问答案就无法做后问。
- "weak"：前一问的背景知识有助于后问理解，但不知道前问答案也能部分作答
- 无关的小问之间不加 dependency

**global_method_novelty 判例：**
- 1：所有方法在高中教材中有明确介绍
- 2：部分方法需要迁移应用
- 3：核心方法在教材中完全没有（如 In-Fusion 克隆、CRISPR）
"""


_SQ_RANGES = {
    "working_memory": (1, 5),
    "reasoning_steps": (1, 10),
    "trap_density": (1, 3),
    "novelty": (1, 3),
    "knowledge_breadth": (1, 3),
}


def parse_big_question_features(raw: str) -> dict | None:
    """解析大题结构化 JSON。返回 None 表示解析失败（触发 fallback）。"""
    if not isinstance(raw, str):
        return None

    data = None
    # 策略 1: 直接解析
    try:
        data = json.loads(raw.strip())
    except (json.JSONDecodeError, TypeError):
        pass
    # 策略 2: code block
    if data is None:
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    # 策略 3: 嵌套提取
    if data is None:
        depth = 0
        start = raw.find('{')
        if start >= 0:
            for i in range(start, len(raw)):
                if raw[i] == '{':
                    depth += 1
                elif raw[i] == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            data = json.loads(raw[start:i + 1])
                        except json.JSONDecodeError:
                            pass
                        break
    # 策略 4: 截断修复（与 parse_features 一致）
    if data is None and raw.count('{') > raw.count('}'):
        logger.warning(f"[大题解析] 疑似截断：{{ 数={raw.count('{')}, }} 数={raw.count('}')}, 原始长度={len(raw)}")
        last_brace = raw.rfind('}')
        if last_brace > 0:
            try:
                candidate = raw[:last_brace + 1]
                candidate = re.sub(r',\s*"[^"]*":\s*"?[^"{}]*$', '', candidate)
                if not candidate.endswith('}'):
                    candidate += '}'
                data = json.loads(candidate)
                logger.info(f"[大题解析] 截断修复成功，恢复了 {len(data)} 个字段")
            except (json.JSONDecodeError, Exception):
                pass

    if not isinstance(data, dict):
        logger.warning(f"[大题解析] JSON 解析失败，原始长度={len(raw)}")
        return None

    # subquestions
    sqs_raw = data.get("subquestions", [])
    if not isinstance(sqs_raw, list) or len(sqs_raw) == 0:
        logger.warning("[大题解析] subquestions 缺失或为空")
        return None

    subquestions = []
    for sq in sqs_raw:
        if not isinstance(sq, dict):
            continue
        cleaned = {
            "id": sq.get("id", len(subquestions) + 1),
            "points": max(1, int(sq.get("points", 2))),
            "brief": str(sq.get("brief", ""))[:20],
        }
        for key, (lo, hi) in _SQ_RANGES.items():
            val = sq.get(key, 2)
            try:
                val = int(val)
            except (ValueError, TypeError):
                val = 2
            cleaned[key] = max(lo, min(hi, val))
        subquestions.append(cleaned)
    if not subquestions:
        return None

    # dependencies
    deps_raw = data.get("dependencies", [])
    dependencies = []
    dropped_deps = 0
    valid_ids = {sq["id"] for sq in subquestions}
    if isinstance(deps_raw, list):
        for dep in deps_raw:
            if not isinstance(dep, dict):
                continue
            fr, to = dep.get("from"), dep.get("to")
            strength = dep.get("strength", "weak")
            if fr in valid_ids and to in valid_ids and strength in ("weak", "strong"):
                dependencies.append({
                    "from": fr, "to": to, "strength": strength,
                    "reason": str(dep.get("reason", ""))[:30],
                })
            else:
                dropped_deps += 1
    if dropped_deps > 0:
        logger.warning(f"[大题解析] 丢弃 {dropped_deps} 条无效依赖（ID 不存在或 strength 非法）")
        if dropped_deps >= len(deps_raw) and len(deps_raw) > 0:
            logger.warning("[大题解析] 所有依赖均无效，视为依赖图矛盾，触发 fallback")
            return None

    # global_features
    gf_raw = data.get("global_features", {})
    if isinstance(gf_raw, dict):
        try:
            scl = max(1, min(3, int(gf_raw.get("shared_context_load", 1))))
        except (ValueError, TypeError):
            scl = 1
        try:
            gmn = max(1, min(3, int(gf_raw.get("global_method_novelty", 1))))
        except (ValueError, TypeError):
            gmn = 1
    else:
        scl, gmn = 1, 1
    global_features = {"shared_context_load": scl, "global_method_novelty": gmn}

    # report fields
    report = {}
    for key in ["bloom", "info_density", "representation_complexity"]:
        val = data.get(key)
        if val is not None:
            lo, hi = REPORT_RANGES.get(key, (1, 6))
            try:
                report[key] = max(lo, min(hi, int(val)))
            except (ValueError, TypeError):
                pass
    for reason_key in _REASON_KEYS:
        if reason_key in data:
            report[reason_key] = str(data[reason_key])[:50]
    bloom_dist = data.get("bloom_distribution")
    if isinstance(bloom_dist, dict):
        cleaned_bd = {}
        for label, count in bloom_dist.items():
            if label in _BLOOM_LABELS:
                try:
                    cleaned_bd[label] = max(0, int(count))
                except (ValueError, TypeError):
                    pass
        if sum(cleaned_bd.values()) > 0:
            report["bloom_distribution"] = cleaned_bd
    qs = data.get("quality_score")
    if qs is not None:
        try:
            report["quality_score"] = max(1, min(5, int(qs)))
        except (ValueError, TypeError):
            pass
    for qkey in _QUALITY_KEYS:
        if qkey in data:
            limit = 200 if qkey == "teacher_comment" else 80
            report[qkey] = str(data[qkey])[:limit]

    result = {
        "subquestions": subquestions,
        "dependencies": dependencies,
        "global_features": global_features,
        "report": report,
    }
    if dropped_deps > 0:
        result["_dropped_deps"] = dropped_deps
    return result


async def extract_big_question_features(question_text: str, options: str = "",
                                        correct_answer: str = "",
                                        question_type: str = "",
                                        subject: str = "biology") -> dict | None:
    """调用 LLM 提取大题结构化特征。返回 None 表示失败。"""
    loader = PromptLoader(subject)
    if loader.exists("big_question_extractor"):
        parts = [question_text]
        if options:
            parts.append(f"选项：{options}")
        if correct_answer:
            parts.append(f"正确答案/参考答案：{correct_answer}")
        question_block = "\n".join(parts)
        qtype_hint = f"\n题型：{question_type}" if question_type else ""
        prompt = loader.load("big_question_extractor",
                            question_block=question_block, qtype_hint=qtype_hint)
    else:
        prompt = build_big_question_prompt(question_text, options, correct_answer, question_type)
    try:
        raw = await send_message_gpt(prompt, max_tokens=2000, temperature=0)
        result = parse_big_question_features(raw)
        if result is None:
            logger.warning(f"[大题提取] 结构化解析失败，原始长度={len(raw)}")
        else:
            logger.info(f"[大题提取] 成功: {len(result['subquestions'])}小问, "
                        f"{len(result['dependencies'])}依赖")
        return result
    except Exception as e:
        logger.error(f"[大题提取] API 调用失败: {e}")
        return None
