"""Summarize saved released-Teacher errors. No inference, fitting or Test reads."""

from __future__ import annotations
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from phishguard_vn.url_inspection import inspect_url

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/tables/week7"


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    lock = json.loads((ROOT / "configs/teacher_lock.json").read_text(encoding="utf-8"))
    saved = ROOT / "reports/tables/stacking/candidate"
    evaluation = json.loads((saved / "evaluation.json").read_text(encoding="utf-8"))
    metadata = json.loads((saved / "metadata.json").read_text(encoding="utf-8"))
    assert lock["teacher_finalized"] and lock["promoted"]
    assert (
        sha(ROOT / lock["bundle"]["path"])
        == evaluation["bundle_sha256"]
        == metadata["model_sha256"]
        == lock["bundle"]["sha256"]
    )
    assert metadata["threshold"] == lock["threshold"]
    validation = read_csv(ROOT / "data/splits/url_val.csv")
    assert all(r["split"] == "val" for r in validation)
    by_id = {r["id"]: r for r in validation}
    assert len(by_id) == len(validation)
    inputs = [
        "configs/teacher_lock.json",
        "reports/tables/stacking/candidate/evaluation.json",
        "reports/tables/stacking/candidate/metadata.json",
        "data/splits/url_val.csv",
        "reports/tables/stacking/candidate/validation_predictions.csv",
        "reports/tables/stacking/candidate/external_predictions.csv",
        "src/phishguard_vn/resources/brand_reference_v1.csv",
        "src/phishguard_vn/brand_features.py",
        "src/phishguard_vn/url_parser.py",
    ]
    rows, summaries = [], {}
    for split, filename in [
        ("validation", "validation_predictions.csv"),
        ("external", "external_predictions.csv"),
    ]:
        records = read_csv(saved / filename)
        assert len({r["id"] for r in records}) == len(records)
        if split == "validation":
            assert {r["id"] for r in records} <= set(
                by_id
            )  # Core subset, not all silver Validation rows.
            assert len({r["id"] for r in records}) == len(records)
        counts, sources, groups = Counter(), {}, Counter()
        for r in records:
            if split == "validation":
                raw = by_id[r["id"]]
                url = raw["url"]
                label = int(r["y_true"])
                assert label == int(raw["label"] == "phishing")
                source = raw["source"]
                prediction = int(r["prediction"])
            else:
                url = r["model_input"]
                source = r["source"]
                label = int(r["label"] == "phishing")
                prediction = int(r["prediction"] == "phishing")
            assert label in (0, 1) and prediction in (0, 1)
            score = float(r["score"])
            assert 0 <= score <= 1
            assert prediction == int(score >= lock["threshold"])
            error = (
                ("TP" if label else "FP") if prediction else ("FN" if label else "TN")
            )
            counts[error] += 1
            sources.setdefault(source, Counter())[error] += 1
            if label == prediction:
                continue
            i = inspect_url(url)
            f = i["features"]
            observed = []
            if f["brand_domain_mismatch"]:
                observed.append("brand_mismatch")
            if f["brand_in_subdomain"]:
                observed.append("brand_in_subdomain")
            if f["brand_in_path"]:
                observed.append("brand_in_path_query")
            if f["brand_typo_score"]:
                observed.append("brand_near_match")
            if f["homoglyph_brand_hit"]:
                observed.append("homoglyph_rule")
            if f["idna_flag"]:
                observed.append("idna")
            if i["is_ip"]:
                observed.append("ip")
            if not i["matches"]:
                observed.append("no_reference_signal")
            if split == "external":
                observed.append("historical_host_only")
            for g in observed:
                groups[f"{error}:{g}"] += 1
            observation = f"{error}; saved score {score:.17g} {'>=' if prediction else '<'} lock threshold. Registered domain: {i['registrable_domain']}; offline rule signals: {', '.join(observed) or 'other_reference_signal'}."
            if error == "FN":
                hypothesis = (
                    "Host-only input may omit discriminative path/query evidence; lexical similarity may differ from Train."
                    if split == "external"
                    else "Some labeled phishing URLs may resemble benign lexical patterns or lack reference coverage."
                )
            else:
                hypothesis = "Benign lexical patterns may overlap phishing training patterns; a rule match does not establish a causal contribution to the stacking score."
            if f["brand_domain_mismatch"]:
                hypothesis += " The rule mismatch coexists with the error; it does not prove which branch/meta-LR caused it."
            rows.append(
                dict(
                    id=r["id"],
                    split=split,
                    source=source,
                    label="phishing" if label else "benign",
                    prediction="phishing" if prediction else "benign",
                    score=r["score"],
                    error=error,
                    url_defanged=url.replace("https://", "hxxps://")
                    .replace("http://", "hxxp://")
                    .replace(".", "[.]"),
                    observation=observation,
                    hypothesis=hypothesis,
                    hypothesis_status="plausible_unverified",
                    next_check="Inspect saved branch scores/Train-neighbor evidence for this ID without changing the operating point; independently review historical label scope. No live URL visit.",
                    rule_evidence=json.dumps(i["matches"], ensure_ascii=False),
                    human_verification="not_performed",
                )
            )
        for key in ["tp", "fp", "tn", "fn"]:
            assert counts[key.upper()] == evaluation[split][key]
        summaries[split] = dict(
            n=len(records),
            positive=counts["TP"] + counts["FN"],
            negative=counts["TN"] + counts["FP"],
            counts=dict(counts),
            error_groups=dict(sorted(groups.items())),
            by_source={s: dict(c) for s, c in sorted(sources.items())},
        )
    return rows, dict(
        model_version=lock["model_version"],
        threshold=lock["threshold"],
        protocol=lock["operating_point_scope"],
        bundle_sha256=lock["bundle"]["sha256"],
        method="Read-only saved labeled predictions; no new evaluation, model fit, threshold selection or Official Test access.",
        inputs_sha256={p: sha(ROOT / p) for p in inputs},
        summaries=summaries,
    )


if __name__ == "__main__":
    rows, summary = build()
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "teacher_errors.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (OUT / "teacher_error_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({s: v["counts"] for s, v in summary["summaries"].items()}))
