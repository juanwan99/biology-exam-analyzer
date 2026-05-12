"""Pipeline schemas and step definitions for analysis pipeline."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class DocumentArtifact:
    """文档解析结果。"""
    filename: str
    image_bytes: List[bytes] = field(default_factory=list, repr=False)
    extracted_text: Optional[str] = None
    extracted_elements: Optional[list] = None
    page_count: int = 0

    def __post_init__(self):
        self.page_count = len(self.image_bytes)


@dataclass
class QuestionDraft:
    """拆分后的题目草稿。"""
    id: int = 0
    content: str = ""
    question_type: str = "unknown"
    total_score: float = 0
    image_indices: List[int] = field(default_factory=list)
    section_header: Optional[str] = None
    media_for_ai: List[Dict] = field(default_factory=list)
    raw: Dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict) -> "QuestionDraft":
        return cls(
            id=d.get("id", 0),
            content=d.get("content", ""),
            question_type=d.get("question_type", "unknown"),
            total_score=d.get("total_score", 0),
            image_indices=d.get("image_indices", []),
            section_header=d.get("_section_header"),
            media_for_ai=d.get("_media_for_ai", []),
            raw=d,
        )

    def to_dict(self) -> Dict:
        result = dict(self.raw)
        result.update({
            "id": self.id,
            "content": self.content,
            "question_type": self.question_type,
            "total_score": self.total_score,
        })
        return result


@dataclass
class QuestionAnalysis:
    """单题分析结果。"""
    question_id: int = 0
    analysis: Dict = field(default_factory=dict)
    difficulty: Dict = field(default_factory=dict)
    competency: Dict = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.error is None and "error" not in self.analysis

    def to_question_dict(self, draft: QuestionDraft) -> Dict:
        result = draft.to_dict()
        result["analysis"] = self.analysis
        result["difficulty"] = self.difficulty
        result["competency"] = self.competency
        return result


@dataclass
class ReportData:
    """报告数据 — 图表和 PDF 的统一数据源。"""
    exam_info: Dict = field(default_factory=dict)
    questions: List[Dict] = field(default_factory=list)
    statistics: Dict = field(default_factory=dict)
    competency_summary: Dict = field(default_factory=dict)
    question_count: int = 0
    total_score: float = 0

    def __post_init__(self):
        self.question_count = len(self.questions)
        self.total_score = sum(
            q.get("total_score", q.get("analysis", {}).get("total_score", 0)) or 0
            for q in self.questions
        )


@dataclass
class StepResult:
    """Pipeline step 的执行结果。"""
    step_name: str
    status: StepStatus = StepStatus.PENDING
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0

    @property
    def is_success(self) -> bool:
        return self.status == StepStatus.SUCCESS


@dataclass
class AnalysisRun:
    """一次分析运行的完整状态。"""
    run_id: str = ""
    subject: str = "biology"
    mode: str = "fast"
    status: str = "pending"
    current_step: str = ""
    steps: List[StepResult] = field(default_factory=list)
    document: Optional[DocumentArtifact] = None
    drafts: List[QuestionDraft] = field(default_factory=list)
    analyses: List[QuestionAnalysis] = field(default_factory=list)
    report_data: Optional[ReportData] = None

    @property
    def progress(self) -> float:
        if not self.steps:
            return 0.0
        done = sum(1 for s in self.steps if s.status in (StepStatus.SUCCESS, StepStatus.SKIPPED))
        return done / len(self.steps)

    @property
    def failed_questions(self) -> List[int]:
        return [a.question_id for a in self.analyses if not a.is_success]
