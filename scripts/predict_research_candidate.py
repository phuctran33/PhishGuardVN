"""Offline research candidate demo; this does not finalize or load Teacher."""
from pathlib import Path
import sys,argparse,json,hashlib
import joblib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from phishguard_vn.research_preprocessing import frame_from_urls
from phishguard_vn.brand_features import load_reference

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("url");p.add_argument("--candidate",choices=["main","compact"],default="main")
    args=p.parse_args()
    proposal=json.loads((ROOT/"reports/tables/url_research/candidate_proposal.json").read_text())
    assert proposal["teacher_finalized"] is False
    for name,digest in proposal["source_sha256"].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,"Research source changed"
    assert load_reference().sha256==proposal["reference_sha256"]
    row=next(r for r in proposal["candidates"] if r["role"]==args.candidate)
    path=ROOT/row["model_path"]
    assert hashlib.sha256(path.read_bytes()).hexdigest()==row["sha256"]
    model=joblib.load(path)
    X=frame_from_urls([args.url],row["spec"])
    score=float(model.predict_proba(X)[0,1]) if hasattr(model,"predict_proba") else float(model.decision_function(X)[0])
    print(json.dumps({"status":"candidate_proposed","teacher_finalized":False,"experiment":row["experiment"],
          "label":"phishing" if int(model.predict(X)[0]) else "benign","score":score,
          "score_kind":"probability" if hasattr(model,"predict_proba") else "svm_margin"}))
if __name__=="__main__":main()
