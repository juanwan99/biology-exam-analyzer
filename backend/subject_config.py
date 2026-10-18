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

# subject key → 课标全称（报告依据署名，2017年版2020年修订）
SUBJECT_CURRICULA: dict[str, str] = {
    "chinese": "普通高中语文课程标准（2017年版2020年修订）",
    "math": "普通高中数学课程标准（2017年版2020年修订）",
    "english": "普通高中英语课程标准（2017年版2020年修订）",
    "physics": "普通高中物理课程标准（2017年版2020年修订）",
    "chemistry": "普通高中化学课程标准（2017年版2020年修订）",
    "biology": "普通高中生物学课程标准（2017年版2020年修订）",
    "politics": "普通高中思想政治课程标准（2017年版2020年修订）",
    "history": "普通高中历史课程标准（2017年版2020年修订）",
    "geography": "普通高中地理课程标准（2017年版2020年修订）",
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


def get_curriculum_name(subject: str | None) -> str:
    """返回该学科课标全称（报告依据署名用）。"""
    return SUBJECT_CURRICULA[normalize_subject(subject)]


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


# 素养聚合结果（competency_summary / competency.distribution）里除维度键外还混入的元键，
# 数据驱动提取维度时需排除。
_COMPETENCY_META_KEYS = frozenset({
    "primary_distribution",
    "seu_primary_distribution",
    "involved_distribution",
})

# 生物四维 → 既有英文 slug（雷达图 CSS class / data-active）。
# 保证生物零回归（既有测试断言这些 slug），其余维度走 dim{index} 兜底。
_LEGACY_COMPETENCY_SLUGS = {
    "生命观念": "life-concept",
    "科学思维": "scientific-thinking",
    "科学探究": "scientific-inquiry",
    "社会责任": "social-responsibility",
}


def competency_dims_from_distribution(distribution: Any,
                                      subject: str | None = None) -> list[str]:
    """从素养分布字典（competency_summary）按数据实际维度提取维度名（保持出现顺序）。

    维度判定：值为 dict 且含 '占比' 或 '总权重'（真实维度条目），排除 primary_distribution
    等元键。无可用维度时回退 get_competency_dims(subject)，保证渲染不空。
    """
    dims: list[str] = []
    if isinstance(distribution, dict):
        for key, value in distribution.items():
            if key in _COMPETENCY_META_KEYS:
                continue
            if isinstance(value, dict) and ("占比" in value or "总权重" in value):
                dims.append(str(key))
    if dims:
        return dims
    return get_competency_dims(subject)


def competency_slug(name: str, index: int = 0) -> str:
    """素养维度名 → 稳定 CSS slug。生物四维用既有英文 slug（零回归），其余用 dim{index}。"""
    return _LEGACY_COMPETENCY_SLUGS.get(str(name), f"dim{index}")
