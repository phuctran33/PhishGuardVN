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
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    bundle = joblib.load(root / "models/week5_readable_models.joblib")
    with threadpool_limits(limits=1):
        result = predict_url(args.url, bundle, args.model)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
