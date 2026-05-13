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
    total_score: Optional[int] = None
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

def validate_llm_output(data: dict, schema_class: type, context: str = "") -> tuple:
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
        try:
            validated = schema_class.model_construct(**data)
            return validated.model_dump(), 0.5, errors
        except Exception:
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
