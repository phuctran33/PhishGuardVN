"""Offline stress contract tests with explicit expected validity and denominators."""
import numpy as np
import pandas as pd
import pytest
from phishguard_vn.features import CANDIDATE_FEATURES, extract_features
from phishguard_vn.robustness import BASE_URLS, run_robustness, robustness_summary, transformations
from phishguard_vn.url_parser import parse_url


@pytest.mark.parametrize("transform", transformations(), ids=lambda t: t.name)
def test_transformation_contract(transform):
    for base in BASE_URLS:
        url = transform.apply(base)
        assert transform.apply(base) == url
        parsed = parse_url(url)
        assert parsed.is_valid == transform.expected_valid
        values = extract_features(url)
        assert tuple(values) == CANDIDATE_FEATURES
        if parsed.is_valid: assert np.isfinite(list(values.values())).all()
        else: assert all(v is None for v in values.values())


def test_reproducible_coverage_and_no_accuracy(monkeypatch):
    import socket
    def deny(*args, **kwargs): raise AssertionError("network is prohibited")
    monkeypatch.setattr(socket.socket, "connect", deny)
    a = run_robustness(lambda u: min(0.99, len(u) / 100))
    b = run_robustness(lambda u: min(0.99, len(u) / 100))
    pd.testing.assert_frame_equal(a, b)
    assert len(a) == 144
    assert a.validity_check_pass.all()
    assert a.loc[a.label_policy.eq("label-preserving"), "resource_equivalence_check"].all()
    summary = robustness_summary(a)
    assert not {"accuracy", "f1", "recall"} & set(summary)
    malformed = summary.loc[summary.transformation.eq("bad_ipv6")].iloc[0]
    assert malformed.paired_predictions == 0 and pd.isna(malformed.prediction_flip_rate)
    assert malformed.expected_validity_pass_rate == 1


def test_invalid_cases_never_predict_and_model_failures_counted():
    def predictor(url):
        assert parse_url(url).is_valid
        raise RuntimeError("synthetic predictor error")
    cases = run_robustness(predictor)
    summary = robustness_summary(cases)
    assert summary.paired_predictions.sum() == 0
    assert summary.predictor_errors.sum() == cases.parser_valid.sum()
    assert cases.loc[~cases.parser_valid, "prediction_status"].eq("invalid_url_skipped").all()


def test_idna_same_normalized_host_but_raw_features_differ():
    assert parse_url("https://bücher.example.com/").hostname == parse_url("https://xn--bcher-kva.example.com/").hostname
    assert extract_features("https://bücher.example.com/")["url_len"] != extract_features("https://xn--bcher-kva.example.com/")["url_len"]
