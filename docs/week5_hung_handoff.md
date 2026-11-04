# Hưng — Week 5 handoff (2026-11-04)

| Task | Current status | Evidence / remaining work |
|---|---|---|
| H5.1 E1 evaluation | DONE | Original 12 features, 3 domain folds, seed 42, threshold 0.5; no Test evaluation |
| H5.2 error analysis | OFFLINE REVIEW DONE / HUMAN REVIEW PENDING | Same 40 selected cases and Codex-authored notes; Hưng must personally review at least 30 |
| H5.3 static robustness | DONE | Same 144 static cases; parser validity, flips, score/logit shifts; no accuracy/F1 for unlabeled variants |
| H5.4 native E2 feature audit | FEATURE AUDIT DONE — PASS / PRELIMINARY | Real Hy trainval X: 13,078 Train + 1,585 Validation, 20 features, 2 exclusions |
| H5.4 E2 model comparison | MODEL COMPARISON PENDING | `PENDING_PRODUCER_E2_PREDICTIONS`; no actual 20-feature model comparison claimed |
| KD evaluation protocol | PREPARED | Same folds; fold-safe Teacher/soft targets; hard-only Student; Train-only tuning; matched metrics/support |

## Integration and provenance

Work stays on `week5/hung-evaluation-robustness`. Started clean at published `d667ac8`; fetched remote branches and verified Hy PR #5 merged into main at `0054a1b1844ce12b84030e52952106488b0cbc10`. Merged `origin/main` safely with merge commit `a7413aae3351703429eba518657b08894afae3e7`; no conflicts, reset, force push or change to main. Only Hưng's integration code, tests and handoff outputs are edited beyond that merge. The user authorizes committing/pushing this completed task on Hưng's branch; no PR merge is authorized.

Runtime base, prior upstream publication, source/input hashes and original E1 generation base (`3e9001c`) remain distinct in `reports/tables/week5/run_manifest.json`. A publication after evaluation does not retroactively replace those runtime records. Verification results are in `reports/tables/week5/verification.json`.

PR #5 changes the parser's deprecated `registered_domain` property to `top_domain_under_public_suffix`. Installed tldextract 5.4.0 implements the former as an alias returning the latter. Cache compatibility is allowed only when reversing that exact spelling change reproduces the old parser source hash; all other training sources, dataset, config, library versions and serialized result/lineage must match. Fresh feature/domain/fold parity is still checked. E2/report/dictionary edits do not trigger E1 training. Original E1 predictions, model bytes, metrics and 40-case sampling/notes remain unchanged.

## Commands and paths

From repository root with the existing `.venv` (Python/library versions are recorded in the run manifest):

```sh
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python scripts/05_build_matrix_x_brand.py --partition trainval
.venv/bin/python scripts/run_week5_evaluation.py --feature-only
.venv/bin/python scripts/run_week5_evaluation.py
.venv/bin/python -m pytest -q
.venv/bin/python -m nbconvert --to notebook --execute --inplace notebooks/05_error_robustness.ipynb --ExecutePreprocessor.timeout=600
```

For a clean checkout, first recreate ignored Week-4 handoffs with existing notebooks **01 → 03 → 02**. Do not assume ignored files or model caches were shared. Jupyter requires nbformat/nbclient/nbconvert/ipykernel; if the kernel is missing, register it with `.venv/bin/python -m ipykernel install --prefix .venv --name python3`. The previously recorded environment is in `requirements-week5-lock.txt`; current `pip check`/versions belong to the verification record.

`configs/week5.toml` sets paths relative to root. `[e2].native_manifest` points directly to Hy's `data/interim/05_matrix_X_brand_trainval.manifest.json`; the adjacent CSV and `05_excluded_rows_trainval.csv` retain Hy's exact schemas. Feature-only mode prepares eligible metadata/folds and checks those native artifacts without loading/training any E1/E2 model or requiring predictions/configs/Teacher lineage. Native extraction reads only IDs/URLs and filters to official Train/Validation IDs before feature computation; it does not open `url_test.csv`. Original table loading for E1 filters out Test before extraction/prediction.

The native adapter is one function in `e2_audit.py`; it reuses ID validation, the E1 contract and Hy's constants/reference loader. It does not convert Hy's artifacts into a second manifest system or require changes to Hy's code. Technical failures write `FAIL` with a reason and stop; expected supports are never relaxed to force a pass.

## Native E2 findings and limitations

`reports/tables/week5/e2_feature_audit.json` records actual checks, split counts, exclusions, artifact/dictionary hashes, version, reference summary and extraction commit. X has exactly **id + 12 unchanged E1 features + 8 brand features**, numeric/finite values, exact eligible IDs, unchanged lexical values by ID and no outer-fold domain leakage. Both excluded Train URLs have `unresolved_domain`, matching E1. No Test IDs enter X; excluded raw URL files stay ignored.

Schema is **e2-brand-v0**. Reference file is named `brand_reference_v1.csv`, but that filename is not a frozen E2 v1 claim. Its actual SHA256 is `32198c1734bacd23263eae979465e22d95c2038bfa63cb2107fdbe8cd115f1cf`; all **37** records are `draft`, and **37** `source_accessed` fields are missing. `frozen=false`, `fully_verified=false`: use **PRELIMINARY**. Hy still owns reference/domain/false-match review, provenance completion and any version/freeze decision. Constant/sparse features are retained under the declared schema; no feature selection is performed here.

## What Phúc has supplied and what is missing

Inspected fetched `origin/phuc-week5-models` at `a4f8a18`: `reports/tables/05_readable_metadata.json` declares `week5_readable_v2`, **feature_set=lexical_12**, 12 feature names and no Test evaluation. Reports and the notebook describe advanced models on those 12 features. These are not 20-feature E2 results. No E2 per-sample OOF/Validation files were found among local artifacts or tracked producer-branch files; ignored files on Phúc's machine may exist but have not been delivered. No Phúc model is trained by this task.

Minimum actual E2 handoff needed:

- OOF and supplementary Validation predictions by `id`, candidate, context/fold, original label and predicted label, plus numeric positive-class ranking score.
- Actual 20-feature order/version (`e2-brand-v0` for this matrix), reference SHA256, input/fold hashes, model/preprocessing/config and exact fitting/tuning scope per context. Learned transforms/selection belong inside each fitting partition.
- Explicit `score_kind` and `decision_rule`, class order and any legitimate Train-only threshold/calibration provenance. Teacher candidates can be supplied later; they are not required for feature-only audit.

Phúc v2 uses `estimator.predict`; SVM supplies **decision_function margins**, default margin boundary **0**, while LR/MLP/HistGB use class-1 probabilities. AP accepts ranking scores including margins. Never apply a [0,1] probability check, threshold 0.5 or arbitrary sigmoid to SVM margins. Only add a margin adapter when actual E2 files and the confirmed producer rule arrive. Do not relabel exploratory v0 results as final v1.

The existing optional `[e2].manifest` / `load_e2_bundle` path remains for the already-tested **probability-only** bundle schema in `configs/e2_manifest.example.json`. It is not imposed on Hy's native features and is not a universal model-score interface. Its common-0.5 and separately audited Train-selected operating points are probability-specific. Real model/lineage checks remain mandatory when model artifacts arrive; do not bypass them to ingest margins. Validation/Test never choose models or thresholds.

## Hưng's direct review checklist

`reports/annotations/week5_human_review.csv` has the same 40 case IDs, defanged URL text, partition/fold, FP/FN and score. It is created once and never overwritten by the runner. Hưng should personally inspect **at least 30**, spanning folds, FP/FN and available Validation cases, using `error_cases.csv`, `error_model_evidence.csv` and the 12-feature contribution table in the notebook.

For each personally reviewed case, enter reviewer/date, whether the observation agrees with offline data, whether the hypothesis remains plausible/unsupported, the checked evidence and notes. Do not visit suspect sites or change original labels based on model outputs. An uncertain hypothesis can remain unresolved after review. The 40 durable notes in `week5_error_reviews.json` were written by Codex offline analysis; they are not human verification. This task leaves all checklist rows pending and never promotes generated case status automatically.

## Other evidence and verification

Khiêm's unmerged source audit/datasheet at `79423ee` was already reviewed; its snapshot hashes and Train/Validation corroboration remain in `source_audit_review.json`. Source-label confounding is unresolved. The actual independently reviewed external pilot is still not delivered and is optional for the core matched E2 comparison. Keep it separate from official splits.

Existing KD protocol was read and retained: no KD/Teacher/calibration/bootstrap implementation is added. This task adds only the native feature adapter, feature-only CLI switch, compact human checklist and regression/leakage checks. No new registry or model runner is introduced; historical results are preserved.

Current verification: **182 tests passed, 0 skipped; native extraction, feature-only audit and full evaluation exited 0; notebook Run All executed all 6 code cells without error**. E1 model bytes/predictions/metrics, original 40-case pool/notes and all 144 robustness outputs retain identical SHA256 to the pre-integration snapshot. `pip check` passes. Only the PR #5 alias spelling changed in the parser; Hy sources match main, and KD protocol is unchanged. Full command outcomes and hashes are in `verification.json`. Notebook/report show real feature-audit results and pending model comparison; synthetic fixtures test logic only.

## Continuation prompt

> Continue Hưng's Week-5 work on `week5/hung-evaluation-robustness`; read this handoff, current report/config and applicable AGENTS.md. Preserve uncommitted work. Verify any new producer artifacts by ID/version/hash. Keep H5.2 human review pending until Hưng actually supplies sign-off; preserve the checklist and Codex annotation origin.
>
> Run Hy's native trainval extraction and feature-only audit before model integration. Do not change expected counts to hide dataset drift, force a draft reference to frozen, or retrain E1 for E2/documentation edits. Actual E2 model comparison remains `PENDING_PRODUCER_E2_PREDICTIONS` until Phúc delivers matched 20-feature OOF/Validation predictions and fitting/score provenance. Respect probability versus SVM margin semantics; implement only the minimal adapter for the real confirmed format. Never convert margins with an arbitrary sigmoid, tune on Validation/Test, train Phúc's models or implement KD here. Run relevant tests/CLI/notebook and update statuses from actual evidence. Commit/push only if explicitly authorized for that continuation; never merge a PR or force push.
