"""Load model v2 để dự đoán URL; không train lại."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import joblib
from threadpoolctl import threadpool_limits
from phishguard_vn.prediction import predict_url


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--model", default=None)
    parser.add_argument("--feature-set", choices=["legacy", "E1", "E2"], default="legacy",
                        help="legacy: bundle 05_advanced_models; E1/E2: bundle 05_e2_ablation")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    filename = ("week5_readable_models.joblib" if args.feature_set == "legacy"
                else f"week5_{args.feature_set.lower()}_ablation.joblib")
    bundle = joblib.load(root / "models" / filename)
    with threadpool_limits(limits=1):
        result = predict_url(args.url, bundle, args.model)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
