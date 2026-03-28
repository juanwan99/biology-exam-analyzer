"""LLM 特征提取 v2 — 7 维 rubric prompt + JSON 解析容错。

设计文档: docs/plans/2026-03-24-difficulty-scoring-v2-design.md §4
"""
import json
import re
from claude_client import send_message_gpt
from logger import get_logger

logger = get_logger()

# 各维度的合法范围 (min, max)
FEATURE_RANGES = {
    "bloom": (1, 6),
    "reasoning_steps": (1, 10),
    "knowledge_breadth": (1, 3),
    "info_density": (1, 3),
    "novelty": (1, 3),
    "representation_complexity": (1, 3),
    "question_type_factor": (1, 4),
}

# 解析失败时的默认值（各维度中位数）
DEFAULT_FEATURES = {
    "bloom": 3,
    "reasoning_steps": 4,
    "knowledge_breadth": 2,
    "info_density": 2,
    "novelty": 2,
    "representation_complexity": 1,
    "question_type_factor": 1,
}

# 所有需要保留的 reason 字段
_REASON_KEYS = [
    "bloom_reason", "steps_detail", "breadth_reason",
    "density_reason", "novelty_reason", "representation_reason",
]

# 质量审查 + 教师点评字段（v4 扩展）
_QUALITY_KEYS = [
    "quality_scientific", "quality_normative", "quality_language",
    "quality_context", "quality_sensitivity", "teacher_comment",
]

# Bloom 中文标签（bloom_distribution 解析用）
_BLOOM_LABELS = {"识记", "理解", "应用", "分析", "评价", "创造"}


def build_feature_prompt(question_text: str, options: str = "",
                         correct_answer: str = "", question_type: str = "") -> str:
    """构建 7 维特征提取 prompt（v2）。"""
    parts = [question_text]
    if options:
        parts.append(f"选项：{options}")
    if correct_answer:
        parts.append(f"正确答案：{correct_answer}")
    question_block = "\n".join(parts)

    qtype_hint = f"\n题型：{question_type}" if question_type else ""

    return f"""你是一名资深高中生物命题审查专家。请从难度特征、命题质量、教学价值三个层面严格分析这道题目。

题目：
{question_block}{qtype_hint}

请输出严格 JSON（不要多余解释）：
{{
  "bloom": 1-6（该题所需的最高认知层级），
  "bloom_distribution": {{"识记": 0, "理解": 0, "应用": 0, "分析": 0, "评价": 0, "创造": 0}}（各层级在该题中出现的次数。选择题：每个选项考查的层级各计1次；非选择题：每个小问独立判定层级各计1次。总数应≥1），
  "bloom_reason": "描述最高层级对应的具体认知操作(≤30字，禁止使用识记/理解/应用/分析/评价/创造等层级名称，只写具体动作)",
  "reasoning_steps": 正整数（从题目信息到答案的最少认知操作数，不含读题/看选项），
  "steps_detail": "简述推理链(≤50字)",
  "knowledge_breadth": 1-3（1单知识点 2跨考点 3跨模块），
  "breadth_reason": "一句话(≤20字)",
  "info_density": 1-3（1低≤2条 2中3-5条 3高>5条或含图表），
  "density_reason": "一句话(≤20字)",
  "novelty": 1-3（1教材原文/常见原题 2变式/改编 3全新情境/陌生素材），
  "novelty_reason": "一句话(≤20字)",
  "representation_complexity": 1-3（1纯文字 2简单图表/示意图 3复杂系谱图/多图联读/装置图），
  "representation_reason": "一句话(≤20字)",
  "question_type_factor": 1-4（1单选 2多选/填空 3简答 4实验设计）,
  "quality_score": 1-5（1=严重缺陷 2=明显问题需修改 3=基本合格有瑕疵 4=较好仅细微建议 5=优秀无需修改。5分应极少出现——大多数真实试题都有改进空间），
  "quality_scientific": "先指出问题，再给评价。检查：知识是否准确、答案是否唯一、有无歧义或事实错误。无问题写'无明显问题'(≤60字)",
  "quality_normative": "先指出问题，再给评价。检查：题干是否完整、选项是否平行、分值是否合理、干扰项是否有效。(≤60字)",
  "quality_language": "先指出问题，再给评价。检查：有无冗余/口语化/歧义/术语错误/表意不清/表述过绝对。(≤60字)",
  "quality_context": "先指出问题，再给评价。检查：素材是否真实、与考查内容是否脱节、背景知识门槛是否合适。(≤60字)",
  "quality_sensitivity": "先指出问题，再给评价。检查：是否涉及政治敏感话题、民族宗教争议、不当伦理情境（如人体实验、基因编辑争议性表述）、可能引发家长或社会舆论的内容。无问题写'无舆情风险'(≤60字)",
  "teacher_comment": "教师视角深度点评(≤150字)：考查目的、各小问难点归因、学生典型错误路径（具体写出学生会怎么错）、针对性教学建议"
}}

**Bloom 层级判定规则（必须逐小问/逐选项判定）：**
1. 选择题：每个选项独立判 bloom 层级，填入 bloom_distribution。例如4个选项中2个考记忆、1个考推理、1个考方案评价，则 bloom_distribution={{"识记":2,"应用":1,"评价":1}}，bloom=5
2. 非选择题：每个小问独立判 bloom 层级，填入 bloom_distribution。一道大题可能5个小问分别是 理解+应用+分析+分析+创造
3. bloom 字段填该题所需的【最高】认知层级
4. ⚠️ 非选择题中以下设问必须判 bloom≥5：
   - "评价/评估/论证/判断...是否合理/正确" → bloom=5
   - "设计实验/提出方案/写出实验步骤/补充完善" → bloom=6
   - "说明理由"：复述课本原理=2，结合材料推理=4，论证方案合理性=5
   - "简述...过程" → bloom=2（不是4）
5. ⚠️ 把非选择题全部判为 bloom=4 是典型错误。一道含5个小问的大题几乎不可能5个小问都是同一层级

**Bloom 判例（生物学科）：**
- bloom=1：直接回忆，如"写出DNA基本组成单位""线粒体的功能是"
- bloom=2：解释/比较，如"解释植物光下释放O₂的原因""简述转录过程"
- bloom=3：套用规律，如"据分离比判断显隐性""用渗透原理解释质壁分离"
- bloom=4：拆解推理，如"分析系谱图推导基因型""据实验数据判断酶活性因素"
- bloom=5：判断论证，如"评价该实验方案的合理性""该同学结论是否正确？说明理由""指出该设计的不足"
- bloom=6：设计创造，如"设计实验验证该激素作用""提出育种方案并写出步骤""补充实验方案使结论更可靠"

**命题质量审查要求（你是审查者，不是表扬者）：**
你的任务是找出命题的真实问题，不是给好评。常见问题清单——逐项检查：
- 选项平行性差（长短悬殊、逻辑类型不一致）
- 题干信息不足以得出唯一答案
- 干扰项过弱（一眼排除）或过强（超出考纲）
- 术语不严谨、口语化表述、表述绝对化
- 情境与考查内容关联勉强、情境过于简单
- 分值与作答量不匹配
quality_score=5 应极少使用。如果你给了5分，请确认以上清单每项都检查过且确实无问题。

**representation_complexity 判例：**
- 1：纯文字题，无图表
- 2：含简单柱状图/折线图/示意图，读图即可获取信息
- 3：复杂系谱图/多图联读/实验装置图，需要从图中推理"""


def parse_features(raw: str) -> dict:
    """从 LLM 原始输出解析 7 维特征，带容错和范围裁剪。

    解析策略：
    1. 直接 JSON 解析
    2. 从 markdown code block 提取
    3. 正则提取第一个 JSON object
    4. 全部失败 → 返回默认值
    """
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

    # 截断检测：JSON 未闭合说明 GPT 输出被 max_tokens 截断
    if data is None and raw.count('{') > raw.count('}'):
        logger.warning(f"[特征提取] 疑似截断：{{ 数={raw.count('{')}, }} 数={raw.count('}')}, 原始长度={len(raw)}")
        # 尝试修复：截取到最后一个完整的 key-value 对
        last_brace = raw.rfind('}')
        if last_brace > 0:
            try:
                # 补全截断的 JSON
                candidate = raw[:last_brace + 1]
                # 移除尾部不完整的 key-value
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

    # 保留 reason 字段（不参与评分，供审查用）
    for reason_key in _REASON_KEYS:
        if reason_key in data:
            val = str(data[reason_key])[:50]  # 限长
            result[reason_key] = val

    # bloom_distribution（v4: 逐选项/逐小问 bloom 分布）
    bloom_dist = data.get("bloom_distribution")
    if isinstance(bloom_dist, dict):
        # 只保留合法的 bloom 标签，值转为 int
        cleaned = {}
        for label, count in bloom_dist.items():
            if label in _BLOOM_LABELS:
                try:
                    cleaned[label] = max(0, int(count))
                except (ValueError, TypeError):
                    pass
        if sum(cleaned.values()) > 0:
            result["bloom_distribution"] = cleaned

    # quality_score（v4: 1-5 命题质量总评分）
    qs = data.get("quality_score")
    if qs is not None:
        try:
            result["quality_score"] = max(1, min(5, int(qs)))
        except (ValueError, TypeError):
            pass

    # 质量审查 + 教师点评字段（v4: 放宽限制）
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
                           question_type: str = "") -> dict:
    """调用 LLM 提取题目特征。

    Returns:
        dict: 7 维特征值
    """
    prompt = build_feature_prompt(question_text, options, correct_answer, question_type)
    try:
        raw = await send_message_gpt(
            prompt,
            max_tokens=1200,
            temperature=0,
        )
        result = parse_features(raw)

        # 完整性评分：数值7 + reason6 + quality5 + bloom_dist1 + quality_score1 = 20 满分
        completeness = len([k for k in FEATURE_RANGES if k in result])  # 数值字段
        completeness += len([k for k in _REASON_KEYS if k in result])   # reason 字段
        completeness += len([k for k in _QUALITY_KEYS if k in result])  # 质量字段
        completeness += (1 if "bloom_distribution" in result else 0)
        completeness += (1 if "quality_score" in result else 0)

        if completeness >= 19:
            logger.info(f"[特征提取] 完整度={completeness}/21, bloom={result.get('bloom')}, qs={result.get('quality_score')}")
        elif completeness >= 13:
            logger.warning(f"[特征提取] 部分缺失 完整度={completeness}/21, 缺: {[k for k in _QUALITY_KEYS if k not in result]}")
        else:
            logger.error(f"[特征提取] 严重不完整 完整度={completeness}/21, 原始长度={len(raw)}")

        return result
    except Exception as e:
        logger.error(f"特征提取 API 调用失败: {e}")
        return dict(DEFAULT_FEATURES)
