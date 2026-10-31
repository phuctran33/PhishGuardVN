"""Reconstruct/audit E1, sample errors, run offline robustness and optionally audit E2."""
from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from phishguard_vn.paths import get_project_root
from phishguard_vn.week5 import run_week5


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--rebuild-e1", action="store_true", help="Regenerate actual fold-held-out predictions with merged E1 pipeline")
    parser.add_argument("--robustness-only", action="store_true", help="Independent parser/extractor stress test; no data/model required")
    args = parser.parse_args()
    result = run_week5(get_project_root(), args.config, rebuild_e1=args.rebuild_e1, robustness_only=args.robustness_only)
    for key, value in result.items():
        print(key + ":", value.to_string(index=False) if hasattr(value, "to_string") else value)


if __name__ == "__main__":
    main()
