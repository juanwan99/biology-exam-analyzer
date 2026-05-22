# Metadata Lineage Inventory

## Scope
This inventory covers the biology exam analysis LLM chain: prompt contracts, parsed schemas, field lineage, report-time governance, and consuming boundaries. Runtime authority is `_llm_calls`, `_metadata_envelope`, and `metadata_quality`.

## LLM Calls
| Stage | Count | purpose | prompt_id | schema | Main dimensions | Parsed fields | Consumer |
| --- | ---: | --- | --- | --- | --- | --- | --- |
| Split | 1 per LLM-split exam | `split_questions` | `biology.split_questions` | `SplitQuestionList` | question ids, text, image indexes, score clues | `id`, `content`, `image_indices`, `total_score`, `sub_questions` | entry metadata, not scoring |
| Question analysis | 1 per question, compact retry on invalid v2 JSON | `question_analysis` | `biology.question_analysis.v1/v2` or `biology.question_analysis.v2.compact_retry` | `AnalysisResult` or `FineGrainedResult` | knowledge, answer, explanation, SEU/DU/SU, Bloom, competency clues | `knowledge_points`, `answer`, `detailed_analysis`, `_fine_grained`, `total_score`, `_extraction_confidence` | factual base for downstream analysis |
| Feature extraction | 1 per normal question, retry up to 1 | `feature_extraction` | `biology.feature_extraction` | `FeatureResult` | working memory, reasoning steps, coupling, traps, novelty, breadth, quality | scoring features, `quality_*`, `teacher_comment` | scoring plus report quality |
| Big-question features | 1 per big question | `big_question_feature_extraction` | `biology.big_question_feature_extraction` | `BigQuestionFeatureResult` | subquestions, dependency graph, shared context, method novelty | `subquestions`, `dependencies`, `global_features`, `report` | big-question scoring and report |
| Competency | 1 per question or v2 supplement | `competency_analysis` | `biology.competency_analysis` | `CompetencyResult` | four biology competencies | dimension weights/details, `primary_competency`, `competency_level` | competency report; v2 SEU weights stay authoritative |
| Report insights | 1 per report | `report_insights` | `biology.report_insights` | `InsightsResult` | whole-exam difficulty, knowledge, competency, Bloom, diagnostics, metadata quality | `overall_assessment`, `recommendations`, `*_analysis` | PDF report text |
| Teaching suggestions | 1 per report | `report_teaching_suggestions` | `biology.report_teaching_suggestions` | `TeachingSuggestions` | error categories, lecture outline, remediation | `error_categories`, `lecture_outline`, `remedial_exercises` | PDF teaching section |

## Required Metadata
Every `_llm_calls[]` item must include `call_id`, `purpose`, `prompt_id`, `prompt_hash`, `provider`, `model`, `input_refs`, `parsed_schema`, `confidence`, `validation_errors`, `fallback_count`, `retry_count`, and `metadata`.

## Question Envelope
`AnalysisService.analyze_question()` collects split, question-analysis, feature, and competency calls into `_metadata_envelope`:
- `question`: id, content, question type, score.
- `llm_calls`: validated and deduplicated call records.
- `analysis_units`: v2 SEU/DU/SU when available.
- `derived`: knowledge points, final difficulty, primary competency.
- `confidence`: overall, analysis, features, competency.
- `lineage`: `knowledge_points -> analysis.knowledge_points`, `difficulty_features -> difficulty.features`, `competency -> competency`.

## Report Gate
`AnalysisService.validate_report_metadata()` runs before PDF generation:
- Missing `_metadata_envelope`, missing `llm_calls`, missing required call fields, or missing required purposes blocks report generation.
- Required purposes are `question_analysis` and one of `feature_extraction` / `big_question_feature_extraction`.
- Competency source is valid when either `competency_analysis` exists or the envelope contains v2 SEU-derived competency weights; SEU-derived competency is authoritative.
- Low overall confidence does not block, but is surfaced in `metadata_quality.low_confidence_questions`.
- Envelope warnings are surfaced in `metadata_quality.warning_questions` and included in the report LLM prompt under `## 元数据治理`.
- `run_full_analysis()` and `run_auto_analysis()` return `metadata_quality` in the API result even when PDF generation is disabled.
- `_render_html()` renders a visible metadata governance summary in the PDF HTML so risks are not only implicit in LLM prose.
- Legacy route-level aggregation in `analysis_router.py` also returns `metadata_quality`; direct route-level PDF generation must call `_validate_report_metadata_for_route()` before building report data.

## Governance Rules
- LLM output without `prompt_hash/purpose/parsed_schema/confidence` is not trusted metadata.
- Scoring fields come only from rule-defined features and SEU weights; report fields must not overwrite scoring fields.
- v2 SEU-derived competency weights take precedence; independent competency analysis only supplements detailed dimensions/explanations.
- `feature_status=partial/failed` must enter envelope warnings and report metadata quality.

## Critical Path Fixes (2026-05-16)
- Proxy: sing-box now exposes a Docker-reachable mixed inbound on `172.17.0.1:7890`; container probe reached Google OAuth through the proxy.
- Throughput: analysis concurrency defaults to `MAX_WORKERS=4`; questions with incomplete required metadata retry sequentially once.
- Long questions: short-answer/non-choice analysis uses a 240s timeout.
- Invalid v2 JSON: question analysis performs compact retry and records `retry_count`, initial parse error, response length, and normalization notes.
- Schema drift: compact v2 retry normalizes `kp_id -> knowledge_point`, Chinese/English Bloom labels, string confidence/difficulty values, and object answers.
- Report robustness: diagnostics/report data tolerate `analysis=None` and SEU `competency=None` with `competency_weights`.
- Real exam evidence: `real_exam_smoke_20260516_093527` split 21 questions, produced 21 envelopes, 63 LLM call records, zero missing required metadata, and generated `/api/reports/real_exam_smoke_20260516_093527.pdf` (345534 bytes).
