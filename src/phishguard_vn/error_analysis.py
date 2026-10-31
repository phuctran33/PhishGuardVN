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
    "bare_host_lexical_ambiguity": "Bare hostname; aggregate counts do not encode token meaning or categorical suffix identity",
    "representation_collision": "Identical full lexical vector in fitting data has the opposite original label; tolerance 1e-12",
    "near_threshold": "Observed score within 0.05 of the fixed 0.5 threshold; descriptive only",
    "subdomain_count_sensitivity": "Observed subdomain/dot structure; exact model terms inspected, semantics unverified",
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


def case_signature(row):
    """Bind durable notes to the actual URL, features, score, labels and context."""
    import json
    from phishguard_vn.features import CANDIDATE_FEATURES
    payload = {k: str(row[k]) for k in ["id", "model", "evaluation_partition", "outcome", "url", "label", "source", "tier"]}
    payload["fold_id"] = None if pd.isna(row.fold_id) else int(row.fold_id)
    payload["score"] = round(float(row.score), 12)
    payload["features"] = {name: round(float(row[name]), 12) for name in CANDIDATE_FEATURES}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def explain_error_cases(sample, metadata, folds, pipeline, *, context_models=None):
    """Exact scaled-LR arithmetic, from the correct held-out model; no causal claim.

    Refit only the selected existing E1 configuration for the three fitting folds
    when context models are absent. Validate every explained score against OOF.
    Relative-to-fitting-mean contributions are not independent causal effects,
    especially for correlated lexical counts. Collision checks use fitting IDs only.
    """
    import numpy as np
    from scipy.special import expit
    from sklearn.base import clone
    from phishguard_vn.features import CANDIDATE_FEATURES
    from phishguard_vn.modeling import _fit
    names = list(CANDIDATE_FEATURES)
    train = metadata.loc[metadata.split.eq("train")].merge(folds, on="id", validate="one_to_one").sort_values("id")
    models = {} if context_models is None else dict(context_models)
    rows, evidence = [], []
    for context in [-1, 0, 1, 2]:
        subset = sample.loc[sample.evaluation_partition.eq("official_validation")] if context == -1 else sample.loc[sample.evaluation_partition.eq("group_cv") & sample.fold_id.eq(context)]
        if subset.empty:
            continue
        fitting = train if context == -1 else train.loc[train.fold_id.ne(context)]
        if context not in models:
            models[context] = pipeline if context == -1 else _fit(clone(pipeline), fitting[names], fitting.label.map({"benign": 0, "phishing": 1}))
        estimator = models[context]
        scaler, model = estimator.named_steps["scaler"], estimator.named_steps["model"]
        fitted_ids_hash = hashlib.sha256("\n".join(sorted(fitting.id)).encode()).hexdigest()
        X = subset[names]
        standardized = scaler.transform(X)
        contributions = standardized * model.coef_[0]
        logits = model.intercept_[0] + contributions.sum(axis=1)
        scores = expit(logits)
        if not np.allclose(scores, subset.score.to_numpy(), rtol=0, atol=1e-10):
            raise ValueError("Explanation model does not reproduce held-out E1 scores")
        if not np.isclose(float(scaler.n_samples_seen_), len(fitting)):
            raise ValueError("Explanation scaler fitting support mismatch")
        for position, (_, row) in enumerate(subset.iterrows()):
            same = np.isclose(fitting[names].to_numpy(), row[names].to_numpy(dtype=float), rtol=0, atol=1e-12).all(axis=1)
            opposites = fitting.loc[same & fitting.label.ne(row.label)]
            plus = sorted([(n, float(c)) for n, c in zip(names, contributions[position]) if c > 0], key=lambda t: -t[1])
            minus = sorted([(n, float(c)) for n, c in zip(names, contributions[position]) if c < 0], key=lambda t: t[1])
            facts = {"id": row.id, "context": context, "case_signature": case_signature(row),
                     "intercept": float(model.intercept_[0]), "logit": float(logits[position]),
                     "reconstructed_score": float(scores[position]), "score_abs_error": float(abs(scores[position] - row.score)),
                     "fit_rows": len(fitting), "fit_ids_sha256": fitted_ids_hash,
                     "same_vector_fitting_rows": int(same.sum()), "opposite_label_fitting_rows": len(opposites),
                     "opposite_label_example_id": str(opposites.id.iloc[0]) if len(opposites) else "",
                     "positive_contributions": "; ".join(f"{n}={c:+.4f}" for n, c in plus[:3]),
                     "negative_contributions": "; ".join(f"{n}={c:+.4f}" for n, c in minus[:3])}
            evidence.append(facts)
            for j, name in enumerate(names):
                rows.append({"id": row.id, "context": context, "feature": name, "raw_value": float(row[name]),
                             "fitting_mean": float(scaler.mean_[j]), "fitting_scale": float(scaler.scale_[j]),
                             "coefficient": float(model.coef_[0, j]), "standardized_value": float(standardized[position, j]),
                             "logit_contribution": float(contributions[position, j])})
    return pd.DataFrame(evidence), pd.DataFrame(rows), models


def apply_case_reviews(sample, evidence, review_path):
    """Read-only overlay; stale/duplicate/unsupported reviews fail before output writes."""
    import json
    from pathlib import Path
    from phishguard_vn.features import CANDIDATE_FEATURES
    cases = case_manifest(sample)
    if not Path(review_path).is_file():
        raise FileNotFoundError(f"Missing durable offline review file: {review_path}")
    document = json.loads(Path(review_path).read_text())
    if document.get("schema_version") != 1:
        raise ValueError("Unsupported offline review schema")
    reviews = pd.DataFrame(document.get("cases", []))
    if reviews.empty or reviews.id.duplicated().any() or not set(sample.id).issubset(set(reviews.id)):
        raise ValueError("Missing/duplicate case reviews")
    facts = evidence.set_index("id")
    source_rows = sample.set_index("id", drop=False)
    for index, row in cases.iterrows():
        reviewed = reviews.loc[reviews.id.eq(row.id)].iloc[0]
        source, fact = source_rows.loc[row.id], facts.loc[row.id]
        if reviewed.get("case_signature") != case_signature(source):
            raise ValueError(f"Stale offline review for {row.id}; re-review changed evidence")
        for field in ["observation", "hypothesis", "next_verification"]:
            if not isinstance(reviewed.get(field), str) or not reviewed[field].strip():
                raise ValueError(f"Missing {field} in review {row.id}")
        tags = reviewed.get("taxonomy", [])
        if not tags or not set(tags).issubset(TAXONOMY):
            raise ValueError("Unknown/empty reviewed taxonomy")
        if "representation_collision" in tags and fact.opposite_label_fitting_rows == 0:
            raise ValueError("Collision taxonomy lacks opposite-label fitting evidence")
        if "near_threshold" in tags and abs(source.score - 0.5) > 0.05:
            raise ValueError("Near-threshold taxonomy lacks score evidence")
        observed = "; ".join(f"{n}={source[n]:.4f}" for n in ["url_len", "dom_len", "subdom_cnt", "digit_cnt", "dot_cnt", "entropy", "path_len"])
        arithmetic = (f"Correct context={int(fact.context)}; score={source.score:.6f}, margin to 0.5={source.score-0.5:+.6f}; "
                      f"intercept={fact.intercept:+.4f}; positive logit terms [{fact.positive_contributions}]; "
                      f"negative logit terms [{fact.negative_contributions}]; fitting opposite-label identical vectors={int(fact.opposite_label_fitting_rows)}.")
        for field in ["observation", "hypothesis", "next_verification"]:
            cases.loc[index, field] = reviewed[field]
        cases.loc[index, "observation"] += " " + observed
        cases.loc[index, "verified_model_arithmetic"] = arithmetic
        cases.loc[index, "taxonomy"] = "|".join(tags)
        cases.loc[index, "case_signature"] = fact.case_signature
        cases.loc[index, "fitting_collision_example_id"] = fact.get("opposite_label_example_id", "")
        cases.loc[index, "root_cause_status"] = "unverified;model_arithmetic_only_verified"
        cases.loc[index, "review_status"] = "offline_engineering_review_complete;human_semantic_verification_pending"
    return cases
