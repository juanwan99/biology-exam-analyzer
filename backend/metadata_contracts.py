"""Metadata governance contracts for prompt, LLM calls, and question envelopes.

This module is intentionally pure data modeling. It does not call the LLM,
database, or filesystem except when explicitly constructing a PromptSpec from a
prompt file.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _validate_sha256(value: str) -> str:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value.lower()):
        raise ValueError("prompt_hash must be a 64-character sha256 hex digest")
    return value.lower()


class PromptSpec(BaseModel):
    """Immutable registry entry for one prompt contract."""

    model_config = ConfigDict(frozen=True)

    prompt_id: str
    purpose: str
    subject: str = "biology"
    version: str = "current"
    source: str = "file"
    path: str | None = None
    prompt_hash: str
    variables: list[str] = Field(default_factory=list)
    output_schema: str
    owner_module: str | None = None

    @field_validator("prompt_hash")
    @classmethod
    def _hash_is_sha256(cls, value: str) -> str:
        return _validate_sha256(value)

    @classmethod
    def from_file(
        cls,
        *,
        prompt_id: str,
        purpose: str,
        subject: str,
        path: str | Path,
        project_root: str | Path,
        variables: Iterable[str],
        output_schema: str,
        owner_module: str | None = None,
        version: str = "current",
    ) -> "PromptSpec":
        prompt_path = Path(path)
        root = Path(project_root)
        content = prompt_path.read_bytes()
        digest = sha256(content).hexdigest()
        try:
            rel_path = prompt_path.relative_to(root).as_posix()
        except ValueError:
            rel_path = prompt_path.as_posix()
        return cls(
            prompt_id=prompt_id,
            purpose=purpose,
            subject=subject,
            version=version,
            source="file",
            path=rel_path,
            prompt_hash=digest,
            variables=list(variables),
            output_schema=output_schema,
            owner_module=owner_module,
        )

    @classmethod
    def from_text(
        cls,
        *,
        prompt_id: str,
        purpose: str,
        subject: str,
        prompt_text: str,
        variables: Iterable[str],
        output_schema: str,
        owner_module: str | None = None,
        version: str = "current",
        path: str | None = None,
    ) -> "PromptSpec":
        return cls(
            prompt_id=prompt_id,
            purpose=purpose,
            subject=subject,
            version=version,
            source="inline",
            path=path,
            prompt_hash=sha256(prompt_text.encode("utf-8")).hexdigest(),
            variables=list(variables),
            output_schema=output_schema,
            owner_module=owner_module,
        )


class PromptRegistry:
    """In-memory registry with duplicate prompt_id protection."""

    def __init__(self, specs: Iterable[PromptSpec]):
        self._specs: dict[str, PromptSpec] = {}
        for spec in specs:
            if spec.prompt_id in self._specs:
                raise ValueError(f"Duplicate prompt_id: {spec.prompt_id}")
            self._specs[spec.prompt_id] = spec

    def get(self, prompt_id: str) -> PromptSpec:
        return self._specs[prompt_id]

    def list_by_purpose(self, purpose: str) -> list[PromptSpec]:
        return [spec for spec in self._specs.values() if spec.purpose == purpose]

    def all(self) -> list[PromptSpec]:
        return list(self._specs.values())


def build_default_prompt_registry(project_root: str | Path, subject: str = "biology") -> PromptRegistry:
    """Build the current file-backed prompt registry for one subject.

    The registry describes existing prompt contracts; it does not decide which
    code path is currently active. That activation mapping is recorded through
    owner_module.
    """
    root = Path(project_root)
    specs: list[PromptSpec] = []
    definitions = [
        {
            "prompt_id": f"{subject}.question_analysis.v2",
            "purpose": "question_analysis",
            "path": root / "backend" / "prompts" / ("analysis_prompt" + "_v" + "2.txt"),
            "variables": ["question_type", "section_header"],
            "output_schema": "FineGrainedResult",
            "owner_module": "question_analyzer.analyze_question",
        },
        {
            "prompt_id": f"{subject}.competency_analysis",
            "purpose": "competency_analysis",
            "path": root / "backend" / "prompts" / "competency_analysis_prompt.txt",
            "variables": ["question_text", "knowledge_points"],
            "output_schema": "CompetencyResult",
            "owner_module": "competency_analyzer.analyze_competency",
        },
        {
            "prompt_id": f"{subject}.feature_extraction",
            "purpose": "feature_extraction",
            "path": root / "prompts" / subject / "feature_extractor.txt",
            "variables": ["question_block", "qtype_hint"],
            "output_schema": "FeatureResult",
            "owner_module": "feature_extractor.extract_features",
        },
        {
            "prompt_id": f"{subject}.big_question_feature_extraction",
            "purpose": "big_question_feature_extraction",
            "path": root / "prompts" / subject / "big_question_extractor.txt",
            "variables": ["question_block", "qtype_hint"],
            "output_schema": "BigQuestionFeatureResult",
            "owner_module": "feature_extractor.extract_big_question_features",
        },
        {
            "prompt_id": f"{subject}.split_questions",
            "purpose": "split_questions",
            "path": root / "prompts" / subject / "split_prompt.txt",
            "variables": [],
            "output_schema": "SplitQuestionList",
            "owner_module": "question_analyzer.split_questions",
        },
    ]
    for item in definitions:
        path = item["path"]
        if path.exists():
            specs.append(
                PromptSpec.from_file(
                    prompt_id=item["prompt_id"],
                    purpose=item["purpose"],
                    subject=subject,
                    path=path,
                    project_root=root,
                    variables=item["variables"],
                    output_schema=item["output_schema"],
                    owner_module=item["owner_module"],
                )
            )
    specs.append(
        PromptSpec.from_text(
            prompt_id=f"{subject}.report_insights",
            purpose="report_insights",
            subject=subject,
            prompt_text="report overall insights prompt built from aggregate report data",
            variables=[
                "exam_info",
                "metrics",
                "difficulty_gradient",
                "knowledge",
                "competency",
                "feature_profile",
                "diagnostics",
            ],
            output_schema="InsightsResult",
            owner_module="report_insights.generate_insights",
            path="backend/report_insights.py:_build_overall_prompt",
        )
    )
    specs.append(
        PromptSpec.from_text(
            prompt_id=f"{subject}.report_teaching_suggestions",
            purpose="report_teaching_suggestions",
            subject=subject,
            prompt_text="report teaching suggestions prompt built from questions and diagnostics",
            variables=["questions", "diagnostics"],
            output_schema="TeachingSuggestions",
            owner_module="report_insights.generate_insights",
            path="backend/report_insights.py:_build_teaching_prompt",
        )
    )
    return PromptRegistry(specs)


class LLMCallRecord(BaseModel):
    """Audit record for one logical LLM call."""

    call_id: str
    question_id: int | None = None
    purpose: str
    prompt_id: str
    prompt_hash: str
    provider: str
    model: str
    input_refs: dict[str, Any] = Field(default_factory=dict)
    raw_output_ref: str | None = None
    parsed_schema: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    validation_errors: list[str] = Field(default_factory=list)
    fallback_count: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("prompt_hash")
    @classmethod
    def _hash_is_sha256(cls, value: str) -> str:
        return _validate_sha256(value)

    def is_trusted(self, min_confidence: float = 0.7) -> bool:
        return self.confidence >= min_confidence and not self.validation_errors


class AnalyzedQuestionEnvelope(BaseModel):
    """Canonical metadata envelope for a fully analyzed question."""

    question: dict[str, Any]
    llm_calls: list[LLMCallRecord] = Field(default_factory=list)
    analysis_units: dict[str, Any] = Field(default_factory=dict)
    derived: dict[str, Any] = Field(default_factory=dict)
    confidence: dict[str, float] = Field(default_factory=dict)
    lineage: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _question_has_id(self) -> "AnalyzedQuestionEnvelope":
        if self.question.get("id") is None:
            raise ValueError("question.id is required")
        return self

    @property
    def question_id(self) -> Any:
        return self.question["id"]
