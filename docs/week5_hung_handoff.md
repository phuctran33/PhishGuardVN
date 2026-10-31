# Hưng — Week 5 handoff and continuation

## Current state

| Task | Status | Evidence / remaining dependency |
|---|---|---|
| H5.1 E1 evaluation | DONE | Reconstructed from merged Phúc pipeline; exact eligible ID/label/fold/threshold validation; metrics, strata, shift and figures in reports/tables/week5 and reports/figures/week5 |
| H5.2 error analysis | DONE (static scope) | 40 reproducible FP/FN cases across folds and Validation, each with durable case-specific offline notes, exact fitting-context LR arithmetic and fitting-only collision diagnostics; observations/hypotheses separated. Human semantic checks remain explicitly pending; labels unchanged |
| H5.3 static robustness | DONE | 24 transformations × 6 reserved-example bases, exact feature/logit-delta explanations and actual E1 benchmark. Conditional URI normalization guards preserve userinfo and non-default ports. No suspicious URL requests |
| H5.4 E2 infrastructure + KD protocol | PREPARED | Loaders/adapters/validators/paired metrics/local predictor hook and docs/kd_evaluation_protocol.md implemented |
| H5.4 actual E2 audit | BLOCKED on artifacts | No E2 experimental outputs or Teacher claims created; synthetic fixtures are tests only |

Published Week-5 snapshot: `251f0c144e0f311db49be5d8e70f837dd2342348` on `week5/hung-evaluation-robustness`, verified against the remote branch. PR #1–#4 and the original E1 pipeline came from merged main `3e9001c`; the initial E1 generation ran on that base. This review runs on top of the published snapshot with uncommitted source/annotation/report changes. Current audit runtime base, immutable E1 generation base, upstream snapshot and runtime hashes are separate fields in `run_manifest.json`. This review does not commit, push, merge or create a PR.

No Week-5 plan file was found in the checkout. The attached H5.1–H5.4 request is the scope. Existing Week-4 modules/notebooks/reports are unchanged. New outputs use Week-5 directories. The runner does not require ignored Week-4 artifacts: it regenerates eligible train/validation features and folds from raw CSV and the merged parser, and compares available handoffs by ID. Official Test is read only as part of the original table load, filtered out before parsing/features/predictions; it is never evaluated.

## Run locally

From the repository root:

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install -e '.[test]' nbclient nbformat nbconvert
.venv/bin/python -m pytest -q
.venv/bin/python scripts/run_week5_evaluation.py
# Only if actual E1 training inputs/config/source/environment changed or reconstruction is required:
# .venv/bin/python scripts/run_week5_evaluation.py --rebuild-e1
.venv/bin/python scripts/run_week5_evaluation.py --robustness-only
```

For an exact recorded environment use `requirements-week5-lock.txt` in a fresh Python environment with the Python version from `reports/tables/week5/run_manifest.json`, then install the local project editable without dependency upgrades. Original requirements retain tldextract/idna pins; version drift is captured in the run manifest. Do not promise bitwise equivalence across BLAS, Python or library versions.

When the E1 result is absent or training dependencies have changed, the full command reconstructs Dummy, standard LR and balanced LR via existing `run_baseline`, preserving 12 features, C=1, lbfgs, max_iter=2000, 3 folds, seed 42 and threshold 0.5. All fitting/scaling is fold-local. Subsequent runs reuse a local E1 result only when actual dataset/training-source/config/environment dependencies and serialized model/lineage hashes match the original generation record. Analysis/report/E2/annotation edits update the audit fingerprint without retraining E1. Only the selected LR is reconstructed on its three existing fitting folds for exact OOF case explanations when explanatory models are unavailable; those models are cached by the original result hash. No hyperparameters or thresholds change. `--rebuild-e1` forces an independent rerun. Result/prediction/lineage artifacts live in ignored `data/interim/week5/`; shared tables/plots/report stay tracked. No Week-4 output is overwritten.

Run All `notebooks/05_error_robustness.ipynb` from a kernel with this editable project installed. It uses the same runner and renders tables, figures, methodology and report text. For headless execution, register the kernel inside the environment and invoke nbconvert directly (the jupyter launcher may resolve to a system executable):

```sh
.venv/bin/python -m ipykernel install --prefix .venv --name python3 --display-name "Python 3 (PhishGuardVN)"
.venv/bin/python -m nbconvert --to notebook --execute --inplace notebooks/05_error_robustness.ipynb --ExecutePreprocessor.timeout=600
```

The independent parser command uses no dataset/model and saves separate parser-only tables. It does not replace the completed E1 robustness report.

## Configuration and required artifacts

`configs/week5.toml` paths are relative to project root; overrides use `--config <path>`. A custom config can set alternate dataset/artifact/table/figure paths; notebook/report links assume the standard table/figure directories, so retain those defaults for the published report. Expected supports intentionally fail on a changed data snapshot; review lineage rather than blindly relaxing them. Baseline config is `configs/baseline.toml`. E2 is enabled with `[e2].manifest = "artifacts/e2/manifest.json"` (replace with the actual path). The manifest's artifact paths are relative to its own directory. No file is inferred by filename or row order.

Hy supplies E2 X, dictionary, feature order/version, reference manifest and extractor tests with command/results; Phúc supplies OOF/Validation predictions, fixed folds, configs, producer training manifests and at most two Teacher candidate names. Khiêm’s source audit, notebook and external datasheet were found on unmerged `origin/khiem-data-quality` at commit `79423ee` and reviewed read-only. Exact snapshot URLs/hashes and eligible Train/Validation corroboration are in `reports/tables/week5/source_audit_review.json`: all five eligible sources are single-label. Hostname-presence checks in that audit differ from PSL-resolved group eligibility; the two unresolved Train positives remain excluded. The external pilot is only a datasheet/proposed 150–300 candidate plan; no actual pilot dataset was found. A future pilot/provenance is optional supporting evidence, not a blocker for core matched E1/E2 evaluation. Pilot labels must have an independent label policy and collection provenance; never combine them with official splits or use source metadata as X. Unknown/missing artifacts stay explicitly pending.

The E2 JSON envelope follows `configs/e2_manifest.example.json` (a schema example, **not** experimental evidence). Every required artifact entry has `path` and SHA256 of raw file bytes. Additional hashed entries may include producer extractor/tests/test-results/config notes for manual evidence review; they are never executed automatically. Required keys: `features`, `dictionary`, `references`, `predictions`, `folds`, `configs`, `lineage`. JSON fields: `schema_version=1`, nonblank `feature_version`, `producer_revision`, `feature_names` in exact matrix order, `threshold=0.5`, `score_definition="phishing_probability"`, `teacher_candidates` (0–2 supplied models), optional `adapter`.

| Producer artifact | Required schema / rules |
|---|---|
| Hy feature matrix, frozen references | CSV `id,<feature_names in exact order>`; one row per eligible train+validation ID, no extras. Includes unchanged E1 12 lexical values plus brand features. Numeric finite values only. Alternatively `feature_layout=brand_only` accepts `id,<brand names>` and joins unchanged lexical values by ID; dictionary still covers the complete declared E2 order |
| Hy feature matrix, fold-local references | CSV `id,fold_id,<feature_names>`; contexts 0/1/2 each cover all eligible Train IDs; -1 covers Train+Validation. The extra fitting rows make alignment/feature provenance reviewable |
| Hy dictionary | CSV `feature,definition,inputs,version`; exactly the declared ordered features; meaningful nonblank descriptions; no metadata/post-hoc inputs |
| Hy references | JSON `version,scope,selection_scope,records`. Every record: `reference_id,source,sha256,obtained_at`. For `scope=frozen_external`, require `selection_scope=external_fixed,independent_of_dataset=true`. For `scope=fold_local`, require `selection_scope=train_only` and contexts `0,1,2,-1`, each with exact `fit_ids` and nonempty `reference_ids`; no held-out/Validation IDs in fit IDs |
| Phúc predictions | CSV `id,model,evaluation_partition,fold_id,true_label,predicted_label,score`; partition `group_cv` (fold 0/1/2) or `official_validation` (fold blank), numeric labels 0/1; score is phishing probability; `predicted_label=(score>=declared context threshold)` (default 0.5; optional contract below). Exact eligible coverage per model; no Test or in-sample predictions |
| Phúc folds | CSV `id,fold_id`; exact match to `data/interim/week5/folds.csv` |
| Phúc configs | JSON keyed by model names. Values contain complete estimator/preprocessing/hyperparameter/reference settings and mandatory `feature_names`, `feature_version`, `reference_version` matching the envelope/reference manifest. Fixed settings or explicit per-context settings may be documented; canonical hash rule below |
| Phúc lineage | JSON keyed by model. Each value has `hyperparameter_selection=inner_train_only`, `threshold_selection=train_only`, and `contexts` `0,1,2,-1`. Each context has exact `fit_ids`, `config_sha256`, `producer_revision`. 0/1/2 fit only other folds; -1 fits all Train. Config hash is `sha256(json.dumps(configs[model], sort_keys=True).encode()).hexdigest()` |

If Phúc's names differ, set `adapter.column_map` as producer->canonical names, `adapter.partition_map` as producer->canonical partition values, optionally `adapter.model` for a single-model artifact. Labels/scores are never guessed, inverted or silently recoded. Validate conversion separately if producer stores string labels or decision_function logits. The primary paired comparison always recomputes E1 and E2 decisions at 0.5. Optional `decision_thresholds` in the E2 manifest maps each candidate to contexts `0,1,2,-1`. Every context record requires `value` strictly between 0 and 1, `selection_scope=inner_train_only`, `prediction_kind=inner_oof`, a nonblank `method`, nonempty unique `selection_ids`, `evidence_artifact` naming a hashed artifact key beginning with `threshold_`, and `inner_fit_ids` keyed by inner fold. Selection IDs must be inside that context's fitting partition; -1 is full Train, never Validation. The evidence artifact is CSV `id,model,context,true_label,score,inner_fold_id`; context is read as a string, scores are finite [0,1], labels must match original metadata, and at least two inner group folds are required. Inner fit IDs must stay within the outer fitting partition and exclude each inner held-out domain. This validates declared provenance and evidence alignment, not the producer's optimization/preprocessing implementation: review its code and method before acceptance.

`e2_comparison.csv` is the common 0.5 comparison; `e2_operating_point_comparison.csv` is the separate comparison at candidate-selected thresholds. Both expose the E1 threshold and E2 threshold set; pooled OOF may combine distinct per-outer-fold thresholds. AP is unaffected by thresholds. Never interpret F1/Recall/FPR deltas at different operating points as threshold-independent ranking improvements. E1 is always 0.5.

Reference semantics and declared producer fitting scope need code review: a manifest is evidence to check, not proof of absence of leakage. Frozen external references must not be selected using Validation/Test or the full labeled corpus. A global label-informed brand matrix must be regenerated per fold, not patched by dropping IDs after generation.

After core E2 checks, supply `[e2].predictor = "trusted_local_module:predict_score"`. Callable signature is `predict_score(url: str) -> float` in [0,1], phishing class. It must use the candidate's actual extractor/reference version/feature order, check finite values in all E2 features, perform no requests, and reject unsupported inputs. Shared parser/finite-feature diagnostics describe the 12 lexical features; extended E2 feature validity must be checked by the adapter and producer extractor tests. The runner repeats the identical stress suite and records predictor exceptions/coverage. Do not deserialize an unknown external joblib simply to inspect metadata. Set `[e2].predictor_model` explicitly for multi-candidate bundles (a sole candidate can be inferred); static E2 decisions use its full-Train context -1 threshold. Bind the callable to that model in the local adapter and record its code/artifact hash in the producer bundle. Without a predictor, E2 metric audit can finish but E2 robustness remains pending.

Optional hashed artifact keys `source_bias` and `external_pilot` accept JSON with `producer_revision,population,collection_protocol,label_policy,official_test_used=false,records`. Population is `official_train_val` or `external_pilot`. Every record has `source,observation,review_status`; pilot records additionally require unique disjoint `id,label,collected_at,label_provenance`. These checks verify declared provenance/schema, not label correctness or independence from unprovided official Test IDs. The loader reports supporting evidence separately and never computes fabricated pilot model metrics.

Khiêm cross-analysis: read source audit and independently collected pilot provenance alongside `distribution_shift.csv`, `stratified_metrics.csv` and paired results. Check source definitions, collection dates, scope/labels and population IDs before interpreting differences. Current source-label confounding is unresolved. No external pilot dataset is fabricated or silently treated as official Validation.

## Outputs and evidence

- `reports/week5_evaluation.md`: real E1 metrics, shift, four testable hypotheses, case methodology and E2 status.
- `reports/week5_robustness.md`: transformation specifications, denominators, actual E1 shifts/flips and limitations.
- `reports/tables/week5/`: overall/per-fold/stratified metrics; shift; safe 40-case manifest; complete error sampling pool; taxonomy; 144 static robustness cases; run provenance.
- `data/interim/week5/`: metadata/features/folds/exclusions; full per-sample E1 predictions; training-ID lineage; cached result and source/config/version fingerprint. Ignored; regenerate instead of assuming shared presence.
- `docs/kd_evaluation_protocol.md`: nested leakage-safe Teacher/soft-target/Student comparisons, uncertainty, operating points, size/latency and negative results.
- `tests/test_week5_audit.py`, `tests/test_robustness.py`: synthetic logic checks only. No synthetic number is reported as a model result.

Durable engineering notes are in `reports/annotations/week5_error_reviews.json`, read-only during regeneration. Every selected ID must have one review, with case signature, taxonomy, specific observation, hypothesis and next verification. The signature binds model/context, original label, source/tier, URL, score and all 12 features. Stale or missing reviews fail rather than silently carrying annotations across changed evidence. No code automatically grants `human_verified`; generated cases remain pending human semantic verification. Additional human sign-off/evidence belongs in a separate reviewed record; retain original labels. Do not visit suspicious URLs.

New evidence tables: `error_model_evidence.csv` (40 correct-context score reconstructions, fitting support/ID hash and opposite-label vector collisions), `error_feature_attributions.csv` (12 standardized-LR terms per case) and `robustness_feature_deltas.csv` (raw feature deltas and exact LR logit deltas). Taxonomy describes observations, including bare-host ambiguity/collisions/near-threshold scores, not verified root causes. Dot/subdomain/length terms are correlated and must not be interpreted as independent causal contributions.

`host_case` and `default_port` are now `conditional-label-preserving`: ASCII HTTP(S) URI normalization under the stated assumptions, not verified live server behavior or labels. The host-only transformation preserves case-sensitive userinfo, path/query/fragment. Default ports are idempotent and non-default ports are skipped. Resource keys distinguish port 0 from an absent port and retain userinfo/fragment for a conservative check. See the RFC references and actual score/feature examples in `reports/week5_robustness.md`.

## Verification of the review

The current acceptance record is `reports/tables/week5/verification.json`; match its audit fingerprint and file hashes to the latest manifest/notebook. The review preserves original E1 predictions/metrics and sampling IDs, reruns affected offline case/robustness analyses and notebook Run All, and runs the full test suite. Current review verification: **140 tests passed, 0 skipped; 6/6 notebook code cells executed with zero error outputs**. E1 serialized result, predictions, overall/fold metrics and the original sampling pool have identical SHA256 before/after the review. All 40 cases have distinct observations/hypotheses/next checks; 30 have opposite-label fitting-vector collisions. Maximum score reconstruction error is 3.33e-16; fitting scaler means/supports, fit-ID hashes and held-out domain exclusion were checked. All 144 parser expectations passed; the 12 conditional-equivalence cases had no flips. Original stress scores are unchanged; feature/logit-delta sums reproduce their shifts. `pip check` passes; original data and teammate baseline sources are unchanged.

The earlier 126-test/forced-reconstruction/clean-bootstrap record remains historical in the published commit and is not presented as a new experiment. No commit/push/merge was performed during this review.

## Continuation prompt (copy to next Codex session)

> Continue Hưng's H5.1–H5.4 in this checkout. Read docs/week5_hung_handoff.md, configs/week5.toml, reports/week5_evaluation.md, docs/kd_evaluation_protocol.md and any applicable AGENTS.md first. Preserve existing uncommitted work and verify Git state; no further commit/push/merge unless the user explicitly authorizes it. Do not train Phúc's advanced models/official Teacher. Keep official Test untouched.
>
> Discover new artifacts from Hy/Phúc/Khiêm locally and via connected sources where available. Record exact paths, versions and SHA256. Configure the E2 manifest envelope according to configs/e2_manifest.example.json; adapt names explicitly rather than reimplementing evaluation. Reject incomplete coverage, labels/folds/order drift, metadata in X, NaN/Inf, global learned references or declared held-out leakage. Ask producers for missing evidence; do not invent provenance or metrics.
>
> Install the project editable, run pytest, reconstruct E1 only if actual training dependencies changed; analysis-only edits must reuse the verified cached result, then run scripts/run_week5_evaluation.py with the E2 config. Use a trusted local predictor adapter bound to the declared E2 candidate to repeat the static robustness suite; no network requests to URL strings. Retain E1-vs-E2 paired IDs/folds, distinguish pooled AP and per-fold mean AP, and report supports/FP per 1,000 benign. Inspect Khiêm's bias/pilot evidence separately before drawing cross-population conclusions; do not claim source bias resolved.
>
> Review the pending manual cases offline with data-owner evidence; retain original labels unless the agreed label policy authorizes corrections. Preserve the durable annotations and any separate human notes; stale signatures require case re-review, not automatic regeneration of judgments. Run All notebook 05 and update report, figures, provenance, test/verification record and this status table from actual evidence. Change H5.4 to DONE only after real E2 schema/lineage/feature review, matched metrics and predictor robustness are complete. Keep explicit PREPARED/BLOCKED states for anything still missing. Final reply must list actual runs and remaining producer dependencies, plus exact resume commands; do not present synthetic fixtures as experiments.
