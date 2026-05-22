# Teacher Review Report Content Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the current commercial-report visual form, but refactor the report content into a teacher-facing exam/question review report that answers: can this paper be used, what must be revised, what should be taught, and whether it fits the target students.

**Architecture:** Preserve the current product-report pipeline and renderer surface. Change the product model contract, deterministic narrative helpers, HTML/PDF copy, and tests so the primary report language becomes teacher review language instead of internal system provenance language. Keep SEU/DU, metadata, and LLM traceability in evidence/methodology sections, not in the executive summary.

**Tech Stack:** Python backend, existing `report_product_model.py`, `report_product_html.py`, `report_product_charts.py`, `report_product_publish.py`, pytest, generated static HTML/PDF report.

---

## Evidence Block

- Current visual form is acceptable to the user; content is not. Evidence: user said “现在报告的形式我比较喜欢，我们现在要对内容进行调整。风格就按此形式”.
- Current executive summary is not teacher-readable. Evidence: user asked what “第 1 题：评分证据 1” means and said current summary is hard to understand.
- Report positioning is an exam/question review report, not a student-score analysis report. Evidence: user specified concerns: high-exam trend fit, feasibility, language expression, public-opinion risk, knowledge coverage, and student-fit.
- Current baseline is frozen before refactor. Evidence: `/home/ubuntu/biology-exam-analyzer/docs/baselines/2026-05-17-report-product-current-logic-baseline.tar.gz`, SHA256 `e2a2f9a8ec721609d69a7e6a1ba18d33e5a3ccffadb0b695aa7c09481d3df62f`.

## Must Preserve

- Preserve the current visual report style: red/black/gray palette, section rhythm, exhibit cards, chart frames, large cover, chaptered report layout.
- Preserve one report pipeline and existing public function names where possible:
  - `/home/ubuntu/biology-exam-analyzer/backend/report_product_model.py::build_report_product_model`
  - `/home/ubuntu/biology-exam-analyzer/backend/report_product_html.py::render_report_product_html`
  - `/home/ubuntu/biology-exam-analyzer/backend/report_product_html.py::render_report_product_pdf_html`
  - `/home/ubuntu/biology-exam-analyzer/backend/report_product_publish.py::write_report_artifacts`
- Preserve current generated filenames unless user explicitly requests otherwise:
  - `/home/ubuntu/biology-exam-analyzer/reports/report_product_demo_20260516.html`
  - `/home/ubuntu/biology-exam-analyzer/reports/report_product_demo_20260516.pdf`
- Preserve metadata/SEU/DU traceability, but demote it from teacher-facing headline language into evidence and methodology.

## Must Not Change

- Do not create a parallel `*_v2.py`, `*_new.py`, `*_old.py`, or a second report endpoint.
- Do not replace the current visual system with a dashboard or academic paper style.
- Do not show pseudo-clickable evidence tags in the executive summary unless they become real links.
- Do not use internal labels such as `SEU/DU`, `metadata envelope`, `figure:*`, `question:Q*`, or `评分证据 1` as primary teacher-facing copy.

## Target Report Contract

The refactored product model should express these top-level sections:

```python
{
    "cover": {...},
    "review_positioning": {
        "report_type": "审题 / 审卷质量诊断报告",
        "audience": "命题教师 / 教研组 / 备课组",
        "use_case": "判断试卷能否使用、如何修订、如何讲评、是否适配学情",
    },
    "executive_summary": {
        "overall_verdict": {
            "label": "建议修改后使用",
            "stance": "watch",
            "teacher_takeaway": "本卷整体结构可用，但后段高压力题和个别科学表述需先复核。",
        },
        "teacher_priorities": [
            {"title": "优先复核题", "summary": "重点检查第 17-19 题的设问边界、评分标准和干扰项合理性。"},
            {"title": "优先讲评点", "summary": "学生主要风险集中在信息提取、干扰项辨析和知识迁移。"},
            {"title": "使用建议", "summary": "适合作为阶段诊断卷；普通班建议拆解后讲评，重点班可整卷使用。"},
        ],
        "evidence_scale": {
            "questions": 21,
            "scoring_units": 67,
            "diagnostic_units": 54,
            "reviewed_risk_items": 0,
        },
    },
    "exam_review": {
        "trend_fit": {...},
        "quality_risks": {...},
        "language_and_fairness": {...},
        "knowledge_coverage": {...},
        "student_fit": {...},
    },
    "question_portfolio": {...},
    "question_review_details": [...],
    "evidence_methodology": {...},
}
```

## Semantic Regression

The refactor is successful only if these user-facing invariants hold:

- A teacher can understand the executive summary without knowing SEU/DU or metadata terminology.
- The first page answers: can the paper be used, what to revise first, what to teach first, and which students it fits.
- Every major claim still has evidence behind it, but evidence is summarized in teacher language and detailed later.
- Current visual quality fixes remain intact: no small 9-12px SVG text, no visible raw reference ids, no text overlap in desktop/mobile screenshots.
- HTML and PDF remain generated from the same model source.

---

## File Map

Modify:

- `/home/ubuntu/biology-exam-analyzer/backend/report_product_model.py`
  - Build the new teacher-review content contract.
  - Add deterministic classification for overall verdict, trend fit, quality risk, language risk, knowledge coverage, and student fit.

- `/home/ubuntu/biology-exam-analyzer/backend/report_product_html.py`
  - Rewrite section copy and rendering order while preserving CSS/visual shell.
  - Replace pseudo evidence chips in the executive summary with teacher-readable evidence scale and review priorities.

- `/home/ubuntu/biology-exam-analyzer/backend/report_product_charts.py`
  - Reuse most charts; adjust chart titles/takeaways to teacher review language where needed.

- `/home/ubuntu/biology-exam-analyzer/backend/test_report_commercial_html.py`
  - Update visible-copy tests to assert teacher-facing language and absence of internal labels.

- `/home/ubuntu/biology-exam-analyzer/backend/test_report_product_model.py`
  - Add model contract tests for review positioning and teacher summary.

- `/home/ubuntu/biology-exam-analyzer/backend/test_report_product_publish.py`
  - Ensure generated HTML/PDF still come from one model and current artifact names.

Create:

- `/home/ubuntu/biology-exam-analyzer/backend/report_teacher_review_narrative.py`
  - Deterministic helper functions only.
  - No LLM calls.
  - Converts existing structured data into teacher-readable verdicts and summaries.

Do not create:

- A new report pipeline.
- A duplicate renderer.
- A new endpoint.

---

## Task 1: Add Teacher Review Narrative Helpers

**Files:**
- Create: `/home/ubuntu/biology-exam-analyzer/backend/report_teacher_review_narrative.py`
- Test: `/home/ubuntu/biology-exam-analyzer/backend/test_report_product_model.py`

- [ ] **Step 1: Write failing tests for teacher-readable verdict helpers**

Append tests to `/home/ubuntu/biology-exam-analyzer/backend/test_report_product_model.py`:

```python
from report_teacher_review_narrative import (
    classify_overall_verdict,
    summarize_teacher_priorities,
    summarize_student_fit,
)


def test_classify_overall_verdict_uses_teacher_language():
    result = classify_overall_verdict(
        high_risk_count=1,
        language_risk_count=0,
        scientific_risk_count=1,
        student_fit_level="medium",
    )

    assert result["label"] == "建议修改后使用"
    assert result["stance"] == "watch"
    assert "复核" in result["teacher_takeaway"]
    assert "SEU" not in result["teacher_takeaway"]
    assert "metadata" not in result["teacher_takeaway"].lower()


def test_summarize_teacher_priorities_are_actionable_for_teachers():
    priorities = summarize_teacher_priorities(
        risk_question_ids=[17, 18, 19],
        weak_dimensions=["信息提取", "干扰项辨析"],
        use_case="阶段诊断卷",
    )

    joined = " ".join(item["summary"] for item in priorities)
    assert "第 17-19 题" in joined
    assert "讲评" in joined
    assert "阶段诊断卷" in joined


def test_summarize_student_fit_distinguishes_use_scenarios():
    fit = summarize_student_fit(avg_difficulty=5.6, high_pressure_count=3, target_group="高三普通班")

    assert fit["fit_level"] in {"适配", "基本适配", "需拆解使用"}
    assert "普通班" in fit["teacher_note"]
    assert "怎么用" not in fit["teacher_note"]
```

- [ ] **Step 2: Run tests and confirm they fail because module does not exist**

Run:

```bash
cd /home/ubuntu/biology-exam-analyzer
python3 -m pytest -q backend/test_report_product_model.py
```

Expected:

```text
ModuleNotFoundError: No module named 'report_teacher_review_narrative'
```

- [ ] **Step 3: Implement deterministic helper module**

Create `/home/ubuntu/biology-exam-analyzer/backend/report_teacher_review_narrative.py`:

```python
from __future__ import annotations


def _range_text(ids: list[int]) -> str:
    if not ids:
        return "暂无明确高风险题"
    ordered = sorted(set(int(item) for item in ids))
    if len(ordered) >= 3 and ordered == list(range(ordered[0], ordered[-1] + 1)):
        return f"第 {ordered[0]}-{ordered[-1]} 题"
    return "、".join(f"第 {item} 题" for item in ordered[:5])


def classify_overall_verdict(
    *,
    high_risk_count: int,
    language_risk_count: int,
    scientific_risk_count: int,
    student_fit_level: str,
) -> dict:
    if scientific_risk_count > 0 or language_risk_count >= 2:
        return {
            "label": "建议修改后使用",
            "stance": "watch",
            "teacher_takeaway": "本卷整体结构可用，但存在需要先复核的科学性或表述风险，建议完成题目修订后再正式使用。",
        }
    if high_risk_count >= 3 or student_fit_level == "low":
        return {
            "label": "谨慎使用",
            "stance": "risk",
            "teacher_takeaway": "本卷压力集中或学情适配不足，建议拆分为专题训练或调整难度后使用。",
        }
    return {
        "label": "可作为诊断卷使用",
        "stance": "positive",
        "teacher_takeaway": "本卷整体质量稳定，可用于阶段诊断；讲评时重点解释高压力题的思维路径。",
    }


def summarize_teacher_priorities(*, risk_question_ids: list[int], weak_dimensions: list[str], use_case: str) -> list[dict]:
    question_text = _range_text(risk_question_ids)
    weak_text = "、".join(weak_dimensions[:3]) if weak_dimensions else "知识迁移和题干信息处理"
    return [
        {
            "title": "优先复核题",
            "summary": f"建议先复核{question_text}的设问边界、评分标准和干扰项合理性。",
        },
        {
            "title": "优先讲评点",
            "summary": f"讲评重点应放在{weak_text}，避免只讲答案不讲审题路径。",
        },
        {
            "title": "使用建议",
            "summary": f"本卷更适合作为{use_case}；若用于基础较弱班级，建议拆题讲评后再整卷训练。",
        },
    ]


def summarize_student_fit(*, avg_difficulty: float, high_pressure_count: int, target_group: str = "高三学生") -> dict:
    if avg_difficulty >= 7 or high_pressure_count >= 5:
        level = "需拆解使用"
        note = f"对{target_group}压力偏高，建议先拆解材料阅读、设问边界和推理链条。"
    elif avg_difficulty >= 5.5 or high_pressure_count >= 2:
        level = "基本适配"
        note = f"整体适配{target_group}，但高压力题需要配套讲评和变式训练。"
    else:
        level = "适配"
        note = f"难度对{target_group}较友好，可作为基础诊断或巩固训练使用。"
    return {"fit_level": level, "teacher_note": note}
```

- [ ] **Step 4: Run focused tests and confirm helper behavior**

Run:

```bash
cd /home/ubuntu/biology-exam-analyzer
python3 -m pytest -q backend/test_report_product_model.py
```

Expected:

```text
passed
```

---

## Task 2: Refactor Product Model Contract To Teacher Review Language

**Files:**
- Modify: `/home/ubuntu/biology-exam-analyzer/backend/report_product_model.py`
- Test: `/home/ubuntu/biology-exam-analyzer/backend/test_report_product_model.py`

- [ ] **Step 1: Add failing tests for new top-level teacher review fields**

Append tests:

```python
from report_product_model import build_report_product_model


def test_product_model_exposes_teacher_review_positioning(sample_report_data):
    model = build_report_product_model(sample_report_data(), {"recommendations": []})

    assert model["review_positioning"]["report_type"] == "审题 / 审卷质量诊断报告"
    assert "命题教师" in model["review_positioning"]["audience"]
    assert "能否使用" in model["review_positioning"]["use_case"]


def test_executive_summary_is_teacher_readable_not_internal_trace(sample_report_data):
    model = build_report_product_model(sample_report_data(), {"recommendations": []})
    summary = model["executive_summary"]

    assert "overall_verdict" in summary
    assert "teacher_priorities" in summary
    assert "evidence_scale" in summary
    rendered_text = str(summary)
    assert "评分证据 1" not in rendered_text
    assert "SEU/DU" not in rendered_text
    assert "metadata envelope" not in rendered_text
```

- [ ] **Step 2: Run tests and confirm they fail on missing keys**

Run:

```bash
cd /home/ubuntu/biology-exam-analyzer
python3 -m pytest -q backend/test_report_product_model.py
```

Expected:

```text
KeyError: 'review_positioning'
```

- [ ] **Step 3: Wire narrative helpers into `build_report_product_model`**

Implementation guidance:

```python
from report_teacher_review_narrative import (
    classify_overall_verdict,
    summarize_teacher_priorities,
    summarize_student_fit,
)
```

Inside `build_report_product_model`, compute:

```python
review_positioning = {
    "report_type": "审题 / 审卷质量诊断报告",
    "audience": "命题教师 / 教研组 / 备课组",
    "use_case": "判断试卷能否使用、如何修订、如何讲评、是否适配学情",
}
```

Replace or augment the current `executive_summary` with:

```python
executive_summary = {
    "lead_judgment": old_lead_judgment,
    "overall_verdict": classify_overall_verdict(
        high_risk_count=high_risk_count,
        language_risk_count=language_risk_count,
        scientific_risk_count=scientific_risk_count,
        student_fit_level=student_fit["fit_level"],
    ),
    "teacher_priorities": summarize_teacher_priorities(
        risk_question_ids=risk_question_ids,
        weak_dimensions=weak_dimensions,
        use_case="阶段诊断卷",
    ),
    "evidence_scale": {
        "questions": total_questions,
        "scoring_units": total_seus,
        "diagnostic_units": total_dus,
        "reviewed_risk_items": high_risk_count,
    },
}
```

Keep existing `big_calls` temporarily only if downstream renderer still needs it, but mark it as compatibility data and stop rendering it in the executive summary after Task 3.

- [ ] **Step 4: Run model tests**

Run:

```bash
cd /home/ubuntu/biology-exam-analyzer
python3 -m pytest -q backend/test_report_product_model.py backend/test_report_commercial_html.py
```

Expected:

```text
passed
```

If existing HTML tests fail because they still expect old executive evidence chips, update them in Task 3 rather than weakening model behavior.

---

## Task 3: Rewrite Executive Summary Rendering

**Files:**
- Modify: `/home/ubuntu/biology-exam-analyzer/backend/report_product_html.py`
- Test: `/home/ubuntu/biology-exam-analyzer/backend/test_report_commercial_html.py`

- [ ] **Step 1: Add failing tests that define the new summary copy**

Append tests:

```python
def test_executive_summary_reads_like_teacher_review_report():
    html = render_report_product_html(_commercial_model())
    visible_html = html.split('<script id="productData"', 1)[0]

    assert "总体使用建议" in visible_html
    assert "优先复核题" in visible_html
    assert "优先讲评点" in visible_html
    assert "使用建议" in visible_html
    assert "证据规模" in visible_html
    assert "评分证据 1" not in visible_html
    assert "第 1 题：评分证据" not in visible_html
    assert "SEU/DU" not in visible_html


def test_executive_summary_does_not_render_pseudo_clickable_evidence_chips():
    html = render_report_product_html(_commercial_model())
    summary = html.split('id="summary"', 1)[1].split('id="glance"', 1)[0]

    assert 'class="evidence-chip"' not in summary
    assert "覆盖题目" in summary
    assert "采分点" in summary
    assert "误区诊断点" in summary
```

- [ ] **Step 2: Run tests and confirm old renderer fails**

Run:

```bash
cd /home/ubuntu/biology-exam-analyzer
python3 -m pytest -q backend/test_report_commercial_html.py
```

Expected:

```text
FAILED ... 总体使用建议 not found
```

- [ ] **Step 3: Replace `_render_summary` content, not the visual shell**

In `/home/ubuntu/biology-exam-analyzer/backend/report_product_html.py`, keep the section heading, card grid, icon system, and stance classes. Change `_render_summary` to render:

- one lead paragraph from `overall_verdict.teacher_takeaway`;
- one large verdict card titled `总体使用建议`;
- three teacher priority cards from `teacher_priorities`;
- one compact evidence scale row.

Rendering rules:

```python
verdict = _dict(_dict(summary.get("overall_verdict")))
priorities = [_dict(item) for item in _items(summary.get("teacher_priorities"))]
scale = _dict(summary.get("evidence_scale"))
```

Teacher-facing labels:

```python
[
    ("覆盖题目", scale.get("questions")),
    ("采分点", scale.get("scoring_units")),
    ("误区诊断点", scale.get("diagnostic_units")),
    ("需复核题", scale.get("reviewed_risk_items")),
]
```

Do not call `_render_evidence` inside `_render_summary`.

- [ ] **Step 4: Run focused HTML tests**

Run:

```bash
cd /home/ubuntu/biology-exam-analyzer
python3 -m pytest -q backend/test_report_commercial_html.py
```

Expected:

```text
passed
```

---

## Task 4: Add Teacher Review Chapters Without Changing Visual Style

**Files:**
- Modify: `/home/ubuntu/biology-exam-analyzer/backend/report_product_model.py`
- Modify: `/home/ubuntu/biology-exam-analyzer/backend/report_product_html.py`
- Test: `/home/ubuntu/biology-exam-analyzer/backend/test_report_commercial_html.py`

- [ ] **Step 1: Add failing tests for teacher review chapter names**

Append:

```python
def test_report_contains_teacher_review_chapter_axis():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})
    html = render_report_product_html(model)
    visible_html = html.split('<script id="productData"', 1)[0]

    for label in [
        "高考趋势匹配",
        "题目质量风险",
        "语言表述与价值风险",
        "知识覆盖与结构",
        "学情适配与使用建议",
    ]:
        assert label in visible_html
```

- [ ] **Step 2: Run test and confirm missing chapter labels**

Run:

```bash
cd /home/ubuntu/biology-exam-analyzer
python3 -m pytest -q backend/test_report_commercial_html.py::test_report_contains_teacher_review_chapter_axis
```

Expected:

```text
FAILED ... 高考趋势匹配 not found
```

- [ ] **Step 3: Build `exam_review` section in model**

Add model content:

```python
exam_review = {
    "trend_fit": {
        "title": "高考趋势匹配",
        "thesis": "检查情境化、实验探究、图表信息提取和综合推理是否真正进入题目任务。",
        "status": "基本匹配",
        "teacher_action": "保留体现真实情境和综合推理的题，复核只做材料包装但未增加能力要求的题。",
    },
    "quality_risks": {
        "title": "题目质量风险",
        "thesis": "优先识别科学性、答案唯一性、设问边界和评分可执行性问题。",
        "status": quality_risk_status,
        "teacher_action": quality_risk_action,
    },
    "language_and_fairness": {
        "title": "语言表述与价值风险",
        "thesis": "检查表述歧义、超长材料、现实情境不当和舆论/价值导向隐患。",
        "status": language_risk_status,
        "teacher_action": language_risk_action,
    },
    "knowledge_coverage": {
        "title": "知识覆盖与结构",
        "thesis": "判断知识点覆盖是否均衡，高分题是否承载核心能力，是否存在重复或遗漏。",
        "status": coverage_status,
        "teacher_action": coverage_action,
    },
    "student_fit": summarize_student_fit(...),
}
```

- [ ] **Step 4: Render `exam_review` as chapter cards**

Reuse existing chapter/report-section styling. Do not create nested cards inside cards. Render each axis as one un-nested review panel with:

- title;
- status;
- thesis;
- teacher action;
- optional linked figure/source note.

- [ ] **Step 5: Run HTML tests**

Run:

```bash
cd /home/ubuntu/biology-exam-analyzer
python3 -m pytest -q backend/test_report_commercial_html.py
```

Expected:

```text
passed
```

---

## Task 5: Rename Deep-Dive Language From Evidence Units To Question Review Details

**Files:**
- Modify: `/home/ubuntu/biology-exam-analyzer/backend/report_product_model.py`
- Modify: `/home/ubuntu/biology-exam-analyzer/backend/report_product_html.py`
- Test: `/home/ubuntu/biology-exam-analyzer/backend/test_report_commercial_html.py`

- [ ] **Step 1: Add failing tests for question-detail teacher language**

Append:

```python
def test_deep_dive_uses_question_review_language_not_internal_unit_language():
    model = build_report_product_model(sample_report_data_with_full_units(), {"recommendations": []})
    html = render_report_product_html(model)
    visible_html = html.split('<script id="productData"', 1)[0]

    assert "单题审查明细" in visible_html
    assert "质量判断" in visible_html
    assert "学生可能卡点" in visible_html
    assert "修订建议" in visible_html
    assert "评分证据 1" not in visible_html
    assert "诊断证据" not in visible_html
```

- [ ] **Step 2: Run test and confirm current copy fails**

Run:

```bash
cd /home/ubuntu/biology-exam-analyzer
python3 -m pytest -q backend/test_report_commercial_html.py::test_deep_dive_uses_question_review_language_not_internal_unit_language
```

Expected:

```text
FAILED ... 单题审查明细 not found
```

- [ ] **Step 3: Keep detailed evidence, change labels and grouping**

In HTML renderer:

- Rename `深入诊断` heading to `单题审查明细` if the section is primarily question-level review.
- Rename SEU visible headings to teacher labels:
  - `评分单元` -> `采分点 / 评分依据`
  - `诊断单元` -> `学生可能卡点`
  - `情境单元` -> `材料与情境信息`
- Keep underlying data keys unchanged to avoid pipeline churn.

- [ ] **Step 4: Run focused and full report HTML tests**

Run:

```bash
cd /home/ubuntu/biology-exam-analyzer
python3 -m pytest -q backend/test_report_commercial_html.py backend/test_report_product_model.py
```

Expected:

```text
passed
```

---

## Task 6: Regenerate Reports And Run Visual QA

**Files:**
- Generated: `/home/ubuntu/biology-exam-analyzer/reports/report_product_demo_20260516.html`
- Generated: `/home/ubuntu/biology-exam-analyzer/reports/report_product_demo_20260516.pdf`
- Sync to: `C:\Users\Administrator\Documents\New project\api\reports\report_product_demo_20260516.html`
- Sync to: `C:\Users\Administrator\Documents\New project\api\reports\report_product_demo_20260516.pdf`

- [ ] **Step 1: Run focused tests**

Run:

```bash
cd /home/ubuntu/biology-exam-analyzer
python3 -m pytest -q backend/test_report_product_model.py backend/test_report_commercial_html.py backend/test_report_product_publish.py
```

Expected:

```text
passed
```

- [ ] **Step 2: Regenerate current demo report through the existing API route**

Use the existing report route so `aggregate_report_data -> generate_insights -> write_report_artifacts` remains the exercised path:

```bash
cd /home/ubuntu/biology-exam-analyzer
curl -sS \
  -F "file=@uploads/20260514_132450_一模定稿.docx" \
  -F "mode=deep" \
  -F "generate_report=true" \
  -F "report_mode=full" \
  http://localhost:8001/api/analyze \
  -o /tmp/teacher_review_report_response.json
python3 - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path('/tmp/teacher_review_report_response.json').read_text(encoding='utf-8'))
report_url = payload.get('report_url') or payload.get('pdf_report_url') or payload.get('pdf_url')
html_url = payload.get('html_report_url') or payload.get('html_url')
print('report_url:', report_url)
print('html_report_url:', html_url)
if not report_url:
    raise SystemExit('missing report_url in API response')
PY
```

Then replace the fixed demo artifact names in place:

```bash
cd /home/ubuntu/biology-exam-analyzer
python3 - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path('/tmp/teacher_review_report_response.json').read_text(encoding='utf-8'))
pdf_name = Path(payload.get('report_url') or payload.get('pdf_report_url') or payload.get('pdf_url')).name
html_name = Path(payload.get('html_report_url') or payload.get('html_url') or '').name
if not html_name:
    html_name = Path(pdf_name).with_suffix('.html').name
reports = Path('reports')
(reports / pdf_name).replace(reports / 'report_product_demo_20260516.pdf')
(reports / html_name).replace(reports / 'report_product_demo_20260516.html')
print('html_bytes:', (reports / 'report_product_demo_20260516.html').stat().st_size)
print('pdf_bytes:', (reports / 'report_product_demo_20260516.pdf').stat().st_size)
PY
```

Expected:

```text
html_bytes: positive integer
pdf_bytes: positive integer
```

- [ ] **Step 3: Sync artifacts to local report path**

Run:

```powershell
scp jdcloud:/home/ubuntu/biology-exam-analyzer/reports/report_product_demo_20260516.html "C:\Users\Administrator\Documents\New project\api\reports\report_product_demo_20260516.html"
scp jdcloud:/home/ubuntu/biology-exam-analyzer/reports/report_product_demo_20260516.pdf "C:\Users\Administrator\Documents\New project\api\reports\report_product_demo_20260516.pdf"
```

Expected:

```text
HTML and PDF local file sizes update without permission errors.
```

- [ ] **Step 4: Run content scan**

Run a scan that asserts:

```text
visible_raw_terms: 0
mojibake_markers: 0
font_size_9_12: 0
teacher_summary_terms_present: True
pseudo_evidence_chips_in_summary: 0
```

- [ ] **Step 5: Run browser/visual verification**

Open:

```text
http://localhost:8877/report_product_demo_20260516.html
```

Verify:

```text
title: AI 试卷质量诊断报告
console errors/warnings: 0
desktop/mobile frontend audit: pass
custom overlap audit: desktop=0, mobile=0
```

---

## Acceptance Criteria

- Executive summary is understandable to a teacher without internal terminology.
- First viewport communicates:
  - overall use verdict;
  - priority review targets;
  - priority teaching points;
  - student-fit/use recommendation;
  - evidence scale.
- Report chapters explicitly cover:
  - high-exam trend fit;
  - item quality risks;
  - language/value/public-opinion risks;
  - knowledge coverage and paper structure;
  - student-fit and usage advice.
- Evidence is still traceable, but detailed evidence appears in later sections and methodology, not as pseudo-buttons in the summary.
- Visual style remains the current commercial report form.
- No new duplicate pipeline files are created.
- Focused tests pass.
- Final generated HTML/PDF are synced to local and remote.

## Review Notes For Executor

- Start from the frozen baseline if a regression needs comparison:
  `/home/ubuntu/biology-exam-analyzer/docs/baselines/2026-05-17-report-product-current-logic-baseline`
- The current untracked report files are intentional working files. Do not delete them.
- The prior full `backend/test_report*.py` suite has one unrelated existing failure in `backend/test_report_insights.py::TestGenerateInsights::test_gpt_failure_raises`; do not treat that as caused by this refactor unless it changes.
