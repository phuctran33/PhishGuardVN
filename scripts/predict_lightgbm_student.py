"""Offline inference with the requested experimental hybrid LightGBM Student."""
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from phishguard_vn.student_lightgbm import load_lightgbm_student


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("urls",nargs="*")
    p.add_argument("--mode",choices=["hard_only","kd_mixed"])
    p.add_argument("--examples",action="store_true")
    args=p.parse_args()
    urls=args.urls or (["example.com","https://EXAMPLE.com/Login?Q=%2F",
        "https://www.hcmus.edu.vn","https://example.com:8443/path","https://bücher.de/"] if args.examples else [])
    if not urls:p.error("Pass URLs or --examples")
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        model=load_lightgbm_student(ROOT,args.mode)
        for url,result in zip(urls,model.predict_batch(urls)):
            print(json.dumps({"url":url,**result},ensure_ascii=False))
    except (ValueError,TypeError,RuntimeError,OSError) as exc:
        p.error(str(exc))


if __name__=="__main__":
    main()
