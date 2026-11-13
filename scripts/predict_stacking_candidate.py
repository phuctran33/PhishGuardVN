"""Offline research-candidate inference; never replaces the Teacher v1 CLI."""
from pathlib import Path
import argparse
import json
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from phishguard_vn.stacking_candidate import load_candidate

EXAMPLES = ["example.com", "https://EXAMPLE.com/A?Q=%2F",
    "https://bank-login-example.com/verify", "https://xn--bcher-kva.de/A",
    "https://example.com:8443/Case"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="*")
    parser.add_argument("--examples", action="store_true")
    args = parser.parse_args()
    urls = args.urls or (EXAMPLES if args.examples else [])
    if not urls:
        parser.error("Supply URLs or --examples")
    candidate = load_candidate(ROOT)
    print(json.dumps(candidate.predict_batch(urls), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
