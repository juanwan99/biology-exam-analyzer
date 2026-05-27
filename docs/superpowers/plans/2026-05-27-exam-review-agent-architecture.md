# Exam Review Agent Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the exam-review architecture as an evidence-driven review agent rather than a single-shot LLM pipeline.

**Architecture:** The generation model remains a replaceable model provider. GenAI App Builder / Discovery Engine becomes the evidence and quality-gate layer: rank evidence before generation, check grounding after generation, and later call Agent Search `servingConfigs:answer` when a Data Store and Engine exist. Channel names must describe behavior, not billing assumptions.

**Tech Stack:** Python backend, existing `llm_client.py`, `services/evidence_gateway.py`, `services/evidence_context.py`, `services/analysis_service.py`, pytest, Discovery Engine REST APIs.

---

## Current Findings

- `Ranking API` and `Check Grounding API` work in the remote environment.
- The current Google project has no Discovery Engine Data Store or Engine: listing returns `200 {}`.
- Direct `generateGroundedContent` returns `404 Method not found` for REST `v1`, REST `v1alpha`, stream `v1alpha`, and official Python REST transport.
- Therefore `app_builder` must not mean "replace every LLM generation call with `generateGroundedContent`." That path blocks the product and does not match the useful Agent Search workflow.

## Target Channels

```text
model
  Direct model generation only. No Discovery Engine ranking or grounding required.

evidence
  Direct model generation plus Discovery Engine Ranking before question analysis and
  Check Grounding after report insights. This is the default quality-improvement path.

agent_search
  Future Search App / Data Store answer generation through servingConfigs:answer.
  It must fail closed until DISCOVERY_ENGINE_ENGINE_ID is configured and smoke-tested.
```

`app_builder`, `genai_app_builder`, `discovery`, and `grant` are aliases for `evidence`, not for unavailable grounded generation.

## Task 1: Replace Channel Semantics

**Files:**
- Modify: `remote_edit/biology-exam-analyzer/backend/services/review_channel.py`
- Modify: `remote_edit/biology-exam-analyzer/backend/llm_client.py`
- Modify: `remote_edit/biology-exam-analyzer/backend/services/analysis_service.py`
- Test: `remote_edit/biology-exam-analyzer/backend/test_llm_client.py`
- Test: `remote_edit/biology-exam-analyzer/backend/test_analysis_service_metadata.py`

- [x] **Step 1: Write failing tests**

Add tests proving:

```python
def test_app_builder_alias_is_evidence_enhanced_not_generation_only():
    from services.review_channel import normalize_review_channel, channel_uses_evidence
    assert normalize_review_channel("app_builder") == "evidence"
    assert channel_uses_evidence("app_builder") is True
```

```python
@pytest.mark.asyncio
async def test_evidence_channel_does_not_intercept_llm_generation():
    from llm_client import llm_call, set_llm_review_channel, reset_llm_review_channel
    token = set_llm_review_channel("evidence")
    try:
        with patch("llm_client.get_providers", return_value=_mock_providers()):
            with patch("llm_client._http_post", return_value=_responses_ok()):
                result = await llm_call([{"role": "user", "content": "hi"}])
    finally:
        reset_llm_review_channel(token)
    assert result
```

- [x] **Step 2: Run tests and verify failure**

Run:

```bash
python -m pytest remote_edit/biology-exam-analyzer/backend/test_llm_client.py remote_edit/biology-exam-analyzer/backend/test_analysis_service_metadata.py -q
```

Expected failure: existing code still treats `app_builder` as grounded generation.

- [x] **Step 3: Replace channel functions**

Implement one canonical channel in `review_channel.py`:

```python
APP_BUILDER_ALIASES = {"app_builder", "genai_app_builder", "discovery", "grant", "1000_grant"}
EVIDENCE_CHANNELS = {"evidence", "evidence_enhanced", "agent_evidence"} | APP_BUILDER_ALIASES
MODEL_CHANNELS = {"model", "llm", "standard"}
AGENT_SEARCH_CHANNELS = {"agent_search"}
```

`normalize_review_channel("app_builder")` returns `"evidence"`.

- [x] **Step 4: Remove `llm_call()` app_builder interception**

`llm_client.llm_call()` must not call Discovery Engine generation for `evidence`. It should use normal providers and include metadata:

```python
"review_channel": _review_channel.get()
```

Keep `generate_grounded_content` client code as a low-level gateway method, but do not wire it to normal LLM calls.

- [x] **Step 5: Replace channel usage assertions**

For `evidence`, assert:

```text
direct model calls are allowed
Discovery Engine Ranking is required for question analysis
Discovery Engine Check Grounding is required for report generation
Discovery Engine generateGroundedContent is not required
```

For `agent_search`, fail closed until a Search Engine ID exists and an `answer` smoke test passes.

- [x] **Step 6: Verify**

Run:

```bash
python -m pytest remote_edit/biology-exam-analyzer/backend/test_llm_client.py remote_edit/biology-exam-analyzer/backend/test_analysis_service_metadata.py -q
```

Expected: PASS.

## Task 2: Add Agent Search Answer Client Boundary

**Files:**
- Modify: `remote_edit/biology-exam-analyzer/backend/services/discovery_engine_client.py`
- Modify: `remote_edit/biology-exam-analyzer/backend/services/evidence_gateway.py`
- Test: `remote_edit/biology-exam-analyzer/backend/test_discovery_engine_client.py`
- Test: `remote_edit/biology-exam-analyzer/backend/test_evidence_gateway.py`

- [x] **Step 1: Add tests**

Test URL:

```text
https://discoveryengine.googleapis.com/v1/projects/{project_id}/locations/{location}/collections/default_collection/engines/{engine_id}/servingConfigs/default_search:answer
```

Request body must include:

```json
{
  "query": {"text": "题目审题问题"},
  "answerGenerationSpec": {
    "ignoreAdversarialQuery": true,
    "includeCitations": true
  }
}
```

- [x] **Step 2: Implement `answer_query()`**

`DiscoveryEngineClient.answer_query()` requires `DISCOVERY_ENGINE_ENGINE_ID`. If missing, raise a clear config error:

```text
DISCOVERY_ENGINE_ENGINE_ID is required for agent_search answer generation; create a Data Store and Search App first.
```

- [x] **Step 3: Gateway wrapper**

`EvidenceGateway.answer_query()` extracts answer text, citation count, and raw response. Missing answer text is a structured failure.

- [x] **Step 4: Verify**

Run:

```bash
python -m pytest remote_edit/biology-exam-analyzer/backend/test_discovery_engine_client.py remote_edit/biology-exam-analyzer/backend/test_evidence_gateway.py -q
```

Expected: PASS.

## Task 3: Build Evidence Agent Audit Contract

**Files:**
- Create: `remote_edit/biology-exam-analyzer/backend/services/evidence_audit.py`
- Modify: `remote_edit/biology-exam-analyzer/backend/services/analysis_service.py`
- Test: `remote_edit/biology-exam-analyzer/backend/test_analysis_service_metadata.py`

- [x] **Step 1: Define audit summary**

Create:

```python
def summarize_evidence_usage(questions: list[dict], insights: dict | None = None) -> dict:
    ...
```

Return counts for direct model generation, ranking, grounding, agent search answer, unsupported generation, evidence gaps, and question ids missing evidence.

- [x] **Step 2: Replace ad hoc channel usage**

`AnalysisService.build_channel_usage()` should delegate to `summarize_evidence_usage()`.

- [x] **Step 3: Make failure messages teacher-readable**

Failures must say which phase failed:

```text
证据增强审题失败：第 21 题缺少 Ranking 证据，不能进入正式报告。
```

- [x] **Step 4: Verify**

Run:

```bash
python -m pytest remote_edit/biology-exam-analyzer/backend/test_analysis_service_metadata.py -q
```

Expected: PASS.

## Task 4: Remote Smoke Gates

**Files:**
- Create: `artifacts/evidence_agent_smoke_20260527.py`

- [x] **Step 1: Smoke Ranking**

Call Ranking with a biology question and confirm `rank_status=ok`.

- [x] **Step 2: Smoke Check Grounding**

Call Check Grounding with a supported claim and confirm `support_score >= 0.6`.

- [x] **Step 3: Smoke Agent Search Inventory**

List engines and data stores. If none exist, report:

```text
agent_search unavailable: no Data Store / Engine configured
```

- [x] **Step 4: Verify no fake success**

The smoke must exit non-zero only for Ranking/Grounding failure. Missing Engine is a known unavailable state, not a silent success.

## Task 5: Agent Search Provisioning Boundary

**Files:**
- Create: `remote_edit/biology-exam-analyzer/backend/services/agent_search_corpus.py`
- Modify: `remote_edit/biology-exam-analyzer/backend/services/discovery_engine_client.py`
- Create: `artifacts/provision_agent_search_20260527.py`
- Test: `remote_edit/biology-exam-analyzer/backend/test_agent_search_corpus.py`
- Test: `remote_edit/biology-exam-analyzer/backend/test_discovery_engine_client.py`

- [x] **Step 1: Add provisioning client methods**

`DiscoveryEngineClient` now exposes `create_data_store()`, `create_engine()`, `import_documents()` and `get_operation()`.

- [x] **Step 2: Build importable corpus documents**

`build_agent_search_documents()` produces Discovery Engine Document objects with `structData` and base64 `text/plain` content.

- [x] **Step 3: Add dry-run provisioning script**

`artifacts/provision_agent_search_20260527.py` writes the corpus JSONL by default. It only creates cloud resources when called with `--apply`.

- [x] **Step 4: Verify**

Local backend tests passed with the provisioning boundary included.

## Completion Criteria

- `evidence` channel runs model generation plus Ranking/Grounding quality gates.
- `agent_search` channel is a separate fail-closed mode, not hidden behind `app_builder`.
- No normal LLM call is silently replaced by unavailable `generateGroundedContent`.
- Channel audit clearly reports ranking, grounding, direct model calls, and unavailable Agent Search state.
- Local targeted tests pass.
- Remote targeted tests pass in `biology_backend`.
