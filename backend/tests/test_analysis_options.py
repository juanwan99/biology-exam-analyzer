from analysis_options import set_analysis_options, want_aux_features, want_competency_supplement, get_analysis_options


def test_defaults_keep_unit_test_behavior():
    assert want_aux_features() is True
    assert want_competency_supplement() is True


def test_analyze_without_report_skips_aux(monkeypatch):
    monkeypatch.delenv("FEATURE_AUX_ALWAYS", raising=False)
    monkeypatch.delenv("COMPETENCY_SUPPLEMENT", raising=False)
    set_analysis_options(generate_report=False, report_mode="full")
    assert want_aux_features() is False
    assert want_competency_supplement() is False


def test_analyze_with_report_keeps_aux(monkeypatch):
    monkeypatch.delenv("FEATURE_AUX_ALWAYS", raising=False)
    set_analysis_options(generate_report=True, report_mode="full")
    assert want_aux_features() is True
    assert want_competency_supplement() is True
    assert get_analysis_options()["generate_report"] is True
