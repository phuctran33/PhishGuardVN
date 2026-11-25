"""Compare the 45-brand reference and extended inspection on the fixed QA fixture."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import platform
from statistics import median, quantiles
from time import perf_counter_ns

from phishguard_vn.brand_features import load_reference
from phishguard_vn.inspection_catalog import load_catalog
from phishguard_vn.url_inspection import inspect_url

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/brand_catalog_eval.csv"
TABLES = ROOT / "reports/tables/week8_9"
DIRECT = {"brand_in_domain", "brand_in_subdomain", "brand_in_path"}
NEGATIVE_GROUPS = {"unrelated", "ambiguous_names"}


def measure(url, catalog):
    start = perf_counter_ns()
    try:
        result = inspect_url(url, catalog=catalog)
    except ValueError:
        signature = (False, set(), set(), set())
    else:
        official = set(result["official_brand_ids"])
        direct = {m["brand_id"] for m in result["matches"] if m["rule"] in DIRECT}
        mismatch = {m["brand_id"] for m in result["matches"] if m["rule"] == "brand_domain_mismatch"}
        signature = (True, official | direct, official, mismatch)
    return signature, (perf_counter_ns() - start) / 1e6


def ratio(n, d):
    return n / d if d else None


def summarize(rows, signatures, gold):
    valid = [row for row in rows if gold[row["case_id"]][0]]
    totals = Counter()
    groups = {}
    for row in rows:
        key = row["case_id"]
        expected, actual = gold[key], signatures[key]
        group = groups.setdefault(row["group"], Counter())
        group["cases"] += 1
        group["brand_set_correct"] += actual[:2] == expected[:2]
        group["all_fields_correct"] += actual == expected
        group["wrong_brand_cases"] += bool(actual[1] - expected[1])
    for row in valid:
        expected, actual = gold[row["case_id"]], signatures[row["case_id"]]
        totals["tp"] += len(actual[1] & expected[1])
        totals["fp"] += len(actual[1] - expected[1])
        totals["fn"] += len(expected[1] - actual[1])
    tp, fp, fn = (totals[key] for key in ("tp", "fp", "fn"))
    negatives = [row for row in valid if row["group"] in NEGATIVE_GROUPS]
    assert all(not gold[row["case_id"]][1] for row in negatives)
    negative_alerts = sum(bool(signatures[row["case_id"]][1]) for row in negatives)
    overall = sum(signatures[key] == expected for key, expected in gold.items())
    return {
        "exact_brand_set_cases": sum(v["brand_set_correct"] for v in groups.values()),
        "fully_correct_cases": overall,
        "wrong_brand_cases": sum(v["wrong_brand_cases"] for v in groups.values()),
        "brand_pairs": {"tp": tp, "fp": fp, "fn": fn},
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
        "benign_negative_cases": len(negatives),
        "benign_negative_wrong_brands": negative_alerts,
        "benign_fpr": ratio(negative_alerts, len(negatives)),
        "groups": {name: dict(values) for name, values in sorted(groups.items())},
    }


def run(rounds):
    start = perf_counter_ns()
    load_reference()
    base_load = (perf_counter_ns() - start) / 1e6
    start = perf_counter_ns()
    catalog = load_catalog()
    extended_load = base_load + (perf_counter_ns() - start) / 1e6
    with FIXTURE.open(encoding="utf-8", newline="") as stream:
        cases = list(csv.DictReader(stream))
    gold = {row["case_id"]: (
        row["valid"] == "1", *(set(filter(None, row[name].split("|")))
                               for name in ("brand_ids", "official_ids", "mismatch_ids"))
    ) for row in cases}
    assert len(cases) == len(gold) and all(v[2] <= v[1] and v[3] <= v[1] for v in gold.values())
    arms = {"baseline": None, "extended": catalog}
    signatures = {name: {} for name in arms}
    latencies = {name: [] for name in arms}
    for row in cases:
        for name, ref in arms.items():
            signatures[name][row["case_id"]], _ = measure(row["url"], ref)
    for repeat in range(rounds):
        order = list(arms) if repeat % 2 == 0 else list(reversed(arms))
        for row in cases:
            if gold[row["case_id"]][0]:
                for name in order:
                    actual, ms = measure(row["url"], arms[name])
                    assert actual == signatures[name][row["case_id"]]
                    latencies[name].append(ms)
    summary = {}
    for name in arms:
        summary[name] = summarize(cases, signatures[name], gold)
        ts = latencies[name]
        summary[name]["latency_ms"] = {
            "p50": median(ts), "p95": quantiles(ts, n=100, method="inclusive")[94], "samples": len(ts),
        }

    base, extended = signatures["baseline"], signatures["extended"]
    gained = [key for key in gold if base[key] != gold[key] == extended[key]]
    regressed = [key for key in gold if base[key] == gold[key] != extended[key]]
    both_missed = [key for key, value in gold.items() if value[1] and
                   not value[1] & base[key][1] and not value[1] & extended[key][1]]
    new_wrong_brands = [key for key, value in gold.items()
                        if (extended[key][1] - value[1]) - base[key][1]]
    summary |= {
        "scope": "fixed offline brand-recognition and domain-status fixture",
        "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        "catalog_sha256": catalog.sha256,
        "sizes": catalog.stats,
        "fixture_cases": len(cases),
        "fixture_valid_cases": sum(row[0] for row in gold.values()),
        "new_fully_correct_ids": gained,
        "regression_ids": regressed,
        "both_fully_missed_ids": both_missed,
        "new_wrong_brand_case_ids": new_wrong_brands,
        "load_ms": {"baseline": base_load, "extended_total": extended_load},
        "python": platform.python_version(),
        "machine": f"{platform.system()} {platform.machine()}",
    }
    rows = []
    for case in cases:
        key = case["case_id"]
        row = {"case_id": key, "group": case["group"]}
        for arm, values in (("expected", gold), *signatures.items()):
            valid, detected, official, mismatch = values[key]
            row |= {f"{arm}_valid": valid, f"{arm}_brands": "|".join(sorted(detected)),
                    f"{arm}_official": "|".join(sorted(official)), f"{arm}_mismatch": "|".join(sorted(mismatch))}
        rows.append(row)
    return summary, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=TABLES)
    parser.add_argument("--rounds", type=int, default=20)
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error("--rounds must be positive")
    summary, rows = run(args.rounds)
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "brand_benchmark.json").open("w", newline="\n", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with (args.out / "brand_benchmark_cases.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    for mode in ("baseline", "extended"):
        print(mode, {k: v for k, v in summary[mode].items() if k != "groups"})
    for key in ("new_fully_correct_ids", "regression_ids", "new_wrong_brand_case_ids", "both_fully_missed_ids", "load_ms"):
        print(key, summary[key])


if __name__ == "__main__":
    main()
