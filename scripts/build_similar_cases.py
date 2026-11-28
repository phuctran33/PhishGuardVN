"""Build the redacted historical catalogue from the released PhishVN Train split."""

import argparse
from collections import Counter
import csv
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path

from phishguard_vn.similar_cases import (
    CORPUS_PATH,
    IDENTIFIER,
    SCHEMA_VERSION,
    HistoricalCase,
    supported_hostname,
)
from phishguard_vn.url_parser import SCHEME_RE, parse_url


ROOT = Path(__file__).resolve().parents[1]
TIERS = ("gold", "silver")


def build_catalogue(train_path: Path) -> dict:
    data = train_path.read_bytes()
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""))
    required = {"id", "url", "label", "tier", "split", "source"}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError("Train CSV is missing required columns")

    eligible = []
    for row in reader:
        if row["split"] != "train":
            raise ValueError("Catalogue input must contain Train rows only")
        if row["label"] == "phishing" and row["tier"] in TIERS:
            eligible.append(row)

    cases = {}
    invalid = duplicates = paths_removed = queries_removed = 0
    # Prefer verified Gold, then use a stable case ID as a tie-breaker.
    for row in sorted(eligible, key=lambda row: (row["tier"] != "gold", row["id"])):
        url = row["url"].strip()
        scheme = url.split("://", 1)[0].lower() if SCHEME_RE.match(url) else "http"
        parsed = parse_url(url)
        if (scheme not in {"http", "https"} or not parsed.is_valid
                or not supported_hostname(parsed.hostname)
                or not IDENTIFIER.fullmatch(row["source"]) or not IDENTIFIER.fullmatch(row["id"])):
            invalid += 1
            continue
        if parsed.hostname in cases:
            duplicates += 1
            continue
        # The catalogue and the query both use hostname only. Do not redistribute
        # credentials, request parameters, paths, ports or fragments from the CSV.
        paths_removed += bool(parsed.path.strip("/"))
        queries_removed += bool(parsed.query)
        cases[parsed.hostname] = HistoricalCase(row["id"], parsed.hostname, scheme, row["source"])
    records = sorted(cases.values(), key=lambda case: case.case_id)
    if not records or len({case.case_id for case in records}) != len(records):
        raise ValueError("Catalogue is empty or case IDs are not unique")
    return {
        "schema": SCHEMA_VERSION,
        "manifest": {
            "dataset": "PhishVN 3.1.0, Thai Nguyen Vu",
            "doi": "10.17632/b97hxbxtpd.4",
            "license": "CC BY 4.0",
            "input_split": "train",
            "input_sha256": hashlib.sha256(data).hexdigest(),
            "tiers": list(TIERS),
            "eligible_rows": len(eligible),
            "invalid_or_unsupported_rows": invalid,
            "duplicate_hostname_rows": duplicates,
            "paths_removed": paths_removed,
            "queries_removed": queries_removed,
            "cases": len(records),
            "source_counts": dict(sorted(Counter(case.source for case in records).items())),
        },
        "cases": [asdict(case) for case in records],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", type=Path, default=ROOT / "data/splits/url_train.csv")
    parser.add_argument("--output", type=Path, default=CORPUS_PATH)
    args = parser.parse_args()
    catalogue = build_catalogue(args.train)
    # One short line per case keeps diffs and handoff data readable.
    header = json.dumps({k: v for k, v in catalogue.items() if k != "cases"}, indent=2)
    rows = ",\n".join(f"    {json.dumps(case)}" for case in catalogue["cases"])
    args.output.write_text(header[:-2] + ',\n  "cases": [\n' + rows + "\n  ]\n}\n",
                           encoding="utf-8", newline="\n")
    print(json.dumps(catalogue["manifest"], indent=2))


if __name__ == "__main__":
    main()
