# Hưng — Week 5 handoff (review fixes 2026-11-07)

| Task | Current status | Evidence / remaining work |
|---|---|---|
| H5.1 E1 evaluation | DONE | Same 12 features, 3 domain folds, seed 42, threshold 0.5; cached original model/predictions |
| H5.2 error analysis | DONE / HUMAN VERIFIED OFFLINE (30/40) | Hưng explicitly confirms matching independent review of the 30 priority cases; 10 additional cases pending |
| H5.3 static robustness | DONE | Same 144 cases, exact E1 score/logit/feature evidence; no ground-truth accuracy/F1 for unlabeled variants |
| H5.4 native E2 features | DONE / PASS / PRELIMINARY | Actual 14,663 Train/Validation rows, 20 features, 2 unresolved Train exclusions |
| H5.4 native model audit | DONE / PASS / PRELIMINARY | Native gzip predictions/partitions checked; all published metrics match within floating-point tolerance |
| E2 robustness | E2_ROBUSTNESS_PENDING_MODEL_ARTIFACT | No trusted fitted E2 MLP/HistGB weights or matching local predictor delivered |
| KD protocol | PREPARED | Reviewed and unchanged; no KD training |

## Branch and provenance

The initial model audit started from published Hưng commit `06526d63614747e903715b9737016415b4088435` on `week5/hung-evaluation-robustness`, with main then at `0054a1b1844ce12b84030e52952106488b0cbc10`. Hy PR #5 was already integrated through `a7413aae3351703429eba518657b08894afae3e7`. At that time PR #6 was open/unmerged at `b230fd6ebe33d43b8bd64d2b83653d546156fe1a`; the subsequent main integration below includes its merge. Its pinned detached worktree remains read-only for auditing the same published artifacts. The current reproducibility fixes start from `e9539fd9eee98b22f1b485ae4fdc19d25d228bdd` and do not change teammate sources or merge any PR.

Native artifacts were independently reviewed and [approved on the exact producer commit](https://github.com/phuctran33/PhishGuardVN/pull/6#pullrequestreview-5766640293). This integration reruns data/partition/metric checks directly, without fitting original models. The previous independent PR review executed 152 producer tests; this integration's own checks and current test count are recorded in `reports/tables/week5/verification.json`.

Hưng audit runtime base and prior upstream publication remain separate from the original E1 generation base `3e9001c` in `run_manifest.json`. Phúc's published artifact revision is also separate from its dirty runtime base `a4f8a18`; export-only notebook changes are documented in producer metadata and the committed notebook code hash matches. Runtime hashes identify sources actually executed. A subsequent publication does not rewrite these captures; find the publication commit with `git log -1` / the branch on GitHub.

Producer protocol is `week5_e1_e2_readable_v1`, feature schema `e2-brand-v0`. `run_manifest.json → native_model_audit` records producer versions, exact SHA256 for all three compressed files, metadata/metric tables/verification, notebook code and normalized LF extractor/reference content. Raw Windows input hashes are retained separately; no false claim of byte equality with regenerated local CSVs is made. IDs, labels, folds and feature contracts are compared against Hưng's canonical data.

## Native E1/E2 model findings

Read **130,780 OOF**, **15,850 Validation**, **52,312 training partition** records: E1/E2 × five models, identical eligible IDs/labels/folds. No duplicates, missing IDs, unexpected Test IDs or wrong score/prediction semantics. The four fitting contexts (outer 0/1/2 plus full Train) match immutable folds; all eight seeded inner memberships are reconstructed within fitting rows and are domain-disjoint. Validation has 24 positives and never enters fitting/selection records. The prior committed-code review verifies preprocessing/GridSearchCV/shortlist selection inside Train; prediction records alone cannot prove the original fitting execution.

SVC scores are **decision_function margins**, boundary **0**; LR/balanced LR/MLP/HistGB scores are **class-1 probabilities**, default boundary **0.5**. Labels come from `estimator.predict`; native probability ties choose class 0, and an exact zero SVC margin requires producer review. AP uses unchanged ranking scores, never a sigmoid. The probability-only generic bundle adapter remains separate and unchanged; no new threshold policy is imposed on Phúc.

Recomputed 30 outer-fold metric rows, 10 Validation rows, 10 mean/sample-SD summaries and 15 paired-fold rows. Maximum absolute discrepancy: **2.22e-16**. Only one small CSV is added: `reports/tables/week5/e2_paired_folds.csv` (15 rows), with actual per-fold E1/E2 metrics and deltas. Full findings and tables are generated from the audited data in `reports/week5_evaluation.md` and the existing notebook.

| Model | Mean outer AP E1 | Mean outer AP E2 |
|---|---|---|
| logistic_regression | 0.5942 | 0.6417 |
| logistic_regression_balanced | 0.5577 | 0.6306 |
| svm_rbf | 0.6426 | 0.6545 |
| mlp | 0.6992 | 0.7335 |
| hist_gradient_boosting | 0.6979 | 0.7224 |

Train-only shortlist: **E2 MLP and E2 HistGB**. All 15 paired AP/F1 deltas are positive, but HistGB adds one FP in each of folds 0 and 2, and MLP recall decreases in fold 1. These are three correlated folds and one seed, with descriptive uncertainty only.

Supplementary Validation AP falls: MLP **0.4314 → 0.3762**, HistGB **0.4338 → 0.4278**, even while fixed-boundary F1 improves. Ranking AP and one-boundary F1 measure different behavior. Source-label confounding, only 24 Validation positives, Train/Validation shift and the unverified brand reference prevent generalization claims. Do not tune a model/threshold/reference using Validation findings.

## Feature/reference and fitted-model limitations

Native Hy features remain exactly `id + 12 lexical + 8 brand`. Fresh audit checks finite/ranged values, exact IDs/order/exclusions, unchanged lexical values by ID, Train/Validation/outer-fold domain disjointness and input/dictionary/reference hashes. The only upstream parser change is the deprecated tldextract alias spelling; reversing that exact change reproduces the original E1 source hash. Cache reuse still requires every other training source, data/config/environment and result/lineage hash to match.

Reference LF SHA256: `32198c1734bacd23263eae979465e22d95c2038bfa63cb2107fdbe8cd115f1cf`. All **37** entries are draft and lack `source_accessed`; `frozen=false`, `fully_verified=false`. The v1 filename is not a frozen E2 v1 claim. Hy must verify brand/domain/false matches, provenance and any freeze decision.

Both checkouts' models/artifact directories and Phúc's tracked/ignored weight extensions were inspected. Only Hưng's E1 result/explanation caches exist; Phúc inference code is present but fitted E2 weights are not supplied. No pickle/joblib from an unknown source is loaded. For E2 robustness, Phúc must provide trusted fitted MLP/HistGB preprocessing+weights, artifact SHA256, training commit/config, exact feature order/schema, embedded reference snapshot/hash, extractor hashes, class order and score semantics. Then reuse the existing 144-case suite; no E2/Teacher/KD retraining is needed for this audit.

## Human review handoff

`reports/annotations/week5_human_review.csv` retains the same 40 IDs, defanged URLs, contexts and FP/FN outcomes. Added case-specific suggested observations, explicitly unverified hypotheses, fitting-only collision counts, signed logit terms and next verification. `suggested_review_order` round-robins each partition/fold/outcome stratum; `priority_first_30` covers all three folds with FP/FN and all five sampled Validation cases (one FN, four FP). Hưng can sort by this order and review those 30 first.

All 40 durable notes were rechecked against static strings, actual original labels/scores, exact fitting-context attribution and collision evidence. Existing valid notes are retained; case signatures detect stale evidence, and reconstructed E1 scores agree to floating-point tolerance. No semantic/root cause or label is asserted verified. Correlated lexical contributions are arithmetic explanations, not independent causal effects.

Hưng has explicitly confirmed his own independent analysis matches the 30 priority cases. Codex recorded that statement at 2026-11-04T12:43:24Z in reviewer/date/checks/notes/status fields for exactly those IDs: **30 human_verified, 10 pending**. `reviewed_at` is the confirmation-recording time; no date was supplied for the earlier work. Review scope is the offline observations, evidence interpretation and qualified hypotheses. Original labels and semantic/root-cause uncertainty remain unchanged. Regeneration preserves the human-owned fields by ID.

### AI-prepared review and subsequent human confirmation

`reports/annotations/week5_ai_review.csv` reviews exactly the 30 priority IDs in suggested order (17 FP, 13 FN). Each has an individual Vietnamese conclusion, evidence, limitations and next verification. All **30 hypotheses are plausible_unverified**, **0 unsupported**; all 30 still require evidence for semantic/label/root-cause verification. Offline observations/features and arithmetic are consistent; maximum score reconstruction error is 3.33e-16. Recounted fitting collisions: 22 opposite-label cases, six without any exact match, two with only same-label matches. No opposite-label collision is asserted for those eight.

The AI preparation supplements the earlier evaluation snapshot; no model/evaluation/notebook rerun is claimed. A subsequent explicit user statement supplies human confirmation for the same 30 priority IDs. The human checklist is updated only in its authorized review fields; all non-review fields and the original evidence/model artifacts remain unchanged. `verification.json` records the statement, current checklist hash and the historical pending-checklist hash. The generator now validates confirmed IDs/reviewer/timestamp against the checklist and renders current status plus the full H5.2 section from reports/templates/week5_h52.md; no manual report overlay is required.

### Final H5.2 handoff and acceptance

The existing `reports/annotations/week5_ai_review.csv` is the 30-case handoff table. It now exposes fold/partition, source/tier, original label, prediction, score, observation, hypothesis and `next_check` directly, alongside evidence/limitations and AI/human status. Labels use phishing=1, benign=0; Validation fold is blank. `next_check` replaces the old AI-only `next_verification` column; original annotation/checklist schemas are unchanged. Observations/hypotheses/next checks are in Vietnamese. Two AI conclusions were tightened (digit attribution versus counterfactual effect; same-label-only fitting matches), and next checks explicitly require recalculating all affected features.

The H5.2 report contains coverage/taxonomy, four falsifiable hypotheses and an acceptance matrix. Method is **Human-assessed offline error analysis (AI-assisted preparation)**. Technical H5.2 and the minimum 30-case human review are DONE based on Hưng's direct confirmation. Ten additional human reviews remain pending. Human confirmation covers the offline analysis and does not certify website behavior, labels or individual root causes. No H5.1/H5.3/H5.4 work is reopened or changed.

## Reproduce the integration

Use the existing `.venv` and ignored Week-4 handoffs. For a clean checkout, generate those handoffs with notebooks 01 → 03 → 02 first. Native E2 features are generated only for Train/Validation; no Official Test file is opened for extraction or prediction.

```sh
git fetch origin
git worktree add --detach /tmp/PhishGuardVN-pr6-b230fd6 b230fd6ebe33d43b8bd64d2b83653d546156fe1a
export PHISHGUARD_E2_PRODUCER_ROOT=/tmp/PhishGuardVN-pr6-b230fd6
.venv/bin/python scripts/05_build_matrix_x_brand.py --partition trainval
.venv/bin/python scripts/run_week5_evaluation.py --feature-only
.venv/bin/python scripts/run_week5_evaluation.py
.venv/bin/python -m pytest -q
.venv/bin/python -m nbconvert --to notebook --execute --inplace notebooks/05_error_robustness.ipynb --ExecutePreprocessor.timeout=600
```

Reuse the worktree if it already exists at that commit. `[e2].producer_root` is an optional root-relative/absolute alternative; the environment variable takes precedence. With neither configured, the runner uses native 06_* artifacts only when they exist in the current checkout (e.g. after an authorized main integration). Feature-only mode deliberately does not require or audit model artifacts. Use the exact publication's commit to reproduce its hashes; do not substitute a newer mutable producer head silently.

## PR #7 reviewer fixes — 2026-11-06

All three requested fixes are confined to Week-5 text I/O and reporting. JSON/notebook/Markdown reads and writes use explicit UTF-8; text writes use LF, and CSV writes specify UTF-8 plus `lineterminator="\n"`. Binary/gzip/model hashes still use original raw bytes. `.gitattributes` pins LF for `reports/annotations/*.csv`, `reports/annotations/*.json` and generated `reports/tables/week5` CSV/JSON; original `/data` policies remain `-text`. The three annotation files retain their existing SHA256 values.

`render_h52_report` reads the live checklist and validates each verified ID, reviewer, timestamp and nonempty review fields against the existing explicit confirmation record. It does not trust the AI ledger's human flag or a cached aggregate count. The minimum comes from the confirmation record; insufficient human review renders PENDING. The full scientific narrative, evidence, four testable hypotheses, conclusions and acceptance matrix are controlled by `reports/templates/week5_h52.md`. The template, annotations and a digest of confirmation fields are included in analysis provenance; changing reports does not invalidate an unchanged E1 training cache.

Regression tests repeat the complete report generator for the actual 30/40 status and for reduced 29/40 and 0/40 checklists, reject mismatched confirmation evidence, and preserve human-owned fields. Simulations cover CP1252 text defaults, CRLF output defaults and Git checkout with core.autocrlf=true/false. These run on macOS; no actual Windows execution is claimed. For an older Windows worktree that already has CRLF annotations, canonicalize line endings only in these three UTF-8 annotation files before raw-byte hash checks; retain reviewer content, do not change expected hashes and do not normalize datasets, gzip or model files.

Actual results for this fix: **211 passed, 0 failed, 0 skipped**; CLI exited 0 with cached E1; notebook Run All executed all six code cells without errors. All **36 captured hashes** for annotations, data, model/cache, metrics, robustness and producer gzip files remain identical. Only report/source/template/notebook and run/verification provenance hashes change for the reviewed fixes. Full commands and evidence are in `reports/tables/week5/verification.json → pr7_review_fixes`. Verification was captured before publication at runtime base `fb203dd`; subsequent publication is identified by branch history. Runtime provenance is retained unchanged; no PR merge was performed.

## Main integration and reporting-test conflict resolution

Fetched `origin/main` at `f78c0247c88676f6074e212f84898b211c87053f` (already includes Phúc PR #6 and Khiêm PRs #8/#9). The merge into Hưng had exactly one add/add conflict: `tests/test_week5_reporting.py`. Phúc's file is retained byte-for-byte from main, while the entire Hưng file is moved unchanged to `tests/test_week5_h52_reporting.py`. Both sets remain collected: 6 Phúc reporting tests and 10 Hưng H5.2 regression tests. All 75 incoming main files retain their exact bytes; no teammate implementation or test is edited.

After resolution: **259 passed, 0 failed, 0 skipped**. UTF-8/CP1252 and LF/CRLF simulations, raw checksums, repeated report regeneration at 30/29/0 human reviews, confirmation guards and all new main tests pass. CLI exits 0 with `cached_e1=True`; notebook Run All executes all six code cells without error. All 36 captured annotation/data/fold/model/cache/metrics/robustness/gzip hashes remain identical. Newly merged native gzip files also match the pinned reviewed producer bytes. Pytest fits only its small synthetic fixtures; the research E1/E2 models are not retrained or tuned, and no actual Official Test evaluation is performed. Actual Windows execution remains untested.

The audit still uses the existing read-only producer checkout through `PHISHGUARD_E2_PRODUCER_ROOT`; its native artifacts match the newly merged main files. Source/config hashes in the run manifest reflect the staged main integration at runtime base `62b3f8b`; the subsequent merge publication is identified by Git history. Full actual outcomes, file hashes and collection checks are recorded in `verification.json → main_merge_resolution`. PR #7 is not merged or approved by this workflow.

## Follow-up: Windows cache and checklist reproducibility

The [follow-up review of e9539fd](https://github.com/phuctran33/PhishGuardVN/pull/7#pullrequestreview-5802851736) confirmed the prior three fixes on Windows and reported two remaining regeneration issues. Fingerprints now write POSIX path keys; cache comparison and the parser-provenance lookup normalize legacy backslashes without rewriting original E1 generation metadata. Conflicting hashes for equivalent keys invalidate the cache. Data/config/training-source/environment/model/lineage checks remain enforced.

Checklist regeneration now preserves each existing score's exact CSV spelling by ID when finite values match within absolute tolerance `1e-12` (relative tolerance zero). Larger differences or non-finite values stop regeneration before writing the checklist, requiring reconciliation of the reviewed evidence. Human fields, IDs and raw-byte SHA256 checks remain intact. Regressions cover legacy Windows self/mixed-platform comparisons, real dependency changes, duplicate-key conflicts, repeated score roundtrips/one-ULP perturbations, invalid or changed scores, and full checklist byte equality under simulated Windows text defaults. Actual Windows execution of this new patch remains for the reviewer; local execution uses macOS.

Executed in the requested order: **269 passed, 0 failed, 0 skipped** before regeneration; CLI exit 0 with `cached_e1=True`; notebook Run All exit 0 with six executed code cells, zero errors and `cached_e1=True`; then **269 passed, 0 failed, 0 skipped** again. All **37 captured hashes** remain identical, including original E1 provenance/model/explanation cache, predictions/folds, dataset/splits, all annotations, metrics, robustness, figures and producer gzip files. The checklist remains 30 human-verified and 10 pending; all four testable hypotheses, conclusions and acceptance matrix survive regeneration. No research model is retrained/tuned and no Official Test is evaluated. The run manifest captures audit base `e9539fd`, separate from original E1 generation base `3e9001c` and the later publication commit. Exact results/hashes are in `verification.json → pr7_reproducibility_fixes`.

## Verification and remaining owners

Prior full evaluation verification at `d3d0d8e`: **198 tests passed, 0 skipped**, native model audit and full CLI succeeded using cached E1; notebook Run All and final output/hash checks are recorded in `verification.json`. Original model bytes, E1 predictions/metrics/folds, 40-case sample/notes and 144-case robustness outputs retain identical SHA256. Hy/Phúc sources, tracked dataset/splits, baseline and KD protocol remain unchanged. No Official Test features/scores, no Validation tuning, no original model retraining. Tests use explicit synthetic fixtures solely for validator failure cases.

Changes are confined to Hưng's existing audit/orchestration/checklist/tests/notebook/config/reports, plus one 15-row CSV. No audit framework, registry, new model runner, KD implementation or baseline refactor is added.

- **Hưng:** confirmed independent offline review of the 30 priority cases; 10 additional cases remain pending. Original source evidence is still needed before stronger semantic/label/root-cause claims.
- **Hy:** verify/freeze brand reference and provenance; current E2 remains PRELIMINARY.
- **Phúc:** optionally deliver trusted fitted E2 weights/predictor for robustness; model audit is already DONE.
- **Khiêm:** resolve source-label confounding evidence and deliver the optional independently reviewed external pilot. Existing source audit snapshot remains supporting evidence, outside X; missing pilot does not block the matched core model audit.
