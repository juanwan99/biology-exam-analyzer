# Diagnosis Graph Metadata Fidelity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the commercial report's whole-exam diagnosis traceable to SEU/DU/SU-level evidence instead of compressed question-level summaries.

**Architecture:** Preserve the full fine-grained analysis contract in `report_data`, derive fact tables in `report_product_model`, and generate structured findings that bind summary claims to evidence refs. Web/PDF rendering can then consume the same model without inventing conclusions in the UI.

**Tech Stack:** Python report model code, pytest, existing SVG/HTML report renderer.

---

### Task 1: Preserve Fine-Grained Metadata In Report Data

**Files:**
- Modify: `backend/report_data.py`
- Test: `backend/test_report_data.py`

- [ ] Add `fine_grained_units` to each question detail when `analysis._fine_grained` exists.
- [ ] Preserve `scoring_units`, `diagnostic_units`, and `stimulus_units` exactly enough for report modeling.
- [ ] Keep the old `seu_knowledge_breakdown` and `diagnostic_highlights` fields for backward compatibility.
- [ ] Add a regression test proving `competency_weights`, `difficulty_estimate`, `allocation_confidence`, and multiple knowledge links survive aggregation.

### Task 2: Build SEU/DU/SU Fact Tables

**Files:**
- Modify: `backend/report_product_model.py`
- Test: `backend/test_report_commercial_model.py`

- [ ] Make `_question_fine_grained()` read `question.fine_grained_units` before falling back to compressed detail fields.
- [ ] Add `knowledge_contribution_rows` using `question_score * score_share * knowledge_link.share`.
- [ ] Add `competency_contribution_rows` using `question_score * score_share * competency_weight`.
- [ ] Add `metadata_audit_rows` with share-sum checks, unit counts, confidence, and warnings.
- [ ] Preserve full per-SEU fields in `seu_rows`.

### Task 3: Generate Evidence-Bound Findings

**Files:**
- Modify: `backend/report_product_model.py`
- Test: `backend/test_report_commercial_model.py`

- [ ] Add `findings[]` to the report model.
- [ ] Each finding must include `claim`, `metrics`, `contributors`, `evidence_refs`, `confidence`, and `recommended_action`.
- [ ] Feed top findings into `executive_summary.big_calls` so the first screen is evidence-backed.
- [ ] Keep existing big-call heuristics as fallback.

### Task 4: Verify And Regenerate Demo

**Files:**
- Existing tests only for this batch.

- [ ] Run focused tests for report data and commercial model.
- [ ] Run the existing commercial report test group.
- [ ] Regenerate the product demo report after tests pass.
- [ ] Verify the served HTML/PDF still load.

---

### Semantic Regression

- A question remains a container; SEU/DU/SU are the analysis units.
- No finding may enter the executive summary without evidence refs.
- Existing compressed fields remain available for legacy rendering.
- No new LLM call is introduced in this batch.
- Programmatic aggregation takes precedence over LLM prose for weights and contribution ranking.
