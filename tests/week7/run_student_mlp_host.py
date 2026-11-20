"""Chạy QA Python–Dart/UI của Hy và lưu kết quả kể cả khi test thất bại."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--android-root", type=Path, required=True)
    parser.add_argument("--student-root", type=Path, required=True)
    parser.add_argument("--flutter", default="flutter")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    qa = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(qa / "tests/week7/prepare_student_mlp_runtime.py"),
                    "--android-root", str(args.android_root.resolve()), "--student-root", str(args.student_root.resolve())], check=True)
    executable = shutil.which(args.flutter) or args.flutter
    harness = qa / "tests/week7/.student_mlp_android_harness"
    logs = harness / "qa_logs"
    logs.mkdir(exist_ok=True)
    pub_log = logs / "pub.log"
    with pub_log.open("w", encoding="utf-8") as log:
        subprocess.run([executable, "pub", "get"], cwd=harness, stdout=log, stderr=subprocess.STDOUT, check=True)
    machine_log = logs / "flutter-tests.jsonl"
    with machine_log.open("w", encoding="utf-8") as log:
        result = subprocess.run([executable, "test", "--no-pub", "--reporter=json", "test/mlp_host_test.dart"],
                                cwd=harness, stdout=log, stderr=subprocess.STDOUT)
    events = []
    for line in machine_log.read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    reports = [json.loads(e["message"].split("QA_MLP_REPORT=", 1)[1]) for e in events
               if e.get("type") == "print" and e.get("message", "").startswith("QA_MLP_REPORT=")]
    report = reports[-1] if reports else {"status": "failed", "error": "No completed MLP QA report"}
    names = {e["test"]["id"]: e["test"]["name"] for e in events if e.get("type") == "testStart"}
    completed = [e for e in events if e.get("type") == "testDone" and not e.get("hidden", False)]
    report["tests"] = {"passed": sum(e["result"] == "success" and not e["skipped"] for e in completed),
                       "failed": sum(e["result"] != "success" for e in completed),
                       "skipped": sum(bool(e["skipped"]) for e in completed),
                       "failures": [names[e["testID"]] for e in completed if e["result"] != "success"]}
    report["flutter_exit_code"] = result.returncode
    if result.returncode or report["tests"]["skipped"] or len(completed) != 79:
        report["status"] = "failed"
    report["source_provenance"] = json.loads((harness / "qa_provenance.json").read_text(encoding="utf-8"))
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "tests": report["tests"], "classified": report.get("classified_matched"),
                      "rejected": report.get("rejected_matched"), "max_score_delta": report.get("max_score_delta"),
                      "output": str(output)}, ensure_ascii=False))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
