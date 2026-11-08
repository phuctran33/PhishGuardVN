"""Evaluate only reviewed external labels with a locked trusted Teacher; never train."""
from pathlib import Path
import argparse
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import pandas as pd
from phishguard_vn.external_pilot import evaluate_verified,load_locked_teacher,sha256


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--teacher-lock',type=Path)
    ap.add_argument('--representation',choices=['host_only','full_url'],default='host_only')
    ap.add_argument('--two-class',action='store_true',help='Exploratory only; requires both verified classes')
    args=ap.parse_args()
    out=ROOT/'reports/tables/external_pilot';manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
    for path,digest in {**manifest['inputs_sha256'],**manifest['outputs_sha256']}.items():
        if sha256(ROOT/path)!=digest: raise ValueError(f'Stale audit input/output: {path}; rerun audit')
    ledger=pd.read_csv(ROOT/'data/external/derived/k53_candidates.csv',keep_default_na=False,encoding='utf-8')
    reasons=[]
    if not ledger.review_status.eq('verified').any():reasons.append('NO_VERIFIED_LABELS')
    if args.teacher_lock is None:reasons.append('NO_FINALIZED_TRUSTED_TEACHER_ARTIFACT')
    if reasons:
        result={'status':'PREPARED_BLOCKED','official':False,'blockers':reasons,'metrics':None,
                'n_candidates':len(ledger),'n_evaluated':0,'representation':args.representation,
                'note':'No candidate/model-predicted labels used as ground truth. No inference or training performed.'}
    else:
        lock=json.loads(args.teacher_lock.read_text(encoding='utf-8'))
        predictor=load_locked_teacher(ROOT,lock)
        result,predictions=evaluate_verified(ledger,predictor,representation=args.representation,two_class=args.two_class)
        result['teacher_lock_sha256']=sha256(args.teacher_lock)
        if not predictions.empty:
            predictions.to_csv(out/'verified_predictions.csv',index=False,encoding='utf-8',lineterminator='\n')
    # Prevent stale previous predictions surviving a newly blocked audit/run.
    if result['n_evaluated']==0:
        (out/'verified_predictions.csv').unlink(missing_ok=True)
    (out/'benchmark_status.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['n_evaluated']>0 else 2  # Blocked is never a successful evaluation.


if __name__=='__main__': raise SystemExit(main())
