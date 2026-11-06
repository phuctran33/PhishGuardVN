"""Reproducible qualitative error sampling and static, evidence-limited annotation."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from string import Template

import pandas as pd

from phishguard_vn.url_parser import parse_url


def render_h52_report(root, cases, taxonomy, markdown):
    """Render the fixed scientific narrative with live, ID-backed human status.

    The checklist is authoritative; an AI status or an old aggregate count is
    never sufficient evidence of human review. This function only reads inputs.
    """
    root = Path(root)
    annotations = root / "reports/annotations"
    human = pd.read_csv(annotations / "week5_human_review.csv", dtype=str, keep_default_na=False, encoding="utf-8")
    ai = pd.read_csv(annotations / "week5_ai_review.csv", keep_default_na=False, encoding="utf-8")
    verification = json.loads((root / "reports/tables/week5/verification.json").read_text(encoding="utf-8"))
    confirmation = verification.get("human_review", {})
    if (not cases.id.is_unique or not human.id.is_unique or set(human.id) != set(cases.id)
            or not human.review_status.isin(["pending", "human_verified"]).all()):
        raise ValueError("H5.2 checklist ID/coverage/status mismatch")
    priority_ids = set(human.loc[human.priority_first_30.eq("True"), "id"])
    if not ai.id.is_unique or set(ai.id) != priority_ids:
        raise ValueError("H5.2 AI ledger must match the exact priority IDs")
    indexed = cases.set_index("id")
    if not ai.case_signature.eq(ai.id.map(indexed.case_signature)).all():
        raise ValueError("H5.2 stale AI case signatures")
    confirmed = confirmation.get("confirmed_ids", [])
    verified = human.loc[human.review_status.eq("human_verified")]
    if (len(confirmed) != len(set(confirmed)) or not set(confirmed).issubset(set(cases.id))
            or not set(verified.id).issubset(confirmed)):
        raise ValueError("H5.2 human review IDs lack confirmation evidence")
    if not verified.empty:
        fields = ["reviewer", "reviewed_at", "observation_checked", "hypothesis_assessed", "evidence_checked", "notes"]
        if (not confirmation.get("confirmation_quote") or not verified[fields].ne("").all().all()
                or not verified.reviewer.eq(confirmation.get("reviewer")).all()
                or not verified.reviewed_at.eq(confirmation.get("confirmation_recorded_at_utc")).all()):
            raise ValueError("H5.2 human reviewer/timestamp/evidence mismatch")
    minimum = int(confirmation.get("minimum_personal_reviews_required", 30))
    if minimum < 1:
        raise ValueError("H5.2 minimum review count must be positive")
    count, pending, done = len(verified), int(human.review_status.eq("pending").sum()), len(verified) >= minimum
    status = (f"H5.2 DONE / HUMAN VERIFIED OFFLINE ({count}/{len(human)})" if done else
              f"H5.2 OFFLINE DONE / HUMAN REVIEW PENDING ({count}/{minimum} verified; {pending} pending)")
    method = "Human-assessed error analysis (AI-assisted preparation)" if done else "AI-assisted offline error analysis; human review pending"
    summary = (f"Current checklist: **{count} human_verified, {pending} pending**. Verified IDs were matched to explicit confirmation data, "
               f"including reviewer, confirmation timestamp and review fields. Minimum required: {minimum}. "
               "The confirmation covers offline observations, evidence interpretation and agreement with qualified hypotheses. "
               "reviewed_at records the confirmation-recording time; the prior independent-work date was not supplied. "
               "Regeneration preserves reviewer/date/checks/notes/status by ID.")
    if count:
        summary += f" Reviewer: {confirmation['reviewer']}; recorded at {confirmation['confirmation_recorded_at_utc']}."
    priority = indexed.loc[ai.id]
    evidence = pd.read_csv(root / "reports/tables/week5/error_model_evidence.csv", encoding="utf-8").set_index("id").loc[ai.id]
    counts = priority.taxonomy.str.split("|").explode().value_counts()
    support = lambda frame: frame.groupby(["evaluation_partition", "fold_id", "outcome"], dropna=False).size().reset_index(name="cases")
    assessment = pd.DataFrame([
        ("Observations consistent with offline strings/features and original metadata", len(ai)),
        ("Twelve feature contributions and score arithmetic checked", len(ai)),
        ("Hypothesis plausible_unverified", int(ai.hypothesis_status.eq("plausible_unverified").sum())),
        ("Hypothesis unsupported", int(ai.hypothesis_status.eq("unsupported").sum())),
        ("Still need semantic/root-cause or label evidence", len(ai)),
        ("Human reviews confirmed from explicit user evidence", count),
        ("Human reviews still pending across the original sample", pending)], columns=["Assessment", "Cases"])
    collisions = int(evidence.opposite_label_fitting_rows.gt(0).sum())
    no_matches = int(evidence.same_vector_fitting_rows.eq(0).sum())
    same_label = int((evidence.same_vector_fitting_rows.gt(0) & evidence.opposite_label_fitting_rows.eq(0)).sum())
    near = int(priority.score.sub(.5).abs().le(.05).sum())
    hierarchy = priority.loc[priority.taxonomy.str.split("|").map(lambda tags: "domain_subdomain" in tags)]
    hierarchy_fp = int(hierarchy.outcome.eq("FP").sum())
    acceptance = (f"PASS — {count} ID-backed human offline reviews meet the minimum {minimum}; {pending} additional cases pending" if done else
                  f"PENDING — only {count}/{minimum} ID-backed human offline reviews; {pending} cases pending")
    conclusion = (f"The technical/offline deliverable and minimum {minimum}-case human review requirement are complete based on explicit confirmation. " if done else
                  f"The technical/offline deliverable is complete; human review remains PENDING with {count}/{minimum} confirmed reviews. ")
    conclusion += (f"{pending} cases remain pending. Website behavior, original-label correctness and individual root causes remain unverified where evidence is missing. "
                   "Human review of the analysis does not promote a plausible hypothesis into verified causality or label certification.")
    values = dict(method=method, case_count=len(cases), priority_count=len(ai), minimum_reviews=minimum,
                  all_collisions=int(cases.taxonomy.str.contains("representation_collision", regex=False).sum()),
                  support_table=markdown(support(cases)), taxonomy_table=markdown(taxonomy), human_summary=summary,
                  ai_intro=f"[AI-prepared review ledger](annotations/week5_ai_review.csv) contains the exact {len(ai)} priority IDs in suggested order: {int(priority.outcome.eq('FP').sum())} FP, {int(priority.outcome.eq('FN').sum())} FN. Each has a Vietnamese conclusion, evidence, limitations and next check. Live human review status is taken from the separate checklist.",
                  assessment_table=markdown(assessment), score_error=f"{evidence.score_abs_error.max():.3g}",
                  priority_collisions=collisions, no_matches=no_matches, same_label_only=same_label, no_opposites=no_matches+same_label,
                  scope_note="AI preparation and human review are recorded separately. " + summary + " Hypotheses remain plausible_unverified; no original label is changed or semantic cause certified.",
                  method_note=f"**Method: {method}.** " + summary + (f" Confirmation statement: “{confirmation['confirmation_quote']}”." if count else ""),
                  source_counts=", ".join(f"{source}={n}" for source, n in priority.source.value_counts().items()),
                  priority_support_table=markdown(support(priority)),
                  priority_taxonomy_table=markdown(pd.DataFrame([(name, int(counts.get(name, 0))) for name in TAXONOMY], columns=["Taxonomy", "Priority cases"])),
                  pattern_summary=f"Measured patterns overlap: {collisions} opposite-label fitting collision cases, {near} cases within 0.05 of the fixed threshold, and {len(hierarchy)} hierarchy cases ({hierarchy_fp} FP, {len(hierarchy)-hierarchy_fp} FN). {no_matches} cases have no exact fitting match; {same_label} have only same-label matches. Single-label sources cannot identify source effects independently of labels. Zero-count categories are retained; no synthetic error cases are added.",
                  hierarchy_fp=hierarchy_fp, near_count=near, fp_count=int(priority.outcome.eq("FP").sum()),
                  fn_count=int(priority.outcome.eq("FN").sum()), term_count=len(ai)*12,
                  human_acceptance=acceptance, conclusion="**Conclusion:** " + conclusion)
    template = (root / "reports/templates/week5_h52.md").read_text(encoding="utf-8")
    return status, Template(template).substitute(values)


def update_human_checklist(cases, evidence, path):
    """Refresh offline suggestions by ID while preserving every human-owned field."""
    path = Path(path)
    checklist = cases[["id", "url_safe", "evaluation_partition", "fold_id", "outcome", "score"]].copy()
    # Round-robin within the already fixed diversity sample; include every stratum
    # before taking another case from any stratum. This does not resample errors.
    keys = ["evaluation_partition", "fold_id", "outcome"]
    order = checklist.assign(turn=checklist.groupby(keys, dropna=False).cumcount()).sort_values("turn", kind="stable").id
    ranks = dict(zip(order, range(1, len(order) + 1)))
    checklist["suggested_review_order"] = checklist.id.map(ranks)
    checklist["priority_first_30"] = checklist.suggested_review_order.le(30)
    checklist["suggested_observation"] = cases.observation
    checklist["unverified_hypothesis"] = cases.hypothesis
    lookup = evidence.set_index("id")
    checklist["offline_evidence"] = [
        f"context={r.context}; fit={r.fit_rows}; opposite-label identical vectors={r.opposite_label_fitting_rows}; "
        f"positive logit terms: {r.positive_contributions}; negative: {r.negative_contributions}"
        for r in lookup.loc[checklist.id].itertuples()]
    checklist["next_verification"] = cases.next_verification
    fields = ["reviewer", "reviewed_at", "observation_checked", "hypothesis_assessed", "evidence_checked", "notes", "review_status"]
    if path.is_file():
        prior = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8").set_index("id")
        if not prior.index.is_unique or set(prior.index) != set(checklist.id):
            raise ValueError("Human checklist IDs changed; preserve and reconcile manually")
        for field in fields:
            checklist[field] = checklist.id.map(prior[field])
    else:
        for field in fields:
            checklist[field] = "pending" if field == "review_status" else ""
    checklist.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
    return checklist

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
    document = json.loads(Path(review_path).read_text(encoding="utf-8"))
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
