# -*- coding: utf-8 -*-
"""Per-request analysis knobs (copied into asyncio tasks via ContextVar)."""
from __future__ import annotations

import os
from contextvars import ContextVar

_options: ContextVar[dict] = ContextVar("analysis_options", default=None)


def set_analysis_options(*, generate_report=False, report_mode="full"):
    aux_always = os.getenv("FEATURE_AUX_ALWAYS", "").strip() in {"1", "true", "TRUE", "yes"}
    comp_always = os.getenv("COMPETENCY_SUPPLEMENT", "").strip() in {"1", "true", "TRUE", "yes"}
    _options.set({
        "generate_report": bool(generate_report),
        "report_mode": report_mode or "full",
        "aux_features": bool(generate_report) or aux_always,
        "competency_supplement": bool(generate_report) or comp_always,
    })


def get_analysis_options() -> dict:
    return _options.get() or {
        "generate_report": False,
        "report_mode": "full",
        "aux_features": True,
        "competency_supplement": True,
    }


def want_aux_features() -> bool:
    return bool(get_analysis_options().get("aux_features", True))


def want_competency_supplement() -> bool:
    return bool(get_analysis_options().get("competency_supplement", True))
