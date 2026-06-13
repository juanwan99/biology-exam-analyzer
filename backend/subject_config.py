"""学科配置中枢 — 九学科核心素养框架与元信息的单一事实源。

设计原则：
- 素养维度名称与 prompts/{subject}/competency_prompt.txt 的 LLM 输出键严格一致
  （2026-06-13 已逐科校验匹配 2017 版 2020 修订课标）。任何改动须两边同步。
- 维度数各科不同（语文/英语/物理/政治/地理 4 维、化学/历史 5 维、数学 6 维、生物 4 维）。
- 全部为内存常量，零文件 IO，热路径安全。
- 未知/缺省学科一律降级为 biology（保护存量数据与旧调用）。
"""
from __future__ import annotations

# subject key → 核心素养维度（顺序即报告/雷达图展示顺序）
SUBJECT_COMPETENCIES: dict[str, list[str]] = {
    "chinese":   ["语言建构与运用", "思维发展与提升", "审美鉴赏与创造", "文化传承与理解"],
    "math":      ["数学抽象", "逻辑推理", "数学建模", "直观想象", "数学运算", "数据分析"],
    "english":   ["语言能力", "文化意识", "思维品质", "学习能力"],
    "physics":   ["物理观念", "科学思维", "科学探究", "科学态度与责任"],
    "chemistry": ["宏观辨识与微观探析", "变化观念与平衡思想", "证据推理与模型认知",
                  "科学探究与创新意识", "科学态度与社会责任"],
    "biology":   ["生命观念", "科学思维", "科学探究", "社会责任"],
    "politics":  ["政治认同", "科学精神", "法治意识", "公共参与"],
    "history":   ["唯物史观", "时空观念", "史料实证", "历史解释", "家国情怀"],
    "geography": ["人地协调观", "综合思维", "区域认知", "地理实践力"],
}

# subject key → 中文学科名（前端展示 / 报告标题 / prompt 角色）
SUBJECT_NAMES: dict[str, str] = {
    "chinese": "语文", "math": "数学", "english": "英语", "physics": "物理",
    "chemistry": "化学", "biology": "生物", "politics": "思想政治",
    "history": "历史", "geography": "地理",
}

DEFAULT_SUBJECT = "biology"


def normalize_subject(subject: str | None) -> str:
    """归一化学科 key；未知/空值降级为默认（biology），保护存量数据与旧调用。"""
    if not subject:
        return DEFAULT_SUBJECT
    key = str(subject).strip().lower()
    return key if key in SUBJECT_COMPETENCIES else DEFAULT_SUBJECT


def get_competency_dims(subject: str | None) -> list[str]:
    """返回该学科的核心素养维度列表（副本，防外部篡改常量）。"""
    return list(SUBJECT_COMPETENCIES[normalize_subject(subject)])


def get_subject_name(subject: str | None) -> str:
    """返回中文学科名。"""
    return SUBJECT_NAMES[normalize_subject(subject)]


def list_subjects() -> list[dict[str, str | int]]:
    """前端学科选择器数据源：[{key, name, dim_count}, ...]，按习惯学科顺序。"""
    order = ["chinese", "math", "english", "physics", "chemistry",
             "biology", "politics", "history", "geography"]
    return [
        {"key": k, "name": SUBJECT_NAMES[k], "dim_count": len(SUBJECT_COMPETENCIES[k])}
        for k in order
    ]


def is_valid_subject(subject: str | None) -> bool:
    return bool(subject) and str(subject).strip().lower() in SUBJECT_COMPETENCIES
