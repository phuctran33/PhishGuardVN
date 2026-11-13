"""Predict offline using the official, hash-checked stacking Teacher (CPython 3.11)."""
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from phishguard_vn.teacher import load_teacher

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("urls",nargs="*")
    p.add_argument("--examples",action="store_true")
    args=p.parse_args()
    urls=args.urls or (["example.com","https://example.com/Login?Q=A","xn--bcher-kva.de",
                       "https://example.com:8443/path","https://www.hcmus.edu.vn"] if args.examples else [])
    if not urls:p.error("Pass one/many URL strings or --examples")
    try:
        model=load_teacher(Path(__file__).resolve().parents[1])
        for url,result in zip(urls,model.predict_batch(urls)):
            print(json.dumps({"url":url,**result},ensure_ascii=False))
    except (ValueError,TypeError,RuntimeError,ImportError,OSError) as exc:
        p.error(str(exc))
if __name__=="__main__":main()
