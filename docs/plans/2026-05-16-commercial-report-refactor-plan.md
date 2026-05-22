# Commercial-Grade Exam Report Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the exam analysis output into a professional commercial/consulting report modeled on Bain-style report structure, BlackRock-style judgment density, and OECD/NWEA-style education measurement rigor.

**Architecture:** Keep the existing analysis pipeline and metadata governance intact. Replace the current thin product-report model and HTML renderer with a consulting-report contract that turns existing `report_data` + `insights` + metadata envelopes into evidence-backed sections: cover, executive summary, at-a-glance, figures, question portfolio, deep dives, and methodology. PDF remains an export artifact; HTML becomes the primary report surface.

**Tech Stack:** Python backend, existing FastAPI routes, existing `report_data.py`, `report_insights.py`, `report_product_model.py`, `report_product_html.py`, `report_product_publish.py`, pytest.

---

## Reference Standard

Primary benchmark: `C:\Users\Administrator\Documents\New project\professional_reports\bain_global_private_equity_report_2025.pdf`

Observed Bain structure:
- Cover: minimal, authority-first.
- Credibility / About: establishes institutional trust before analysis.
- Contents: clear sections, not a dashboard dump.
- Opening letter / lead essay: one coherent market-level judgment.
- At a Glance: 3 decisive claims before detailed evidence.
- Chapters: each starts with a clear thesis, then supporting figures.
- Figures: every chart has a conclusion-style title, notes, and sources.
- Pull quotes: important judgment is visually separated.
- Appendix/methodology: credibility comes from data provenance.

Target adaptation:
- This is not a UI beautification task.
- This is a report-product refactor: professional judgment first, evidence second, chart third, action last.
- Every high-level claim must have explicit evidence references.

---

## Report Product Contract

The final `CommercialExamReportModel` must contain these top-level sections:

```python
{
    "cover": {
        "title": "AI 试卷质量诊断报告",
        "exam_name": "string",
        "subject": "biology",
        "generated_at": "ISO datetime",
        "report_version": "commercial_report.v1",
    },
    "credibility": {
        "analysis_scope": {"questions": 21, "total_score": 100},
        "metadata_status": "pass|warning|blocked",
        "llm_calls_total": 63,
        "method_note": "string",
    },
    "executive_summary": {
        "lead_judgment": "string",
        "big_calls": [
            {
                "id": "quality_risk",
                "title": "string",
                "stance": "positive|watch|risk",
                "why_it_matters": "string",
                "evidence_refs": ["metric:avg_difficulty", "question:12", "metadata:warning_questions"],
                "recommended_action": "string",
            }
        ],
    },
    "at_a_glance": [
        {"metric": "平均难度", "value": "6.4", "interpretation": "string", "evidence_ref": "metric:avg_difficulty"}
    ],
    "chapters": [
        {
            "id": "exam_structure",
            "title": "整卷结构诊断",
            "thesis": "string",
            "figures": [
                {
                    "id": "difficulty_gradient",
                    "title": "难度梯度显示后段压力集中",
                    "takeaway": "string",
                    "data": {},
                    "source": "report_data.difficulty_gradient",
                    "notes": "string",
                }
            ],
            "implications": ["string"],
        }
    ],
    "question_portfolio": {
        "thesis": "string",
        "rows": [
            {
                "question_id": 1,
                "risk_level": "high|medium|low",
                "quality_level": "硬伤|待优化|稳定|未评估",
                "difficulty": 6.2,
                "metadata_confidence": 0.91,
                "primary_issue": "string",
                "action": "string",
                "evidence_refs": ["question:1.quality", "question:1.metadata"],
            }
        ],
    },
    "deep_dives": [
        {
            "question_id": 1,
            "headline": "string",
            "diagnosis": "string",
            "seu_breakdown": [],
            "du_diagnostics": [],
            "revision_plan": ["string"],
            "metadata_trace": {"purposes": [], "confidence": 0.91, "warnings": []},
        }
    ],
    "methodology": {
        "llm_call_summary": {},
        "prompt_inventory": [],
        "parsed_fields": [],
        "quality_gates": [],
        "limitations": [],
    },
}
```

Hard invariant:
- No executive claim without `evidence_refs`.
- No figure without `source`.
- No question risk row without metadata confidence.
- No methodology page without LLM purpose counts.

---

## File Map

Modify:
- `/home/ubuntu/biology-exam-analyzer/backend/report_product_model.py`
  - Replace the current thin UI model with the commercial report contract.
  - Keep function name `build_report_product_model(report_data, insights=None)` to avoid route churn.
- `/home/ubuntu/biology-exam-analyzer/backend/report_product_html.py`
  - Replace current dashboard-style renderer with report-page renderer.
  - Use sections, figure blocks, source notes, and methodology appendix.
- `/home/ubuntu/biology-exam-analyzer/backend/report_product_publish.py`
  - Keep public function `write_report_artifacts`.
  - Ensure it writes PDF and HTML from the same commercial model source.
- `/home/ubuntu/biology-exam-analyzer/backend/services/analysis_service.py`
  - Preserve current report generation path.
  - Ensure `html_report_url` remains returned when HTML exists.
- `/home/ubuntu/biology-exam-analyzer/backend/analysis_router.py`
  - Preserve existing `report_url` and `html_report_url`.
  - Do not duplicate report generation logic.

Create:
- `/home/ubuntu/biology-exam-analyzer/backend/report_commercial_narrative.py`
  - Deterministic narrative helpers only.
  - Converts metrics into evidence-backed business-report language.
  - No LLM calls.
- `/home/ubuntu/biology-exam-analyzer/backend/test_report_commercial_model.py`
  - Tests contract, evidence invariants, methodology completeness.
- `/home/ubuntu/biology-exam-analyzer/backend/test_report_commercial_html.py`
  - Tests Bain-style sections render with source notes and deep dives.

Do not create:
- `*_v2.py`, `*_new.py`, `commercial_report_old.py`.
- Any parallel report endpoint.
- Any second report pipeline that bypasses metadata gates.

---

## Task 1: Model Contract and Evidence Invariants

**Files:**
- Modify: `/home/ubuntu/biology-exam-analyzer/backend/report_product_model.py`
- Create: `/home/ubuntu/biology-exam-analyzer/backend/report_commercial_narrative.py`
- Create: `/home/ubuntu/biology-exam-analyzer/backend/test_report_commercial_model.py`

- [ ] **Step 1: Write failing tests for commercial report shape**

Create `test_report_commercial_model.py` with tests that assert:

```python
from report_product_model import build_report_product_model


def sample_report_data():
    return {
        "exam_info": {"name": "真实高三生物试卷", "total_questions": 21, "total_score": 100, "mode": "deep"},
        "metrics": {"avg_difficulty": 6.4, "avg_cognitive_level": 4.8, "bloom_distribution": {"分析": 0.4}},
        "difficulty_gradient": {"front": 4.2, "middle": 6.1, "back": 7.8, "gradient_type": "前易后难"},
        "knowledge": {"top_points": [{"name": "遗传", "weighted_score": 18}], "unmapped_count": 1},
        "competency": {"distribution": {"生命观念": {"占比": 0.45}, "科学思维": {"占比": 0.35}, "科学探究": {"占比": 0.2}, "社会责任": {"占比": 0}}},
        "fine_grained_summary": {"total_seus": 44, "total_dus": 19, "avg_allocation_confidence": 0.86},
        "metadata_quality": {
            "total_questions": 21,
            "missing_envelope_questions": [],
            "low_confidence_questions": [7],
            "warning_questions": [{"id": 7, "warnings": ["feature_status:partial"]}],
            "llm_call_counts": {"question_analysis": 21, "feature_extraction": 21, "competency_analysis": 21},
        },
        "questions": [
            {
                "id": 1,
                "total_score": 6,
                "question_type": "single_choice",
                "difficulty": 4.2,
                "difficulty_label": "中等",
                "quality_score": 5,
                "metadata_confidence": 0.95,
                "metadata_warnings": [],
                "metadata_call_purposes": ["question_analysis", "feature_extraction", "competency_analysis"],
                "knowledge_points": ["光合作用"],
                "primary_competency": "生命观念",
                "seu_knowledge_breakdown": [{"label": "识别光反应场所", "score_share": 1.0}],
                "diagnostic_highlights": [],
            },
            {
                "id": 7,
                "total_score": 12,
                "question_type": "short_answer",
                "difficulty": 7.8,
                "difficulty_label": "困难",
                "quality_score": 2,
                "quality_scientific": "科学性表述存在风险",
                "metadata_confidence": 0.62,
                "metadata_warnings": ["feature_status:partial"],
                "metadata_call_purposes": ["question_analysis", "feature_extraction", "competency_analysis"],
                "knowledge_points": ["遗传"],
                "primary_competency": "科学思维",
                "seu_knowledge_breakdown": [{"label": "推断遗传方式", "score_share": 0.5}],
                "diagnostic_highlights": [{"option": "step_2", "misconception": "混淆显隐性", "trap_strength": 3}],
            },
        ],
    }


def test_commercial_report_has_consulting_structure():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})
    assert set(model) >= {
        "cover", "credibility", "executive_summary", "at_a_glance",
        "chapters", "question_portfolio", "deep_dives", "methodology"
    }
    assert model["cover"]["report_version"] == "commercial_report.v1"
    assert model["executive_summary"]["big_calls"]
    assert model["question_portfolio"]["rows"]
    assert model["methodology"]["llm_call_summary"]["question_analysis"] == 21


def test_every_big_call_has_evidence_and_action():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})
    for call in model["executive_summary"]["big_calls"]:
        assert call["title"]
        assert call["evidence_refs"]
        assert call["recommended_action"]


def test_every_figure_has_source_and_takeaway():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})
    figures = [fig for chapter in model["chapters"] for fig in chapter["figures"]]
    assert figures
    for fig in figures:
        assert fig["title"]
        assert fig["takeaway"]
        assert fig["source"]


def test_question_portfolio_rows_include_metadata_confidence():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})
    row = next(item for item in model["question_portfolio"]["rows"] if item["question_id"] == 7)
    assert row["risk_level"] == "high"
    assert row["metadata_confidence"] == 0.62
    assert "question:7" in " ".join(row["evidence_refs"])
```

- [ ] **Step 2: Run RED**

Run:

```bash
docker exec -w /app biology_backend pytest -q test_report_commercial_model.py
```

Expected:
- Fails because current `report_product_model.py` does not expose the commercial sections.

- [ ] **Step 3: Implement deterministic narrative helper**

Create `report_commercial_narrative.py`:

```python
from __future__ import annotations

from typing import Any, Dict, List


def risk_stance(risk_level: str) -> str:
    return {"high": "risk", "medium": "watch", "low": "positive"}.get(risk_level, "watch")


def difficulty_thesis(avg_difficulty: Any, gradient_type: str) -> str:
    if isinstance(avg_difficulty, (int, float)) and avg_difficulty >= 7:
        return f"整卷平均难度达到 {avg_difficulty:.2f}，需要重点复核高压题组是否超出目标学生承受区间。"
    if isinstance(avg_difficulty, (int, float)) and avg_difficulty >= 6:
        return f"整卷难度处于中高区间，{gradient_type or '梯度结构'} 是解释学生表现分化的关键线索。"
    return f"整卷难度整体可控，{gradient_type or '梯度结构'} 仍需结合分值权重复核。"


def metadata_status(metadata_quality: Dict[str, Any]) -> str:
    if metadata_quality.get("missing_envelope_questions"):
        return "blocked"
    if metadata_quality.get("warning_questions") or metadata_quality.get("low_confidence_questions"):
        return "warning"
    return "pass"


def question_risk_level(question: Dict[str, Any]) -> str:
    score = question.get("quality_score")
    confidence = question.get("metadata_confidence", 0)
    warnings = question.get("metadata_warnings") or []
    if score in (1, 2) or (isinstance(confidence, (int, float)) and confidence < 0.7):
        return "high"
    if score == 3 or warnings:
        return "medium"
    return "low"


def primary_issue(question: Dict[str, Any]) -> str:
    for key in ("quality_scientific", "quality_normative", "quality_language", "quality_context"):
        value = question.get(key)
        if value and "无明显问题" not in value and value not in ("规范", "严谨", "真实", "良好"):
            return str(value)
    warnings = question.get("metadata_warnings") or []
    if warnings:
        return "元数据存在需复核项：" + "、".join(map(str, warnings))
    return "未发现显性质量问题"


def action_for_question(question: Dict[str, Any]) -> str:
    risk = question_risk_level(question)
    if risk == "high":
        return "进入命题复核清单，先确认科学性、设问边界与元数据可靠性。"
    if risk == "medium":
        return "进行人工抽样复核，补充设问限定或修正解析口径。"
    return "保留当前设计，作为同类题目参照。"
```

- [ ] **Step 4: Replace model construction**

Modify `report_product_model.py` so `build_report_product_model()` returns `commercial_report.v1` with:
- `cover`
- `credibility`
- `executive_summary`
- `at_a_glance`
- `chapters`
- `question_portfolio`
- `deep_dives`
- `methodology`

Implementation rule:
- Use the existing function name.
- Do not leave the old top-level `hero_conclusions` contract as a parallel version.
- If temporary compatibility is needed, adapt tests and callers in the same batch, not by adding `legacy_*`.

- [ ] **Step 5: Run GREEN**

Run:

```bash
docker exec -w /app biology_backend pytest -q test_report_commercial_model.py test_report_product_publish.py
```

Expected:
- Commercial model tests pass.
- Publish layer still writes PDF + HTML.

---

## Task 2: Bain-Style HTML Renderer

**Files:**
- Modify: `/home/ubuntu/biology-exam-analyzer/backend/report_product_html.py`
- Create: `/home/ubuntu/biology-exam-analyzer/backend/test_report_commercial_html.py`

- [ ] **Step 1: Write failing renderer tests**

Create `test_report_commercial_html.py`:

```python
from report_product_html import render_report_product_html


def commercial_model():
    return {
        "cover": {"title": "AI 试卷质量诊断报告", "exam_name": "高三生物一模", "report_version": "commercial_report.v1"},
        "credibility": {"metadata_status": "warning", "llm_calls_total": 63, "analysis_scope": {"questions": 21, "total_score": 100}},
        "executive_summary": {
            "lead_judgment": "本卷具备完整能力覆盖，但高分值题组存在复核风险。",
            "big_calls": [
                {"id": "quality", "title": "1 道题进入高风险复核", "stance": "risk", "why_it_matters": "影响结论可信度", "evidence_refs": ["question:7"], "recommended_action": "先复核 Q7"}
            ],
        },
        "at_a_glance": [{"metric": "LLM 调用", "value": "63", "interpretation": "完整覆盖三类分析", "evidence_ref": "metadata:llm_call_counts"}],
        "chapters": [
            {"id": "exam_structure", "title": "整卷结构诊断", "thesis": "难度后移。", "figures": [{"id": "difficulty", "title": "难度梯度显示后段压力集中", "takeaway": "后段题组是区分度来源", "data": {"front": 4.2, "back": 7.8}, "source": "report_data.difficulty_gradient", "notes": "按题序三段计算"}], "implications": ["复核压轴题分值"]}
        ],
        "question_portfolio": {"thesis": "高风险集中于 Q7。", "rows": [{"question_id": 7, "risk_level": "high", "quality_level": "硬伤", "difficulty": 7.8, "metadata_confidence": 0.62, "primary_issue": "科学性表述存在风险", "action": "进入命题复核清单", "evidence_refs": ["question:7.quality"]}]},
        "deep_dives": [{"question_id": 7, "headline": "Q7 需优先复核", "diagnosis": "科学性和元数据同时触发风险。", "seu_breakdown": [], "du_diagnostics": [], "revision_plan": ["重写设问"], "metadata_trace": {"purposes": ["question_analysis"], "confidence": 0.62, "warnings": ["feature_status:partial"]}}],
        "methodology": {"llm_call_summary": {"question_analysis": 21}, "prompt_inventory": [], "parsed_fields": ["quality_score"], "quality_gates": ["metadata_required"], "limitations": ["LLM 结论需人工复核"]},
    }


def test_html_renders_commercial_report_sections():
    html = render_report_product_html(commercial_model())
    assert "Executive Summary" in html
    assert "At a Glance" in html
    assert "整卷结构诊断" in html
    assert "Question Portfolio" in html
    assert "Methodology & Metadata" in html
    assert "Source: report_data.difficulty_gradient" in html
    assert "Q7 需优先复核" in html
```

- [ ] **Step 2: Run RED**

Run:

```bash
docker exec -w /app biology_backend pytest -q test_report_commercial_html.py
```

Expected:
- Fails because current HTML renderer is dashboard-style and lacks commercial report sections.

- [ ] **Step 3: Replace renderer page structure**

Modify `report_product_html.py` into these render functions:
- `_render_cover(model)`
- `_render_credibility(model)`
- `_render_executive_summary(model)`
- `_render_at_a_glance(model)`
- `_render_chapters(model)`
- `_render_question_portfolio(model)`
- `_render_deep_dives(model)`
- `_render_methodology(model)`
- `_css()`
- `render_report_product_html(product_model)`
- `write_report_product_html(product_model, output_path)`

Renderer rules:
- No marketing hero.
- No decorative cards inside decorative cards.
- Every figure block renders title, takeaway, source, notes.
- Every table row has risk level and metadata confidence.
- Methodology appears as a first-class section, not a footer footnote.
- Color system: professional dark editorial, restrained gold/green/cyan/red; no purple gradient theme.

- [ ] **Step 4: Run GREEN**

Run:

```bash
docker exec -w /app biology_backend pytest -q test_report_commercial_html.py test_report_product_html.py test_report_product_publish.py
```

Expected:
- New commercial HTML tests pass.
- Update or remove obsolete assertions in `test_report_product_html.py` in the same commit if they assert the old dashboard contract.

---

## Task 3: Real Data Density and Metadata Appendix

**Files:**
- Modify: `/home/ubuntu/biology-exam-analyzer/backend/report_product_model.py`
- Modify: `/home/ubuntu/biology-exam-analyzer/backend/report_data.py` only if required fields are missing.
- Test: `/home/ubuntu/biology-exam-analyzer/backend/test_report_commercial_model.py`

- [ ] **Step 1: Add tests for methodology completeness**

Add:

```python
def test_methodology_exposes_prompt_and_parsed_field_inventory():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})
    methodology = model["methodology"]
    assert "llm_call_summary" in methodology
    assert "parsed_fields" in methodology
    assert "quality_gates" in methodology
    assert "limitations" in methodology
    assert methodology["llm_call_summary"]["question_analysis"] == 21
```

- [ ] **Step 2: Implement methodology extraction**

Methodology must include:
- LLM call counts by purpose from `metadata_quality.llm_call_counts`.
- Prompt inventory from question metadata call purposes where available.
- Parsed field list from fields actually used by report:
  - `quality_score`
  - `difficulty`
  - `knowledge_points`
  - `primary_competency`
  - `seu_knowledge_breakdown`
  - `diagnostic_highlights`
  - `metadata_confidence`
  - `metadata_warnings`
- Quality gates:
  - `metadata envelope required`
  - `question_analysis required`
  - `feature_extraction or big_question_feature_extraction required`
  - `competency_analysis or SEU-derived competency required`
- Limitations:
  - LLM-derived diagnosis needs teacher review.
  - Low-confidence metadata should not be used as definitive judgment.

- [ ] **Step 3: Run focused tests**

Run:

```bash
docker exec -w /app biology_backend pytest -q test_report_commercial_model.py test_metadata_quality_visibility.py
```

Expected:
- Methodology tests pass.
- Existing metadata visibility stays pass.

---

## Task 4: Real Exam Smoke Report

**Files:**
- Modify existing smoke script if present, or create `/home/ubuntu/biology-exam-analyzer/backend/scripts/generate_real_commercial_report.py`.
- Do not hardcode fake questions into production code.

- [ ] **Step 1: Create a script that saves structured real report input**

Script behavior:
- Locate one real uploaded exam file already used for smoke testing.
- Run the existing analysis path, or load the latest successful smoke result if a structured JSON cache exists.
- Write:
  - `/home/ubuntu/biology-exam-analyzer/reports/{exam_id}.pdf`
  - `/home/ubuntu/biology-exam-analyzer/reports/{exam_id}.html`
  - `/home/ubuntu/biology-exam-analyzer/reports/{exam_id}.report_data.json`
  - `/home/ubuntu/biology-exam-analyzer/reports/{exam_id}.commercial_model.json`

- [ ] **Step 2: Run real smoke**

Run:

```bash
docker exec -w /app biology_backend python scripts/generate_real_commercial_report.py
```

Expected output must include:
- exam_id
- question count
- LLM call total
- metadata blocked count
- HTML path
- PDF path

- [ ] **Step 3: Verify served HTML**

Run:

```bash
curl -s -D /tmp/commercial_headers.txt -o /tmp/commercial_report.html http://localhost:8001/api/reports/{exam_id}.html
sed -n '1,12p' /tmp/commercial_headers.txt
wc -c /tmp/commercial_report.html
```

Expected:
- `HTTP/1.1 200 OK`
- `content-type: text/html; charset=utf-8`
- HTML size materially larger than the old demo report.

---

## Task 5: API and Frontend Contract

**Files:**
- Modify: `/home/ubuntu/biology-exam-analyzer/backend/services/analysis_service.py`
- Modify: `/home/ubuntu/biology-exam-analyzer/backend/analysis_router.py`
- Modify frontend only after locating current report link rendering.

- [ ] **Step 1: Preserve API compatibility**

Invariant:
- `report_url` remains PDF.
- `html_report_url` remains HTML.
- Existing clients that only use PDF do not break.

- [ ] **Step 2: Add route tests if not already present**

Ensure:

```python
assert result["report_url"].endswith(".pdf")
assert result["html_report_url"].endswith(".html")
```

Run:

```bash
docker exec -w /app biology_backend pytest -q test_analysis_router_metadata.py test_metadata_quality_visibility.py
```

Expected:
- Both pass.

- [ ] **Step 3: Frontend link behavior**

Frontend behavior:
- Primary button: `查看专业报告` -> `html_report_url`.
- Secondary button: `下载 PDF` -> `report_url`.
- If `html_report_url` missing, show report generation error or fallback to PDF.

Do not touch frontend until the source files and components are identified with `rg`.

---

## Task 6: Visual QA Against Bain Standard

**Files:**
- Generated report HTML.
- Optional screenshots under `/home/ubuntu/biology-exam-analyzer/reports/qa/`.

- [ ] **Step 1: Manual checklist**

Check generated HTML against these criteria:
- First viewport communicates report name and one lead judgment.
- Executive Summary visible before detailed charts.
- At a Glance has 3-5 dense findings, not generic cards.
- Figures have title, takeaway, source, and notes.
- Question portfolio is scannable as a decision table.
- Deep dives show SEU/DU and metadata trace.
- Methodology is explicit and credible.

- [ ] **Step 2: Browser verification**

Use the actual browser surface to open:

```text
http://localhost:8001/api/reports/{exam_id}.html
```

Expected:
- Page opens.
- No overlapping text.
- Mobile width remains readable.
- Long Chinese labels do not overflow.

---

## Verification Commands

Focused:

```bash
docker exec -w /app biology_backend pytest -q \
  test_report_commercial_model.py \
  test_report_commercial_html.py \
  test_report_product_publish.py \
  test_metadata_quality_visibility.py \
  test_analysis_router_metadata.py
```

Static scoped check:

```bash
cd /home/ubuntu/biology-exam-analyzer
git diff --check -- \
  backend/report_product_model.py \
  backend/report_commercial_narrative.py \
  backend/report_product_html.py \
  backend/report_product_publish.py \
  backend/services/analysis_service.py \
  backend/analysis_router.py \
  backend/test_report_commercial_model.py \
  backend/test_report_commercial_html.py
```

Runtime:

```bash
docker restart biology_backend
docker inspect biology_backend --format '{{.State.Health.Status}}'
curl -s -D /tmp/report_headers.txt -o /tmp/report.html http://localhost:8001/api/reports/{exam_id}.html
```

---

## Acceptance Criteria

The refactor is complete only when:
- A real 21-question exam generates a commercial-style HTML report.
- The report opens from `html_report_url`.
- Executive Summary contains evidence-backed big calls.
- At least 4 figure blocks include title, takeaway, source, and notes.
- Question portfolio contains all questions with risk level and metadata confidence.
- Deep dives include high-risk questions with SEU/DU detail.
- Methodology exposes LLM call counts, prompt/field inventory, gates, and limitations.
- PDF generation remains available and does not regress.
- Focused tests pass.
- Backend is restarted and healthy.

---

## Known Risks

- Existing full `pytest -q` is not clean due to unrelated historical tests; use focused regression suite for this refactor and report full-suite residual failures separately.
- If real smoke requires expensive LLM calls, cache `report_data` and `commercial_model` JSON after the first successful run.
- If frontend report links are stale, backend HTML can still be verified through `/api/reports/{exam_id}.html`.

---

## Execution Options

Recommended execution:
1. Task 1-3 as one backend model/render batch.
2. Stop for visual checkpoint with generated sample.
3. Task 4 real exam smoke.
4. Stop for user review.
5. Task 5 frontend integration.

Do not do all tasks in one unreviewed batch because this is a visual + data-contract + report-product refactor.
