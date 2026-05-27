# Full Tested Architecture Handoff

Date: 2026-05-27

## Authoritative Baseline

Remote repo:

```text
/home/ubuntu/biology-exam-analyzer
```

Branch and tag:

```text
branch: clean-for-submission
tag: baseline-2026-05-27-full-tested-architecture
commit: 07250fc9aefa61f22c8e9368d135835d8e98ca89
```

Local clean copy:

```text
C:\Users\Administrator\Documents\New project\remote_edit\biology-exam-analyzer-clean-20260527
```

The older local directory below is retained as historical working material and should not be used as the current baseline:

```text
C:\Users\Administrator\Documents\New project\remote_edit\biology-exam-analyzer
```

## Review Architecture

The review pipeline now has explicit channel semantics:

- `model`: standard model-only path.
- `app_builder` / `evidence`: Gemini generation plus Discovery Engine Ranking and Check Grounding.
- `agent_search`: evidence path plus Agent Search `answer_query` with required citations.
- `grounded_generation`: experimental path, not the default production route.

The important point is that App Builder is not pretending to make Gemini generation free. It is used where it fits the product: evidence ranking, cited Agent Search answers, and grounding checks.

## No Silent Failure Contract

Current contract:

- LLM parse or validation failures are recorded and block report generation.
- Provider fallback is recorded through `fallback_count` / provider errors and blocks formal report generation.
- Discovery Engine Ranking failures do not produce fake evidence.
- Agent Search answers without citations do not count as success.
- Check Grounding failures or missing checks block the evidence channel.
- Internal SEU derivation, competency supplement, or competency merge degradation now enters metadata warnings and pipeline gate checks.

## Verification

Backend full suite:

```bash
docker exec -w /app -e PYTHONPATH=/app biology_backend python -m pytest -q
```

Result:

```text
592 passed, 8 warnings
```

Frontend build:

```bash
cd frontend && npm run build
```

Result: passed.

Latest report audit:

```text
questions=21
pipeline_status=ok
blockers=0
warnings=0
discovery_rank_count=21
agent_search_answer_count=21
discovery_grounding_check_count=57
unsupported_generation_count=0
missing_rank_question_ids=[]
evidence_gap_questions=[]
```

Latest PDF visual check:

```text
zhuzhou_yimo_arch_agent_search_qualityroot_pdfrootfix_20260527.pdf
pages=15
problem_count=0
```

## Latest Report Artifacts

Remote:

```text
/home/ubuntu/biology-exam-analyzer/reports/zhuzhou_yimo_arch_agent_search_qualityroot_pdfrootfix_20260527.html
/home/ubuntu/biology-exam-analyzer/reports/zhuzhou_yimo_arch_agent_search_qualityroot_pdfrootfix_20260527.pdf
/home/ubuntu/biology-exam-analyzer/reports/zhuzhou_yimo_arch_agent_search_qualityroot_e2e_20260527.response.json
```

Local:

```text
C:\Users\Administrator\Documents\New project\api\reports\zhuzhou_yimo_arch_agent_search_qualityroot_pdfrootfix_20260527.html
C:\Users\Administrator\Documents\New project\api\reports\zhuzhou_yimo_arch_agent_search_qualityroot_pdfrootfix_20260527.pdf
```

## Next Work

Recommended next step is not more patching. Use the clean baseline and run a fresh E2E from the frontend/API with `exam_review_channel=agent_search` or `app_builder`, then compare the generated response audit against the contract above.
