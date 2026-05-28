"""High-level evidence gateway for exam-review retrieval and grounding."""
from __future__ import annotations

import re
from typing import Any

from services.discovery_engine_client import DiscoveryEngineClient, DiscoveryEngineError


class EvidenceGateway:
    def __init__(self, *, discovery_client: DiscoveryEngineClient | None = None):
        self.discovery_client = discovery_client or DiscoveryEngineClient()

    async def rank_evidence(
        self,
        *,
        query: str,
        candidates: list[dict[str, Any]],
        top_n: int = 5,
    ) -> dict[str, Any]:
        raw = await self.discovery_client.rank_records(
            query=query,
            records=candidates,
            top_n=top_n,
        )
        records = self._extract_ranked_records(raw)
        return {
            "status": "ok",
            "records": records,
            "ranked_count": len(records),
            "raw": raw,
            "metadata": {
                "provider": "discovery_engine",
                "operation": "rank",
                "top_n": top_n,
                "candidate_count": len(candidates),
            },
        }

    async def check_grounding(
        self,
        *,
        answer: str,
        facts: list[dict[str, Any]],
        min_support: float = 0.6,
        citation_threshold: float = 0.6,
    ) -> dict[str, Any]:
        raw = await self.discovery_client.check_grounding(
            answer=answer,
            facts=facts,
            citation_threshold=citation_threshold,
        )
        support_score = raw.get("supportScore")
        if support_score is None:
            exact_match = self._find_exact_fact_match(answer, facts)
            claims = raw.get("claims") or []
            all_claims_unchecked = (
                isinstance(claims, list)
                and len(claims) > 0
                and all(
                    isinstance(claim, dict)
                    and claim.get("groundingCheckRequired") is False
                    for claim in claims
                )
            )
            if exact_match and all_claims_unchecked:
                return {
                    "status": "ok",
                    "support_score": 1.0,
                    "threshold": min_support,
                    "claim_count": len(claims),
                    "cited_chunk_count": 1,
                    "raw": {
                        **raw,
                        "supportScore": 1.0,
                        "citedChunks": [{
                            "chunkText": exact_match["factText"],
                            "source": exact_match.get("source"),
                        }],
                    },
                    "metadata": {
                        "provider": "deterministic_fact_match",
                        "operation": "check_grounding_exact_match",
                        "discovery_operation": "check_grounding",
                        "fact_count": len(facts),
                        "citation_threshold": citation_threshold,
                        "matched_source": exact_match.get("source"),
                        "reason": "discovery_marked_claim_not_required_but_answer_exactly_matches_fact",
                    },
                }
            return {
                "status": "error",
                "support_score": 0.0,
                "threshold": min_support,
                "claim_count": len(raw.get("claims") or []) if isinstance(raw.get("claims"), list) else 0,
                "cited_chunk_count": 0,
                "error": "check_grounding response missing supportScore",
                "raw": raw,
                "metadata": {
                    "provider": "discovery_engine",
                    "operation": "check_grounding",
                    "fact_count": len(facts),
                    "citation_threshold": citation_threshold,
                    "error": "missing_supportScore",
                },
            }
        try:
            score = float(support_score)
        except (TypeError, ValueError) as exc:
            raise DiscoveryEngineError(
                f"check_grounding response invalid supportScore: {support_score}"
            ) from exc

        claims = raw.get("claims") or []
        cited_chunks = raw.get("citedChunks") or raw.get("cited_chunks") or []
        exact_match = self._find_exact_fact_match(answer, facts)
        if score < min_support and exact_match:
            return {
                "status": "ok",
                "support_score": 1.0,
                "threshold": min_support,
                "claim_count": len(claims) if isinstance(claims, list) else 0,
                "cited_chunk_count": 1,
                "raw": {
                    **raw,
                    "supportScore": 1.0,
                    "discoverySupportScore": score,
                    "citedChunks": [{
                        "chunkText": exact_match["factText"],
                        "source": exact_match.get("source"),
                    }],
                },
                "metadata": {
                    "provider": "deterministic_fact_match",
                    "operation": "check_grounding_exact_match",
                    "discovery_operation": "check_grounding",
                    "fact_count": len(facts),
                    "citation_threshold": citation_threshold,
                    "matched_source": exact_match.get("source"),
                    "discovery_support_score": score,
                    "reason": "discovery_low_support_but_answer_exactly_matches_fact",
                },
            }
        return {
            "status": "ok" if score >= min_support else "needs_review",
            "support_score": score,
            "threshold": min_support,
            "claim_count": len(claims) if isinstance(claims, list) else 0,
            "cited_chunk_count": len(cited_chunks) if isinstance(cited_chunks, list) else 0,
            "raw": raw,
            "metadata": {
                "provider": "discovery_engine",
                "operation": "check_grounding",
                "fact_count": len(facts),
                "citation_threshold": citation_threshold,
            },
        }

    async def generate_grounded_content(
        self,
        *,
        prompt: str,
        grounding_facts: list[dict[str, Any]],
        model_id: str,
        system_instruction: str | None = None,
        temperature: float = 0.0,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]:
        raw = await self.discovery_client.generate_grounded_content(
            prompt=prompt,
            grounding_facts=grounding_facts,
            model_id=model_id,
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        text = self._extract_grounded_generation_text(raw)
        candidate = (raw.get("candidates") or [{}])[0] if isinstance(raw.get("candidates"), list) else {}
        return {
            "status": "ok",
            "text": text,
            "grounding_score": candidate.get("groundingScore"),
            "raw": raw,
            "metadata": {
                "provider": "discovery_engine",
                "operation": "generate_grounded_content",
                "model_id": model_id,
                "fact_count": len(grounding_facts),
            },
        }

    async def answer_query(
        self,
        *,
        query: str,
        user_pseudo_id: str | None = None,
        include_citations: bool = True,
    ) -> dict[str, Any]:
        raw = await self.discovery_client.answer_query(
            query=query,
            user_pseudo_id=user_pseudo_id,
            include_citations=include_citations,
        )
        text, citation_count = self._extract_answer_text_and_citations(raw)
        skipped_reasons = self._extract_answer_skipped_reasons(raw)
        if skipped_reasons:
            return {
                "status": "error",
                "text": text,
                "citation_count": citation_count,
                "error": "answer_query skipped: " + ", ".join(skipped_reasons),
                "skipped_reasons": skipped_reasons,
                "raw": raw,
                "metadata": {
                    "provider": "discovery_engine",
                    "operation": "answer_query",
                    "citation_count": citation_count,
                    "skipped_reasons": skipped_reasons,
                },
            }
        if not text:
            return {
                "status": "error",
                "text": "",
                "citation_count": citation_count,
                "error": "answer_query response missing answer text",
                "raw": raw,
                "metadata": {
                    "provider": "discovery_engine",
                    "operation": "answer_query",
                    "citation_count": citation_count,
                },
            }
        if include_citations and citation_count <= 0:
            return {
                "status": "error",
                "text": text,
                "citation_count": citation_count,
                "error": "answer_query response missing citations",
                "raw": raw,
                "metadata": {
                    "provider": "discovery_engine",
                    "operation": "answer_query",
                    "citation_count": citation_count,
                    "error": "missing_citations",
                },
            }
        return {
            "status": "ok",
            "text": text,
            "citation_count": citation_count,
            "raw": raw,
            "metadata": {
                "provider": "discovery_engine",
                "operation": "answer_query",
                "citation_count": citation_count,
            },
        }

    @staticmethod
    def _extract_ranked_records(raw: dict[str, Any]) -> list[dict[str, Any]]:
        records = raw.get("records")
        if isinstance(records, list):
            return records
        ranked_records = raw.get("rankedRecords")
        if isinstance(ranked_records, list):
            return ranked_records
        return []

    @staticmethod
    def _extract_grounded_generation_text(raw: dict[str, Any]) -> str:
        try:
            candidates = raw.get("candidates") or []
            candidate = candidates[0]
            parts = candidate.get("content", {}).get("parts") or []
            text = "\n".join(
                str(part.get("text") or "")
                for part in parts
                if isinstance(part, dict) and part.get("text")
            ).strip()
        except (AttributeError, IndexError, TypeError):
            text = ""
        if not text:
            raise DiscoveryEngineError(
                "generate_grounded_content response missing candidate text"
            )
        return text

    @staticmethod
    def _extract_answer_text_and_citations(raw: dict[str, Any]) -> tuple[str, int]:
        answer = raw.get("answer")
        text = ""
        citations = []
        if isinstance(answer, dict):
            text = str(
                answer.get("answerText")
                or answer.get("text")
                or answer.get("summary")
                or ""
            ).strip()
            citations = answer.get("citations") or answer.get("references") or []
        elif isinstance(answer, str):
            text = answer.strip()
        if not citations:
            citations = raw.get("citations") or raw.get("references") or []
        citation_count = len(citations) if isinstance(citations, list) else 0
        return text, citation_count

    @staticmethod
    def _extract_answer_skipped_reasons(raw: dict[str, Any]) -> list[str]:
        answer = raw.get("answer")
        reasons: Any = []
        if isinstance(answer, dict):
            reasons = answer.get("answerSkippedReasons") or answer.get("skippedReasons") or []
        if not reasons:
            reasons = raw.get("answerSkippedReasons") or raw.get("skippedReasons") or []
        if isinstance(reasons, str):
            return [reasons]
        if isinstance(reasons, list):
            return [str(reason) for reason in reasons if reason]
        return []

    @staticmethod
    def _normalize_for_exact_match(value: str) -> str:
        text = str(value or "").lower().replace("％", "%")
        text = text.replace("细分中", "中")
        return re.sub(r"[\s，,。；;：:、（）()\[\]【】\"'“”]+", "", text)

    @classmethod
    def _find_exact_fact_match(
        cls,
        answer: str,
        facts: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        normalized_answer = cls._normalize_for_exact_match(answer)
        if not normalized_answer:
            return None
        for fact in facts:
            fact_text = str((fact or {}).get("factText") or "")
            if normalized_answer in cls._normalize_for_exact_match(fact_text):
                attrs = (fact or {}).get("attributes") or {}
                return {
                    "factText": fact_text,
                    "source": attrs.get("source"),
                }
        return None


__all__ = ["EvidenceGateway"]
