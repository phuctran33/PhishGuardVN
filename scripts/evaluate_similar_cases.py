"""Summarize development retrieval coverage and latency using Validation queries."""

from collections import Counter
import csv
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from phishguard_vn.similar_cases import CORPUS_PATH, SimilarCasesIndex
from phishguard_vn.url_parser import parse_url


ROOT = Path(__file__).resolve().parents[1]


def main():
    started = perf_counter()
    index = SimilarCasesIndex.load(CORPUS_PATH)
    startup_ms = (perf_counter() - started) * 1000
    corpus_hosts = {case.hostname for case in index.cases}
    with (ROOT / "data/splits/url_val.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = [row for row in csv.DictReader(stream) if row["tier"] in {"gold", "silver"}]
    if {row["split"] for row in rows} != {"val"}:
        raise ValueError("Expected the development Validation split")

    outcomes = {"phishing": Counter(), "benign": Counter()}
    accepted = []
    for row in rows:
        host = parse_url(row["url"])
        counters = outcomes[row["label"]]
        if not host.is_valid:
            counters["invalid"] += 1
        elif host.hostname in corpus_hosts:
            counters["exact_corpus_host_excluded"] += 1
        else:
            accepted.append(row)

    for row in accepted[:10]:
        index.search(row["url"])
    timings_ms = []
    for row in accepted:
        started = perf_counter()
        cases = index.search(row["url"])
        timings_ms.append((perf_counter() - started) * 1000)
        counters = outcomes[row["label"]]
        counters["queries"] += 1
        counters["with_matches" if cases else "empty"] += 1

    print(json.dumps({
        "scope": "Gold/Silver Validation queries outside exact Train hosts",
        "catalogue_cases": len(index.cases),
        "startup_ms": round(startup_ms, 3),
        "lookup_p50_ms": round(float(np.percentile(timings_ms, 50)), 3),
        "lookup_p95_ms": round(float(np.percentile(timings_ms, 95)), 3),
        "by_label": outcomes,
    }, indent=2))


if __name__ == "__main__":
    main()
