"""Check post-training int8 storage for the locked MLP without retuning."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score
from threadpoolctl import threadpool_limits

from kd_bronze_data import DATA_CACHE, ROOT
from kd_bronze_runner import OUT, PLAN, Recipe, fit_once, matrices
from phishguard_vn.student import sha256
from tiny_mlp_export import ASSETS, benchmark, bundle, load_bundle
from train_lightgbm_student import write_csv, write_json


def main():
    lock = json.loads((OUT / "mlp_final_lock.json").read_text(encoding="utf8"))
    cfg = Recipe(**lock["kd_recipe"])
    seeds = lock["verification_seeds"]
    known = pd.read_csv(OUT/"mlp_final_oof.csv.gz")
    known = known[known.candidate.eq(cfg.tag)].set_index(["fold_id","seed","id"])
    folder = ROOT / "artifacts/student_bronze_kd/mlp_final/compact"
    folder.mkdir(parents=True, exist_ok=True)
    results, predictions = [], []
    for fold in PLAN["folds"]:
        data = joblib.load(DATA_CACHE / f"fold{fold}.joblib")
        features = matrices("tfidf", data, cfg.extra_rows)
        held = data["held"]
        for seed in seeds:
            model = fit_once(cfg, seed, data, features)
            native = model.score(features[1])
            archived = known.loc[(fold,seed)].loc[held.id].score
            np.testing.assert_allclose(native, archived, atol=1e-12, rtol=0)
            par = model.parameters
            weights = tuple(par[name] for name in ("first_weight","first_bias","output_weight","output_bias"))
            with TemporaryDirectory() as temp:
                output = folder if (fold,seed)==(0,seeds[0]) else Path(temp)
                full_path = output / "mlp_float32.npz"
                compact_path = output / "mlp_int8.npz"
                for path, quantized in ((full_path,False),(compact_path,True)):
                    pkg = bundle(path, features[3], None, None, weights, .5, quantized=quantized)
                    loaded = load_bundle(path)
                    new_scores = loaded.predict_proba(held.url)
                    if not quantized:
                        np.testing.assert_allclose(native,new_scores,atol=2e-6,rtol=0)
                    diff = np.max(np.abs(native - new_scores))
                    ap = average_precision_score(held.target,new_scores)
                    name = "int8" if quantized else "float32"
                    timing = {}
                    if output==folder:
                        urls = held.sort_values("id").sample(n=250,random_state=2357).url.tolist()
                        timing = benchmark(loaded,urls,warmup=30)
                    results.append(dict(fold=fold,seed=seed,encoding=name,held_ap=ap,
                        native_ap=average_precision_score(held.target,native),delta_ap=ap-average_precision_score(held.target,native),
                        max_abs_score_delta=float(diff),package_bytes=pkg["package_bytes"],npz_bytes=pkg["model_bytes"],
                        sha256=sha256(path),**timing))
                    predictions.append(pd.DataFrame(dict(fold_id=fold,seed=seed,encoding=name,id=held.id,
                                                         y_true=held.target,score=new_scores)))
    table = pd.DataFrame(results)
    write_csv(OUT/"mlp_compression.csv",table)
    write_csv(OUT/"mlp_compression_oof.csv.gz",pd.concat(predictions,ignore_index=True))
    write_json(folder/"manifest.json",dict(candidate=cfg.tag, seed=seeds[0], fold=0,
        files_sha256={p.name:sha256(p) for p in folder.glob("*.npz")},
        required_psl={ASSETS[0].name:sha256(ASSETS[0])}, android_verified=False,
        threshold_scope="Score-only prototype; embedded 0.5 is a serialization field and not a selected operating point.",
        compression="Int8 first layer, per hidden unit scale; Python reference dequantizes arrays into float32.",
        comparison="Same trained weights and TF-IDF; no retuning. Held folds reused in development."))
    print(table.groupby("encoding").held_ap.mean().to_string(),flush=True)
    print(table.dropna(subset=["p95_ms"])[["encoding","package_bytes","p95_ms"]].to_string(index=False),flush=True)


if __name__=="__main__":
    with threadpool_limits(limits=1):
        main()
