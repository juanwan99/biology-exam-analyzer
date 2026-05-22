from report_product_model import build_report_product_model
from test_report_commercial_model import sample_report_data


def test_product_model_uses_single_commercial_report_contract():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})

    assert "meta" not in model
    assert "hero_conclusions" not in model
    assert set(model) >= {
        "cover",
        "credibility",
        "executive_summary",
        "at_a_glance",
        "chapters",
        "question_portfolio",
        "deep_dives",
        "methodology",
    }
    assert model["cover"]["report_version"] == "commercial_report.v1"
    assert model["credibility"]["llm_calls_total"] == 63
    assert model["executive_summary"]["big_calls"][0]["evidence_refs"]
    assert model["question_portfolio"]["rows"][0]["metadata_confidence"] is not None
