"""Commercial-grade report model for exam quality diagnosis.

This module converts the existing ``report_data`` aggregate into a
Bain-style report contract: judgment first, evidence second, figures and
actions after that. It does not call AIs and does not render HTML/PDF.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import re
from typing import Any, Dict, Iterable, List

from analysis_calibration import canonicalize_knowledge_point
from report_commercial_narrative import (
    action_for_question,
    contains_risk_text as _contains_risk_text,
    difficulty_thesis,
    metadata_status,
    primary_issue,
    question_risk_level,
    risk_stance,
)
from report_teacher_review_narrative import (
    classify_overall_verdict,
    summarize_student_fit,
    summarize_teacher_priorities,
)


PARSED_FIELDS = [
    "quality_score",
    "difficulty",
    "knowledge_points",
    "primary_competency",
    "fine_grained_units",
    "seu_knowledge_breakdown",
    "diagnostic_highlights",
    "competency_weights",
    "difficulty_estimate",
    "metadata_confidence",
    "metadata_warnings",
]

PROMPT_CONTRACTS = {
    "question_analysis": {
        "prompt_id": "biology.question_analysis.v2",
        "prompt": "backend/prompts/analysis_prompt_v2.txt：分析题目结构、采分点、误区诊断、知识关联、核心素养、难度与元数据追踪。",
        "analysis_dimensions": [
            "quality",
            "difficulty",
            "knowledge",
            "competency",
            "seu_du",
            "metadata",
        ],
        "parsed_fields": [
            "knowledge_points",
            "primary_competency",
            "fine_grained_units",
            "scoring_units",
            "diagnostic_units",
            "stimulus_units",
            "seu_knowledge_breakdown",
            "diagnostic_highlights",
            "competency_weights",
            "difficulty_estimate",
            "metadata_confidence",
            "metadata_warnings",
        ],
    },
    "feature_extraction": {
        "prompt_id": "biology.feature_extraction",
        "prompt": "prompts/biology/feature_extractor.txt 或 feature_extractor.build_feature_prompt：分析难度驱动因素、命题质量与教学价值。",
        "analysis_dimensions": [
            "working_memory",
            "reasoning_steps",
            "chain_coupling",
            "trap_density",
            "novelty",
            "knowledge_breadth",
            "bloom",
            "representation_complexity",
            "quality",
        ],
        "parsed_fields": [
            "working_memory",
            "reasoning_steps",
            "chain_coupling",
            "trap_density",
            "novelty",
            "knowledge_breadth",
            "bloom",
            "quality_score",
            "quality_scientific",
            "quality_normative",
            "quality_language",
            "quality_context",
            "teacher_comment",
            "metadata_confidence",
        ],
    },
    "big_question_feature_extraction": {
        "prompt_id": "biology.big_question_feature_extraction",
        "prompt": "prompts/biology/big_question_extractor.txt：分析小问依赖、全局情境负荷、方法新颖度、难度与质量。",
        "analysis_dimensions": [
            "sub_questions",
            "dependencies",
            "global_features",
            "difficulty",
            "quality",
            "metadata",
        ],
        "parsed_fields": [
            "sub_questions",
            "dependencies",
            "global_features",
            "bloom_distribution",
            "quality_score",
            "teacher_comment",
            "metadata_confidence",
        ],
    },
    "competency_analysis": {
        "prompt_id": "biology.competency_analysis",
        "prompt": "backend/prompts/competency_analysis_prompt.txt：映射四类生物核心素养，输出权重、层级与证据。",
        "analysis_dimensions": [
            "life_concept",
            "scientific_thinking",
            "scientific_inquiry",
            "social_responsibility",
            "evidence",
        ],
        "parsed_fields": [
            "生命观念",
            "科学思维",
            "科学探究",
            "社会责任",
            "metadata_confidence",
        ],
    },
    "split_questions": {
        "prompt_id": "biology.split_questions",
        "prompt": "prompts/biology/split_prompt.txt：在详细分析前，将原始试卷内容拆分为结构化题目记录。",
        "analysis_dimensions": ["question_boundary", "question_type", "section_header"],
        "parsed_fields": ["id", "content", "question_type", "section_header"],
    },
}

QUALITY_GATES = [
    "metadata envelope required",
    "question_analysis required",
    "feature_extraction or big_question_feature_extraction required",
    "competency_analysis or scoring-unit-derived competency required",
]

FAIL_CLOSED_DIFFICULTY_FLAGS = {
    "big_question_structure_failed",
    "big_question_points_mismatch",
    "points_sum_mismatch",
    "score_share_sum_mismatch",
    "points_unknown",
    "cannot_identify_subquestions",
    "invalid_subquestion_schema",
    "invalid_dependency_ids",
    "insufficient_stem",
    "json_parse_failed",
    "json_truncated",
    "llm_parse_error",
    "llm_parse_failure",
    "provider_failed",
    "quality_score_too_low",
    "question_analysis_failed",
    "feature_extraction_failed",
    "no_evaluation",
    "seu_fallback",
    "big_question_fallback",
}

LIMITATIONS = [
    "AI 生成的诊断结论在正式使用前应由学科教师复核。",
    "低置信度元数据是复核信号，不等同于最终质量判定。",
    "题目风险等级综合模型输出与元数据质量，用于排序人工复核优先级。",
]

FAILURE_COPY = {
    "insufficient_stem": {
        "stage": "题面完整性检查",
        "title": "题面不完整",
        "reason": "系统识别到的题面不完整，无法确认小问总数、材料边界和分值分配。",
        "impact": "该题不纳入逐题难度排名、平均难度计算和高风险题排序。",
        "action": "请核对原始试卷或 Word/PDF 抽取结果，补齐缺失题面后重新生成报告。",
        "severity": "blocked",
    },
    "big_question_structure_failed": {
        "stage": "大题结构化解析",
        "title": "大题结构未闭合",
        "reason": "系统未能把大题拆成可校验的小问、采分点和分值结构。",
        "impact": "该题难度、压力指数和题目质量结论不能作为正式判断。",
        "action": "请先补齐题面、图表和答案分值，再重新进行大题结构化分析。",
        "severity": "blocked",
    },
    "big_question_points_mismatch": {
        "stage": "大题分值校验",
        "title": "小问分值不闭合",
        "reason": "结构化小问分值之和与题目总分不一致。",
        "impact": "采分点权重、难度均值和能力分布会被污染。",
        "action": "请核对各小问分值或评分细则，保证采分点总分与题目总分一致。",
        "severity": "blocked",
    },
    "points_sum_mismatch": {
        "stage": "大题分值校验",
        "title": "小问分值不闭合",
        "reason": "模型拆出的各小问/采分点分值合计与题目总分不一致。",
        "impact": "该题的采分点权重、难度均值和能力分布会被污染，不能按正常题进入统计。",
        "action": "请核对该题各小问分值、参考答案或评分细则；分值闭合后重新生成报告。",
        "severity": "blocked",
    },
    "feature_extraction_failed": {
        "stage": "题目特征提取",
        "title": "题目特征提取失败",
        "reason": "系统未能得到可用的难度驱动因素、质量特征或教学价值字段。",
        "impact": "该题不能进入正常难度测算和质量排序。",
        "action": "请检查题面、答案和解析是否完整；必要时重跑该题分析。",
        "severity": "blocked",
    },
    "quality_score_too_low": {
        "stage": "题目质量评估",
        "title": "题目质量阻断",
        "reason": "题目质量评分低于自动入统阈值，系统停止展示推断难度。",
        "impact": "该题不纳入逐题难度曲线、平均难度和正常质量排序，避免把高风险题伪装成正常题。",
        "action": "请先由教师核对答案、科学性、设问边界和评分口径；确认修正后再重新生成报告。",
        "severity": "blocked",
    },
    "quality_issue_low_score": {
        "stage": "题目质量评估",
        "title": "题目质量低分",
        "reason": "系统识别到题目质量评分偏低，但题面和特征仍足以估算难度。",
        "impact": "该题保留难度估算，同时进入人工优先复核清单，避免把质量风险误当成数据缺失。",
        "action": "请核对科学性、设问边界、答案和评分口径；如确认题目可用，可继续参考难度结果。",
        "severity": "warning",
    },
    "feature_extraction_partial": {
        "stage": "题目特征提取",
        "title": "题目特征不完整",
        "reason": "系统只取得了部分题目特征字段。",
        "impact": "相关质量或难度结论需要人工复核。",
        "action": "请检查缺失字段并重跑该题特征提取。",
        "severity": "warning",
    },
    "analysis_failed": {
        "stage": "题目分析",
        "title": "题目分析失败",
        "reason": "题目分析阶段没有产出可用于定稿的结构化结果。",
        "impact": "该题不能作为正常题参与结论汇总。",
        "action": "请查看该题调用日志、题面和答案后重跑分析。",
        "severity": "blocked",
    },
    "difficulty_missing": {
        "stage": "难度评估",
        "title": "难度结果缺失",
        "reason": "难度模块没有产出数值结果。",
        "impact": "该题不纳入难度曲线、平均难度和高压题判断。",
        "action": "请检查上游题目分析、分值和特征提取是否通过。",
        "severity": "blocked",
    },
    "no_evaluation": {
        "stage": "难度评估",
        "title": "难度未评估",
        "reason": "该题没有进入有效难度评估流程。",
        "impact": "该题不纳入难度曲线、平均难度和高压题判断。",
        "action": "请检查题目元数据和分值后重新生成报告。",
        "severity": "blocked",
    },
    "big_question_fallback": {
        "stage": "大题结构化解析",
        "title": "大题结构化失败",
        "reason": "大题结构化结果不可用，系统拒绝使用回退难度伪装正常结论。",
        "impact": "该题需要人工复核，不能按稳定题处理。",
        "action": "请补齐题面、图表、答案和小问分值后重新分析。",
        "severity": "blocked",
    },
    "diagnostic_units_missing": {
        "stage": "误区诊断抽取",
        "title": "误区诊断缺失",
        "reason": "系统未抽取到学生可能误区或干扰项诊断。",
        "impact": "该题的讲评建议和陷阱强度图不完整。",
        "action": "请补充或重跑该题误区诊断后再定稿。",
        "severity": "warning",
    },
    "stimulus_units_missing": {
        "stage": "材料情境抽取",
        "title": "材料情境缺失",
        "reason": "系统未抽取到题干材料、表格、图片或情境单元。",
        "impact": "该题材料负担和信息提取难度不可判断。",
        "action": "请检查图文抽取和题面绑定，再重新生成报告。",
        "severity": "warning",
    },
    "stimulus_units_blank": {
        "stage": "材料情境抽取",
        "title": "材料描述过空",
        "reason": "系统只得到泛化材料描述，未形成可复核的图表或情境说明。",
        "impact": "该题材料负担、图文关系和信息提取难度证据不足。",
        "action": "请补齐图表说明、材料来源或重新进行图文绑定。",
        "severity": "warning",
    },
    "missing_llm_calls": {
        "stage": "AI 调用追踪",
        "title": "AI 调用记录缺失",
        "reason": "报告数据中没有可追溯的模型调用记录。",
        "impact": "无法判断该结论来自哪次提示词、哪类解析和哪种校验。",
        "action": "请重跑分析并保留调用元数据。",
        "severity": "warning",
    },
    "llm_parse_failure": {
        "stage": "AI 返回解析",
        "title": "AI 返回解析失败",
        "reason": "模型返回内容曾无法解析为约定结构。",
        "impact": "相关字段需要复核，不能只看最终摘要。",
        "action": "请查看解析失败的调用目的；必要时调整提示词或重跑该题。",
        "severity": "warning",
    },
    "llm_retry": {
        "stage": "AI 调用重试",
        "title": "AI 调用发生重试",
        "reason": "系统检测到模型输出或证据链不满足要求后进行了重试。",
        "impact": "最终结果可用性取决于重试后的结构化校验是否通过。",
        "action": "请在单题审查中查看该题是否仍有解析失败或证据缺口。",
        "severity": "info",
    },
    "missing_score": {
        "stage": "分值抽取",
        "title": "题目分值缺失",
        "reason": "系统未能从题目或分析结果中取得有效分值。",
        "impact": "该题不会参与按分值加权的统计，避免污染整卷指标。",
        "action": "请补齐题目分值或评分细则后重新生成报告。",
        "severity": "warning",
    },
    "non_positive_score": {
        "stage": "分值抽取",
        "title": "题目分值异常",
        "reason": "题目分值为 0 或负数，不符合试卷统计要求。",
        "impact": "该题不会参与按分值加权的统计。",
        "action": "请核对原卷分值后重新生成报告。",
        "severity": "warning",
    },
    "invalid_score": {
        "stage": "分值抽取",
        "title": "题目分值格式无效",
        "reason": "题目分值不是可解析的数值。",
        "impact": "该题不会参与按分值加权的统计。",
        "action": "请修正题目分值字段后重新生成报告。",
        "severity": "warning",
    },
}

FAILURE_COPY_ALIASES = {
    "score_share_sum_mismatch": "points_sum_mismatch",
    "points_unknown": "big_question_points_mismatch",
    "cannot_identify_subquestions": "big_question_structure_failed",
    "invalid_subquestion_schema": "big_question_structure_failed",
    "invalid_dependency_ids": "big_question_structure_failed",
    "json_parse_failed": "feature_extraction_failed",
    "json_truncated": "feature_extraction_failed",
    "llm_parse_error": "feature_extraction_failed",
    "llm_parse_failure": "feature_extraction_failed",
    "provider_failed": "feature_extraction_failed",
    "question_analysis_failed": "analysis_failed",
    "seu_fallback": "big_question_fallback",
}

BLOOM_LEVEL_LABELS = {
    1: "识记",
    2: "理解",
    3: "应用",
    4: "分析",
    5: "评价",
    6: "创造",
}

CORE_COMPETENCIES = ("生命观念", "科学思维", "科学探究", "社会责任")

COMPETENCY_SUBDIMENSION_RULES = {
    "生命观念": [
        ("稳态与平衡观", ("稳态", "平衡", "调节", "反馈", "内环境", "激素", "神经", "homeostasis", "balance")),
        ("结构与功能观", ("结构", "功能", "蛋白", "细胞器", "膜", "器官", "structure", "function")),
        ("遗传与信息观", ("遗传", "基因", "dna", "rna", "染色体", "染色单体", "碱基", "基因型", "表型", "花粉", "分离比", "复制", "转录", "翻译", "突变", "遗传信息")),
        ("物质与能量观", ("物质", "能量", "代谢", "光合", "呼吸", "atp", "energy", "metabolism")),
        ("进化与适应观", ("进化", "适应", "选择", "遗传变异", "evolution", "adaptation")),
        ("生态观", ("生态", "种群", "群落", "生态系统", "食物网", "污染", "ecology")),
    ],
    "科学思维": [
        ("模型建构", ("模型", "建模", "图示", "机制", "路径", "model", "mechanism")),
        ("数据分析", ("数据", "表格", "曲线", "图表", "统计", "计算", "大小", "比例", "条带", "电泳", "密码表", "pcr", "data", "table", "chart")),
        ("证据推理", ("推理", "推断", "证据", "判断", "论证", "解释", "预测", "排除", "辨析", "识别", "遗传方式", "inference", "evidence", "reasoning", "explanation")),
        ("变量控制", ("变量", "对照", "控制", "control", "variable")),
        ("批判评价", ("评价", "质疑", "比较", "优劣", "evaluate", "critique")),
    ],
    "科学探究": [
        ("实验设计", ("实验", "方案", "设计", "探究", "处理组", "筛选", "培养", "鉴定", "引物", "扩增", "pcr", "experiment", "design")),
        ("变量控制", ("变量", "对照", "单一变量", "control", "variable")),
        ("数据处理", ("数据", "结果", "表格", "曲线", "统计", "条带", "电泳", "产物大小", "data", "result", "table")),
        ("证据解释", ("解释", "结论", "证据", "说明", "explain", "evidence", "conclusion")),
        ("反思改进", ("改进", "误差", "局限", "优化", "improve", "limitation")),
    ],
    "社会责任": [
        ("健康生活", ("健康", "疾病", "用药", "医学", "health", "disease")),
        ("生态环保", ("生态", "环保", "污染", "治理", "保护", "修复", "浮床", "重金属", "铜", "铅", "固碳", "碳", "environment", "pollution")),
        ("生物安全", ("安全", "生物安全", "转基因", "crispr", "基因编辑", "biosecurity")),
        ("伦理意识", ("伦理", "道德", "社会影响", "ethic")),
        ("农业与技术应用", ("农业", "育种", "技术", "工程", "应用", "agriculture", "technology")),
    ],
}

DEFAULT_SUB_COMPETENCY = {
    "生命观念": "结构与功能观",
    "科学思维": "证据推理",
    "科学探究": "实验设计",
    "社会责任": "社会责任情境",
}


def _as_dict(value: Any) -> Dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List:
    return value if isinstance(value, list) else []


def _num(value: Any, default: float = 0.0) -> float:
    return value if isinstance(value, (int, float)) else default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _format_num(value: Any, digits: int = 1) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}"
    return str(value) if value is not None else "-"


_SUBQUESTION_RE = re.compile(r"[（(]([0-9一二三四五六七八九十]+)[)）]")
_CIRCLED_SUBQUESTION_RE = re.compile(r"[①②③④⑤⑥⑦⑧⑨⑩]")
_DOTTED_SUBQUESTION_RE = re.compile(r"(?<!\d)([1-9][0-9]?)\s*[.．、]")
_QUESTION_HEADER_RE = re.compile(r"^\s*[1-9][0-9]?\s*[.．、]\s*(?:[（(][^）)]{0,12}分[)）])?\s*")
_LEADING_CIRCLED_SUBQUESTION_RE = re.compile(r"^\s*[①②③④⑤⑥⑦⑧⑨⑩]")
_LEADING_DOTTED_SUBQUESTION_RE = re.compile(r"^\s*([1-9][0-9]?)\s*[.．、]")
_CIRCLED_SUBQUESTION_NUMBERS = {
    "①": 1,
    "②": 2,
    "③": 3,
    "④": 4,
    "⑤": 5,
    "⑥": 6,
    "⑦": 7,
    "⑧": 8,
    "⑨": 9,
    "⑩": 10,
}


def _cn_subquestion_number(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    mapping = {
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    if value in mapping:
        return mapping[value]
    if value.startswith("十") and len(value) == 2 and value[1] in mapping:
        return 10 + mapping[value[1]]
    if value.endswith("十") and len(value) == 2 and value[0] in mapping:
        return mapping[value[0]] * 10
    if "十" in value:
        left, right = value.split("十", 1)
        if left in mapping and right in mapping:
            return mapping[left] * 10 + mapping[right]
    return None


def _question_source_text(question: Dict[str, Any]) -> str:
    parts = [
        question.get("content"),
        question.get("question_text"),
        question.get("source_excerpt"),
        question.get("stem"),
    ]
    return "\n".join(str(part) for part in parts if part)


def _subquestion_numbers(question: Dict[str, Any], text: str) -> List[int]:
    parenthesized = [
        parsed
        for parsed in (_cn_subquestion_number(match.group(1)) for match in _SUBQUESTION_RE.finditer(text))
        if parsed is not None
    ]
    if parenthesized:
        return parenthesized

    numbers: List[int] = []
    question_id = question.get("id")
    for raw_line in text.splitlines() or [text]:
        line = _QUESTION_HEADER_RE.sub("", raw_line.strip(), count=1)
        if _LEADING_CIRCLED_SUBQUESTION_RE.match(line):
            numbers.extend(
                _CIRCLED_SUBQUESTION_NUMBERS[match.group(0)]
                for match in _CIRCLED_SUBQUESTION_RE.finditer(line)
            )
            continue
        if _LEADING_DOTTED_SUBQUESTION_RE.match(line):
            for match in _DOTTED_SUBQUESTION_RE.finditer(line):
                parsed = int(match.group(1))
                if isinstance(question_id, int) and parsed == question_id and match.start() <= 6:
                    continue
                numbers.append(parsed)
    return numbers


def _top_level_subquestion_numbers(question: Dict[str, Any]) -> List[int]:
    text = _question_source_text(question)
    if not text:
        return []
    return _subquestion_numbers(question, text)


def _question_structure_warnings(question: Dict[str, Any]) -> List[str]:
    if not _is_constructed_response_question(question):
        return []
    text = _question_source_text(question)
    if not text:
        return []
    numbers = _subquestion_numbers(question, text)
    if not numbers:
        return []

    warnings: List[str] = []
    duplicates = sorted({number for number in numbers if numbers.count(number) > 1})
    if duplicates:
        warnings.append("题面小问编号重复：" + "、".join(f"（{number}）" for number in duplicates))

    expected = set(range(1, max(numbers) + 1))
    missing = sorted(expected - set(numbers))
    if missing:
        warnings.append("题面小问编号缺失：" + "、".join(f"（{number}）" for number in missing))
    return warnings

def _question_label(qid: Any) -> str:
    return f"第{qid}题" if qid not in (None, "") else "该题"


def _subquestion_label(numbers: Iterable[int]) -> str:
    return "、".join(f"（{number}）" for number in numbers)


def _copy_with_question_context(code: str, question: Dict | None = None, qid: Any = None) -> Dict[str, Any]:
    copy_code = FAILURE_COPY_ALIASES.get(code, code)
    base = dict(FAILURE_COPY.get(copy_code) or {
        "stage": "数据质量检查",
        "title": "未归类的数据异常",
        "reason": f"系统记录到异常代码 {code}，但尚未归类为具体失败范式。",
        "impact": "相关结论需要人工复核，不能作为自动化最终判断。",
        "action": "请查看方法论中的元数据追踪和原始调用记录。",
        "severity": "warning",
    })
    qid = qid if qid not in (None, "") else (_as_dict(question or {}).get("id"))
    if code == "insufficient_stem" and question:
        numbers = sorted(set(_top_level_subquestion_numbers(question)))
        if numbers:
            expected = set(range(1, max(numbers) + 1))
            missing = sorted(expected - set(numbers))
            if missing:
                base["reason"] = (
                    f"系统只识别到{_question_label(qid)}的{_subquestion_label(numbers)}小问，"
                    f"未识别到{_subquestion_label(missing)}问；因此无法确认小问总数、材料边界和分值分配。"
                )
    if code == "quality_score_too_low" and question:
        question_data = _as_dict(question)
        difficulty = _as_dict(question_data.get("difficulty"))
        features = _as_dict(difficulty.get("features"))
        detail = (
            features.get("quality_scientific")
            or features.get("quality_normative")
            or question_data.get("quality_scientific")
            or question_data.get("primary_issue")
            or question_data.get("teacher_comment")
        )
        score = features.get("quality_score", question_data.get("quality_score"))
        score_text = f"质量评分 {score:g}，" if isinstance(score, (int, float)) else ""
        if detail:
            base["reason"] = f"{_question_label(qid)}{score_text}低于自动入统阈值；核心原因：{detail}"
    return base


def _failure_explanation(
    code: str,
    question: Dict | None = None,
    qid: Any = None,
    stage: str | None = None,
    severity: str | None = None,
    raw_reason: str | None = None,
    source: str | None = None,
) -> Dict[str, Any]:
    code = str(code or "unknown")
    copy = _copy_with_question_context(code, question, qid)
    if stage:
        copy["stage"] = stage
    if severity:
        copy["severity"] = severity
    if raw_reason and code not in FAILURE_COPY and code not in FAILURE_COPY_ALIASES:
        copy["reason"] = str(raw_reason)
    qid = qid if qid not in (None, "") else (_as_dict(question or {}).get("id"))
    item = {
        "question_id": qid,
        "code": code,
        "stage": copy["stage"],
        "title": copy["title"],
        "reason": copy["reason"],
        "impact": copy["impact"],
        "action": copy["action"],
        "severity": copy.get("severity", "warning"),
    }
    if source:
        item["source"] = source
    item["display"] = (
        f"失败阶段：{item['stage']}；原因：{item['reason']}；"
        f"影响：{item['impact']}；处理：{item['action']}"
    )
    return item


def _warning_to_failure_explanation(warning: str, question: Dict | None = None, qid: Any = None) -> Dict[str, Any] | None:
    text = str(warning or "").strip()
    if not text:
        return None
    if ":" in text:
        prefix, value = text.split(":", 1)
    else:
        prefix, value = text, ""
    if prefix == "analysis_failed":
        return _failure_explanation(value or "analysis_failed", question, qid, source="metadata_warning")
    if prefix == "difficulty_blocked":
        return _failure_explanation(value or "difficulty_missing", question, qid, source="metadata_warning")
    if prefix == "llm_parse_failure":
        item = _failure_explanation("llm_parse_failure", question, qid, source="metadata_warning")
        item["reason"] = f"{value or 'AI 调用'} 返回内容曾无法解析为约定结构。"
        item["display"] = (
            f"失败阶段：{item['stage']}；原因：{item['reason']}；"
            f"影响：{item['impact']}；处理：{item['action']}"
        )
        return item
    if prefix == "llm_retry":
        item = _failure_explanation("llm_retry", question, qid, source="metadata_warning")
        item["reason"] = f"{value or 'AI 调用'} 发生过重试。"
        item["display"] = (
            f"失败阶段：{item['stage']}；原因：{item['reason']}；"
            f"影响：{item['impact']}；处理：{item['action']}"
        )
        return item
    if prefix == "feature_status" and value in {"failed", "missing", "partial"}:
        failure_reason = str(
            _as_dict(question or {}).get("failure_reason")
            or _as_dict(_as_dict(question or {}).get("difficulty")).get("failure_reason")
            or ""
        )
        if failure_reason == "quality_score_too_low":
            return _failure_explanation(failure_reason, question, qid, source="metadata_warning")
        code = "feature_extraction_failed" if value != "partial" else "feature_extraction_partial"
        return _failure_explanation(code, question, qid, source="metadata_warning")
    if prefix == "missing_llm_calls":
        return _failure_explanation("missing_llm_calls", question, qid, source="metadata_warning")
    return None


def _dedupe_failure_explanations(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    deduped: List[Dict[str, Any]] = []
    severity_rank = {"blocked": 0, "warning": 1, "info": 2}
    for item in sorted(
        [_as_dict(item) for item in items if isinstance(item, dict)],
        key=lambda value: (
            severity_rank.get(str(value.get("severity") or "warning"), 1),
            value.get("question_id") if value.get("question_id") is not None else 9999,
            str(value.get("code") or ""),
        ),
    ):
        key = (item.get("question_id"), item.get("code"), item.get("reason"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _append_metadata_warnings(question: Dict[str, Any], warnings: Iterable[str]) -> None:
    existing = [str(item) for item in _as_list(question.get("metadata_warnings")) if item]
    for warning in warnings:
        if warning and warning not in existing:
            existing.append(warning)
    question["metadata_warnings"] = existing


def _difficulty_review_warnings(question: Dict[str, Any]) -> List[str]:
    if _is_difficulty_blocked(question):
        return []
    if not isinstance(question.get("difficulty"), (int, float)):
        return []

    warnings: List[str] = []
    confidence = question.get("difficulty_confidence")
    if isinstance(confidence, (int, float)) and confidence < 0.7:
        warnings.append(f"难度置信度偏低：{confidence:.2f}")

    flags = set(str(flag) for flag in _as_list(question.get("difficulty_flags")))
    if "rule_llm_mismatch" in flags:
        warnings.append("规则特征与 AI 难度判断不一致")
    return warnings


def _quality_level(score: Any, feature_status: str = "ok") -> str:
    if feature_status in {"failed", "missing"} and not isinstance(score, (int, float)):
        return "数据不足"
    if feature_status == "failed":
        return "待优化"
    if not isinstance(score, (int, float)):
        return "证据不足"
    if score <= 2:
        return "硬伤"
    if score == 3:
        return "待优化"
    return "稳定"


def _teacher_quality_level(score: Any, feature_status: str, issue: str) -> str:
    level = _quality_level(score, feature_status)
    if level == "数据不足":
        return level
    if level == "证据不足":
        return "需复核" if _contains_risk_text(issue) else "未见显性问题"
    return level


def _sorted_questions(questions: Iterable[Dict]) -> List[Dict]:
    return sorted(_as_list(list(questions)), key=lambda item: (item.get("id") is None, item.get("id") or 0))


def _difficulty_label(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "未评估"
    if value <= 3.5:
        return "简单"
    if value <= 6.5:
        return "中等"
    return "困难"


def _is_multiple_choice_question(question: Dict[str, Any]) -> bool:
    qtype = str(question.get("question_type") or "").lower()
    section = str(question.get("_section_header") or question.get("section_header") or "")
    return any(token in qtype for token in ("multiple", "multi", "多选", "多项", "不定项")) or any(
        token in section for token in ("多选", "多项", "不定项")
    )


def _weighted_percentile(values: List[tuple[float, float]], percentile: float) -> float:
    if not values:
        return 0.0
    threshold = _clamp(percentile, 0.0, 1.0)
    cumulative = 0.0
    for value, share in sorted(values, key=lambda item: item[0]):
        cumulative += max(0.0, share)
        if cumulative >= threshold:
            return value
    return max(value for value, _ in values)


def _is_constructed_response_question(question: Dict[str, Any]) -> bool:
    qtype = str(question.get("question_type") or "").lower()
    if any(token in qtype for token in ("short", "answer", "essay", "fill", "constructed")):
        return True
    if "choice" in qtype or _is_multiple_choice_question(question):
        return False
    return _num(question.get("total_score"), 0) > 4


def _normalized_score_load(question: Dict[str, Any]) -> float:
    return _clamp(_num(question.get("total_score"), 0) / 14, 0, 1)


def _response_production_load(
    question: Dict[str, Any],
    scoring_units: List[Dict],
    evidence_difficulty: float,
) -> float:
    if not _is_constructed_response_question(question):
        return 0.0
    load = _normalized_score_load(question) * 0.55
    low_cognitive_gap = _clamp((6.2 - evidence_difficulty) / 6.2, 0, 1)
    return load * low_cognitive_gap


def _independent_scoring_relief(
    question: Dict[str, Any],
    scoring_units: List[Dict],
    normalized_values: List[tuple[float, float]],
) -> float:
    if not _is_constructed_response_question(question) or not scoring_units:
        return 0.0
    unit_avg = sum(value * share for value, share in normalized_values)
    broad_parts = _clamp((len(scoring_units) - 5) / 2, 0, 1.5)
    moderate_unit_load = _clamp((unit_avg - 6.0) / 4, 0, 1)
    return broad_parts * moderate_unit_load


def _objective_tail_damping(
    question: Dict[str, Any],
    evidence_difficulty: float,
    normalized_values: List[tuple[float, float]],
) -> float:
    if _is_constructed_response_question(question):
        return 0.0
    hard_share = sum(share for value, share in normalized_values if value >= 8.0)
    return max(0.0, evidence_difficulty - 6.8) * (0.5 + hard_share * 0.5)


def _difficulty_flags_from_value(value: Any) -> List[str]:
    flags: List[str] = []
    if isinstance(value, dict):
        flags.extend(str(flag) for flag in _as_list(value.get("flags")) if flag)
    return flags


def _is_difficulty_blocked(question: Dict[str, Any]) -> bool:
    if question.get("analysis_failed"):
        return True
    raw_difficulty = question.get("difficulty")
    feature_status = str(question.get("feature_status") or "").lower()
    has_numeric_difficulty = isinstance(raw_difficulty, (int, float)) or (
        isinstance(raw_difficulty, dict) and isinstance(raw_difficulty.get("final_difficulty"), (int, float))
    )
    if feature_status == "failed" or (feature_status == "missing" and not has_numeric_difficulty):
        return True
    if isinstance(raw_difficulty, dict):
        if raw_difficulty.get("analysis_failed"):
            return True
        features = _as_dict(raw_difficulty.get("features"))
        if features.get("_feature_status") == "failed":
            return True
        if any(flag in FAIL_CLOSED_DIFFICULTY_FLAGS for flag in _difficulty_flags_from_value(raw_difficulty)):
            return True
        if raw_difficulty and not isinstance(raw_difficulty.get("final_difficulty"), (int, float)):
            return True
    if any(flag in FAIL_CLOSED_DIFFICULTY_FLAGS for flag in _as_list(question.get("difficulty_flags"))):
        return True
    return False


def _effective_question_difficulty(
    question: Dict[str, Any],
    scoring_units: List[Dict],
    diagnostic_units: List[Dict] | None = None,
) -> Any:
    if _is_difficulty_blocked(question):
        return None
    base_raw = question.get("difficulty")
    raw_was_dict = isinstance(base_raw, dict)
    if raw_was_dict:
        final_difficulty = base_raw.get("final_difficulty")
        if isinstance(final_difficulty, (int, float)):
            base_raw = final_difficulty
    base_available = isinstance(base_raw, (int, float))
    if question.get("_difficulty_authoritative") is True and base_available and not raw_was_dict:
        return round(_clamp(base_raw, 0, 10), 2)
    base = _clamp(base_raw if base_available else 0, 0, 10)
    if not scoring_units:
        return round(base, 2) if base_available else None
    weighted_values: List[tuple[float, float]] = []
    for unit in scoring_units:
        difficulty = _clamp(_unit_difficulty(unit, question), 0, 10)
        share = max(0.0, _num(unit.get("score_share"), 1 / max(len(scoring_units), 1)))
        weighted_values.append((difficulty, share))
    share_sum = sum(share for _, share in weighted_values)
    if share_sum <= 0:
        normalized_values = [(value, 1 / len(weighted_values)) for value, _ in weighted_values]
    else:
        normalized_values = [(value, share / share_sum) for value, share in weighted_values]

    unit_avg = sum(value * share for value, share in normalized_values)
    hard_share = sum(share for value, share in normalized_values if value >= 8.0)
    upper_tail = _weighted_percentile(normalized_values, 0.85)
    tail_weight = 0.18 + _clamp(hard_share / 0.35, 0, 1) * 0.17
    evidence_difficulty = _clamp(
        unit_avg * (1 - tail_weight) + upper_tail * tail_weight,
        0,
        10,
    )
    if not base_available:
        base = evidence_difficulty
    complete_unit_evidence = share_sum <= 0 or 0.85 <= share_sum <= 1.15
    if complete_unit_evidence:
        base_adjustment = _clamp(base - evidence_difficulty, -0.25, 0.25) * 0.30
        evidence_difficulty = _clamp(evidence_difficulty + base_adjustment, 0, 10)
    else:
        evidence_difficulty = _clamp(evidence_difficulty * 0.75 + base * 0.25, 0, 10)

    raw_difficulty = (
        evidence_difficulty * 0.30
        + _normalized_score_load(question) * 2.00
        + _response_production_load(question, scoring_units, evidence_difficulty) * 3.00
        - _independent_scoring_relief(question, scoring_units, normalized_values) * 2.00
        - _objective_tail_damping(question, evidence_difficulty, normalized_values) * 0.30
    )
    final_difficulty = _clamp(2.8 + raw_difficulty * 1.35, 0, 10)
    if not _is_constructed_response_question(question) and diagnostic_units:
        trap_values = []
        for unit in diagnostic_units:
            unit = _as_dict(unit)
            try:
                trap_values.append(float(unit.get("trap_strength", 1)))
            except (TypeError, ValueError):
                trap_values.append(1.0)
        strong_count = sum(1 for value in trap_values if value >= 3)
        medium_count = sum(1 for value in trap_values if value >= 2)
        if final_difficulty < 6.2 and medium_count >= 3:
            final_difficulty += min(
                0.95,
                0.28 + 0.08 * medium_count + 0.10 * strong_count,
            )
    return round(_clamp(final_difficulty, 0, 10), 2)


def _score_weighted_avg(questions: List[Dict[str, Any]]) -> float:
    questions = [question for question in questions if isinstance(question.get("difficulty"), (int, float))]
    total_score = sum(_num(question.get("total_score"), 0) for question in questions)
    if total_score > 0:
        return round(
            sum(_num(question.get("difficulty"), 0) * _num(question.get("total_score"), 0) for question in questions)
            / total_score,
            2,
        )
    return round(sum(_num(question.get("difficulty"), 0) for question in questions) / len(questions), 2) if questions else 0.0


def _should_reconcile_score_total(exam: Dict[str, Any], questions: List[Dict[str, Any]]) -> bool:
    total_questions = exam.get("total_questions")
    if isinstance(total_questions, (int, float)) and int(total_questions) > 0:
        return len(questions) == int(total_questions)
    return True


def _compute_difficulty_gradient_from_questions(questions: List[Dict[str, Any]]) -> Dict[str, Any]:
    unavailable = [question.get("id") for question in questions if not isinstance(question.get("difficulty"), (int, float))]
    questions = [question for question in questions if isinstance(question.get("difficulty"), (int, float))]
    question_points = [
        {
            "question_id": question.get("id"),
            "difficulty": _num(question.get("difficulty")),
            "score": _num(question.get("total_score")),
            "difficulty_label": question.get("difficulty_label"),
        }
        for question in questions
    ]
    if len(questions) < 3:
        avg = _num(questions[0].get("difficulty")) if questions else 0
        label = "题目过少" if questions else "难度数据不足"
        return {
            "front": avg,
            "middle": avg,
            "back": avg,
            "gradient_type": label,
            "question_points": question_points,
            "unavailable_questions": unavailable,
        }
    size = len(questions) // 3
    parts = [questions[:size], questions[size:size * 2], questions[size * 2:]]
    front, middle, back = (_score_weighted_avg(part) for part in parts)
    if back > middle > front:
        gradient_type = "前易后难（递增）"
    elif front > middle > back:
        gradient_type = "前难后易（递减）"
    elif abs(front - middle) < 0.5 and abs(middle - back) < 0.5:
        gradient_type = "难度均衡"
    else:
        gradient_type = "难度波动较大"
    return {
        "front": front,
        "middle": middle,
        "back": back,
        "gradient_type": gradient_type,
        "question_points": question_points,
        "unavailable_questions": unavailable,
    }


def _normalize_questions_for_report(exam: Dict[str, Any], questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized = [dict(question) for question in questions]
    exam_total = exam.get("total_score")
    if isinstance(exam_total, (int, float)) and _should_reconcile_score_total(exam, normalized):
        current_total = sum(_num(question.get("total_score"), 0) for question in normalized)
        if current_total != exam_total:
            for question in normalized:
                if _is_multiple_choice_question(question) and _num(question.get("total_score")) <= 2:
                    original_score = _num(question.get("total_score"))
                    question["total_score"] = 4
                    question["score_adjusted_from"] = original_score
                    question["score_adjustment_reason"] = "multiple_choice_section_score_normalized"
            corrected_total = sum(_num(question.get("total_score"), 0) for question in normalized)
            if corrected_total != exam_total:
                remainder = exam_total - corrected_total
                constructed = [question for question in normalized if _is_constructed_response_question(question)]
                if not constructed:
                    raise ValueError(
                        f"score total mismatch: expected {exam_total:g}, got {corrected_total:g}, "
                        "and no constructed-response question can absorb the remainder"
                    )
                target = sorted(constructed, key=lambda question: _num(question.get("id"), 0))[-1]
                current_score = _num(target.get("total_score"))
                if current_score + remainder <= 0:
                    raise ValueError(
                        f"score total mismatch: expected {exam_total:g}, got {corrected_total:g}, "
                        f"remainder {remainder:g} would make Q{target.get('id')} nonpositive"
                    )
                target["total_score"] = current_score + remainder
                final_total = sum(_num(question.get("total_score"), 0) for question in normalized)
                if final_total != exam_total:
                    raise ValueError(f"score total mismatch: expected {exam_total:g}, got {final_total:g}")
    for question in normalized:
        raw_difficulty = question.get("difficulty")
        if isinstance(raw_difficulty, dict):
            flags = _difficulty_flags_from_value(raw_difficulty)
            question.setdefault("difficulty_flags", flags)
            question.setdefault("difficulty_source", raw_difficulty.get("difficulty_source") or raw_difficulty.get("source") or "")
            for field in (
                "content_difficulty",
                "difficulty_density",
                "score_risk",
                "score_layer",
                "difficulty_model_version",
            ):
                if field in raw_difficulty and field not in question:
                    question[field] = raw_difficulty.get(field)
            if isinstance(raw_difficulty.get("confidence"), (int, float)):
                question["difficulty_confidence"] = raw_difficulty.get("confidence")
            elif isinstance(question.get("confidence"), (int, float)):
                question["difficulty_confidence"] = question.get("confidence")
            features = _as_dict(raw_difficulty.get("features"))
            if features.get("_feature_status"):
                question.setdefault("feature_status", features.get("_feature_status"))
            if raw_difficulty.get("analysis_failed") or any(flag in FAIL_CLOSED_DIFFICULTY_FLAGS for flag in flags):
                question["analysis_failed"] = True
                question["failure_reason"] = raw_difficulty.get("failure_reason") or (
                    "big_question_structure_failed" if "big_question_fallback" in flags else "analysis_failed"
                )
            elif isinstance(raw_difficulty.get("final_difficulty"), (int, float)):
                question["_difficulty_authoritative"] = True
        existing_flags = _as_list(question.get("difficulty_flags"))
        if any(flag in FAIL_CLOSED_DIFFICULTY_FLAGS for flag in existing_flags):
            question["analysis_failed"] = True
            if not question.get("failure_reason"):
                question["failure_reason"] = (
                    "big_question_structure_failed" if "big_question_fallback" in existing_flags else "analysis_failed"
                )
        if not isinstance(question.get("difficulty_confidence"), (int, float)) and isinstance(question.get("confidence"), (int, float)):
            question["difficulty_confidence"] = question.get("confidence")
        structure_warnings = _question_structure_warnings(question)
        if structure_warnings:
            question["structure_warnings"] = structure_warnings
            _append_metadata_warnings(
                question,
                [f"题目结构：{warning}" for warning in structure_warnings],
            )
        scoring_units = _question_scoring_units(question)
        diagnostic_units = _question_diagnostic_units(question)
        effective_difficulty = _effective_question_difficulty(question, scoring_units, diagnostic_units)
        question["difficulty"] = effective_difficulty
        question["difficulty_label"] = _difficulty_label(effective_difficulty)
        difficulty_warnings = _difficulty_review_warnings(question)
        if difficulty_warnings:
            question["difficulty_review_warnings"] = difficulty_warnings
            _append_metadata_warnings(
                question,
                [f"难度复核：{warning}" for warning in difficulty_warnings],
            )
    return normalized


def _report_data_with_recomputed_difficulty(report_data: Dict[str, Any], questions: List[Dict[str, Any]]) -> Dict[str, Any]:
    updated = dict(report_data)
    metrics = dict(_as_dict(updated.get("metrics")))
    metrics["avg_difficulty"] = _score_weighted_avg(questions)
    bloom_distribution = _compute_bloom_distribution_from_questions(questions)
    if bloom_distribution:
        metrics["bloom_distribution"] = bloom_distribution
        metrics["bloom_distribution_source"] = "fine_grained_exhibits.seu_rows"
    updated["metrics"] = metrics
    updated["difficulty_gradient"] = _compute_difficulty_gradient_from_questions(questions)
    updated["questions"] = questions
    return updated


def _llm_total(llm_counts: Dict[str, Any]) -> int:
    return int(sum(value for value in llm_counts.values() if isinstance(value, (int, float))))


def _competency_pct(value: Any) -> float:
    if isinstance(value, dict):
        value = value.get("占比", value.get("percentage", value.get("value", 0)))
    return float(value) if isinstance(value, (int, float)) else 0.0


def _missing_competency_dims(competency: Dict) -> List[str]:
    distribution = _as_dict(competency.get("distribution"))
    missing = []
    for name in ("生命观念", "科学思维", "科学探究", "社会责任"):
        if _competency_pct(distribution.get(name)) <= 0:
            missing.append(name)
    return missing


def _build_cover(exam: Dict) -> Dict:
    return {
        "title": "AI 审题与审卷质量诊断报告",
        "exam_name": exam.get("name", "未命名试卷"),
        "subject": exam.get("subject", "biology"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "report_version": "commercial_report.v1",
    }


def _build_credibility(exam: Dict, questions: List[Dict], metadata: Dict) -> Dict:
    llm_counts = _as_dict(metadata.get("llm_call_counts"))
    total_score = exam.get("total_score")
    if not isinstance(total_score, (int, float)):
        total_score = sum(_num(q.get("total_score")) for q in questions)
    return {
        "analysis_scope": {
            "questions": exam.get("total_questions", len(questions)),
            "total_score": total_score,
        },
        "metadata_status": metadata_status(metadata),
        "llm_calls_total": _llm_total(llm_counts),
        "method_note": "报告基于题目分析、难度特征、核心素养与元数据门禁生成；高风险结论用于排序人工复核优先级。",
    }


def _build_question_rows(questions: List[Dict]) -> List[Dict]:
    rows = []
    for question in _sorted_questions(questions):
        qid = question.get("id")
        risk = question_risk_level(question)
        feature_status = question.get("feature_status", "ok")
        confidence = question.get("metadata_confidence", 0)
        scoring_units = _question_scoring_units(question)
        diagnostic_units = _question_diagnostic_units(question)
        pressure = _question_pressure(question, scoring_units, diagnostic_units)
        issue = primary_issue(question)
        difficulty = _effective_question_difficulty(question, scoring_units, diagnostic_units)
        difficulty_display = _format_num(difficulty, 1) if isinstance(difficulty, (int, float)) else "未评估"
        structure_review_warnings = _as_list(question.get("structure_warnings"))
        difficulty_review_warnings = _as_list(question.get("difficulty_review_warnings"))
        explicit_review_warnings = structure_review_warnings + difficulty_review_warnings
        needs_review = _contains_risk_text(issue) or bool(explicit_review_warnings)
        quality_level = _teacher_quality_level(question.get("quality_score"), feature_status, issue)
        if explicit_review_warnings and risk != "data_gap":
            quality_level = "需复核"
        action = action_for_question(question)
        if explicit_review_warnings and risk != "data_gap":
            if structure_review_warnings and difficulty_review_warnings:
                action = "先人工复核题面结构和难度评估证据，再决定是否进入正式使用。"
            elif structure_review_warnings:
                action = "先人工复核题面小问编号、材料边界和评分口径，再决定是否进入正式使用。"
            else:
                action = "先人工复核难度评估证据和采分点负荷，再决定是否进入正式使用。"
        elif needs_review and str(question.get("failure_reason") or "") != "quality_score_too_low":
            action = "进入人工优先复核清单，确认设问边界、评分标准和讲评口径。"
        is_difficulty_blocked = not isinstance(difficulty, (int, float))
        rows.append({
            "question_id": qid,
            "risk_level": risk,
            "stance": "watch" if risk == "low" and needs_review else risk_stance(risk),
            "needs_priority_review": needs_review and risk != "data_gap",
            "quality_level": quality_level,
            "difficulty": difficulty,
            "difficulty_label": _difficulty_label(difficulty),
            "difficulty_display": difficulty_display,
            "data_quality_status": "gap" if risk == "data_gap" or is_difficulty_blocked else "ok",
            "score": question.get("total_score"),
            "metadata_confidence": confidence,
            "metadata_gap": pressure["metadata_gap"],
            "evidence_density": pressure["evidence_density"],
            "pressure_index": pressure["pressure_index"],
            "dominant_pressure": pressure["dominant_pressure"],
            "score_risk": pressure["score_risk"],
            "content_difficulty": question.get("content_difficulty"),
            "difficulty_density": question.get("difficulty_density"),
            "score_layer": question.get("score_layer", {}),
            "primary_issue": issue,
            "action": action,
            "evidence_refs": [f"question:{qid}.quality", f"question:{qid}.metadata"],
        })
    return rows


def _question_fine_grained(question: Dict) -> Dict:
    fine_units = _as_dict(question.get("fine_grained_units"))
    if fine_units:
        return fine_units
    analysis = _as_dict(question.get("analysis"))
    fine = _as_dict(analysis.get("_fine_grained"))
    if fine:
        return fine
    envelope = _as_dict(question.get("_metadata_envelope"))
    return _as_dict(envelope.get("analysis_units"))


def _question_scoring_units(question: Dict) -> List[Dict]:
    fine = _question_fine_grained(question)
    units = _as_list(fine.get("scoring_units"))
    if units:
        return [_as_dict(unit) for unit in units]
    return [_as_dict(unit) for unit in _as_list(question.get("seu_knowledge_breakdown"))]


def _question_diagnostic_units(question: Dict) -> List[Dict]:
    fine = _question_fine_grained(question)
    units = _as_list(fine.get("diagnostic_units"))
    if units:
        return [_as_dict(unit) for unit in units]
    return [_as_dict(unit) for unit in _as_list(question.get("diagnostic_highlights"))]


def _question_stimulus_units(question: Dict) -> List[Dict]:
    fine = _question_fine_grained(question)
    return [_as_dict(unit) for unit in _as_list(fine.get("stimulus_units"))]


def _unit_knowledge(unit: Dict, question: Dict) -> str:
    links = _as_list(unit.get("knowledge_links"))
    for link in links:
        link = _as_dict(link)
        if link.get("knowledge_point"):
            return str(link.get("knowledge_point"))
    points = _as_list(question.get("knowledge_points"))
    return str(points[0]) if points else "未标注知识点"


def _unit_competency(unit: Dict, question: Dict) -> str:
    weights = _as_dict(unit.get("competency_weights"))
    weighted = {key: value for key, value in weights.items() if isinstance(value, (int, float))}
    if weighted:
        return str(max(weighted, key=weighted.get))
    competency = unit.get("competency")
    if isinstance(competency, dict):
        return str(competency.get("primary") or question.get("primary_competency") or "未标注素养")
    if competency:
        return str(competency)
    return str(question.get("primary_competency") or "未标注素养")


def _unit_competency_weights(unit: Dict, question: Dict) -> Dict[str, float]:
    weights = _as_dict(unit.get("competency_weights"))
    weighted = {str(key): float(value) for key, value in weights.items() if isinstance(value, (int, float))}
    if weighted:
        total = sum(value for value in weighted.values() if value > 0)
        return {key: round(value / total, 4) for key, value in weighted.items()} if total > 0 else weighted
    primary = _unit_competency(unit, question)
    return {primary: 1.0} if primary and primary != "未标注素养" else {}


def _explicit_sub_competency(unit: Dict, competency: str) -> str:
    for key in ("sub_competency", "competency_subdimension", "secondary_competency", "competency_detail"):
        value = unit.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    competency_obj = _as_dict(unit.get("competency"))
    for key in ("sub", "detail", "sub_competency", "secondary"):
        value = competency_obj.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    tags = _as_list(unit.get("competency_tags"))
    for tag in tags:
        if isinstance(tag, str) and tag.strip() and tag.strip() != competency:
            return tag.strip()
    return ""


def _infer_sub_competency(unit: Dict, question: Dict, competency: str, knowledge_point: str) -> tuple[str, str]:
    explicit = _explicit_sub_competency(unit, competency)
    if explicit:
        return explicit, "explicit"
    text_parts = [
        unit.get("label"),
        unit.get("reasoning_brief"),
        knowledge_point,
        question.get("primary_issue"),
        " ".join(str(item) for item in _as_list(question.get("knowledge_points"))),
    ]
    text = " ".join(str(part or "") for part in text_parts).lower()
    for sub_competency, keywords in COMPETENCY_SUBDIMENSION_RULES.get(competency, []):
        if any(keyword.lower() in text for keyword in keywords):
            return sub_competency, "rule_inferred"
    return DEFAULT_SUB_COMPETENCY.get(competency, "未细分素养"), "default_inferred"


def _unit_bloom(unit: Dict, question: Dict) -> int:
    value = unit.get("bloom_level", question.get("bloom_level", question.get("bloom", 3)))
    return int(value) if isinstance(value, (int, float)) else 3


def _explicit_bloom_level(unit: Dict, question: Dict) -> int | None:
    value = unit.get("bloom_level")
    if not isinstance(value, (int, float)):
        value = question.get("bloom_level", question.get("bloom"))
    if not isinstance(value, (int, float)):
        return None
    level = int(value)
    return level if level in BLOOM_LEVEL_LABELS else None


def _compute_bloom_distribution_from_questions(questions: List[Dict[str, Any]]) -> Dict[str, float]:
    weighted: Dict[str, float] = {label: 0.0 for label in BLOOM_LEVEL_LABELS.values()}
    for question in questions:
        score = _num(question.get("total_score"), 0)
        if score <= 0:
            continue
        raw_units = []
        for unit in _question_scoring_units(question):
            level = _explicit_bloom_level(unit, question)
            if level is None:
                continue
            raw_units.append((level, max(0.0, _num(unit.get("score_share"), 0))))
        if raw_units:
            share_total = sum(share for _, share in raw_units)
            if share_total <= 0:
                raw_units = [(level, 1 / len(raw_units)) for level, _ in raw_units]
                share_total = 1.0
            for level, share in raw_units:
                weighted[BLOOM_LEVEL_LABELS[level]] += score * share / share_total
            continue
        level = _explicit_bloom_level({}, question)
        if level is not None:
            weighted[BLOOM_LEVEL_LABELS[level]] += score

    total = sum(weighted.values())
    if total <= 0:
        return {}
    return {
        label: round(weight / total, 4)
        for label, weight in weighted.items()
        if weight > 0
    }


def _unit_difficulty(unit: Dict, question: Dict) -> float:
    value = unit.get("difficulty_estimate", question.get("difficulty", 5))
    return float(value) if isinstance(value, (int, float)) else 5.0


def _question_pressure(question: Dict, scoring_units: List[Dict], diagnostic_units: List[Dict]) -> Dict[str, Any]:
    difficulty = max(0.0, min(1.0, _num(question.get("difficulty"), 0) / 10))
    score_risk = max(0.0, min(1.0, _num(question.get("score_risk"), _num(question.get("difficulty"), 0)) / 10))
    quality_score = _num(question.get("quality_score"), 5)
    quality_gap = max(0.0, min(1.0, (5 - quality_score) / 5))
    metadata_gap = max(0.0, min(1.0, 1 - _num(question.get("metadata_confidence"), 1)))
    max_trap = max((_num(unit.get("trap_strength"), 0) for unit in diagnostic_units), default=0)
    trap_pressure = max(0.0, min(1.0, max_trap / 3))
    evidence_density = len(scoring_units) + len(diagnostic_units)
    density_pressure = max(0.0, min(1.0, evidence_density / 5))

    components = {
        "难度": difficulty,
        "分值压力": score_risk,
        "质量": quality_gap,
        "元数据": metadata_gap,
        "陷阱": trap_pressure,
        "证据密度": density_pressure,
    }
    weighted = (
        difficulty * 0.24
        + score_risk * 0.16
        + quality_gap * 0.22
        + metadata_gap * 0.18
        + trap_pressure * 0.12
        + density_pressure * 0.08
    )
    return {
        "pressure_index": round(weighted * 100, 1),
        "dominant_pressure": max(components, key=components.get),
        "metadata_gap": round(metadata_gap, 2),
        "evidence_density": evidence_density,
        "quality_gap": round(quality_gap, 2),
        "trap_pressure": round(trap_pressure, 2),
        "score_risk": round(score_risk * 10, 1),
    }


def _build_knowledge_exhibit_rows(knowledge: Dict, seu_rows: List[Dict]) -> List[Dict]:
    aggregate: Dict[str, Dict[str, Any]] = {}

    def bucket(name: str) -> Dict[str, Any]:
        return aggregate.setdefault(name, {
            "name": name,
            "weighted_score": 0.0,
            "seu_ids": set(),
            "question_ids": set(),
            "risk_question_ids": set(),
            "bloom_total": 0.0,
            "bloom_count": 0,
            "aliases": set(),
        })

    def _canon(raw_value: Any) -> tuple[str, str]:
        raw_name = str(raw_value or "未标注知识点")
        label, _diag = canonicalize_knowledge_point(raw_name)
        return (label or raw_name), raw_name

    # 源1：采分点贡献（per-link）。归一知识点名作分组 key，seu_id 去重计数。
    for row in seu_rows:
        name, raw_name = _canon(row.get("knowledge_point"))
        item = bucket(name)
        if raw_name and raw_name != name:
            item["aliases"].add(raw_name)
        item["weighted_score"] += _num(row.get("score_contribution"), _num(row.get("weighted_score")))
        seu_id = row.get("seu_id")
        if seu_id is not None:
            item["seu_ids"].add(seu_id)
        qid = row.get("question_id")
        if qid is not None:
            item["question_ids"].add(qid)
            if row.get("risk_level") == "high":
                item["risk_question_ids"].add(qid)
        bloom = row.get("bloom_level")
        if isinstance(bloom, (int, float)):
            item["bloom_total"] += bloom
            item["bloom_count"] += 1

    has_seu_data = bool(aggregate)

    # 源2：题目级先验 top_points（已 canonical）。同样归一，只抬升 weighted_score 上界。
    for point in _as_list(knowledge.get("top_points")):
        point = _as_dict(point)
        name, raw_name = _canon(point.get("name") or point.get("label"))
        item = bucket(name)
        if raw_name and raw_name != name:
            item["aliases"].add(raw_name)
        item["weighted_score"] = max(
            item["weighted_score"],
            _num(point.get("weighted_score", point.get("value", point.get("count")))),
        )

    rows = []
    for item in aggregate.values():
        seu_count = len(item["seu_ids"])
        # 有采分点数据时，纯先验空壳（无任何 seu 支撑）不排进 Top
        if has_seu_data and seu_count == 0:
            continue
        bloom_count = item["bloom_count"] or 1
        rows.append({
            "name": item["name"],
            "weighted_score": round(item["weighted_score"], 2),
            "seu_count": seu_count,
            "question_count": len(item["question_ids"]),
            "risk_count": len(item["risk_question_ids"]),
            "avg_bloom": round(item["bloom_total"] / bloom_count, 2) if item["bloom_count"] else 0,
            "aliases": sorted(item["aliases"]),
        })
    return sorted(rows, key=lambda row: (-row["weighted_score"], -row["risk_count"], row["name"]))[:10]


def _aggregate_competency_detail_rows(rows: List[Dict]) -> List[Dict]:
    aggregate: Dict[tuple[str, str], Dict[str, Any]] = {}
    for row in rows:
        competency = str(row.get("competency") or "未标注素养")
        sub_competency = str(row.get("sub_competency") or DEFAULT_SUB_COMPETENCY.get(competency, "未细分素养"))
        key = (competency, sub_competency)
        item = aggregate.setdefault(key, {
            "competency": competency,
            "sub_competency": sub_competency,
            "score_contribution": 0.0,
            "question_ids": set(),
            "seu_count": 0,
            "seu_labels": [],
            "source": row.get("source", "default_inferred"),
        })
        item["score_contribution"] += _num(row.get("score_contribution"))
        item["seu_count"] += 1
        if row.get("question_id") is not None:
            item["question_ids"].add(row.get("question_id"))
        label = str(row.get("label") or row.get("seu_id") or "")
        if label and len(item["seu_labels"]) < 3:
            item["seu_labels"].append(label)
        if item["source"] != "explicit" and row.get("source") == "rule_inferred":
            item["source"] = "rule_inferred"
        if row.get("source") == "explicit":
            item["source"] = "explicit"

    result = []
    for item in aggregate.values():
        result.append({
            "competency": item["competency"],
            "sub_competency": item["sub_competency"],
            "score_contribution": round(item["score_contribution"], 2),
            "question_ids": sorted(item["question_ids"]),
            "seu_count": item["seu_count"],
            "seu_labels": item["seu_labels"],
            "source": item["source"],
        })
    return sorted(result, key=lambda row: (-row["score_contribution"], row["competency"], row["sub_competency"]))


def _competency_distribution_scores(distribution: Dict, detail_rows: List[Dict]) -> Dict[str, float]:
    scores = {}
    for name in CORE_COMPETENCIES:
        value = _competency_pct(_as_dict(distribution).get(name))
        scores[name] = round(value * 100, 1) if 0 < value <= 1 else value
    if any(value > 0 for value in scores.values()):
        return scores
    totals = {name: 0.0 for name in CORE_COMPETENCIES}
    for row in detail_rows:
        competency = str(row.get("competency") or "")
        if competency in totals:
            totals[competency] += _num(row.get("score_contribution"))
    total = sum(totals.values())
    return {name: round(value / total * 100, 1) if total else 0.0 for name, value in totals.items()}


def _build_competency_gap_rows(distribution: Dict, detail_rows: List[Dict]) -> List[Dict]:
    scores = _competency_distribution_scores(distribution, detail_rows)
    recommendations = {
        "生命观念": "可补充结构与功能、稳态调节或生态系统解释类采分点。",
        "科学思维": "可增加证据推理、模型建构或数据解释的显性评分要求。",
        "科学探究": "可通过实验设计、变量控制、结果解释类小问补足。",
        "社会责任": "可引入健康生活、生态治理、生物安全或技术伦理情境。",
    }
    rows = []
    for name in CORE_COMPETENCIES:
        value = scores.get(name, 0.0)
        if value <= 0:
            status = "缺失"
        elif value < 12:
            status = "低覆盖"
        else:
            continue
        rows.append({
            "competency": name,
            "share": round(value, 1),
            "status": status,
            "recommendation": recommendations[name],
        })
    return rows


def _build_competency_diagnosis(competency: Dict, fine_exhibits: Dict) -> Dict[str, Any]:
    distribution = _as_dict(competency.get("distribution"))
    detail_rows = _as_list(fine_exhibits.get("competency_detail_rows"))
    evidence_rows = _as_list(fine_exhibits.get("competency_evidence_rows"))
    scores = _competency_distribution_scores(distribution, detail_rows)
    dominant = max(scores.items(), key=lambda item: item[1]) if scores else ("未标注", 0)
    top_detail = detail_rows[0] if detail_rows else {}
    gap_rows = _build_competency_gap_rows(distribution, detail_rows)
    return {
        "distribution": distribution,
        "detail_rows": detail_rows,
        "evidence_rows": evidence_rows,
        "gap_rows": gap_rows,
        "summary": {
            "dominant_competency": dominant[0],
            "dominant_share": round(dominant[1], 1),
            "top_sub_competency": top_detail.get("sub_competency", "暂无细分"),
            "top_sub_score": top_detail.get("score_contribution", 0),
            "gap_count": len(gap_rows),
        },
    }


def _build_fine_grained_exhibits(questions: List[Dict], rows: List[Dict]) -> Dict:
    by_id = {row["question_id"]: row for row in rows}
    seu_rows: List[Dict] = []
    du_rows: List[Dict] = []
    su_rows: List[Dict] = []
    knowledge_contribution_rows: List[Dict] = []
    competency_contribution_rows: List[Dict] = []
    competency_evidence_rows: List[Dict] = []
    metadata_audit_rows: List[Dict] = []
    factor_rows: List[Dict] = []

    for question in _sorted_questions(questions):
        qid = question.get("id")
        row = by_id.get(qid, {})
        score = _num(question.get("total_score"), 1.0) or 1.0
        scoring_units = _question_scoring_units(question)
        diagnostic_units = _question_diagnostic_units(question)
        stimulus_units = _question_stimulus_units(question)
        share_sum = 0.0
        knowledge_share_valid = True
        competency_weight_valid = True

        for index, unit in enumerate(scoring_units, 1):
            share = _num(unit.get("score_share"), 1 / max(len(scoring_units), 1))
            share_sum += share
            confidence = _num(unit.get("allocation_confidence"), question.get("metadata_confidence", 0))
            weighted_score = round(score * share, 2)
            knowledge_links = [_as_dict(link) for link in _as_list(unit.get("knowledge_links"))]
            competency_weights = _unit_competency_weights(unit, question)
            seu_id = unit.get("seu_id") or f"Q{qid}-SEU{index}"
            if knowledge_links:
                link_sum = sum(_num(link.get("share"), 0) for link in knowledge_links)
                if abs(link_sum - 1.0) > 0.03:
                    knowledge_share_valid = False
            weight_sum = sum(value for value in competency_weights.values() if isinstance(value, (int, float)))
            if competency_weights and abs(weight_sum - 1.0) > 0.03:
                competency_weight_valid = False
            seu_rows.append({
                "question_id": qid,
                "seu_id": seu_id,
                "label": unit.get("label") or f"采分单元 {index}",
                "score_share": round(share, 4),
                "weighted_score": weighted_score,
                "allocation_source": unit.get("allocation_source", "inferred"),
                "knowledge_point": _unit_knowledge(unit, question),
                "knowledge_links": knowledge_links,
                "competency": _unit_competency(unit, question),
                "competency_weights": competency_weights,
                "bloom_level": _unit_bloom(unit, question),
                "difficulty_estimate": round(_unit_difficulty(unit, question), 2),
                "allocation_confidence": round(confidence, 2),
                "reasoning_brief": unit.get("reasoning_brief", ""),
                "risk_level": row.get("risk_level", "medium"),
            })
            for link in knowledge_links:
                link_share = _num(link.get("share"), 1 / max(len(knowledge_links), 1))
                knowledge_contribution_rows.append({
                    "question_id": qid,
                    "seu_id": seu_id,
                    "knowledge_point": link.get("knowledge_point", "未标注知识点"),
                    "share": round(link_share, 4),
                    "score_contribution": round(score * share * link_share, 2),
                    "allocation_confidence": round(confidence, 2),
                    "risk_level": row.get("risk_level", "medium"),
            })
            for dim, weight in competency_weights.items():
                if weight <= 0:
                    continue
                sub_competency, sub_source = _infer_sub_competency(unit, question, dim, _unit_knowledge(unit, question))
                competency_contribution_rows.append({
                    "question_id": qid,
                    "seu_id": seu_id,
                    "competency": dim,
                    "weight": round(weight, 4),
                    "score_contribution": round(score * share * weight, 2),
                    "allocation_confidence": round(confidence, 2),
                    "risk_level": row.get("risk_level", "medium"),
                })
                competency_evidence_rows.append({
                    "question_id": qid,
                    "seu_id": seu_id,
                    "label": unit.get("label") or f"采分单元 {index}",
                    "competency": dim,
                    "sub_competency": sub_competency,
                    "weight": round(weight, 4),
                    "score_contribution": round(score * share * weight, 2),
                    "allocation_confidence": round(confidence, 2),
                    "source": sub_source,
                    "risk_level": row.get("risk_level", "medium"),
                })

        for index, unit in enumerate(diagnostic_units, 1):
            du_rows.append({
                "question_id": qid,
                "du_id": unit.get("du_id") or f"Q{qid}-DU{index}",
                "option_or_trap": unit.get("option_or_trap") or unit.get("option") or f"trap_{index}",
                "distractor_type": unit.get("distractor_type", "misconception"),
                "misconception": unit.get("misconception", ""),
                "trap_strength": int(_num(unit.get("trap_strength"), 2)),
                "knowledge_boundary": unit.get("knowledge_boundary", ""),
                "risk_level": row.get("risk_level", "medium"),
                "question_difficulty": row.get("difficulty", question.get("difficulty")),
                "question_pressure": row.get("pressure_index", 0),
                "question_score": row.get("score", question.get("total_score")),
            })

        for index, unit in enumerate(stimulus_units, 1):
            su_rows.append({
                "question_id": qid,
                "su_id": unit.get("su_id") or f"Q{qid}-SU{index}",
                "stimulus_type": unit.get("stimulus_type", unit.get("type", "unknown")),
                "description": unit.get("description", ""),
                "complexity": unit.get("complexity", unit.get("complexity_level")),
                "is_core": unit.get("is_core", True),
            })

        bloom_values = [_unit_bloom(unit, question) for unit in scoring_units]
        difficulty_values = [_unit_difficulty(unit, question) for unit in scoring_units]
        trap_values = [_num(unit.get("trap_strength"), 0) for unit in diagnostic_units]
        pressure = _question_pressure(question, scoring_units, diagnostic_units)
        avg_conf = (
            round(sum(_num(unit.get("allocation_confidence"), question.get("metadata_confidence", 0)) for unit in scoring_units) / len(scoring_units), 2)
            if scoring_units else _num(question.get("metadata_confidence"), 0)
        )
        metadata_audit_rows.append({
            "question_id": qid,
            "seu_count": len(scoring_units),
            "du_count": len(diagnostic_units),
            "su_count": len(stimulus_units),
            "score_share_sum": round(share_sum, 4) if scoring_units else 0,
            "score_share_valid": abs(share_sum - 1.0) <= 0.03 if scoring_units else False,
            "knowledge_share_valid": knowledge_share_valid,
            "competency_weight_valid": competency_weight_valid,
            "avg_allocation_confidence": avg_conf,
            "metadata_confidence": _num(question.get("metadata_confidence")),
            "warnings": _as_list(question.get("metadata_warnings")),
        })
        factor_rows.append({
            "question_id": qid,
            "score": score,
            "difficulty": _num(question.get("difficulty"), sum(difficulty_values) / len(difficulty_values) if difficulty_values else 0),
            "quality_score": _num(question.get("quality_score")),
            "metadata_confidence": _num(question.get("metadata_confidence")),
            "metadata_gap": pressure["metadata_gap"],
            "evidence_density": pressure["evidence_density"],
            "pressure_index": pressure["pressure_index"],
            "dominant_pressure": pressure["dominant_pressure"],
            "score_risk": pressure["score_risk"],
            "content_difficulty": _num(question.get("content_difficulty"), question.get("difficulty")),
            "difficulty_density": question.get("difficulty_density"),
            "partial_credit_relief": _num(_as_dict(question.get("score_layer")).get("partial_credit_relief")),
            "quality_gap": pressure["quality_gap"],
            "trap_pressure": pressure["trap_pressure"],
            "seu_count": len(scoring_units),
            "du_count": len(diagnostic_units),
            "avg_bloom": round(sum(bloom_values) / len(bloom_values), 2) if bloom_values else _num(question.get("bloom_level"), 0),
            "avg_seu_difficulty": round(sum(difficulty_values) / len(difficulty_values), 2) if difficulty_values else _num(question.get("difficulty")),
            "max_trap_strength": max(trap_values) if trap_values else 0,
            "risk_level": row.get("risk_level", "medium"),
        })

    avg_conf = (
        round(sum(row["allocation_confidence"] for row in seu_rows) / len(seu_rows), 2)
        if seu_rows else 0
    )
    return {
        "summary": {
            "total_seus": len(seu_rows),
            "total_dus": len(du_rows),
            "total_sus": len(su_rows),
            "knowledge_links": len(knowledge_contribution_rows),
            "competency_links": len(competency_contribution_rows),
            "avg_allocation_confidence": avg_conf,
            "questions_with_units": len([row for row in factor_rows if row["seu_count"] > 0]),
        },
        "seu_rows": seu_rows,
        "du_rows": du_rows,
        "su_rows": su_rows,
        "knowledge_contribution_rows": knowledge_contribution_rows,
        "competency_contribution_rows": competency_contribution_rows,
        "competency_evidence_rows": competency_evidence_rows,
        "competency_detail_rows": _aggregate_competency_detail_rows(competency_evidence_rows),
        "metadata_audit_rows": metadata_audit_rows,
        "difficulty_factor_rows": factor_rows,
    }


def _metric(name: str, value: Any, unit: str = "") -> Dict[str, Any]:
    return {"name": name, "value": value, "unit": unit}


def _build_review_positioning() -> Dict[str, str]:
    return {
        "report_type": "审题 / 审卷质量诊断报告",
        "audience": "命题教师 / 教研组 / 备课组",
        "use_case": "判断试卷能否使用、如何修订、如何讲评、是否适配学情",
    }


def _row_review_tier(row: Dict[str, Any]) -> str:
    # 复核分层: must=必须先复核 / watch=建议关注 / none=无需
    # 对齐系统风险语义: medium 本就是 watch(关注)不等于必须复核; 硬伤=must, 待优化=watch
    # 只改展示分层, 不改 risk_level/quality_level 的计算
    if row.get("needs_priority_review") is True:
        return "must"
    if row.get("risk_level") == "data_gap":
        return "none"
    if row.get("risk_level") == "high":
        return "must"
    if row.get("quality_level") == "硬伤":
        return "must"
    if row.get("risk_level") == "medium":
        return "watch"
    if row.get("quality_level") == "待优化":
        return "watch"
    if _contains_risk_text(row.get("primary_issue")):
        return "watch"
    return "none"


def _row_needs_priority_review(row: Dict[str, Any]) -> bool:
    return _row_review_tier(row) == "must"


def _priority_review_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [row for row in rows if _row_review_tier(row) == "must"]


def _attention_review_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [row for row in rows if _row_review_tier(row) == "watch"]


def _question_range_text(ids: Iterable[Any]) -> str:
    ordered = sorted({int(item) for item in ids if isinstance(item, int)})
    if not ordered:
        return "暂无明确题号"
    if len(ordered) >= 3 and ordered == list(range(ordered[0], ordered[-1] + 1)):
        return f"第 {ordered[0]}-{ordered[-1]} 题"
    return "、".join(f"第 {item} 题" for item in ordered)


def _quality_risk_counts(questions: List[Dict]) -> Dict[str, int]:
    checks = {
        "科学性": ["quality_scientific", "scientific_risk"],
        "可行性": ["quality_context", "quality_feasibility", "feasibility_risk"],
        "语言表述": ["quality_language"],
        "规范性": ["quality_normative"],
        "舆论隐患": ["quality_public_opinion", "quality_opinion", "public_opinion_risk", "opinion_risk"],
    }
    counts = {label: 0 for label in checks}
    for raw_question in questions:
        question = _as_dict(raw_question)
        for label, fields in checks.items():
            if any(_contains_risk_text(question.get(field)) for field in fields):
                counts[label] += 1
    return counts


def _quality_risk_summary(counts: Dict[str, int]) -> str:
    return "、".join(f"{label} {counts.get(label, 0)} 道" for label in ("科学性", "可行性", "语言表述", "规范性", "舆论隐患"))


def _teacher_weak_dimensions(rows: List[Dict]) -> List[str]:
    mapping = {
        "难度": "综合推理",
        "质量": "题目质量辨析",
        "元数据": "信息完整性",
        "陷阱": "干扰项辨析",
        "证据密度": "信息提取",
    }
    dimensions: List[str] = []
    for row in sorted(rows, key=lambda item: _num(item.get("pressure_index")), reverse=True):
        label = mapping.get(str(row.get("dominant_pressure")), str(row.get("dominant_pressure") or "知识迁移"))
        if label not in dimensions:
            dimensions.append(label)
    return dimensions[:3]


def _build_findings(
    report_data: Dict,
    rows: List[Dict],
    fine_exhibits: Dict,
    knowledge_exhibit_rows: List[Dict],
) -> List[Dict]:
    summary = _as_dict(fine_exhibits.get("summary"))
    factor_rows = _as_list(fine_exhibits.get("difficulty_factor_rows"))
    seu_rows = _as_list(fine_exhibits.get("seu_rows"))
    du_rows = _as_list(fine_exhibits.get("du_rows"))
    audit_rows = _as_list(fine_exhibits.get("metadata_audit_rows"))
    findings: List[Dict] = []

    if summary.get("total_seus"):
        evidence = [
            f"seu:Q{row.get('question_id')}:{row.get('seu_id')}"
            for row in seu_rows[:6]
        ]
        findings.append({
            "id": "fine_grained_fidelity",
            "type": "metadata_finding",
            "title": "综合诊断已建立在审题证据层上",
            "claim": (
                f"本次报告可追溯到 {summary.get('total_seus', 0)} 个采分点、"
                f"{summary.get('total_dus', 0)} 个误区诊断点和 {summary.get('total_sus', 0)} 个材料情境点。"
            ),
            "why_it_matters": (
                "执行摘要不再依赖题目级均值，而是绑定到可展开的采分点、误区诊断和材料情境。"
            ),
            "severity": "medium",
            "confidence": summary.get("avg_allocation_confidence", 0),
            "metrics": [
                _metric("采分点", summary.get("total_seus", 0), "个"),
                _metric("误区诊断点", summary.get("total_dus", 0), "个"),
                _metric("材料情境点", summary.get("total_sus", 0), "个"),
                _metric("知识点链接", summary.get("knowledge_links", 0), "条"),
            ],
            "contributors": [row.get("question_id") for row in factor_rows if row.get("seu_count")][:8],
            "evidence_refs": evidence,
            "recommended_action": "所有执行摘要结论优先引用采分点与误区诊断贡献表，题目级均值只作为导航层。",
        })

    if len(factor_rows) >= 5:
        sorted_factors = sorted(factor_rows, key=lambda row: row.get("question_id") or 0)
        tail = sorted_factors[-5:]
        total_score = sum(_num(row.get("score")) for row in sorted_factors) or 1
        tail_score = sum(_num(row.get("score")) for row in tail)
        tail_seus = sum(int(_num(row.get("seu_count"))) for row in tail)
        tail_dus = sum(int(_num(row.get("du_count"))) for row in tail)
        tail_pressure = round(sum(_num(row.get("pressure_index")) for row in tail) / len(tail), 1)
        top_tail = sorted(tail, key=lambda row: _num(row.get("pressure_index")), reverse=True)[:3]
        findings.append({
            "id": "tail_pressure_source",
            "type": "difficulty_finding",
            "title": "后段题组是整卷压力和区分度的主要来源",
            "claim": (
                f"后 5 题占 {round(tail_score / total_score * 100, 1)}% 分值，"
                f"包含 {tail_seus} 个采分点和 {tail_dus} 个误区诊断点。"
            ),
            "why_it_matters": (
                "后段题组同时承载更高分值、更多采分点和更多诊断陷阱，是复核命题梯度的优先区域。"
            ),
            "severity": "high" if tail_pressure >= 65 else "medium",
            "confidence": summary.get("avg_allocation_confidence", 0),
            "metrics": [
                _metric("后段分值占比", round(tail_score / total_score * 100, 1), "%"),
                _metric("后段采分点", tail_seus, "个"),
                _metric("后段误区诊断点", tail_dus, "个"),
                _metric("后段平均压力指数", tail_pressure),
            ],
            "contributors": [row.get("question_id") for row in top_tail],
            "evidence_refs": [f"question:Q{row.get('question_id')}.pressure" for row in top_tail],
            "recommended_action": "优先展开后段题组，检查高阶能力要求、评分标准和陷阱设计是否匹配。",
        })

    invalid_rows = [
        row for row in audit_rows
        if not row.get("score_share_valid")
        or not row.get("knowledge_share_valid")
        or not row.get("competency_weight_valid")
        or _num(row.get("avg_allocation_confidence"), 1) < 0.7
    ]
    if invalid_rows:
        findings.append({
            "id": "metadata_audit_gap",
            "type": "metadata_finding",
            "title": "部分题目的细粒度权重需要复核",
            "claim": f"{len(invalid_rows)} 道题存在权重守恒、知识点占比或置信度风险。",
            "why_it_matters": "元数据权重不守恒会直接扭曲知识点贡献、素养覆盖和后续图表诊断。",
            "severity": "high",
            "confidence": 0.7,
            "metrics": [
                _metric("需复核题数", len(invalid_rows), "道"),
                _metric("审计覆盖题数", len(audit_rows), "道"),
            ],
            "contributors": [row.get("question_id") for row in invalid_rows[:8]],
            "evidence_refs": [f"metadata:Q{row.get('question_id')}" for row in invalid_rows[:8]],
            "recommended_action": "正式导出前先复核这些题的分值占比、知识点权重和素养权重。",
        })
    elif audit_rows:
        findings.append({
            "id": "metadata_audit_pass",
            "type": "metadata_finding",
            "title": "采分点权重审计未发现阻断项",
            "claim": "采分点分值守恒、知识点占比和素养权重可支撑当前聚合诊断。",
            "why_it_matters": "权重审计通过意味着当前综合诊断具备可追溯的审题证据底座。",
            "severity": "low",
            "confidence": summary.get("avg_allocation_confidence", 0),
            "metrics": [
                _metric("审计覆盖题数", len(audit_rows), "道"),
                _metric("平均采分点置信度", summary.get("avg_allocation_confidence", 0)),
            ],
            "contributors": [row.get("question_id") for row in audit_rows[:8]],
            "evidence_refs": [f"metadata:Q{row.get('question_id')}" for row in audit_rows[:8]],
            "recommended_action": "继续使用审计矩阵作为正式报告的可信度底座。",
        })

    top_knowledge = knowledge_exhibit_rows[:3]
    if top_knowledge:
        findings.append({
            "id": "knowledge_concentration",
            "type": "knowledge_finding",
            "title": "知识点诊断可追溯到采分点分值贡献",
            "claim": "高权重知识点不再只来自题目标签，而是来自采分点与知识点占比的分值贡献。",
            "why_it_matters": "知识点优先级来自分值贡献后，复习建议和图表排序才不会被粗粒度题目标签误导。",
            "severity": "medium",
            "confidence": summary.get("avg_allocation_confidence", 0),
            "metrics": [
                _metric(row.get("name"), row.get("weighted_score"), "分")
                for row in top_knowledge
            ],
            "contributors": [row.get("name") for row in top_knowledge],
            "evidence_refs": ["fine_grained_exhibits.knowledge_contribution_rows"],
            "recommended_action": "知识点复习建议按分值贡献和高风险题关联排序，而不是按出现次数排序。",
        })

    return findings[:6]


def _build_big_calls(report_data: Dict, rows: List[Dict]) -> List[Dict]:
    metadata = _as_dict(report_data.get("metadata_quality"))
    metrics = _as_dict(report_data.get("metrics"))
    gradient = _as_dict(report_data.get("difficulty_gradient"))
    competency = _as_dict(report_data.get("competency"))
    knowledge = _as_dict(report_data.get("knowledge"))
    calls = []

    high_risk = [row for row in rows if row["risk_level"] == "high"]
    if high_risk:
        ids = [row["question_id"] for row in high_risk[:6]]
        calls.append({
            "id": "question_quality_risk",
            "title": f"{len(high_risk)} 道题进入高风险复核",
            "stance": "risk",
            "why_it_matters": "高风险题会直接影响整卷诊断可信度和教师采信程度。",
            "evidence_refs": [f"question:{qid}" for qid in ids],
            "recommended_action": "先复核高风险题的科学性、设问边界与元数据链路。",
        })

    status = metadata_status(metadata)
    if status != "pass":
        warning_count = len(_as_list(metadata.get("warning_questions")))
        missing_count = len(_as_list(metadata.get("missing_envelope_questions")))
        calls.append({
            "id": "metadata_governance",
            "title": "元数据治理存在交付前关注项",
            "stance": "risk" if status == "blocked" else "watch",
            "why_it_matters": f"warning={warning_count}，missing={missing_count}；元数据是报告结论可追溯性的根。",
            "evidence_refs": ["metadata:warning_questions", "metadata:missing_envelope_questions"],
            "recommended_action": "正式交付前先处理低置信度和 warning 题目，再出最终判断。",
        })

    avg_difficulty = metrics.get("avg_difficulty")
    if isinstance(avg_difficulty, (int, float)):
        stance = "risk" if avg_difficulty >= 7 else "watch" if avg_difficulty >= 6 else "positive"
        calls.append({
            "id": "difficulty_structure",
            "title": f"平均难度 {_format_num(avg_difficulty, 2)}",
            "stance": stance,
            "why_it_matters": gradient.get("gradient_type", "难度梯度待确认"),
            "evidence_refs": ["metric:avg_difficulty", "figure:difficulty_gradient"],
            "recommended_action": "结合高分值题与后段题组检查区分度是否来自合理能力要求。",
        })

    missing_dims = _missing_competency_dims(competency)
    if missing_dims:
        calls.append({
            "id": "competency_gap",
            "title": "核心素养覆盖存在空档",
            "stance": "watch",
            "why_it_matters": "缺失素养会削弱整卷对课程目标的覆盖解释力。",
            "evidence_refs": ["figure:competency_distribution"],
            "recommended_action": "补充或重写采分点，使缺失素养进入可评估范围：" + "、".join(missing_dims),
        })

    unmapped = knowledge.get("unmapped_count")
    if isinstance(unmapped, int) and unmapped > 0:
        calls.append({
            "id": "knowledge_mapping_gap",
            "title": f"{unmapped} 个知识点未完成标准映射",
            "stance": "watch",
            "why_it_matters": "知识点无法标准映射会影响教材覆盖和复习建议。",
            "evidence_refs": ["knowledge:unmapped_count"],
            "recommended_action": "补齐知识点标准化映射后再生成正式知识覆盖结论。",
        })

    if not calls:
        calls.append({
            "id": "stable_structure",
            "title": "整卷结构具备进入人工抽样复核的条件",
            "stance": "positive",
            "why_it_matters": "未发现元数据阻断项或高风险题集中暴露。",
            "evidence_refs": ["metadata:llm_call_counts", "question_portfolio:risk_levels"],
            "recommended_action": "进入教研组抽样复核并确认最终口径。",
        })

    return calls[:5]


def _build_executive_summary(
    report_data: Dict,
    rows: List[Dict],
    findings: List[Dict] | None = None,
    fine_exhibits: Dict | None = None,
) -> Dict:
    metrics = _as_dict(report_data.get("metrics"))
    gradient = _as_dict(report_data.get("difficulty_gradient"))
    calls = list(findings or []) + _build_big_calls(report_data, rows)
    high_count = len([row for row in rows if row["risk_level"] == "high"])
    questions = _as_list(report_data.get("questions"))
    language_risk_count = len([q for q in questions if _contains_risk_text(_as_dict(q).get("quality_language"))])
    scientific_risk_count = len([q for q in questions if _contains_risk_text(_as_dict(q).get("quality_scientific"))])
    priority_rows = _priority_review_rows(rows)
    blocking_rows = [
        row for row in rows
        if row.get("risk_level") == "data_gap" or not isinstance(row.get("difficulty"), (int, float))
    ]
    high_pressure_rows = [
        row for row in rows
        if _num(row.get("pressure_index")) >= 60
        or row.get("risk_level") == "high"
        or (isinstance(row.get("difficulty"), (int, float)) and row.get("difficulty") >= 8.5)
    ]
    avg_difficulty = _num(metrics.get("avg_difficulty"))
    student_fit = summarize_student_fit(
        avg_difficulty=avg_difficulty,
        high_pressure_count=len(high_pressure_rows),
        target_group="高三学生",
    )
    blocking_question_ids = [int(row["question_id"]) for row in blocking_rows if isinstance(row.get("question_id"), int)]
    blocking_id_set = set(blocking_question_ids)
    priority_rows = [row for row in priority_rows if row.get("question_id") not in blocking_id_set]
    risk_question_ids = [int(row["question_id"]) for row in priority_rows if isinstance(row.get("question_id"), int)]
    attention_rows = [row for row in _attention_review_rows(rows) if row.get("question_id") not in blocking_id_set]
    attention_question_ids = [int(row["question_id"]) for row in attention_rows if isinstance(row.get("question_id"), int)]
    fine_summary = _as_dict(_as_dict(fine_exhibits).get("summary"))
    if blocking_rows:
        lead = (
            "本报告用于判断试卷能否使用、哪些题需先修订、讲评时应聚焦哪些能力卡点。"
            f"当前存在 {len(blocking_rows)} 道阻断题（{_q_label_list(blocking_question_ids)}），"
            "不得用推断难度或默认结论掩盖；需先处理对应失败原因。"
            f"另有 {len(priority_rows)} 道人工优先复核题。"
        )
    elif priority_rows:
        lead = (
            "本报告用于判断试卷能否使用、哪些题需先修订、讲评时应聚焦哪些能力卡点。"
            f"当前识别 {len(priority_rows)} 道人工优先复核题，建议先完成复核，再作为阶段诊断卷使用。"
        )
    else:
        lead = difficulty_thesis(metrics.get("avg_difficulty"), gradient.get("gradient_type", ""))
    teacher_priorities = []
    if blocking_question_ids:
        block_reason = ""
        blocking_action = (
            f"先处理 {_q_label_list(blocking_question_ids)} 的失败原因；"
            "处理前不得展示推断难度，也不得把该题计入整卷均值。"
        )
        for question in questions:
            if question.get("id") in blocking_question_ids:
                explanations = _question_evidence_integrity_trace(question).get("failure_explanations", [])
                if explanations:
                    first = explanations[0]
                    block_reason = f" 主要原因：Q{question.get('id')} {first.get('title')}，{first.get('reason')}"
                    if first.get("code") == "quality_score_too_low":
                        blocking_action = (
                            f"先核对 {_q_label_list(blocking_question_ids)} 的答案、科学性、设问边界和评分口径；"
                            "修正前不得展示推断难度，也不得把该题计入整卷均值。"
                        )
                    break
        teacher_priorities.append({
            "title": "阻断题先处理",
            "summary": (
                f"{blocking_action}{block_reason}"
            ),
            "stance": "risk",
            "id": "blocking_questions",
        })
    teacher_priorities.extend(summarize_teacher_priorities(
        risk_question_ids=risk_question_ids,
        attention_question_ids=attention_question_ids,
        weak_dimensions=_teacher_weak_dimensions(rows),
        use_case="阶段诊断卷",
    ))
    return {
        "lead_judgment": lead,
        "overall_verdict": classify_overall_verdict(
            high_risk_count=high_count,
            language_risk_count=language_risk_count,
            scientific_risk_count=scientific_risk_count,
            student_fit_level=student_fit["fit_level"],
            review_candidate_count=len(priority_rows),
        ),
        "teacher_priorities": teacher_priorities,
        "student_fit": student_fit,
        "evidence_scale": {
            "questions": _as_dict(report_data.get("exam_info")).get("total_questions", len(rows)),
            "scoring_units": fine_summary.get("total_seus", _as_dict(report_data.get("fine_grained_summary")).get("total_seus", 0)),
            "diagnostic_units": fine_summary.get("total_dus", _as_dict(report_data.get("fine_grained_summary")).get("total_dus", 0)),
            "reviewed_risk_items": len(priority_rows),
            "blocked_items": len(blocking_rows),
        },
        "blocking_questions": blocking_question_ids,
        "big_calls": calls[:5],
    }


def _build_at_a_glance(
    exam: Dict,
    report_data: Dict,
    metadata: Dict,
    questions: List[Dict],
    fine_exhibits: Dict | None = None,
) -> List[Dict]:
    metrics = _as_dict(report_data.get("metrics"))
    gradient = _as_dict(report_data.get("difficulty_gradient"))
    unavailable = _as_list(gradient.get("unavailable_questions"))
    fine = _as_dict(_as_dict(fine_exhibits).get("summary")) or _as_dict(report_data.get("fine_grained_summary"))
    llm_counts = _as_dict(metadata.get("llm_call_counts"))
    difficulty_interpretation = "用于判断整卷压力水平和区分度来源。"
    if unavailable:
        difficulty_interpretation = (
            f"仅统计已通过难度评估的 {max(len(questions) - len(unavailable), 0)} 题；"
            f"{_q_label_list(unavailable)} 已阻断，不纳入均值。"
        )
    return [
        {
            "metric": "题目数量",
            "value": str(exam.get("total_questions", len(questions))),
            "interpretation": "本次诊断覆盖全卷题目。",
            "evidence_ref": "exam_info.total_questions",
        },
        {
            "metric": "平均难度",
            "value": _format_num(metrics.get("avg_difficulty"), 2),
            "interpretation": difficulty_interpretation,
            "evidence_ref": "metric:avg_difficulty",
        },
        {
            "metric": "采分点 / 误区点",
            "value": f"{fine.get('total_seus', 0)} / {fine.get('total_dus', 0)}",
            "interpretation": "采分点和误区诊断点决定讲评与修订能否落到题目细节。",
            "evidence_ref": "fine_grained_summary",
        },
        {
            "metric": "AI 调用",
            "value": str(_llm_total(llm_counts)),
            "interpretation": "统计题目分析、特征抽取和素养分析的调用覆盖。",
            "evidence_ref": "metadata:llm_call_counts",
        },
    ]


def _build_chapters(
    report_data: Dict,
    rows: List[Dict],
    fine_exhibits: Dict | None = None,
    knowledge_exhibit_rows: List[Dict] | None = None,
) -> List[Dict]:
    metrics = _as_dict(report_data.get("metrics"))
    gradient = _as_dict(report_data.get("difficulty_gradient"))
    knowledge = _as_dict(report_data.get("knowledge"))
    competency = _as_dict(report_data.get("competency"))
    fine = _as_dict(report_data.get("fine_grained_summary"))
    metadata = _as_dict(report_data.get("metadata_quality"))

    high_count = len([row for row in rows if row["risk_level"] == "high"])
    medium_count = len([row for row in rows if row["risk_level"] == "medium"])
    priority_count = len(_priority_review_rows(rows))
    quality_counts = _quality_risk_counts(_as_list(report_data.get("questions")))
    quality_summary = _quality_risk_summary(quality_counts)

    fine_exhibits = _as_dict(fine_exhibits)
    knowledge_exhibit_rows = knowledge_exhibit_rows or _as_list(knowledge.get("top_points"))
    competency_diagnosis = _build_competency_diagnosis(competency, fine_exhibits)
    unavailable_difficulty = _as_list(gradient.get("unavailable_questions"))
    difficulty_notes = "逐题点来自题目与采分点综合难度；前中后三段均值只用于解释整卷走势。"
    if unavailable_difficulty:
        difficulty_notes += f" {_q_label_list(unavailable_difficulty)} 因难度评估阻断未纳入曲线和均值。"
    chapters = [
        {
            "id": "exam_structure",
            "title": "试卷可用性与学情适配",
            "thesis": (
                f"{difficulty_thesis(metrics.get('avg_difficulty'), gradient.get('gradient_type', ''))}"
                " 本章回答这份卷能否直接给当前高三学生使用，以及是否需要拆题、降阶或调整讲评节奏。"
            ),
            "figures": [
                {
                    "id": "difficulty_gradient",
                    "title": "逐题难度曲线定位高压题" if gradient else "逐题难度数据不足",
                    "takeaway": "逐题曲线用于定位具体高压题；三段均值只作为整卷走势背景。",
                    "data": {**gradient, "avg_difficulty": metrics.get("avg_difficulty")},
                    "source": "report_data.difficulty_gradient",
                    "notes": difficulty_notes,
                },
                {
                    "id": "bloom_distribution",
                    "title": "能力层级分布反映高考趋势贴合度",
                    "takeaway": "高阶占比用于判断趋势贴合度，但不是越高越好；需同步核查设问边界、材料负担和评分标准。",
                    "data": metrics.get("bloom_distribution", {}),
                    "source": metrics.get("bloom_distribution_source", "report_data.metrics.bloom_distribution"),
                    "notes": "层级按采分点分值加权统计；高阶口径为分析、评价、创造。",
                },
            ],
            "implications": ["先判断本卷适合整卷测试、分层训练还是拆题讲评，再决定进入正式使用。"],
        },
        {
            "id": "knowledge_competency",
            "title": "知识覆盖与高考趋势适配",
            "thesis": "审题报告不只呈现知识覆盖率，还要判断覆盖结构是否贴合高考趋势、课程目标和本校学生复习进度。",
            "figures": [
                {
                    "id": "knowledge_top_points",
                    "title": "高权重知识点决定复习建议优先级",
                    "takeaway": "权重最高且关联高风险题的知识点应在教学建议中优先解释。",
                    "data": knowledge_exhibit_rows,
                    "source": "fine_grained_exhibits.seu_rows + report_data.knowledge.top_points",
                    "notes": "按题目分值、采分点数量、涉及题数、风险题数和平均能力层级综合排序。",
                },
                {
                    "id": "competency_distribution",
                    "title": "核心素养覆盖诊断定位课程目标缺口",
                    "takeaway": "一级素养只做总览；二级素养和采分点证据用于判断课程目标是否真正落到题目上。",
                    "data": competency_diagnosis,
                    "source": "fine_grained_exhibits.competency_detail_rows",
                    "notes": "一级分布来自报告素养分布；二级明细由采分点标签、知识点和素养权重映射生成，未显式标注时标记为规则推断。",
                },
            ],
            "implications": ["把知识覆盖、素养覆盖和高考趋势放在同一张图里解释；核心素养必须追溯到具体采分点，避免只给一级比例。"],
        },
        {
            "id": "quality_metadata",
            "title": "题目质量风险审查",
            "thesis": (
                f"模型高风险分层：当前有 {high_count} 道高风险题、{medium_count} 道关注题；"
                f"另有 {priority_count} 道人工优先复核题。"
                f"质量审查覆盖科学性、可行性、语言表述、规范性和舆论隐患，自动证据提示：{quality_summary}。"
            ),
            "figures": [
                {
                    "id": "question_risk_distribution",
                    "title": "质量风险分层决定复核顺序",
                    "takeaway": "先处理科学性、可行性、语言表述和舆论隐患，再处理一般性元数据 warning 题。",
                    "data": {
                        "high": high_count,
                        "medium": medium_count,
                        "low": len([row for row in rows if row["risk_level"] == "low"]),
                    },
                    "source": "question_portfolio.risk_level",
                    "notes": "由质量评分、元数据置信度和 warning 共同决定。",
                },
                {
                    "id": "metadata_quality",
                    "title": "数据可信度决定结论能否采信",
                    "takeaway": metadata_status(metadata),
                    "data": metadata,
                    "source": "report_data.metadata_quality",
                    "notes": "报告生成前必须确认题号、分值、题干、答案、解析和分析记录完整。",
                },
            ],
            "implications": ["题目修订优先处理科学性、可行性、语言表述和舆论隐患，再讨论图表展示。"],
        },
    ]
    fine_summary = _as_dict(fine_exhibits.get("summary"))
    if fine_summary.get("total_seus") or fine_summary.get("total_dus"):
        chapters.append({
            "id": "fine_grained_evidence",
            "title": "采分点与误区诊断矩阵",
            "thesis": (
                f"本报告的核心优势不是平均值，而是把 {fine_summary.get('total_seus', 0)} 个采分点"
                f"和 {fine_summary.get('total_dus', 0)} 个误区诊断点转化为题目级审查依据。"
            ),
            "figures": [
                {
                    "id": "fine_grained_heatmap",
                    "title": "题目 × 审题压力热力图",
                    "takeaway": "逐题比较难度、质量、置信度、采分点数量和陷阱强度，定位粗粒度均值掩盖的异常题。",
                    "data": fine_exhibits.get("difficulty_factor_rows", []),
                    "source": "fine_grained_exhibits.difficulty_factor_rows",
                    "notes": "由题目元数据、采分点和误区诊断派生，不新增 AI 调用。",
                },
                {
                    "id": "seu_competency_matrix",
                    "title": "采分点 × 知识点 × 素养矩阵",
                    "takeaway": "按采分权重追踪知识点和核心素养，展示每个分值点到底考什么。",
                    "data": fine_exhibits.get("seu_rows", []),
                    "source": "fine_grained_exhibits.seu_rows",
                    "notes": "采分点用于说明每个得分依据；加权分 = 题目分值 × 分值占比。",
                },
                {
                    "id": "du_trap_map",
                    "title": "学生误区负荷图",
                    "takeaway": "按题目汇总误区数量、平均强度、最高陷阱强度和题目难度，服务于讲评和命题修订。",
                    "data": fine_exhibits.get("du_rows", []),
                    "source": "fine_grained_exhibits.du_rows",
                    "notes": "误区诊断点不参与分值守恒，但决定教学解释价值。",
                },
            ],
            "implications": [
                "报告应从题目组合进入采分点和误区诊断，而不是停留在题目级平均值。",
                "低置信度采分点或高陷阱强度误区应成为人工复核优先级。",
            ],
        })
    return chapters


def _build_question_portfolio(rows: List[Dict]) -> Dict:
    high = [row for row in rows if row["risk_level"] == "high"]
    data_gaps = [row for row in rows if row["risk_level"] == "data_gap"]
    priority_rows = _priority_review_rows(rows)
    thesis = (
        f"模型高风险题集中在 {_question_range_text(row.get('question_id') for row in high)}，应作为第一批复核对象。"
        if high else
        (
            f"{_question_range_text(row.get('question_id') for row in data_gaps)}分析数据不完整，应先补齐分析再判断题目质量。"
            if data_gaps else
            (
            f"当前未发现模型高风险题，但{_question_range_text(row.get('question_id') for row in priority_rows)}"
            "在科学性、表述边界或学情压力上建议进入人工优先复核。"
            if priority_rows else
            "当前未发现模型高风险题，建议抽样复核高分值题、材料复杂题和表述较长题。"
            )
        )
    )
    return {
        "thesis": thesis,
        "rows": rows,
    }


def _question_difficulty_flags(question: Dict) -> List[str]:
    flags = list(_as_list(question.get("difficulty_flags")))
    raw_difficulty = question.get("difficulty")
    if isinstance(raw_difficulty, dict):
        flags.extend(_as_list(raw_difficulty.get("flags")))
    unique_flags: List[str] = []
    for flag in flags:
        if flag and flag not in unique_flags:
            unique_flags.append(str(flag))
    return unique_flags


def _q_label_list(ids: Iterable[Any], limit: int = 8) -> str:
    clean_ids = [qid for qid in ids if qid not in (None, "")]
    shown = clean_ids[:limit]
    text = ", ".join(f"Q{qid}" for qid in shown)
    if len(clean_ids) > limit:
        text += f" 等 {len(clean_ids)} 题"
    return text


def _question_evidence_integrity_trace(question: Dict) -> Dict:
    flags = _question_difficulty_flags(question)
    has_source_excerpt = bool(_question_source_text(question).strip() or question.get("answer"))
    failure_explanations: List[Dict[str, Any]] = []
    if question.get("analysis_failed") or question.get("failure_reason"):
        failure_explanations.append(
            _failure_explanation(question.get("failure_reason") or "analysis_failed", question)
        )
    for flag in flags:
        if (
            str(flag) in FAIL_CLOSED_DIFFICULTY_FLAGS
            or str(flag) in FAILURE_COPY
            or str(flag) in FAILURE_COPY_ALIASES
        ):
            failure_explanations.append(_failure_explanation(str(flag), question))
    for warning in _as_list(question.get("metadata_warnings")):
        explanation = _warning_to_failure_explanation(str(warning), question)
        if explanation:
            failure_explanations.append(explanation)
    trace = {
        "difficulty_flags": flags,
        "difficulty_source": question.get("difficulty_source", ""),
        "difficulty_confidence": question.get("difficulty_confidence", question.get("confidence", 0)),
        "analysis_failed": bool(question.get("analysis_failed")),
        "failure_reason": question.get("failure_reason", ""),
        "source_excerpt_status": "available" if has_source_excerpt else "missing",
        "failure_explanations": _dedupe_failure_explanations(failure_explanations),
    }
    if "score_adjusted_from" in question:
        trace["score_adjusted_from"] = question.get("score_adjusted_from")
        trace["score_adjusted_to"] = question.get("total_score")
        trace["score_adjustment_reason"] = question.get("score_adjustment_reason", "")
    return trace


def _question_source_excerpt(question: Dict, limit: int = 2400) -> Dict[str, Any]:
    text = _question_source_text(question).strip()
    answer = question.get("answer")
    if answer is None and isinstance(question.get("analysis"), dict):
        answer = question.get("analysis", {}).get("answer")
    answer_text = "" if answer is None else str(answer).strip()
    return {
        "status": "available" if text or answer_text else "missing",
        "question_text": text[:limit],
        "answer": answer_text[:1200],
        "truncated": len(text) > limit or len(answer_text) > 1200,
    }


def _build_evidence_integrity(
    report_data: Dict,
    questions: List[Dict],
    fine_exhibits: Dict,
    insights: Dict | None = None,
) -> Dict:
    metadata = _as_dict(report_data.get("metadata_quality"))
    knowledge = _as_dict(report_data.get("knowledge"))
    insights = _as_dict(insights)
    grounding_checks = _as_list(insights.get("_grounding_checks"))
    grounding_status = str(insights.get("_grounding_status") or "").strip()
    seu_rows = _as_list(fine_exhibits.get("seu_rows"))
    competency_rows = _as_list(fine_exhibits.get("competency_evidence_rows"))
    allocation_counts = Counter(row.get("allocation_source") or "unknown" for row in seu_rows)
    competency_source_counts = Counter(row.get("source") or "unknown" for row in competency_rows)
    difficulty_fallback_questions = sorted({
        question.get("id")
        for question in questions
        if "big_question_fallback" in _question_difficulty_flags(question)
    })
    missing_purpose_questions = _as_list(metadata.get("missing_purpose_questions"))
    blocked_questions = _as_list(metadata.get("blocked_questions"))
    evidence_gap_questions = _as_list(metadata.get("evidence_gap_questions"))
    retry_questions = _as_list(metadata.get("retry_questions"))
    missing_purpose_ids = sorted({
        item.get("id")
        for item in missing_purpose_questions
        if isinstance(item, dict) and item.get("id") not in (None, "")
    })
    blocked_ids = sorted({
        item.get("id")
        for item in blocked_questions
        if isinstance(item, dict) and item.get("id") not in (None, "")
    })
    evidence_gap_ids = sorted({
        item.get("id")
        for item in evidence_gap_questions
        if isinstance(item, dict) and item.get("id") not in (None, "")
    })
    structure_warning_ids = sorted({
        question.get("id")
        for question in questions
        if _as_list(question.get("structure_warnings")) and question.get("id") not in (None, "")
    })
    difficulty_review_ids = sorted({
        question.get("id")
        for question in questions
        if _as_list(question.get("difficulty_review_warnings")) and question.get("id") not in (None, "")
    })
    score_adjustment_ids = sorted({
        question.get("id")
        for question in questions
        if "score_adjusted_from" in question and question.get("id") not in (None, "")
    })
    question_text_missing_ids = [q.get("id") for q in questions if not q.get("question_text")]
    answer_missing_ids = [q.get("id") for q in questions if not q.get("answer")]
    question_text_missing_count = int(_num(metadata.get("question_text_missing_count"), len(question_text_missing_ids)))
    answer_missing_count = int(_num(metadata.get("answer_missing_count"), len(answer_missing_ids)))
    knowledge_unmapped_count = int(_num(knowledge.get("unmapped_count"), 0))
    knowledge_total_count = int(_num(knowledge.get("total_knowledge_points"), 0))
    knowledge_unmapped_points = _as_list(knowledge.get("unmapped_points"))
    knowledge_non_textbook_count = int(_num(knowledge.get("non_textbook_count"), 0))
    knowledge_non_textbook_points = _as_list(knowledge.get("non_textbook_points"))

    items: List[Dict] = []
    if grounding_checks:
        first_grounding = _as_dict(grounding_checks[0])
        status = str(first_grounding.get("status") or grounding_status or "unknown")
        score = _num(first_grounding.get("support_score"), 0.0)
        threshold = _num(first_grounding.get("threshold"), 0.6)
        severity = "info" if status == "ok" and score >= threshold else "warning"
        items.append({
            "id": "report_grounding",
            "title": "整卷结论证据校验",
            "value": f"{score:.2f}",
            "detail": (
                f"证据核查状态 {status}，阈值 {threshold:.2f}；"
                f"声明数={int(_num(first_grounding.get('claim_count'), 0))}，"
                f"引用证据块={int(_num(first_grounding.get('cited_chunk_count'), 0))}。"
                "低于阈值时，整卷总结需要人工复核。"
            ),
            "severity": severity,
        })
    for event in _as_list(insights.get("_report_failure_events")):
        if isinstance(event, dict):
            items.append({
                "id": f"report_event_{len(items) + 1}",
                "title": "报告生成环节失败",
                "value": str(event.get("stage") or "unknown"),
                "detail": str(event.get("reason") or ""),
                "severity": str(event.get("severity") or "warning"),
            })
    if difficulty_fallback_questions:
        items.append({
            "title": "大题结构化回退",
            "value": f"{len(difficulty_fallback_questions)}题",
            "detail": _q_label_list(difficulty_fallback_questions),
            "severity": "blocked",
        })
    if blocked_questions:
        items.append({
            "title": "难度评估阻断",
            "value": f"{len(blocked_questions)}项",
            "detail": f"涉及 {_q_label_list(blocked_ids)}；这些题不得展示推断难度。",
            "severity": "blocked",
        })
    if evidence_gap_questions:
        items.append({
            "title": "证据链异常",
            "value": f"{len(evidence_gap_questions)}项",
            "detail": f"涉及 {_q_label_list(evidence_gap_ids)}；需补齐误区诊断或材料描述后再定稿。",
            "severity": "blocked",
        })
    if structure_warning_ids or difficulty_review_ids:
        details = []
        if structure_warning_ids:
            details.append(f"题面结构：{_q_label_list(structure_warning_ids)}")
        if difficulty_review_ids:
            details.append(f"难度证据：{_q_label_list(difficulty_review_ids)}")
        items.append({
            "title": "题面/难度证据警告",
            "value": f"{len(set(structure_warning_ids + difficulty_review_ids))}题",
            "detail": "；".join(details) + "；这些题必须显性复核，不能按稳定题处理。",
            "severity": "warning",
        })
    if score_adjustment_ids:
        items.append({
            "title": "分值规范化提示",
            "value": f"{len(score_adjustment_ids)}题",
            "detail": (
                f"涉及 {_q_label_list(score_adjustment_ids)}；原始分值与试卷总分不一致，"
                "系统仅做多选题分值规范化并在此显性标记，需回看原卷确认。"
            ),
            "severity": "warning",
        })
    if question_text_missing_count or answer_missing_count:
        items.append({
            "title": "原题/答案摘录缺失",
            "value": f"{question_text_missing_count} / {answer_missing_count}",
            "detail": "报告数据未带入原题或答案摘录，结论可用但复核时需回看原卷。",
            "severity": "warning",
        })
    if knowledge_unmapped_count:
        examples = "、".join(
            str(item.get("name"))
            for item in knowledge_unmapped_points[:5]
            if isinstance(item, dict) and item.get("name")
        )
        detail = (
            f"{knowledge_unmapped_count}/{knowledge_total_count} 个知识点未完成教材标准映射；"
            "教材覆盖分布仍可参考，但这些知识点需补充同义词或标准节点。"
        )
        if examples:
            detail += f" 示例：{examples}。"
        items.append({
            "id": "knowledge_mapping_gap",
            "title": "知识点标准映射缺口",
            "value": f"{knowledge_unmapped_count}项",
            "detail": detail,
            "severity": "warning",
        })
    if knowledge_non_textbook_count:
        examples = "、".join(
            str(item.get("name"))
            for item in knowledge_non_textbook_points[:5]
            if isinstance(item, dict) and item.get("name")
        )
        detail = (
            f"{knowledge_non_textbook_count} 个能力/方法表述未计入教材章节覆盖率；"
            "这些内容应在核心素养或讲评建议中解释，不应硬塞进教材知识点统计。"
        )
        if examples:
            detail += f" 示例：{examples}。"
        items.append({
            "id": "knowledge_non_textbook_scope",
            "title": "能力/方法项未计入教材映射",
            "value": f"{knowledge_non_textbook_count}项",
            "detail": detail,
            "severity": "info",
        })
    inferred_allocations = int(allocation_counts.get("inferred", 0))
    rule_inferred = int(competency_source_counts.get("rule_inferred", 0))
    default_inferred = int(competency_source_counts.get("default_inferred", 0))
    legacy_fallback_subtypes = int(competency_source_counts.get("fallback", 0))
    inferred_subtypes = rule_inferred + default_inferred + legacy_fallback_subtypes
    if inferred_allocations or inferred_subtypes:
        items.append({
            "title": "采分点/二级素养规则推断",
            "value": f"{inferred_allocations} / {inferred_subtypes}",
            "detail": (
                f"采分点分值推断 {inferred_allocations} 项；"
                f"二级素养关键词命中 {rule_inferred} 项，默认规则归类 {default_inferred + legacy_fallback_subtypes} 项。"
                "这些是证据口径提示，不是题目数量，也不等同于人工标注。"
            ),
            "severity": "info",
        })
    if missing_purpose_questions:
        items.append({
            "title": "AI 调用链缺口",
            "value": f"{len(missing_purpose_questions)}项",
            "detail": f"涉及 {_q_label_list(missing_purpose_ids)}，需要补齐后再作最终定稿。",
            "severity": "warning",
        })

    question_by_id = {question.get("id"): question for question in questions if isinstance(question, dict)}
    failure_explanations: List[Dict[str, Any]] = []
    for question in questions:
        failure_explanations.extend(_question_evidence_integrity_trace(question).get("failure_explanations", []))
    for item in blocked_questions:
        if isinstance(item, dict):
            qid = item.get("id")
            failure_explanations.append(
                _failure_explanation(item.get("reason") or "difficulty_missing", question_by_id.get(qid), qid)
            )
    for item in evidence_gap_questions:
        if isinstance(item, dict):
            qid = item.get("id")
            failure_explanations.append(
                _failure_explanation(item.get("reason") or "diagnostic_units_missing", question_by_id.get(qid), qid)
            )
    for item in missing_purpose_questions:
        if isinstance(item, dict):
            qid = item.get("id")
            purpose = item.get("purpose") or "unknown"
            explanation = _failure_explanation("missing_llm_calls", question_by_id.get(qid), qid)
            explanation["reason"] = f"{purpose} 调用记录缺失，无法追溯该结论的提示词和解析过程。"
            explanation["display"] = (
                f"失败阶段：{explanation['stage']}；原因：{explanation['reason']}；"
                f"影响：{explanation['impact']}；处理：{explanation['action']}"
            )
            failure_explanations.append(explanation)
    for item in retry_questions:
        if isinstance(item, dict):
            qid = item.get("id")
            explanation = _failure_explanation("llm_retry", question_by_id.get(qid), qid)
            if item.get("purpose"):
                explanation["reason"] = f"{item.get('purpose')} 发生过重试。"
                explanation["display"] = (
                    f"失败阶段：{explanation['stage']}；原因：{explanation['reason']}；"
                    f"影响：{explanation['impact']}；处理：{explanation['action']}"
                )
            failure_explanations.append(explanation)
    for item in _as_list(metadata.get("score_issue_questions")):
        if isinstance(item, dict):
            qid = item.get("id")
            failure_explanations.append(
                _failure_explanation(item.get("reason") or "missing_score", question_by_id.get(qid), qid)
            )
    for item in _as_list(metadata.get("failure_events")):
        if isinstance(item, dict):
            qid = item.get("question_id")
            stage = {
                "exam_statistics": "整卷统计",
                "score_extraction": "分值抽取",
                "difficulty": "难度评估",
            }.get(str(item.get("stage") or ""), str(item.get("stage") or "数据质量检查"))
            failure_explanations.append(
                _failure_explanation(
                    item.get("reason") or "analysis_failed",
                    question_by_id.get(qid),
                    qid,
                    stage=stage,
                    severity=item.get("severity"),
                    raw_reason=item.get("reason"),
                    source="failure_events",
                )
            )
    for item in _as_list(metadata.get("warning_questions")):
        if isinstance(item, dict):
            qid = item.get("id")
            for warning in _as_list(item.get("warnings")):
                explanation = _warning_to_failure_explanation(str(warning), question_by_id.get(qid), qid)
                if explanation:
                    failure_explanations.append(explanation)
    failure_explanations = _dedupe_failure_explanations(failure_explanations)

    return {
        "difficulty_fallback_questions": difficulty_fallback_questions,
        "blocked_questions": blocked_questions,
        "evidence_gap_questions": evidence_gap_questions,
        "structure_warning_questions": structure_warning_ids,
        "difficulty_review_questions": difficulty_review_ids,
        "score_adjustment_questions": score_adjustment_ids,
        "retry_questions": retry_questions,
        "question_text_missing_count": question_text_missing_count,
        "answer_missing_count": answer_missing_count,
        "question_text_missing_ids": question_text_missing_ids,
        "answer_missing_ids": answer_missing_ids,
        "knowledge_unmapped_count": knowledge_unmapped_count,
        "knowledge_total_count": knowledge_total_count,
        "knowledge_unmapped_points": knowledge_unmapped_points,
        "knowledge_non_textbook_count": knowledge_non_textbook_count,
        "knowledge_non_textbook_points": knowledge_non_textbook_points,
        "grounding_status": grounding_status,
        "grounding_checks": grounding_checks,
        "missing_purpose_questions": missing_purpose_questions,
        "source_counts": {
            "seu_allocation": dict(allocation_counts),
            "competency_subtype": dict(competency_source_counts),
        },
        "failure_explanations": failure_explanations,
        "items": items,
    }


def _deep_dive_priority(question: Dict, row: Dict) -> tuple[float, int]:
    difficulty = _num(row.get("difficulty"), _num(question.get("difficulty")))
    pressure = _num(row.get("pressure_index"))
    qid = question.get("id")
    flags = _question_difficulty_flags(question)
    issue = f"{row.get('primary_issue', '')} {question.get('quality_scientific', '')} {question.get('quality_language', '')}"
    risk_bonus = {"high": 18, "data_gap": 12, "medium": 8, "low": 0}.get(row.get("risk_level", "low"), 0)
    flag_bonus = 95 if any(flag in FAIL_CLOSED_DIFFICULTY_FLAGS for flag in flags) else (8 if flags else 0)
    severe_terms = ("科学性", "不唯一", "矛盾", "不严谨", "重复", "边界", "答案", "表述")
    severe_bonus = 10 if any(term in issue for term in severe_terms) else 0
    hard_bonus = 18 if difficulty >= 8.5 else 0
    tail_bonus = _num(qid) * 0.25 if isinstance(qid, int) else 0
    score = difficulty * 10 + pressure * 0.25 + risk_bonus + flag_bonus + severe_bonus + hard_bonus + tail_bonus
    return (-score, int(qid) if isinstance(qid, int) else 999)


def _build_deep_dives(questions: List[Dict], rows: List[Dict]) -> List[Dict]:
    by_id = {row["question_id"]: row for row in rows}
    ranked_questions = sorted(
        _sorted_questions(questions),
        key=lambda q: _deep_dive_priority(q, by_id.get(q.get("id"), {})),
    )
    dives = []
    for question in ranked_questions[:8]:
        qid = question.get("id")
        row = by_id.get(qid, {})
        dives.append({
            "question_id": qid,
            "headline": f"Q{qid} {row.get('quality_level', '未见显性问题')}：{row.get('primary_issue', '需复核')}",
            "diagnosis": row.get("primary_issue", primary_issue(question)),
            "seu_breakdown": _question_scoring_units(question),
            "du_diagnostics": _question_diagnostic_units(question),
            "su_context": _question_stimulus_units(question),
            "revision_plan": [row.get("action", action_for_question(question))],
            "metadata_trace": {
                "purposes": _as_list(question.get("metadata_call_purposes")),
                "confidence": question.get("metadata_confidence", 0),
                "warnings": _as_list(question.get("metadata_warnings")),
            },
            "source_excerpt": _question_source_excerpt(question),
            "evidence_integrity": _question_evidence_integrity_trace(question),
        })
    return dives


def _build_methodology(metadata: Dict, questions: List[Dict], evidence_integrity: Dict | None = None) -> Dict:
    llm_counts = _as_dict(metadata.get("llm_call_counts"))
    traced_counts: Dict[str, int] = {}
    for question in questions:
        for purpose in _as_list(question.get("metadata_call_purposes")):
            traced_counts[purpose] = traced_counts.get(purpose, 0) + 1

    purpose_counts: Dict[str, int] = {}
    for purpose, count in traced_counts.items():
        purpose_counts[purpose] = int(count)
    for purpose, count in llm_counts.items():
        if isinstance(count, (int, float)):
            purpose_counts[purpose] = int(count)

    prompt_inventory = []
    for purpose, count in sorted(purpose_counts.items()):
        contract = _as_dict(PROMPT_CONTRACTS.get(purpose))
        prompt_inventory.append({
            "purpose": purpose,
            "prompt_id": contract.get("prompt_id", f"biology.{purpose}"),
            "prompt": contract.get("prompt", f"Prompt contract for {purpose} is not registered."),
            "analysis_dimensions": _as_list(contract.get("analysis_dimensions")),
            "parsed_fields": _as_list(contract.get("parsed_fields")),
            "records": count,
            "question_traces": traced_counts.get(purpose, 0),
        })

    return {
        "llm_call_summary": {
            "total": sum(purpose_counts.values()),
            "purpose_counts": purpose_counts,
            "question_traced_counts": traced_counts,
        },
        "prompt_inventory": prompt_inventory,
        "parsed_fields": list(PARSED_FIELDS),
        "quality_gates": list(QUALITY_GATES),
        "limitations": list(LIMITATIONS),
        "evidence_integrity": _as_dict(evidence_integrity),
    }


def build_report_product_model(report_data: Dict, insights: Dict | None = None) -> Dict:
    """Build the commercial report model from report aggregate data."""
    report_data = _as_dict(report_data)
    exam = _as_dict(report_data.get("exam_info"))
    questions = _normalize_questions_for_report(exam, _sorted_questions(_as_list(report_data.get("questions"))))
    report_data = _report_data_with_recomputed_difficulty(report_data, questions)
    metadata = _as_dict(report_data.get("metadata_quality"))
    rows = _build_question_rows(questions)
    fine_exhibits = _build_fine_grained_exhibits(questions, rows)
    knowledge_exhibit_rows = _build_knowledge_exhibit_rows(
        _as_dict(report_data.get("knowledge")),
        _as_list(fine_exhibits.get("knowledge_contribution_rows")) or _as_list(fine_exhibits.get("seu_rows")),
    )
    evidence_integrity = _build_evidence_integrity(report_data, questions, fine_exhibits, insights)
    findings = _build_findings(report_data, rows, fine_exhibits, knowledge_exhibit_rows)

    return {
        "cover": _build_cover(exam),
        "review_positioning": _build_review_positioning(),
        "credibility": _build_credibility(exam, questions, metadata),
        "executive_summary": _build_executive_summary(report_data, rows, findings, fine_exhibits),
        "at_a_glance": _build_at_a_glance(exam, report_data, metadata, questions, fine_exhibits),
        "chapters": _build_chapters(report_data, rows, fine_exhibits, knowledge_exhibit_rows),
        "fine_grained_exhibits": fine_exhibits,
        "evidence_integrity": evidence_integrity,
        "findings": findings,
        "question_portfolio": _build_question_portfolio(rows),
        "deep_dives": _build_deep_dives(questions, rows),
        "methodology": _build_methodology(metadata, questions, evidence_integrity),
    }
