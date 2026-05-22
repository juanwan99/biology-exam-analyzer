# Metadata Governance Handoff

## Goal
Metadata governance is now on the critical path: LLM calls emit `_llm_calls`, analyzed questions carry `_metadata_envelope`, API/PDF expose `metadata_quality`, and PDF generation is blocked when required lineage is missing.

## Must Preserve
- Preserve existing `/api/analyze_auto` business semantics; only add audit metadata, envelope, route/report gates, and visibility.
- Preserve v2 SEU-derived competency as authoritative; `competency_analysis` is supplemental when present.
- Preserve Docker proxy path `172.17.0.1:7890`, `MAX_WORKERS=4`, sequential metadata retry, long-question 240s timeout, compact v2 retry, and schema normalization notes.

## Must Not Change
- Do not overwrite `.env`, `.secrets/`, uploads, generated reports, or unrelated dirty files.
- Do not relax report metadata gate to hide missing envelopes.
- Do not make report rendering consume raw unvalidated LLM dicts directly.

## Evidence
- Tests: metadata/report suite `47 passed, 6 warnings`.
- Real exam: `real_exam_smoke_20260516_093527` -> 21 questions, 21 envelopes, 63 LLM calls, zero required metadata gaps.
- Report: `/api/reports/real_exam_smoke_20260516_093527.pdf`, file size 345534 bytes.
- Health after restart: `status=healthy`, database `ok`, `llm_providers=2`.
