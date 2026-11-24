"""Rule-based inspection, separate from ML prediction; no network or model calls."""

from phishguard_vn.brand_features import explain_brand_matches, load_reference
from phishguard_vn.url_parser import parse_url


def inspect_url(url: str) -> dict:
    parsed = parse_url(url)
    if not parsed.is_valid:
        raise ValueError("Invalid URL")
    reference = load_reference()
    features, events = explain_brand_matches(url, reference)
    names = {b.brand_id: b.canonical_name for b in reference.brands}
    return dict(
        scope="rule_based_url_inspection",
        hostname=parsed.hostname,
        registrable_domain=parsed.registrable_domain,
        subdomain=parsed.subdomain,
        path=parsed.path,
        is_ip=parsed.is_ip,
        scheme_was_added=parsed.scheme_was_added,
        reference_sha256=reference.sha256,
        reference_brands=len(reference.brands),
        official_brand_ids=[
            b.brand_id
            for b in reference.brands
            if parsed.registrable_domain in b.official_domains
        ],
        features=features,
        matches=[
            dict(event, brand_name=names.get(event["brand_id"], "")) for event in events
        ],
        limitations=[
            "Heuristic signals are not a phishing verdict or intrinsic model explanation.",
            "A reference-domain match does not certify website safety or current ownership.",
            "The path matching zone includes decoded path and query; the frozen engine has limited typo/homoglyph coverage.",
        ],
    )
