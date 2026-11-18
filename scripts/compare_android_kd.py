"""Compare frozen Student runs and assemble offline handoff ZIPs for Android."""
import argparse
import hashlib
import json
from time import perf_counter_ns
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from train_lightgbm_student import ROOT, CACHE, load_inputs, write_csv, write_json
from experiment_android_additive import PortableAdditive, ASSETS
from experiment_android_hash import HashReference
from phishguard_vn.student import metrics, sha256
from phishguard_vn.student_lightgbm import HybridLightGBMStudent, load_lightgbm_student
from tiny_mlp_analysis import paired_domain_bootstrap

TABLES = ROOT / "reports/tables"
ART = ROOT / "artifacts"
OUT = TABLES / "android_kd_comparison"
HANDOFF = ART / "android_kd_handoff"


def read(path):
    return json.loads(path.read_text(encoding="utf8"))


def encode(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf8")


def handoff(kind):
    """Include all inference data plus checksums and raw URL reference cases."""
    boost_dir = ART / "android_kd_boost"
    add_dir = ART / "android_kd_additive"
    boost = read(boost_dir / "manifest.json")
    add = read(add_dir / "manifest.json")
    if kind == "boost200":
        model_path = boost_dir / "kd_mixed.json"
        paths = [model_path, *[ROOT / name for name in boost["shared_assets"]]]
        for path in paths:
            if sha256(path) != boost["sha256"][path.relative_to(ROOT).as_posix()]:
                raise ValueError("Boost asset mismatch: " + str(path))
        model = HybridLightGBMStudent(read(paths[1]), read(model_path))
        score_one = lambda url: model.predict_one(url)["score"]
        threshold = read(model_path)["threshold"]
    else:
        model_path = add_dir / "kd.json"
        paths = [model_path, *ASSETS]
        if sha256(model_path) != add["models"]["kd"]:
            raise ValueError("Additive weights mismatch")
        for path in ASSETS:
            if sha256(path) != {k.replace(chr(92), "/"): v for k, v in add["assets"].items()}[path.relative_to(ROOT).as_posix()]:
                raise ValueError("Additive asset mismatch")
        model = PortableAdditive(read(model_path))
        score_one = lambda url: float(model.predict_proba([url])[0])
        threshold = model.threshold

    cases = []
    for case in read(boost_dir / "python_reference.json")["cases"]:
        url = case["url"]
        try:
            value = score_one(url)
        except (TypeError, ValueError):
            if case["status"] != "rejected":
                raise
            cases.append(dict(url=url, status="rejected"))
            continue
        if case["status"] != "classified":
            raise ValueError("Model accepted a rejected input")
        if kind == "boost200":
            np.testing.assert_allclose(value, case["expected"]["kd_mixed"]["score"], atol=1e-12, rtol=0)
        cases.append(dict(url=url, status="classified", score=value, class_id=int(value >= threshold)))
    files = {p.name:p.read_bytes() for p in paths}
    files["python_reference.json"] = encode(cases)
    digest = lambda data: hashlib.sha256(data).hexdigest()
    files["manifest.json"] = encode(dict(family=kind, model=model_path.name, threshold=threshold,
        sha256={name:digest(data) for name,data in files.items()}, preprocessing="canonical-reference-v1",
        e2="frozen E2 v1 extracted from raw URL", e2_source=add["assets"] if kind=="additive16k" else boost["shared_assets"],
        decision_rule="score >= threshold", score_kind="uncalibrated sigmoid", classes=["benign","phishing"],
        input_scope="offline URL text", android_verified=False))
    HANDOFF.mkdir(parents=True, exist_ok=True)
    result = HANDOFF / (kind + ".zip")
    with ZipFile(result, "w") as archive:
        for name,data in files.items():
            archive.writestr(ZipInfo(name, date_time=(1980,1,1,0,0,0)), data,
                             compress_type=ZIP_DEFLATED, compresslevel=6)
    with ZipFile(result) as archive:
        for name,data in files.items():
            if archive.read(name) != data:
                raise ValueError("ZIP roundtrip mismatch")
    return dict(model=kind, file=result.relative_to(ROOT).as_posix(), sha256=sha256(result),
                zip_bytes=result.stat().st_size, valid=sum(c["status"]=="classified" for c in cases),
                rejected=sum(c["status"]=="rejected" for c in cases))


def load_handoff(kind):
    with ZipFile(HANDOFF / (kind + ".zip")) as archive:
        meta = json.loads(archive.read("manifest.json"))
        files = {name:archive.read(name) for name in meta["sha256"]}
    for name,digest in meta["sha256"].items():
        if hashlib.sha256(files[name]).hexdigest() != digest:
            raise ValueError("Handoff data mismatch: " + name)
    # The desktop reference uses the project's frozen extractor and its copies of these same assets.
    for path in ASSETS:
        if files[path.name] != path.read_bytes():
            raise ValueError("Local E2 asset differs from the package: " + path.name)
    bundle = json.loads(files[meta["model"]])
    if kind == "boost200":
        model = HybridLightGBMStudent(json.loads(files["features.json"]), bundle)
        return lambda u: model.predict_one(u)["score"], meta
    model = PortableAdditive(bundle)
    return lambda u: float(model.predict_proba([u])[0]), meta


def compare():
    train, val, _ = load_inputs()
    cv, val_records = [], []
    for folder, run_file, key, prefix in (
        ("android_kd_boost", "cv_predictions.csv.gz", "lr0.10_200x15_", "boost"),
        ("android_kd_additive", "oof.csv.gz", "add16384_", "add"),
        ("android_kd_hash", "oof.csv.gz", "65536_", "hash"),
    ):
        part = pd.read_csv(TABLES / folder / run_file)
        part = part[part.candidate.str.startswith(key)].copy()
        part["candidate"] = prefix + "_" + part.candidate.str[len(key):].replace(
            {"kd_mixed":"kd", "hard_only":"hard"})
        cv.append(part)
        scores = pd.read_csv(TABLES / folder / ("validation_metrics.csv" if prefix=="boost" else "validation.csv"))
        for r in scores.to_dict("records"):
            mode = {"kd_mixed":"kd","hard_only":"hard"}.get(r["mode"],r["mode"])
            val_records.append(dict(candidate=prefix+"_"+mode, threshold=r["threshold"], val_ap=r["ap"],
                                    val_tp=r["tp"], val_fp=r["fp"], val_fn=r["fn"], val_tn=r["tn"],
                                    val_recall=r["recall"], val_precision=r["precision"], val_f1=r["f1"],
                                    val_fpr=r["fpr"], package_bytes=r.get("package_bytes",r.get("total_bytes"))))
    historical = pd.concat([pd.read_csv(CACHE / f"outer{f}_held_reference.csv.gz") for f in (0, 1, 2)])
    cv.append(historical.rename(columns={"target":"y_true","teacher_score":"score"}).assign(candidate="teacher",seed=42))
    oof = pd.concat(cv, ignore_index=True)
    expected = train.set_index("id").sort_index()
    for name, rows in oof.groupby("candidate"):
        aligned = rows.set_index("id").sort_index()
        if not aligned.index.equals(expected.index):
            raise ValueError("Unpaired Train IDs in " + name)
        np.testing.assert_array_equal(aligned.y_true, expected.target)
        np.testing.assert_array_equal(aligned.fold_id, expected.fold_id)
    paired_domain_bootstrap(oof, train.set_index("id").group, [
        ("add_kd","add_hard"), ("boost_kd","boost_hard"), ("hash_kd","hash_hard"),
        ("add_kd","boost_kd"), ("add_kd","teacher")], output_path=OUT / "paired_ap.csv")
    for r in val_records:
        rows = oof[oof.candidate == r["candidate"]]
        r["cv_ap"] = np.mean([metrics(part.y_true,part.score,0.5)["ap"] for _, part in rows.groupby("fold_id")])
        r["train_oof_tp"] = metrics(rows.y_true,rows.score,r["threshold"])["tp"]
        r["train_oof_fp"] = metrics(rows.y_true,rows.score,r["threshold"])["fp"]
    write_csv(OUT / "comparison.csv",pd.DataFrame(val_records))
    write_csv(OUT / "handoff.csv",pd.DataFrame(handoff(k) for k in ("boost200","additive16k")))
    # Interleave models on identical URLs; run the exact models in the ZIPs.
    score_boost, _ = load_handoff("boost200")
    score_add, _ = load_handoff("additive16k")
    hashed = HashReference(ART/"android_kd_hash/kd.zip")
    original = load_lightgbm_student(ROOT, "kd_mixed")
    scorers = dict(boost200=score_boost, additive16k=score_add, hash65536=hashed.score,
                   boost400=lambda u: original.predict_one(u)["score"])
    urls = val.sort_values("id").sample(n=250,random_state=42).url.tolist()
    times = {key:[] for key in scorers}
    for fn in scorers.values():
        for url in urls[:30]:
            fn(url)
    for permutation in (list(scorers), list(reversed(scorers))):
        for url in urls:
            for key in permutation:
                begin = perf_counter_ns()
                scorers[key](url)
                times[key].append((perf_counter_ns()-begin)/1e6)
    write_csv(OUT/"desktop_latency.csv", pd.DataFrame(dict(model=key,p50_ms=np.median(t),
        p95_ms=np.percentile(t,95),calls=len(t),distinct_urls=len(urls),warmup=30) for key,t in times.items()))


if __name__ == "__main__":
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--model", choices=["boost200","additive16k"], default="boost200")
    args.add_argument("--predict", help="Score one URL offline from its ZIP without training")
    args = args.parse_args()
    with threadpool_limits(limits=1):
        if args.predict is None:
            compare()
        else:
            fn, meta = load_handoff(args.model)
            score = fn(args.predict)
            print(json.dumps(dict(score=score, threshold=meta["threshold"], class_id=int(score>=meta["threshold"]))))
