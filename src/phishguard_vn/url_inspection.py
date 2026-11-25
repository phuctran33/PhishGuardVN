"""Offline analysis for /inspect. No model calls or outbound requests."""

from collections import defaultdict
from functools import lru_cache
from urllib.parse import parse_qsl, unquote

from phishguard_vn.brand_features import explain_brand_matches, load_reference
from phishguard_vn.inspection_catalog import (
    CATALOG_VERSION, InspectionCatalog, active_catalog, decoded_dns, words,
)
from phishguard_vn.url_parser import ParsedURL, parse_url


@lru_cache(maxsize=1)
def _baseline():
    reference = load_reference()
    if not reference.is_fully_verified:
        raise ValueError("Inspection reference failed provenance checks")
    return reference, {brand.brand_id: brand for brand in reference.brands}


def _alias_hits(parts, catalog: InspectionCatalog):
    for text in parts:
        tokens = words(text)
        for start in range(len(tokens)):
            for count in range(1, min(catalog.max_alias_words, len(tokens) - start) + 1):
                key = tokens[start:start + count]
                if brand_id := catalog.aliases.get(key):
                    yield brand_id, " ".join(key)


def _catalog_events(parsed: ParsedURL, catalog: InspectionCatalog, features):
    # Distinct path segments and query components cannot manufacture a phrase
    # by matching a suffix of one against a prefix of the next.
    zones = (
        ("domain", (decoded_dns(parsed.registrable_domain or "").split(".")[0],)),
        ("subdomain", tuple(decoded_dns(label) for label in parsed.subdomain.split("."))),
        ("path", tuple(unquote(segment) for segment in parsed.path.split("/"))),
        ("query", tuple(part for pair in parse_qsl(parsed.query, keep_blank_values=True) for part in pair)),
    )
    hits = defaultdict(dict)
    for zone, parts in zones:
        for brand_id, key in _alias_hits(parts, catalog):
            hits[brand_id].setdefault(zone, key)
    for brand_id, signals in hits.items():
        for zone, key in signals.items():
            rule = "brand_in_path" if zone == "query" else f"brand_in_{zone}"
            features[rule] = 1.0
            yield dict(rule=rule, brand_id=brand_id, key=key, text=key, zone=zone, value=1.0)
        if parsed.registrable_domain not in catalog.by_id[brand_id].domains:
            # Per-brand check. A domain assigned to another brand doesn't exempt it.
            zone, key = next(iter(signals.items()))
            features["brand_domain_mismatch"] = 1.0
            yield dict(rule="brand_domain_mismatch", brand_id=brand_id, key=key, text=key, zone=zone, value=1.0)


def inspect_url(url: str, *, catalog: InspectionCatalog | None = None) -> dict:
    """Common comparison entry point; catalog=None explicitly uses the 45-brand baseline."""
    parsed = parse_url(url)
    if not parsed.is_valid:
        raise ValueError("Invalid URL")
    reference, brands = _baseline()
    features, events = explain_brand_matches(url, reference)
    official = [b.brand_id for b in reference.brands if parsed.registrable_domain in b.official_domains]
    if catalog is not None:
        if bid := catalog.by_domain.get(parsed.registrable_domain):
            official.append(bid)
        events.extend(_catalog_events(parsed, catalog, features))

    def details(brand_id):
        if catalog is not None and brand_id in catalog.by_id:
            brand = catalog.by_id[brand_id]
            return brand.name, list(brand.domains)
        brand = brands.get(brand_id)
        return (brand.canonical_name, sorted(brand.official_domains)) if brand else ("", [])

    matches = []
    for event in events:
        name, domains = details(event["brand_id"])
        evidence = dict(event, brand_name=name, official_domains=domains)
        # Frozen E2 returns the entire folded path/query zone. Avoid echoing
        # potentially sensitive query values in the public inspection response.
        if event["rule"] in {"brand_in_path", "brand_domain_mismatch"}:
            evidence["text"] = event["key"]
        matches.append(evidence)

    return dict(
        scope="rule_based_url_inspection",
        hostname=parsed.hostname,
        registrable_domain=parsed.registrable_domain,
        subdomain=parsed.subdomain,
        path=parsed.path,
        is_ip=parsed.is_ip,
        scheme_was_added=parsed.scheme_was_added,
        reference_sha256=catalog.sha256 if catalog else reference.sha256,
        reference_brands=catalog.n_brands if catalog else len(reference.brands),
        catalog_version=CATALOG_VERSION if catalog else "e2-brand-v1",
        catalog_status="expanded" if catalog else "fallback_v1",
        official_brand_ids=official,
        official_brands=[
            dict(brand_id=brand_id, brand_name=name, official_domains=domains)
            for brand_id in official for name, domains in [details(brand_id)]
        ],
        features=features,
        matches=matches,
        limitations=[
            "Heuristic signals are not a phishing verdict or intrinsic model explanation.",
            "A reference-domain match does not certify website safety or current ownership.",
            "Path and query can contain mentions unrelated to the domain owner.",
            "Expanded entries support exact verified domains and selected aliases. Typo/homoglyph rules use v1.",
        ],
    )


def inspect_with_catalog(url: str) -> dict:
    return inspect_url(url, catalog=active_catalog())
