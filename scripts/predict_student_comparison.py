"""Offline JSON inference for the selected experimental Student comparison model."""
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from phishguard_vn.student_comparison import load_comparison_student


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls",nargs="*")
    parser.add_argument("--candidate",help="Example: e2_hist__kd_mixed; default from manifest")
    parser.add_argument("--examples",action="store_true")
    args=parser.parse_args()
    urls=args.urls or (["example.com","https://EXAMPLE.com/Login?Q=%2F",
        "https://www.hcmus.edu.vn","https://example.com:8443/path","https://bücher.de/"] if args.examples else [])
    if not urls:parser.error("Pass URLs or --examples")
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        model=load_comparison_student(ROOT,args.candidate)
        for url,row in zip(urls,model.predict_batch(urls)):
            print(json.dumps({"url":url,**row},ensure_ascii=False))
    except (ValueError,TypeError,RuntimeError,OSError) as exc:
        parser.error(str(exc))


if __name__=="__main__":
    main()
