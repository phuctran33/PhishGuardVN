"""Versioned domain/alias catalog for URL inspection only."""

from __future__ import annotations

from collections import Counter
import csv
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
import hashlib
from io import StringIO
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

import idna
import tldextract

from phishguard_vn.brand_features import REFERENCE_PATH, STOPLIST, fold_text, load_reference
from phishguard_vn.url_parser import parse_url

CATALOG_PATH = REFERENCE_PATH.with_name("brand_catalog_v2.csv")
MANIFEST_PATH = CATALOG_PATH.with_suffix(".manifest.json")
CATALOG_VERSION = "brand-catalog-v2"
VIETNAM_SCOPES = (
    "vietnamese", "international_operating_in_vietnam", "international_popular_in_vietnam",
)
_IMPORTED_V1_BRANDS = {"shopee", "lazada", "jtexpress"}
FIELDS = (
    "brand_id", "canonical_name", "aliases", "official_domain", "category",
    "country_or_region", "source_url", "listed_url", "vietnam_scope", "vietnam_scope_source_url",
    "vietnam_scope_evidence", "verified_at", "verification_status", "notes",
)

# Keep the frozen parser's grouping semantics. Inspection uses the private PSL
# as an additional admission check, so a tenant cannot contribute the shared root.
_PRIVATE_PSL = tldextract.TLDExtract(cache_dir=None, suffix_list_urls=(), include_psl_private_domains=True)
_SHARED_ROOTS = {"facebook.com", "linkedin.com", "linktr.ee", "medium.com", "twitter.com", "x.com",
                 "youtu.be", "youtube.com", "bit.ly", "tinyurl.com", "goo.gl", "forms.gle", "sites.google.com"}
_COMMON_ALIASES = STOPLIST | {
    "air", "best", "booking", "care", "first", "free", "global", "home", "life", "line",
    "link", "login", "market", "money", "next", "open", "prime", "secure", "team", "time",
    "trust", "true", "visa", "wise", "work", "zoom",
}
_WORDS = re.compile(r"[a-z0-9]+")
_ID = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*")


def words(value: str) -> tuple[str, ...]:
    return tuple(_WORDS.findall(fold_text(value)))


def decoded_dns(host: str) -> str:
    try:
        return idna.decode(host)
    except idna.IDNAError:
        return host


def listed_domain(listed_url: str, *, source_hostname: str = "") -> str:
    """Accept a listed registrable host or its www hostname. Never infer tenant ownership."""
    if any(ch.isspace() or ord(ch) < 32 for ch in listed_url) or "\\" in listed_url:
        raise ValueError("Invalid listed website")
    value = listed_url if "://" in listed_url else "https://" + listed_url
    parts = urlsplit(value)
    parsed = parse_url(value)
    if (
        parts.scheme not in {"http", "https"} or parts.username is not None or parts.password is not None
        or parsed.port is not None or not parsed.is_valid or parsed.is_ip or not parsed.registrable_domain
    ):
        raise ValueError("Invalid listed website")
    domain = parsed.registrable_domain
    if parsed.hostname not in {domain, "www." + domain} or _PRIVATE_PSL(parsed.hostname).is_private:
        raise ValueError("Website is a specific subdomain or shared tenant")
    if ((domain in _SHARED_ROOTS and source_hostname not in {domain, "www." + domain})
            or idna.encode(domain, uts46=True).decode("ascii") != domain):
        raise ValueError("Shared or noncanonical domain")
    return domain


@dataclass(frozen=True)
class CatalogBrand:
    brand_id: str
    name: str
    domains: tuple[str, ...]


@dataclass(frozen=True)
class InspectionCatalog:
    by_id: dict[str, CatalogBrand]
    by_domain: dict[str, str]
    aliases: dict[tuple[str, ...], str]
    max_alias_words: int
    sha256: str
    stats: dict

    @property
    def n_brands(self) -> int:
        return self.stats["combined"]["brands"]


def _stats(brands, domains, aliases, categories, regions, scopes):
    return {
        "brands": brands,
        "domains": domains,
        "aliases": aliases,
        "categories": dict(sorted(categories.items())),
        "regions": dict(sorted(regions.items())),
        "vietnam_scope": {scope: scopes[scope] for scope in VIETNAM_SCOPES},
    }


def _source_hostname(url: str) -> str:
    source = urlsplit(url)
    if (source.scheme != "https" or not source.hostname or source.username is not None
            or source.password is not None or any(ch.isspace() for ch in url)):
        raise ValueError("Missing HTTPS provenance")
    return source.hostname


def read_catalog(raw: bytes) -> InspectionCatalog:
    """Validate all additions before exposing any of them to inspection."""
    reference = load_reference()
    reference_rows = list(csv.DictReader(StringIO(REFERENCE_PATH.read_text(encoding="utf-8"))))
    rows = csv.DictReader(StringIO(raw.decode("utf-8"), newline=""))
    if tuple(rows.fieldnames or ()) != FIELDS:
        raise ValueError("Unexpected catalog columns")
    base_ids = {brand.brand_id for brand in reference.brands}
    metadata, domains_by_id, domains, aliases = {}, {}, {}, {}
    alias_owners = dict.fromkeys(reference.all_keys, "reference_v1")
    entity_ids = {}
    for row in rows:
        if None in row or any(col not in row or row[col] is None for col in FIELDS):
            raise ValueError("Unexpected catalog record")
        bid, name = row["brand_id"], row["canonical_name"]
        category, region = row["category"], row["country_or_region"]
        if (not _ID.fullmatch(bid) or bid in base_ids or not name.strip() or not category or not region
                or row["verification_status"] != "verified" or not row["notes"].strip()
                or any(ord(ch) < 32 or ord(ch) == 127 for ch in name + category + region)):
            raise ValueError("Invalid catalog identity or provenance")
        source_hostname = _source_hostname(row["source_url"])
        scope = row["vietnam_scope"]
        if (scope not in VIETNAM_SCOPES or not row["vietnam_scope_evidence"].strip()
                or (scope == "vietnamese" and region != "VN")):
            raise ValueError("Missing Vietnam scope or evidence")
        _source_hostname(row["vietnam_scope_source_url"])
        if date.fromisoformat(row["verified_at"]) > date.today():
            raise ValueError("Verification date in the future")
        domain = row["official_domain"]
        if (domain != listed_domain(row["listed_url"], source_hostname=source_hostname) or domain in domains
                or domain in reference.all_official_domains):
            raise ValueError("Duplicate or unverified domain")
        entity_key = (words(name) or (name.casefold(),), region.casefold())
        if entity_ids.setdefault(entity_key, bid) != bid:
            raise ValueError("Duplicate catalog entity")
        identity = (name, category, region, row["aliases"], scope)
        if metadata.setdefault(bid, identity) != identity:
            raise ValueError("Conflicting domains for one brand ID")
        for alias in filter(None, row["aliases"].split("|")):
            tokens = words(alias)
            key = "".join(tokens)
            if not 4 <= len(key) <= 64 or len(tokens) > 5 or key in _COMMON_ALIASES:
                raise ValueError("Insufficiently specific alias")
            if alias_owners.setdefault(key, bid) != bid:
                raise ValueError("Colliding normalized alias")
            if tokens in aliases and bid not in domains_by_id:
                raise ValueError("Duplicate alias")
            aliases[tokens] = bid
        domains_by_id.setdefault(bid, []).append(domain)
        domains[domain] = bid
    if not metadata:
        raise ValueError("Empty catalog")
    by_id = {bid: CatalogBrand(bid, info[0], tuple(sorted(domains_by_id[bid]))) for bid, info in metadata.items()}
    old_regions = Counter({"VN": len(reference.brands)})  # Reference v1 covers Vietnam-facing services.
    old_categories = Counter(row["sector"] for row in reference_rows)
    new_regions = Counter(info[2] for info in metadata.values())
    new_categories = Counter(info[1] for info in metadata.values())
    old_scopes = Counter("international_operating_in_vietnam" if brand in _IMPORTED_V1_BRANDS else "vietnamese"
                         for brand in base_ids)
    new_scopes = Counter(info[4] for info in metadata.values())
    old = _stats(len(reference.brands), len(reference.all_official_domains), len(reference.all_keys),
                 old_categories, old_regions, old_scopes)
    added = _stats(len(by_id), len(domains), len(aliases), new_categories, new_regions, new_scopes)
    combined = _stats(old["brands"] + added["brands"], old["domains"] + added["domains"],
                      old["aliases"] + added["aliases"], old_categories + new_categories,
                      old_regions + new_regions, old_scopes + new_scopes)
    return InspectionCatalog(
        by_id, domains, aliases, max(map(len, aliases), default=0), hashlib.sha256(raw).hexdigest(),
        {"baseline": old, "additions": added, "combined": combined},
    )


@lru_cache(maxsize=2)
def load_catalog(path: Path = CATALOG_PATH, manifest_path: Path = MANIFEST_PATH) -> InspectionCatalog:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw = path.read_bytes()
    if (manifest["version"] != CATALOG_VERSION
            or hashlib.sha256(raw).hexdigest() != manifest["catalog_sha256"]
            or load_reference().sha256 != manifest["reference_v1_sha256"]):
        raise ValueError("Inspection catalog checksum/version mismatch")
    catalog = read_catalog(raw)
    if catalog.stats != manifest["counts"]:
        raise ValueError("Inspection catalog manifest counts differ")
    return catalog


@lru_cache(maxsize=1)
def active_catalog() -> InspectionCatalog | None:
    """Cache startup result, including fallback. Restart after replacing assets."""
    try:
        return load_catalog()
    except (OSError, ValueError, TypeError, KeyError, csv.Error, UnicodeError):
        return None
