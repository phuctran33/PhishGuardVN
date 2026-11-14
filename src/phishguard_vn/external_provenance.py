"""Strict frozen-audit validation with one explicitly registered adapter revision."""
from pathlib import Path
import json,hashlib
def validate_audit_manifest(root,manifest):
    root=Path(root)
    p=root/"reports/tables/teacher_release/external_adapter_lineage.json"
    lineage=json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    revisions=lineage.get("revisions",[lineage])
    for path,expected in {**manifest["inputs_sha256"],**manifest["outputs_sha256"]}.items():
        actual=hashlib.sha256((root/path).read_bytes()).hexdigest()
        if actual==expected:continue
        allowed={"src/phishguard_vn/external_pilot.py":"text_teacher_dispatch_only",
                 "scripts/evaluate_external_pilot.py":"reviewed_text_teacher_cli"}
        if path in allowed and any(r.get("path")==path and r.get("historical_sha256")==expected
             and r.get("current_sha256")==actual and r.get("change")==allowed[path] for r in revisions):
            continue
        raise ValueError(f"Stale audit input/output: {path}; review audit/adapter provenance")
