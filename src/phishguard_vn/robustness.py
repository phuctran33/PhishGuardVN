"""Deterministic offline URL stress tests; transformed strings have no ground truth."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote, urlsplit, urlunsplit

import numpy as np
import pandas as pd

from phishguard_vn.features import CANDIDATE_FEATURES, extract_features_from_parsed
from phishguard_vn.url_parser import parse_url

# Reserved example domains and documentation IPs only. Never perform network IO.
BASE_URLS = (
    "https://example.com/", "http://example.org/account", "https://www.example.net/search?q=test",
    "https://example.com/a/b?x=1", "https://example.org/login", "http://example.net/index.html",
)


@dataclass(frozen=True)
class Transformation:
    name: str
    specification: str
    label_policy: str
    expected_valid: bool
    apply: Callable[[str], str]
    applicable: Callable[[str], bool] = lambda url: True


def _replace(url, **kwargs):
    return urlunsplit(urlsplit(url)._replace(**kwargs))


def _http_host(url):
    parts = urlsplit(url)
    return parts.scheme.lower() in ("http", "https") and bool(parts.hostname) and parts.hostname.isascii()


def _host_case(url):
    parts = urlsplit(url)
    # Userinfo may be case sensitive: only uppercase the host, never the authority.
    userinfo = parts.netloc[:parts.netloc.rfind("@") + 1]
    host = parts.hostname or ""
    host = "[" + host.upper() + "]" if ":" in host else host.upper()
    port = "" if parts.port is None else ":" + str(parts.port)
    return _replace(url, netloc=userinfo + host + port)


def _default_port_applicable(url):
    parts = urlsplit(url)
    return _http_host(url) and parts.port in (None, 443 if parts.scheme.lower() == "https" else 80)


def _default_port(url):
    if not _default_port_applicable(url):
        return url
    parts = urlsplit(url)
    if parts.port is not None:
        return url
    return _replace(url, netloc=parts.netloc + (":443" if parts.scheme.lower() == "https" else ":80"))


def transformations():
    unknown = "label-unknown"
    preserve = "conditional-label-preserving"
    return (
        Transformation("host_case", "ASCII HTTP(S) host case normalization only; preserve userinfo/path/query/fragment; URI-equivalent under standard HTTP normalization, not verified live routing", preserve, True,
                       _host_case, _http_host),
        Transformation("default_port", "Add HTTP(S) default port only when absent; skip non-default ports; URI-equivalent under standard HTTP normalization, not verified live routing", preserve, True,
                       _default_port, _default_port_applicable),
        Transformation("subdomain", "Prepend login.verify subdomain; different host", unknown, True,
                       lambda u: _replace(u, netloc="login.verify." + urlsplit(u).netloc)),
        Transformation("deep_subdomain", "Prepend twelve safe subdomain labels", unknown, True,
                       lambda u: _replace(u, netloc="a." * 12 + urlsplit(u).netloc)),
        Transformation("path_query", "Append account/verify path and token-like query", unknown, True,
                       lambda u: _replace(u, path=urlsplit(u).path + "/account/verify", query="session=123456&next=home")),
        Transformation("long_path", "Append 4096 ASCII path characters", unknown, True,
                       lambda u: _replace(u, path="/" + "a" * 4096)),
        Transformation("long_query", "Append deterministic high variety 4096-character query", unknown, True,
                       lambda u: _replace(u, query="token=" + "aZ09_-" * 683)),
        Transformation("percent_encoding", "Percent-encoded path including encoded slash; routing semantics unknown", unknown, True,
                       lambda u: _replace(u, path="/%61ccount%2Fverify")),
        Transformation("double_encoding", "Double-encoded slash in path; decoder-dependent semantics", unknown, True,
                       lambda u: _replace(u, path="/%252Faccount")),
        Transformation("unicode_idna", "Unicode bücher label under example.com", unknown, True,
                       lambda u: _replace(u, netloc="bücher.example.com")),
        Transformation("punycode", "Punycode spelling of bücher.example.com; matches unicode_idna host", unknown, True,
                       lambda u: _replace(u, netloc="xn--bcher-kva.example.com")),
        Transformation("homoglyph", "Cyrillic a in pаypal subdomain; lexical cue, no verified brand identity", unknown, True,
                       lambda u: _replace(u, netloc="pаypal.example.com")),
        Transformation("brand_token", "paypal-login subdomain and secure path under reserved example domain", unknown, True,
                       lambda u: _replace(u, netloc="paypal-login.example.com", path="/secure/verify")),
        Transformation("shortener_pattern", "Short opaque path under go.example.com, no redirect claim", unknown, True,
                       lambda u: _replace(u, netloc="go.example.com", path="/aB3x9")),
        Transformation("ipv4", "Documentation IPv4 host 192.0.2.1", unknown, True,
                       lambda u: _replace(u, netloc="192.0.2.1")),
        Transformation("ipv6", "Documentation bracketed IPv6 host 2001:db8::1", unknown, True,
                       lambda u: _replace(u, netloc="[2001:db8::1]")),
        Transformation("userinfo", "Userinfo brand cue before documentation host", unknown, True,
                       lambda u: _replace(u, netloc="paypal.com@" + urlsplit(u).netloc)),
        Transformation("fragment", "Append fragment; client-side routing may alter semantics", unknown, True,
                       lambda u: _replace(u, fragment="/login/verify")),
        Transformation("unicode_path", "Unicode path and percent-encoded query", unknown, True,
                       lambda u: _replace(u, path="/đăng-nhập", query="next=" + quote("xác minh"))),
        Transformation("bad_port", "Non-numeric port (expected parser rejection)", unknown, False,
                       lambda u: _replace(u, netloc="example.com:invalid")),
        Transformation("bad_ipv6", "Unclosed IPv6 bracket (expected parser rejection)", unknown, False,
                       lambda u: "https://[2001:db8::1/path"),
        Transformation("missing_host", "Empty authority (expected parser rejection)", unknown, False,
                       lambda u: "https:///path"),
        Transformation("host_whitespace", "Space in DNS hostname (expected parser rejection)", unknown, False,
                       lambda u: "https://exa mple.com/path"),
        Transformation("unresolved_suffix", "Reserved invalid suffix; extractor cannot resolve domain", unknown, False,
                       lambda u: "https://example.invalid/path"),
    )


def _resource_key(url):
    parts = urlsplit(url)
    return (parts.scheme.lower(), (parts.hostname or "").lower(),
            parts.port if parts.port is not None else (443 if parts.scheme.lower() == "https" else 80),
            parts.username, parts.password, parts.path, parts.query, parts.fragment)


def run_robustness(predictor=None, *, bases=BASE_URLS, threshold=0.5):
    """predictor(url)->finite phishing probability; invalid URLs must never reach it.

    Model exceptions are recorded, not silently counted as successful coverage.
    Flip/shift denominators contain only valid paired predictions.
    """
    records = []
    for base_index, original in enumerate(bases):
        for transform in transformations():
            applicable = transform.applicable(original)
            modified = transform.apply(original)
            parsed = parse_url(modified)
            values = extract_features_from_parsed(parsed)
            finite = np.isfinite(np.array([np.nan if values[k] is None else values[k] for k in CANDIDATE_FEATURES], dtype=float)).all()
            check = bool(parsed.is_valid == transform.expected_valid)
            resource_check = (_resource_key(original) == _resource_key(modified)) if applicable and transform.label_policy == "conditional-label-preserving" else None
            row = {"base_id": f"static_{base_index:02d}", "original_url": original, "transformed_url": modified,
                   "transformation": transform.name, "specification": transform.specification,
                   "seed": "none_deterministic", "label_policy": transform.label_policy,
                   "applicable": applicable,
                   "expected_valid": transform.expected_valid, "parser_valid": parsed.is_valid,
                   "validity_check_pass": check, "resource_equivalence_check": resource_check,
                   "feature_finite": bool(finite), "error_reason": parsed.error_reason,
                   "prediction_status": "unavailable" if predictor is None else "invalid_url_skipped",
                   "original_score": None, "transformed_score": None, "score_shift": None, "flip": None}
            if not applicable:
                row["prediction_status"] = "not_applicable"
            if applicable and predictor is not None and parsed.is_valid and finite:
                try:
                    before, after = float(predictor(original)), float(predictor(modified))
                    if not np.isfinite([before, after]).all() or not (0 <= before <= 1 and 0 <= after <= 1):
                        raise ValueError("nonfinite_or_out_of_range_score")
                    row.update(prediction_status="paired", original_score=before, transformed_score=after,
                               score_shift=after - before, flip=bool((before >= threshold) != (after >= threshold)))
                except Exception as exc:
                    row.update(prediction_status=f"predictor_error:{type(exc).__name__}")
            records.append(row)
    return pd.DataFrame(records)


def robustness_summary(cases):
    rows = []
    for name, group in cases.groupby("transformation", sort=False):
        paired = group.loc[group.prediction_status.eq("paired")]
        rows.append({"transformation": name, "label_policy": group.label_policy.iloc[0], "n_cases": len(group),
                     "parser_valid_rate": float(group.parser_valid.mean()),
                     "expected_validity_pass_rate": float(group.validity_check_pass.mean()),
                     "finite_feature_coverage": float(group.feature_finite.mean()),
                     "paired_predictions": len(paired),
                     "prediction_flip_rate": float(paired.flip.astype(float).mean()) if len(paired) else None,
                     "stability": 1 - float(paired.flip.astype(float).mean()) if len(paired) else None,
                     "mean_score_shift": float(paired.score_shift.mean()) if len(paired) else None,
                     "mean_abs_score_shift": float(paired.score_shift.abs().mean()) if len(paired) else None,
                     "max_abs_score_shift": float(paired.score_shift.abs().max()) if len(paired) else None,
                     "predictor_errors": int(group.prediction_status.str.startswith("predictor_error:").sum())})
    return pd.DataFrame(rows)


def explain_lexical_shifts(cases, pipeline):
    """Exact LR logit changes caused by raw lexical feature deltas, no model refit."""
    from scipy.special import expit
    names = list(CANDIDATE_FEATURES)
    scaler, model = pipeline.named_steps["scaler"], pipeline.named_steps["model"]
    rows = []
    for _, case in cases.loc[cases.prediction_status.eq("paired")].iterrows():
        before = extract_features_from_parsed(parse_url(case.original_url))
        after = extract_features_from_parsed(parse_url(case.transformed_url))
        a, b = np.array([before[n] for n in names]), np.array([after[n] for n in names])
        before_logit = float(model.intercept_[0] + np.sum((a - scaler.mean_) / scaler.scale_ * model.coef_[0]))
        after_logit = float(model.intercept_[0] + np.sum((b - scaler.mean_) / scaler.scale_ * model.coef_[0]))
        if not np.allclose(expit([before_logit, after_logit]), [case.original_score, case.transformed_score], atol=1e-12, rtol=0):
            raise ValueError("Robustness explanation does not reproduce E1 probabilities")
        for j, feature in enumerate(names):
            delta = float(b[j] - a[j])
            if not np.isclose(delta, 0, atol=1e-12, rtol=0):
                rows.append({"base_id": case.base_id, "transformation": case.transformation,
                             "feature": feature, "original_value": float(a[j]), "transformed_value": float(b[j]),
                             "feature_delta": delta, "coefficient": float(model.coef_[0, j]),
                             "fitting_scale": float(scaler.scale_[j]),
                             "logit_delta": float(delta / scaler.scale_[j] * model.coef_[0, j]),
                             "total_logit_delta": after_logit - before_logit})
    return pd.DataFrame(rows)
