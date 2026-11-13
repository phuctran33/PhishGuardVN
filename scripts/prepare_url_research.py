"""Download only the pinned public encoder artifacts; never visit dataset URLs."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib
import requests
ROOT=Path(__file__).resolve().parents[1]

def main():
    meta=json.loads((ROOT/"configs/url_research_plan.json").read_text())["pretrained"]
    out=ROOT/"data/interim/url_research/pretrained";out.mkdir(parents=True,exist_ok=True)
    previous=json.loads((out/"provenance.json").read_text()) if (out/"provenance.json").exists() else {}
    expected={r["file"]:r["sha256"] for r in previous.get("files",[])}
    rows=[]
    for name in ["config.json","vocab.txt","model.safetensors","README.md"]:
        path=out/name
        url=f"https://huggingface.co/{meta['checkpoint']}/resolve/{meta['revision']}/{name}"
        if not path.exists():
            response=requests.get(url,timeout=90);response.raise_for_status()
            path.write_bytes(response.content)
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if name in expected:
            assert digest==expected[name], "Cached encoder artifact changed; do not relabel its provenance"
        rows.append({"file":name,"url":url,"bytes":path.stat().st_size,
                     "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"status":"available"})
    (out/"provenance.json").write_text(json.dumps({"checkpoint":meta["checkpoint"],
       "revision":meta["revision"],"license":meta["license"],"accessed_utc":datetime.now(timezone.utc).isoformat(),
       "files":rows},indent=2)+"\n",encoding="utf-8")
    print("Pinned encoder/vocabulary available; target websites were not visited.")
if __name__=="__main__":main()
