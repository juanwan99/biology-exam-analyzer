"""LLM 输出 Schema 校验 — 4 条 JSON 出口的 Pydantic 模型。

校验失败不阻断流程，而是标记 extraction_confidence 和 validation_errors。
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator
from logger import get_logger

logger = get_logger()


# ── 1. 主分析（question_analyzer）────────────────────────────────

class AnalysisResult(BaseModel):
    knowledge_points: List[str] = Field(default_factory=list, min_length=0)
    detailed_analysis: str = ""
    difficulty: str = "中等"
    common_mistakes: List[str] = Field(default_factory=list)
    answer: str = ""
    total_score: int = 0
    bloom_level: Optional[int] = Field(default=None, ge=1, le=6)
    competency: Optional[Dict[str, Any]] = None
    sub_questions: Optional[List[Dict]] = None
    option_difficulty_breakdown: Optional[Dict] = None

    class Config:
        extra = "allow"


# ── 2. 难度特征（feature_extractor）─────────────────────────────

class FeatureResult(BaseModel):
    working_memory: int = Field(default=3, ge=1, le=5)
    reasoning_steps: int = Field(default=4, ge=1, le=10)
    chain_coupling: int = Field(default=2, ge=1, le=3)
    trap_density: int = Field(default=2, ge=1, le=3)
    novelty: int = Field(default=2, ge=1, le=3)
    knowledge_breadth: int = Field(default=2, ge=1, le=3)
    bloom: int = Field(default=3, ge=1, le=6)
    info_density: int = Field(default=2, ge=1, le=3)
    representation_complexity: int = Field(default=1, ge=1, le=3)

    class Config:
        extra = "allow"


# ── 3. 素养分析（competency_analyzer）───────────────────────────

class CompetencyDim(BaseModel):
    涉及: bool = False
    具体维度: List[str] = Field(default_factory=list)
    权重: float = Field(default=0, ge=0, le=1)
    分析说明: str = ""

    class Config:
        extra = "allow"


class CompetencyResult(BaseModel):
    生命观念: CompetencyDim = Field(default_factory=CompetencyDim)
    科学思维: CompetencyDim = Field(default_factory=CompetencyDim)
    科学探究: CompetencyDim = Field(default_factory=CompetencyDim)
    社会责任: CompetencyDim = Field(default_factory=CompetencyDim)
    primary_competency: str = ""
    competency_level: str = ""

    class Config:
        extra = "allow"


# ── 4. 报告分析（report_insights）───────────────────────────────

class InsightsResult(BaseModel):
    overall_assessment: str = ""
    recommendations: List[Any] = Field(default_factory=list)
    difficulty_analysis: str = ""
    knowledge_analysis: str = ""
    competency_analysis: str = ""
    bloom_analysis: str = ""

    class Config:
        extra = "allow"


# ── 校验入口 ────────────────────────────────────────────────────

def validate_llm_output(
    data: dict,
    schema_class: type,
    context: str = "",
    allow_construct: bool = False,
) -> tuple:
    """校验 LLM JSON 输出，返回 (validated_data, confidence, errors)。

    - confidence: 1.0 = 完全通过, 0.5 = 有字段修正, 0.0 = 完全失败
    - errors: 校验错误列表（空 = 无错误）
    """
    try:
        validated = schema_class.model_validate(data)
        return validated.model_dump(), 1.0, []
    except Exception as e:
        errors = []
        if hasattr(e, "errors"):
            errors = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
        else:
            errors = [str(e)]
        logger.warning(f"[Schema] {context} 校验失败 ({len(errors)} 个错误): {errors[:3]}")
        if allow_construct:
            try:
                validated = schema_class.model_construct(**data)
                return validated.model_dump(), 0.5, errors
            except Exception:
                pass
        return data, 0.0, errors


# ── 一致性检查（L2 confidence）──────────────────────────────────

def check_consistency(features: dict) -> tuple:
    """检查特征内部一致性，返回 (consistency_score, flags)。"""
    flags = []
    score = 1.0

    bloom = features.get("bloom", 3)
    steps = features.get("reasoning_steps", 4)
    wm = features.get("working_memory", 3)

    if bloom >= 5 and steps <= 2:
        flags.append("bloom_high_steps_low")
        score -= 0.2
    if bloom <= 2 and steps >= 8:
        flags.append("bloom_low_steps_high")
        score -= 0.2
    if wm >= 4 and steps <= 2:
        flags.append("wm_high_steps_low")
        score -= 0.15
    if wm <= 2 and steps >= 7:
        flags.append("wm_low_steps_high")
        score -= 0.15

    return max(0.0, score), flags


# ── 5. 细粒度分析（SEU/DU/SU typed units）───────────────────────

class KnowledgeLink(BaseModel):
    knowledge_point: str
    share: float = Field(ge=0.0, le=1.0)  # 在 SEU 中占的比例


COMPETENCY_DIMS = ["生命观念", "科学思维", "科学探究", "社会责任"]


class CompetencyLink(BaseModel):
    primary: str = ""
    weight: float = Field(default=1.0, ge=0.0, le=1.0)


class ScoringEvidenceUnit(BaseModel):
    """采分证据单元 — 承载正向分值归因"""
    seu_id: str
    label: str
    score_share: float = Field(ge=0.0, le=1.0)
    allocation_source: str = "inferred"
    allocation_confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    knowledge_links: List[KnowledgeLink]
    bloom_level: int = Field(default=3, ge=1, le=6)
    competency: Optional[CompetencyLink] = None
    competency_weights: Optional[Dict[str, float]] = None
    difficulty_estimate: float = Field(default=5.0, ge=0.0, le=10.0)
    reasoning_brief: str = ""

    def get_competency_weights(self) -> Dict[str, float]:
        """获取四维素养权重（兼容新旧格式）。"""
        if self.competency_weights:
            w = {d: self.competency_weights.get(d, 0.0) for d in COMPETENCY_DIMS}
            total = sum(w.values())
            if total > 0:
                return {k: v / total for k, v in w.items()}
            return {d: 0.25 for d in COMPETENCY_DIMS}
        if self.competency and self.competency.primary:
            w = {d: 0.0 for d in COMPETENCY_DIMS}
            if self.competency.primary in w:
                w[self.competency.primary] = self.competency.weight
                remaining = 1.0 - self.competency.weight
                others = [d for d in COMPETENCY_DIMS if d != self.competency.primary]
                for d in others:
                    w[d] = remaining / len(others)
            return w
        return {d: 0.25 for d in COMPETENCY_DIMS}


class DiagnosticUnit(BaseModel):
    """诊断干扰单元 — 承载干扰项/误区分析，不参与分值聚合"""
    du_id: str
    option_or_trap: str  # "A"/"B" 或 "trap_1"
    distractor_type: str = "misconception"  # misconception/partial_truth/calculation_trap/reading_trap
    misconception: str = ""
    trap_strength: int = Field(default=2, ge=1, le=3)
    knowledge_boundary: str = ""
    if_selected_means: List[str] = []


class StimulusUnit(BaseModel):
    """情境/过程单元 — 承载材料、图表、共享情境"""
    su_id: str
    stimulus_type: str = "text"  # text/chart/table/pedigree/device/flowchart/multi
    complexity: int = Field(default=1, ge=1, le=3)
    is_core: bool = False
    description: str = ""  # ≤30字


class FineGrainedResult(BaseModel):
    """细粒度分析结果 — 三类 units + 向后兼容字段"""
    scoring_units: List[ScoringEvidenceUnit]
    diagnostic_units: List[DiagnosticUnit] = []
    stimulus_units: List[StimulusUnit] = []
    answer: str = ""
    total_score: int = 0
    detailed_analysis: str = ""
    # 向后兼容字段（由 compute_summary_from_units 派生）
    knowledge_points: List[str] = []
    common_mistakes: List[str] = []
    difficulty: str = "中等"

    class Config:
        extra = "allow"

    @model_validator(mode="after")
    def check_score_conservation(self):
        """分值守恒：所有 SEU 的 score_share 加总必须 ≈ 1.0"""
        if self.scoring_units:
            total = sum(s.score_share for s in self.scoring_units)
            if abs(total - 1.0) > 0.02:
                raise ValueError(f"score_share sum={total:.3f}, expected 1.0")
        return self


# ── 细粒度分析辅助函数 ──────────────────────────────────────────

def validate_score_conservation(result: FineGrainedResult, total_score: float) -> tuple:
    """分值守恒硬检查。返回 (is_valid, errors)"""
    errors = []
    # 检查 SEU score_share 总和
    share_sum = sum(s.score_share for s in result.scoring_units)
    if abs(share_sum - 1.0) > 0.02:
        errors.append(f"score_share sum={share_sum:.3f}, expected 1.0")
    # 检查每个 SEU 的 knowledge_links share 总和
    for seu in result.scoring_units:
        kl_sum = sum(kl.share for kl in seu.knowledge_links)
        if abs(kl_sum - 1.0) > 0.02:
            errors.append(f"{seu.seu_id}: knowledge_links share sum={kl_sum:.3f}")
    return (len(errors) == 0, errors)


def compute_summary_from_units(fg: FineGrainedResult) -> dict:
    """从 typed units 派生旧格式字段。纯 Python，无 LLM。"""
    # knowledge_points: 按 score_share * kl.share 加权，取前 5
    _ABILITY_BLACKLIST = {"数据处理", "数据分析", "实验设计", "信息获取", "信息处理",
                          "逻辑推理", "模型建构", "批判性思维", "科学探究能力"}
    kp_scores = {}
    for seu in fg.scoring_units:
        for kl in seu.knowledge_links:
            kp = kl.knowledge_point
            if kp in _ABILITY_BLACKLIST:
                continue
            kp_scores[kp] = kp_scores.get(kp, 0) + seu.score_share * kl.share
    sorted_kps = sorted(kp_scores.items(), key=lambda x: -x[1])
    knowledge_points = [kp for kp, _ in sorted_kps[:5]]

    # common_mistakes: 从 DU 提取
    common_mistakes = [du.misconception for du in fg.diagnostic_units if du.misconception][:3]

    # primary_competency: 从 SEU 四维权重加权
    comp_weights = {d: 0.0 for d in COMPETENCY_DIMS}
    for seu in fg.scoring_units:
        w = seu.get_competency_weights()
        for d in COMPETENCY_DIMS:
            comp_weights[d] += seu.score_share * w.get(d, 0)
    primary_comp = max(comp_weights, key=comp_weights.get) if any(comp_weights.values()) else "科学思维"

    # bloom: 分值加权
    bloom_sum = sum(seu.bloom_level * seu.score_share for seu in fg.scoring_units)
    bloom = round(bloom_sum)

    # bloom_distribution: 按 SEU bloom_level 计数
    bloom_dist = {}
    bloom_labels = {1: "识记", 2: "理解", 3: "应用", 4: "分析", 5: "评价", 6: "创造"}
    for seu in fg.scoring_units:
        label = bloom_labels.get(seu.bloom_level, "应用")
        bloom_dist[label] = bloom_dist.get(label, 0) + 1

    # competency details: 四维素养权重加权聚合
    all_comps = {d: 0.0 for d in COMPETENCY_DIMS}
    for seu in fg.scoring_units:
        w = seu.get_competency_weights()
        for d in COMPETENCY_DIMS:
            all_comps[d] += seu.score_share * w.get(d, 0)

    # allocation confidence
    avg_conf = sum(s.allocation_confidence for s in fg.scoring_units) / len(fg.scoring_units) if fg.scoring_units else 0

    return {
        "knowledge_points": knowledge_points,
        "common_mistakes": common_mistakes,
        "primary_competency": primary_comp,
        "competency_level": "中" if bloom <= 3 else "高",
        "bloom_level": bloom,
        "bloom_distribution": bloom_dist,
        "competency_details": all_comps,
        "allocation_confidence_avg": round(avg_conf, 2),
        "difficulty": fg.difficulty,
    }
