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
    assert a.loc[a.label_policy.eq("conditional-label-preserving"), "resource_equivalence_check"].all()
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


def test_host_case_preserves_case_sensitive_userinfo_and_request_parts():
    from phishguard_vn.robustness import _resource_key
    transform = next(t for t in transformations() if t.name == "host_case")
    base = "https://User:Pass@example.com:443/aB?X=One#Route"
    changed = transform.apply(base)
    assert changed == "https://User:Pass@EXAMPLE.COM:443/aB?X=One#Route"
    assert _resource_key(base) == _resource_key(changed)
    assert _resource_key(base) != _resource_key(base.replace("Pass", "PASS"))
    assert _resource_key("http://example.com:0/") != _resource_key("http://example.com/")


def test_default_port_is_idempotent_and_skips_nondefault():
    transform = next(t for t in transformations() if t.name == "default_port")
    assert transform.apply("https://example.com:443/a") == "https://example.com:443/a"
    assert transform.apply("http://example.com:8080/a") == "http://example.com:8080/a"
    assert not transform.applicable("http://example.com:8080/a")
    calls=[]
    cases=run_robustness(lambda u: calls.append(u) or 0.4, bases=["http://example.com:8080/a"])
    skipped=cases.loc[cases.transformation.eq("default_port")].iloc[0]
    assert skipped.prediction_status == "not_applicable"
    assert pd.isna(skipped.resource_equivalence_check)


def test_raw_lexical_shift_decomposes_lr_logits():
    from phishguard_vn.robustness import explain_lexical_shifts
    from phishguard_vn.modeling import build_logistic_baseline, predict_url
    names=list(CANDIDATE_FEATURES)
    urls=["https://example.com/", "http://example.org/abc", "https://www.example.net/a?q=x", "http://example.com:80/def"]
    X=pd.DataFrame([extract_features(u) for u in urls],columns=names)
    pipeline=build_logistic_baseline().fit(X,[0,1,0,1])
    cases=run_robustness(lambda u: predict_url(u,pipeline,names)["score"])
    deltas=explain_lexical_shifts(cases,pipeline)
    host=set(deltas.loc[deltas.transformation.eq("host_case"),"feature"])
    port=set(deltas.loc[deltas.transformation.eq("default_port"),"feature"])
    assert host == {"entropy"}
    assert port == {"entropy","url_len","digit_cnt"}
    for _,group in deltas.groupby(["base_id","transformation"]):
        assert group.logit_delta.sum() == pytest.approx(group.total_logit_delta.iloc[0],abs=1e-10)
