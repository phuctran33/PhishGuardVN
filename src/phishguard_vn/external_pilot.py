"""K5.3: offline candidate audit and gated evaluation; no collection or training."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import numpy as np
import pandas as pd

from phishguard_vn.url_parser import SCHEME_RE, parse_url

LABELS = {"benign", "phishing"}
REVIEW_FIELDS = ["id", "candidate_signature", "review_status", "reviewer", "reviewed_at",
                 "review_evidence", "label_scope", "full_url_verified", "source_independence",
                 "review_method", "evidence_document_sha256", "evidence_locator", "evidence_limitations"]


def validate_review_method(review):
    """Document verification is explicitly distinct from human/live-site review."""
    if review["review_method"] not in {"human", "ai_document_review"}:
        raise ValueError("Review method must distinguish human from AI document review")
    if review["review_status"] == "verified" and review["review_method"] == "ai_document_review":
        if (review["label_scope"] != "hostname_historical"
                or str(review["full_url_verified"]).lower() != "false"):
            raise ValueError("AI historical document review cannot verify current/full-URL state")
        if (not re.fullmatch(r"[0-9a-f]{64}", str(review["evidence_document_sha256"]))
                or not str(review["evidence_locator"]).strip()
                or not str(review["evidence_limitations"]).strip()):
            raise ValueError("AI document review requires document hash, locator and limitations")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def url_views(raw_url):
    """Preserve observed scheme/path; host-only is a separate lossy experiment.

    parse_url's fallback http is only a parser aid, never an observed URL field.
    A scheme-independent comparison key is conservative overlap evidence, not
    proof that HTTP/HTTPS resources or URL labels are equivalent.
    """
    if not isinstance(raw_url, str):
        raise ValueError("raw_url must be a string, never coerce missing to 'nan'")
    value = raw_url.strip()
    parsed = parse_url(raw_url)
    explicit = bool(SCHEME_RE.match(value))
    working = value if explicit else "http:"+value if value.startswith("//") else "http://"+value
    try:
        parts = urlsplit(working)
        port = parts.port
    except ValueError:
        parts, port = urlsplit(""), None
    observed_http = explicit and parts.scheme.lower() in {"http", "https"}
    host = parsed.hostname if parsed.is_valid else ""
    host_input = f"[{host}]" if parsed.is_ip and ":" in host else host
    netloc = host_input + (f":{port}" if port is not None else "")
    if parts.username is not None:
        netloc = parts.netloc.rsplit("@", 1)[0] + "@" + netloc
    scheme = parts.scheme.lower() if explicit else ""
    normalized = urlunsplit((scheme, netloc, parts.path, parts.query, parts.fragment)) if host else ""
    if not explicit:
        normalized = normalized.removeprefix("//")
    comparison = urlunsplit(("", netloc, parts.path, parts.query, parts.fragment)).removeprefix("//") if host else ""
    signature = json.dumps([observed_http, bool(parts.path), bool(parts.query), bool(parts.fragment),
                            port is not None, parts.username is not None, value != raw_url])
    return {"normalized_url": normalized, "comparison_url_key": comparison,
            "hostname": host, "registrable_domain": parsed.registrable_domain or "",
            "model_input_host": host_input, "model_input_full": normalized if observed_http and host else "",
            "parse_valid": bool(parsed.is_valid), "parse_error": parsed.error_reason or "",
            "observed_http_scheme": observed_http, "has_path": bool(parts.path), "path": parts.path,
            "has_query": bool(parts.query), "has_fragment": bool(parts.fragment), "has_port": port is not None,
            "has_userinfo": parts.username is not None, "has_unicode": not value.isascii(),
            "has_punycode": any(p.startswith("xn--") for p in host.split(".")), "format_signature": signature}


def candidate_signature(row):
    return hashlib.sha256(json.dumps({k: str(row[k]) for k in
        ["id", "raw_url", "label", "source", "source_reference"]}, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def reference_keys(urls):
    keys = {k: set() for k in ["normalized_url", "comparison_url_key", "hostname", "registrable_domain"]}
    for url in set(urls):
        view = url_views(url)
        for k in keys:
            if view[k]: keys[k].add(view[k])
    return keys


def source_family(source):
    # These are provenance categories, not proof of independent collection.
    if "NCSC" in source: return "NCSC_warning_or_republication"
    if "VNCERT" in source: return "VNCERT_warning"
    if source == "tinnhiemmang": return "NCSC_TinNhiemMang"
    return source


def build_ledger(candidates, core_keys, legacy_keys=None, reviews=None):
    required = {"id", "url", "label", "source", "evidence_ref", "review_status", "review_note"}
    if not required.issubset(candidates) or candidates.id.isna().any() or not candidates.id.is_unique:
        raise ValueError("Candidate schema/unique IDs invalid")
    if not candidates.label.isin(LABELS).all(): raise ValueError("Unknown candidate label")
    ledger = candidates.copy().rename(columns={"url": "raw_url", "evidence_ref": "source_reference",
                                              "hostname": "stored_hostname", "registrable_domain": "stored_registrable_domain"})
    ledger["snapshot_id"] = "k53_current_167"
    views = pd.DataFrame([url_views(u) for u in ledger.raw_url], index=ledger.index)
    ledger = pd.concat([ledger, views], axis=1)
    ledger["stored_url_norm_mismatch"] = ledger.url_norm.ne(ledger.comparison_url_key) if "url_norm" in ledger else False
    ledger["candidate_signature"] = [candidate_signature(r) for r in ledger.to_dict("records")]
    ledger["source_family"] = ledger.source.map(source_family)
    ledger["source_origin_related_to_core"] = ledger.source_family.eq("NCSC_warning_or_republication")
    ledger["source_reference_host"] = ledger.source_reference.map(lambda x:urlsplit(x).hostname or "")
    ledger["review_evidence"] = ledger.review_note
    ledger["reviewer"] = ""; ledger["reviewed_at"] = ""
    ledger["label_scope"] = "unconfirmed"; ledger["full_url_verified"] = False
    ledger["source_independence"] = "unresolved"
    for field in REVIEW_FIELDS[9:]: ledger[field] = ""
    # Never turn a source link/AI observation into a verified label automatically.
    if not ledger.review_status.isin(["pending", "verified", "rejected"]).all():
        raise ValueError("Unknown review status; do not silently promote legacy 'accepted'")
    if ledger.review_status.eq("verified").any():
        raise ValueError("Verified input needs the separate signed review record; raw source files remain candidates")
    if reviews is not None and not reviews.empty:
        if set(reviews.columns) != set(REVIEW_FIELDS) or not reviews.id.is_unique or not set(reviews.id).issubset(ledger.id):
            raise ValueError("Review IDs/schema invalid")
        lookup = ledger.set_index("id")
        for r in reviews.to_dict("records"):
            validate_review_method(r)
            if r["candidate_signature"] != lookup.loc[r["id"], "candidate_signature"]:
                raise ValueError("Stale review: candidate facts changed")
            if r["review_status"] not in {"pending", "verified", "rejected"}:
                raise ValueError("Unknown review status")
            if r["review_status"] != "pending":
                if any(not str(r[k]).strip() for k in ["reviewer", "review_evidence", "reviewed_at"]):
                    raise ValueError("Review lacks identity/time/evidence")
                if pd.isna(pd.to_datetime(r["reviewed_at"], errors="coerce", utc=True)):
                    raise ValueError("Invalid review timestamp")
            if r["review_status"] == "verified":
                source=urlsplit(lookup.loc[r["id"],"source_reference"])
                if source.scheme not in {"http","https"} or not source.hostname:
                    raise ValueError("Verified labels require a usable source reference")
                if r["label_scope"] not in {"hostname_historical","hostname_current","full_url"}:
                    raise ValueError("Verified labels require an explicit representation/time scope")
            if str(r["full_url_verified"]).lower() not in {"true", "false"}:
                raise ValueError("full_url_verified must be explicit true/false")
            mask = ledger.id.eq(r["id"])
            for k in REVIEW_FIELDS[2:]:
                ledger.loc[mask, k] = str(r[k]).lower()=="true" if k=="full_url_verified" else r[k]
    for scope, keys in [("core", core_keys), ("legacy", legacy_keys or {})]:
        for key in ["normalized_url", "comparison_url_key", "hostname", "registrable_domain"]:
            ledger[f"{scope}_overlap_{key}"] = ledger[key].ne("") & ledger[key].isin(keys.get(key, set()))
    for key in ["raw_url", "normalized_url", "model_input_host", "registrable_domain"]:
        usable = ledger[key].ne("")
        ledger[f"shared_{key}"] = usable & ledger[key].duplicated(keep=False)
        conflict = ledger.loc[usable].groupby(key).label.nunique().gt(1)
        ledger[f"conflicting_labels_{key}"] = ledger[key].isin(conflict.index[conflict])
    core_overlap = ledger[[c for c in ledger if c.startswith("core_overlap_")]].any(axis=1)
    # Shared external registrable domains are flagged, never deleted or rejected.
    verified = ledger.review_status.eq("verified") & ledger.reviewer.ne("") & ledger.reviewed_at.ne("") & ledger.review_evidence.ne("")
    shared_input = ledger.shared_model_input_host
    common = verified & ledger.parse_valid & ~core_overlap & ~shared_input
    ledger["eligible_host_only"] = common & ledger.label_scope.isin(["hostname_historical", "hostname_current"])
    ledger["eligible_full_url"] = (verified & ledger.parse_valid & ~core_overlap & ledger.observed_http_scheme
                                    & ledger.full_url_verified & ledger.label_scope.eq("full_url") & ~ledger.shared_normalized_url)
    # No rows, labels or review statuses are removed because of any audit flag.
    if len(ledger)!=len(candidates) or set(ledger.id)!=set(candidates.id): raise ValueError("Lost candidate IDs")
    return ledger


def format_diagnostic(frame, input_column):
    """Candidate-label purity within format strata, NOT detection accuracy."""
    signatures = frame[input_column].map(lambda u:url_views(u)["format_signature"])
    counts = pd.crosstab(signatures, frame.label)
    return {"n":len(frame), "format_strata":len(counts), "pure_strata":int(counts.gt(0).sum(axis=1).eq(1).sum()),
            "apparent_majority_label_matches":int(counts.max(axis=1).sum()),
            "definition":"Resubstitution purity of candidate labels using only format; no model/ground-truth performance claim."}


def evaluate_verified(ledger, predictor, *, representation="host_only", two_class=False):
    """Default recall-only pilot; caller must first validate a frozen Teacher lock.

    Pending/rejected rows remain in the ledger and are never scored as ground
    truth. No threshold/model selection, fitting or leave-source-out training.
    """
    if representation not in {"host_only", "full_url"}: raise ValueError("Unknown representation")
    eligible = ledger[f"eligible_{representation}"].eq(True) & ledger.review_status.eq("verified")
    selected = ledger.loc[eligible].copy()
    if not two_class: selected = selected.loc[selected.label.eq("phishing")]
    if selected.empty:
        return {"status":"BLOCKED_NO_VERIFIED_ELIGIBLE_LABELS", "official":False, "metrics":None,
                "n_candidates":len(ledger), "n_evaluated":0, "by_source":[]}, pd.DataFrame()
    if two_class and set(selected.label)!=LABELS: raise ValueError("Two-class metrics require both verified classes")
    column = "model_input_host" if representation=="host_only" else "model_input_full"
    if selected[["reviewer","reviewed_at","review_evidence"]].eq("").any().any():
        raise ValueError("Eligible flags cannot replace review identity/time/evidence")
    for review in selected.to_dict("records"): validate_review_method(review)
    if pd.to_datetime(selected.reviewed_at,errors="coerce",utc=True).isna().any():
        raise ValueError("Invalid review timestamp")
    scopes={"hostname_historical","hostname_current"} if representation=="host_only" else {"full_url"}
    if not selected.label_scope.isin(scopes).all():raise ValueError("Review scope differs from model representation")
    for r in selected.to_dict("records"):
        if r["candidate_signature"]!=candidate_signature(r) or r[column]!=url_views(r["raw_url"])[column]:
            raise ValueError("Stale review or changed model input")
    if selected[column].eq("").any() or selected[column].duplicated().any():
        raise ValueError("Empty/duplicate model inputs need explicit curation, not silent dropping")
    predictions = []
    for r in selected.to_dict("records"):
        result = predictor(r[column])
        if result["label"] not in LABELS or result["score_kind"] not in {"probability","decision_function"} or not np.isfinite(result["score"]):
            raise ValueError("Invalid inference output; do not silently drop inference failures")
        if result["score_kind"]=="probability" and not 0<=result["score"]<=1: raise ValueError("Invalid probability")
        predictions.append({"id":r["id"],"source":r["source"],"label":r["label"],"prediction":result["label"],
                            "score":result["score"],"score_kind":result["score_kind"],"model_input":r[column]})
    pred = pd.DataFrame(predictions)
    def metrics(group, both):
        positive=group.label.eq("phishing"); predicted=group.prediction.eq("phishing")
        tp=int((positive & predicted).sum()); fn=int((positive & ~predicted).sum())
        fp=int((~positive & predicted).sum()); tn=int((~positive & ~predicted).sum())
        value={"n":len(group),"positive_support":int(positive.sum()),"negative_support":int((~positive).sum()),
               "tp":tp,"fn":fn,"recall_phishing":tp/(tp+fn) if tp+fn else None,
               "precision":None,"f1":None,"accuracy":None,"fpr":None}
        if both:
            value.update(fp=fp,tn=tn,precision=tp/(tp+fp) if tp+fp else None,
                         f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,
                         accuracy=(tp+tn)/len(group),fpr=fp/(fp+tn))
        return value
    per_source=[{"source":source,**metrics(group,False)} for source,group in pred.groupby("source")]
    return {"status":"EXPLORATORY_TWO_CLASS" if two_class else "PHISHING_RECALL_PILOT", "official":False,
            "representation":representation,"metrics":metrics(pred,two_class),"n_candidates":len(ledger),
            "n_evaluated":len(pred),"by_source":per_source,
            "review_methods":selected.review_method.value_counts().to_dict(),
            "limitations":["No source-disjoint generalization claim; source-label confounding remains.",
                           "Host-only is lossy and needs host-scoped reviewed labels; no live-site verification implied."]}, pred


def load_locked_teacher(root, lock):
    """Only trusted local bundles with a pre-external, Core-CV Teacher decision."""
    from phishguard_vn.brand_features import FEATURE_SCHEMA_VERSION
    from phishguard_vn.features import CANDIDATE_FEATURES
    from phishguard_vn.prediction import predict_url
    if (lock.get("teacher_finalized") is not True or lock.get("selected_by")!="core_train_group_cv"
            or lock.get("external_used_for_selection") is not False):
        raise ValueError("Teacher must be finalized using Core Train Group CV before external evaluation")
    if lock.get("feature_set") not in {"lexical_12",FEATURE_SCHEMA_VERSION}:
        raise ValueError("Frozen Teacher schema differs from current extractor; do not relabel v0 as v1")
    if lock.get("score_kind") not in {"probability","decision_function"}: raise ValueError("Unknown Teacher score kind")
    if lock.get("decision_rule")!="estimator.predict" or lock.get("operating_point_scope")!="fixed_core_protocol":
        raise ValueError("Use the existing fixed Core decision rule; no external/Validation retuning")
    if lock.get("threshold") != (0 if lock.get("score_kind")=="decision_function" else .5):
        raise ValueError("Operating point differs from the unchanged Core protocol")
    for key in ["bundle", "selection_record"]:
        p=Path(root)/lock[key]["path"]
        if not p.is_file() or sha256(p)!=lock[key]["sha256"]: raise ValueError(f"Missing/changed {key}")
    selection=json.loads((Path(root)/lock["selection_record"]["path"]).read_text(encoding="utf-8"))
    if selection.get("primary_metric")!="mean_outer_average_precision" or selection.get("test_evaluated") is not False:
        raise ValueError("Selection record is not the fixed Core Train Group CV protocol")
    prefix="E1" if lock["feature_set"]=="lexical_12" else "E2"
    if prefix=="E2" and selection.get("feature_schema_version")!=FEATURE_SCHEMA_VERSION:
        raise ValueError("Core selection evidence belongs to a different E2 version")
    if f'{prefix}__{lock["model_name"]}' not in selection.get("teacher_candidates",[]):
        raise ValueError("Teacher not in the Core-CV shortlist")
    import joblib
    bundle=joblib.load(Path(root)/lock["bundle"]["path"])  # User-provided trusted local artifact only.
    if bundle["feature_set"]!=lock["feature_set"] or bundle["protocol"]!=selection["protocol"]:
        raise ValueError("Bundle does not match the selection/feature protocol")
    expected=list(CANDIDATE_FEATURES)
    if lock["feature_set"]!="lexical_12":
        from phishguard_vn.brand_features import E2_FEATURES,load_reference
        expected=list(E2_FEATURES)
        if bundle["brand_reference"].sha256!=load_reference().sha256: raise ValueError("Teacher reference snapshot differs")
        if selection.get("reference",{}).get("sha256")!=bundle["brand_reference"].sha256:
            raise ValueError("Selection record reference differs from Teacher")
    if bundle["feature_names"]!=expected or bundle["score_kinds"][lock["model_name"]]!=lock["score_kind"]:
        raise ValueError("Feature order/score kind differs from locked Teacher")
    if list(bundle["models"][lock["model_name"]].classes_)!=[0,1]:
        raise ValueError("Teacher class order must be benign=0, phishing=1")
    return lambda url:predict_url(url,bundle,lock["model_name"])
