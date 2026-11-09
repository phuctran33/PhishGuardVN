"""Load Teacher v1 và dự đoán offline; không train hoặc truy cập URL."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from threadpoolctl import threadpool_limits
from phishguard_vn.external_pilot import load_locked_teacher


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?", help="URL cần thử")
    parser.add_argument("--examples", action="store_true", help="Thử năm URL mẫu")
    args = parser.parse_args()
    if args.url is None and not args.examples:
        parser.error("Truyền URL hoặc --examples")
    root = Path(__file__).resolve().parents[1]
    lock = json.loads((root / "configs/week6_teacher_lock.json").read_text(encoding="utf-8"))
    predictor = load_locked_teacher(root, lock)
    urls = [args.url] if args.url else [
        "https://www.vietcombank.com.vn", "https://vietcombank-login.example.com/xacminh",
        "https://example.com/login?account=123", "https://xn--bcher-kva.de", "https://www.hcmus.edu.vn"]
    with threadpool_limits(limits=1):
        for url in urls:
            print(json.dumps({"url": url, **predictor(url)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
