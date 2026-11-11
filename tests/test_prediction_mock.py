import numpy as np
import pytest

from phishguard_vn.features import extract_features
from phishguard_vn.prediction import predict_url


def test_valid_url_cases_return_expected_result(
    valid_url_cases, mock_bundle, mock_model, mock_prediction_result
):
    for url in valid_url_cases.values():
        result = predict_url(url, mock_bundle)

        assert result == mock_prediction_result
        X = mock_model.predict.call_args.args[0]
        expected_features = extract_features(url)
        assert X.columns.tolist() == mock_bundle["feature_names"]
        assert X.shape == (1, len(expected_features))
        assert X.iloc[0].to_dict() == expected_features
        assert mock_model.predict_proba.call_args.args[0] is X
        mock_model.reset_mock()


def test_invalid_url_cases_are_rejected_before_model_call(
    invalid_url_cases, mock_bundle, mock_model
):
    for url in invalid_url_cases.values():
        with pytest.raises(ValueError, match="URL kh\u00f4ng h\u1ee3p l\u1ec7"):
            predict_url(url, mock_bundle)

    mock_model.predict.assert_not_called()
    mock_model.predict_proba.assert_not_called()


def test_missing_url_cases_are_rejected_before_model_call(
    missing_url_cases, mock_bundle, mock_model
):
    for url in missing_url_cases.values():
        with pytest.raises(ValueError, match="URL kh\u00f4ng h\u1ee3p l\u1ec7"):
            predict_url(url, mock_bundle)

    mock_model.predict.assert_not_called()
    mock_model.predict_proba.assert_not_called()


def test_feature_schema_mismatch_is_rejected_before_model_call(sample_url, mock_bundle, mock_model):
    mock_bundle["feature_names"] = mock_bundle["feature_names"][:-1]

    with pytest.raises(ValueError, match="Feature schema"):
        predict_url(sample_url, mock_bundle)

    mock_model.predict.assert_not_called()


def test_unknown_model_is_rejected(sample_url, mock_bundle, mock_model):
    with pytest.raises(ValueError, match="Kh\u00f4ng c\u00f3 model"):
        predict_url(sample_url, mock_bundle, model_name="missing_model")

    mock_model.predict.assert_not_called()


def test_unsupported_score_kind_is_rejected_after_prediction(sample_url, mock_bundle, mock_model):
    mock_bundle["score_kinds"]["mock_model"] = "unknown"

    with pytest.raises(ValueError, match="Lo\u1ea1i score ch\u01b0a h\u1ed7 tr\u1ee3"):
        predict_url(sample_url, mock_bundle)

    mock_model.predict.assert_called_once()
    mock_model.predict_proba.assert_not_called()


def test_non_finite_probability_is_rejected(sample_url, mock_bundle, mock_model):
    mock_model.predict_proba.return_value = np.array([[0.05, np.nan]])

    with pytest.raises(ValueError, match="Model tr\u1ea3 score kh\u00f4ng h\u1eefu h\u1ea1n"):
        predict_url(sample_url, mock_bundle)


def test_decision_function_model_returns_margin(sample_url, mock_bundle, mock_model):
    mock_bundle["score_kinds"]["mock_model"] = "decision_function"
    mock_model.decision_function.return_value = np.array([-0.4])

    result = predict_url(sample_url, mock_bundle)

    assert result["score"] == pytest.approx(-0.4)
    assert result["score_kind"] == "decision_function"
    assert "không phải xác suất" in result["score_definition"]
    mock_model.decision_function.assert_called_once()
    mock_model.predict_proba.assert_not_called()
