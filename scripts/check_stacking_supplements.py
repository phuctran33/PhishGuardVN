"""User-requested addendum checks, no training and no changes to historical outputs."""
from pathlib import Path
from urllib.parse import urlsplit
import json
import sys
import joblib
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import run_stacking as run
from summarize_stacking import transform_url
from phishguard_vn.stacking import raw_frame, score_model
from phishguard_vn.url_parser import SCHEME_RE, parse_url

OUT = run.OUT


def parts(value):
    working = value if SCHEME_RE.match(value) else ("http:" + value if value.startswith("//") else "//" + value)
    return urlsplit(working)


def main():
    train = run.load_train()
    source_table = pd.crosstab(train.source, train.label).reset_index()
    run.write_csv(OUT / "source_label.csv", source_table)
    ledger = pd.read_csv(OUT / "fit_ledger.csv")
    historical = ledger.loc[ledger.context.str.startswith("outer")]
    hist = historical.loc[historical.model.isin(["hist", "histgb"])]
    assert hist.training_rows.max() < 10000
    checks = []
    # Verify saved outer HistGB and every fixed-base cache; preserve all fitted objects.
    for path in list(run.LOCAL.glob("histgb_outer*.joblib")) + list(run.LOCAL.glob("stack_hist_outer*.joblib")) + list((run.LOCAL / "base_cache").glob("*.joblib")):
        value = joblib.load(path)
        if isinstance(value, dict):
            model = value["bases"]["hist"]
        elif hasattr(value, "bases"):
            model = value.bases["hist"]
        else:
            model = value
        fitted = model.named_steps["model"]
        assert fitted.do_early_stopping_ is False and fitted.n_iter_ == 300
        checks.append(dict(path=path.relative_to(ROOT).as_posix(), sha256=run.sha(path),
            parameter=fitted.early_stopping, effective_early_stopping=False, n_iter=300))
    changed = [transform_url(u, "uppercase_hostname") for u in train.url]
    path_query_equal, host_changed, domain_equal = [], [], []
    for original, modified in zip(train.url, changed):
        a, b = parts(original), parts(modified)
        assert (a.path, a.query, a.fragment, a.username, a.password, a.port) == (b.path, b.query, b.fragment, b.username, b.password, b.port)
        # Compare netloc hostname text, not .hostname (urlsplit lowercases ASCII there).
        a_host = a.netloc.rsplit("@", 1)[-1].split(":")[0]
        b_host = b.netloc.rsplit("@", 1)[-1].split(":")[0]
        host_changed.append(a_host != b_host)
        path_query_equal.append(True)
        domain_equal.append(parse_url(original).registrable_domain == parse_url(modified).registrable_domain)
    assert all(domain_equal)
    stress_frame = raw_frame(changed)
    rows = []
    for name in ["raw_svm", "stack_hist"]:
        for fold in [0, 1, 2]:
            model = joblib.load(run.LOCAL / f"{name}_outer{fold}.joblib")
            mask = train.fold_id.eq(fold).to_numpy()
            score = score_model(model, stress_frame.loc[mask])
            pred = model.predict(stress_frame.loc[mask])
            saved = pd.read_csv(OUT / "stress.csv").query("experiment == @name and fold == @fold and transform == 'uppercase_hostname'").iloc[0]
            current = run.metrics(train.loc[mask, "target"], pred, score)
            for key, value in current.items():
                assert abs(value - saved[key]) < 1e-12, (name, fold, key)
            rows.append(dict(experiment=name, fold=fold, **current))
    run.write_csv(OUT / "hostname_case_recheck.csv", pd.DataFrame(rows))
    run.write_json(OUT / "supplement.json", dict(
        historical_benchmark_preserved=True, grid_retrained=False,
        hist_cv_fits=len(hist), hist_max_cv_fitting_rows=int(hist.training_rows.max()),
        hist_persisted_checks=checks, candidate_full_train_before_addendum=False,
        case_rows=len(train), actual_hostname_text_changed=int(sum(host_changed)),
        path_query_userinfo_fragment_port_preserved=all(path_query_equal),
        registrable_domain_preserved=all(domain_equal), outer_case_metrics_recomputed=True,
        source_label_pure=bool(source_table[["benign", "phishing"]].gt(0).sum(axis=1).eq(1).all()),
        limitation="All phishing and benign sources are disjoint by label. Domain Group CV and removing source input do not remove URL source proxies or establish source-disjoint generalization.",
        source_sha256=run.sha(Path(__file__)), addendum_sha256=run.sha(ROOT / "configs/teacher_v2_addendum.json")))
    print(source_table.to_string(index=False))
    print("Addendum checks PASS; historical benchmark and raw labels unchanged.")


if __name__ == "__main__":
    from threadpoolctl import threadpool_limits
    with threadpool_limits(limits=2):
        main()
