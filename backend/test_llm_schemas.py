from llm_schemas import FeatureResult, FineGrainedResult, validate_llm_output


def test_validate_llm_output_fails_closed_without_model_construct():
    data = {"working_memory": "not-a-number"}

    validated, confidence, errors = validate_llm_output(data, FeatureResult, "unit-test")

    assert validated == data
    assert confidence == 0.0
    assert errors


def test_validate_llm_output_construct_is_explicit_opt_in():
    data = {"working_memory": "not-a-number"}

    validated, confidence, errors = validate_llm_output(
        data,
        FeatureResult,
        "unit-test",
        allow_construct=True,
    )

    assert validated["working_memory"] == "not-a-number"
    assert confidence == 0.5
    assert errors


def test_fine_grained_score_share_mismatch_fails_validation():
    data = {
        "total_score": 12,
        "scoring_units": [
            {
                "seu_id": "1",
                "label": "unit 1",
                "score_share": 0.4,
                "knowledge_links": [{"knowledge_point": "遗传", "share": 1.0}],
            },
            {
                "seu_id": "2",
                "label": "unit 2",
                "score_share": 0.4,
                "knowledge_links": [{"knowledge_point": "表达", "share": 1.0}],
            },
        ],
    }

    validated, confidence, errors = validate_llm_output(data, FineGrainedResult, "unit-test")

    assert validated == data
    assert confidence == 0.0
    assert any("score_share sum=0.800" in error for error in errors)
