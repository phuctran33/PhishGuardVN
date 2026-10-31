"""Reproducible qualitative error sampling and static, evidence-limited annotation."""
from __future__ import annotations

import hashlib
import re

import pandas as pd

from phishguard_vn.url_parser import parse_url

TAXONOMY = {
    "brand_cues": "Visible generic brand-like tokens; no proof of impersonation",
    "domain_subdomain": "Multiple subdomain labels",
    "lexical_patterns": "Digits, hyphens, or action tokens in the string",
    "url_complexity": "Long URL, path or query",
    "idna_ip": "Unicode, punycode or IP literal",
    "source_effects": "Source-label confounding is a population hypothesis",
    "label_uncertainty": "Dataset label retained; semantic confirmation pending",
    "unknown": "No selected static cue; mechanism undetermined",
}
BRAND_TOKENS = ("paypal", "google", "microsoft", "facebook", "apple", "vietcombank", "bidv", "bank")


def defang_url(value):
    """Plain text, no live URI, HTML or spreadsheet-formula payload; preserve content."""
    text = str(value).replace("://", "[:]//").replace(".", "[.]")
    text = text.replace("@", "[@]")
    text = text.replace("<", "\\u003c").replace(">", "\\u003e")
    text = "".join(ch if ch.isprintable() else f"\\u{ord(ch):04x}" for ch in text)
    return "URL_TEXT: " + text


def sample_errors(frame, *, model, n=40, seed=42):
    """Round robin partition/fold/type/source/tier queues, hash-ranked IDs.

    Round robin within each queue by domain prevents one repeated domain dominating.
    This is a diversity sample, not prevalence-weighted inference. No score ranking.
    """
    errors = frame.loc[frame.model.eq(model) & frame.outcome.isin(["FP", "FN"])].copy()
    if errors.empty:
        return errors
    errors["sampling_fold"] = errors.fold_id.fillna(-1).astype(int)
    errors["sampling_hash"] = errors.id.map(lambda x: hashlib.sha256(f"{seed}:{x}".encode()).hexdigest())
    errors = errors.sort_values(["sampling_hash", "id"])
    keys = ["evaluation_partition", "sampling_fold", "outcome", "source", "tier"]
    queues = []
    for _, block in errors.groupby(keys, dropna=False, sort=True):
        block = block.copy()
        block["_domain_rank"] = block.groupby("registrable_domain").cumcount()
        queues.append(list(block.sort_values(["_domain_rank", "sampling_hash", "id"]).index))
    chosen = []
    while len(chosen) < min(n, len(errors)):
        for queue in queues:
            if queue and len(chosen) < n:
                chosen.append(queue.pop(0))
    sample = errors.loc[chosen].copy()
    sample["sampling_seed"] = seed
    return sample.reset_index(drop=True)


def annotate_case(row):
    raw = row["url"]
    parsed = parse_url(raw)
    tags, observations = [], []
    lower = raw.lower()
    tokens = [token for token in BRAND_TOKENS if token in lower]
    if tokens:
        tags.append("brand_cues")
        observations.append("Visible token(s): " + ", ".join(tokens) + "; lexical match only")
    if parsed.subdomain:
        tags.append("domain_subdomain")
        observations.append(f"Subdomain labels={len(parsed.subdomain.split('.'))}")
    if re.search(r"[0-9_-]|login|verify|secure|account", lower):
        tags.append("lexical_patterns")
        observations.append("Contains digit/hyphen/underscore or login/verify/secure/account substring")
    if len(raw) > 80 or parsed.query or len(parsed.path) > 1:
        tags.append("url_complexity")
        observations.append(f"Raw length={len(raw)}, path length={len(parsed.path)}, query present={bool(parsed.query)}")
    if parsed.is_ip or not raw.isascii() or "xn--" in lower:
        tags.append("idna_ip")
        observations.append(f"IP={parsed.is_ip}; Unicode={not raw.isascii()}; punycode={'xn--' in lower}")
    if not tags:
        tags.append("unknown")
        observations.append("No cue in the predefined static checklist")
    observations.append(f"Dataset label={row['label']}; observed outcome={row['outcome']}; source={row['source']}")
    return {
        "taxonomy": "|".join(tags), "url_safe": defang_url(raw),
        "observation": "; ".join(observations),
        "hypothesis": "Lexical representation and source composition may contribute; individual cause unverified.",
        "next_verification": "Inspect fold-local feature contributions and approved offline collection evidence; verify semantics with data owner; do not visit URL.",
        "review_status": "static_observation_complete;human_verification_pending",
        "label_review_status": "unverified_original_label_retained",
        "source_effects_status": "population_hypothesis_not_case_causality",
    }


def case_manifest(sample):
    fields = ["id", "model", "evaluation_partition", "fold_id", "source", "tier", "true_label", "predicted_label",
              "score", "outcome", "sampling_seed", "sampling_hash"]
    return pd.DataFrame([{**{k: row[k] for k in fields}, **annotate_case(row)} for _, row in sample.iterrows()])


def taxonomy_summary(cases):
    counts = cases.taxonomy.str.split("|").explode().value_counts()
    return pd.DataFrame([{"category": key, "definition": description, "sample_cases": int(counts.get(key, 0)),
                          "interpretation": "multi-label sample cue count, not population frequency"}
                         for key, description in TAXONOMY.items()])
