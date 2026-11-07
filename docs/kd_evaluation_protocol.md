# Week 6 — KD evaluation protocol (Hưng)

Status: PREPARED, no Teacher or KD experiments have been performed. Phúc owns model training. Hưng owns evaluation, artifact checks and interpretation. PhishVN labels remain phishing=1/benign=0; broad fraud/abuse semantics and label uncertainty remain in scope.

## Data and locked comparisons

Use the same 13,078 eligible Gold/Silver official Train IDs, outer domain folds 0/1/2, seed 42 and the 12-feature E1 contract. Do not rebuild folds separately per model. Official Validation (1,585 rows, 24 positive in the current snapshot) is supplementary after choices are frozen. Official Test stays untouched until the final project evaluation.

Run Student hard-only and Student KD with identical architecture, input features, preprocessing, training budget, random seeds and evaluation IDs. Record any unequal compute budget. A richer Teacher is allowed, but declare a privileged-information setup explicitly; additionally compare Teacher and Student with a matched feature contract where feasible. E1 vs E2 feature ablations and KD effects are distinct comparisons. Source/tier/split/ID/labels/post-collection metadata never enter X. Do not add is_https to E1. Learned scaling, feature selection, brand-reference fitting and calibration occur only inside the applicable fitting partition.

## Teacher selection — at most two candidates

Phúc proposes at most two named candidates with configs, feature order/version, reference manifests and training provenance. Eligibility requires complete outer OOF coverage, no domain leakage, consistent positive-score semantics, finite outputs and a loadable local predictor. Passing schema checks does not establish semantic leakage absence: review reference generation and model code as well.

Choose the primary candidate by a predeclared Train-only nested evaluation: AP primary, then Recall at the predeclared FPR operating point, then model size/latency. E1 is the baseline comparator. A second candidate is permitted only for a documented complementary trade-off (for example calibration or lower deployment cost), selected without Validation/Test. Do not expand the candidate set after seeing Validation. Record the actual candidate names when artifacts arrive; this document nominates no nonexistent Teacher.

Teacher candidate families must be fixed before outer evaluation. If choosing between candidates, select the candidate separately inside each outer fitting partition T_f using its inner grouped CV, and record the chosen identity for that context. A candidate chosen from pooled outer-OOF scores may be selected for the final full-Train/Validation model, but cannot retroactively be used as the allegedly independent Teacher for those same outer Student evaluations. Report fixed-candidate runs or the complete nested selection policy explicitly. No outer held-out label may influence its Teacher identity.

## Leakage-safe soft-target generation

For each outer fold f:

1. Lock outer held-out IDs H_f and domain-disjoint fitting IDs T_f. Never use H_f labels for training, temperature, alpha, architecture, stopping, threshold or reference selection.
2. Split T_f into inner domain groups, fixing mappings before tuning. Fit every learned transform/brand reference inside the inner fitting groups. Select hyperparameters, distillation temperature T, hard/soft mixing alpha, stopping rules and thresholds using only inner held-out groups.
3. Generate Student-training soft targets by inner cross-fitting: each i in T_f receives a Teacher score/logit from a Teacher fitted on T_f minus i's entire inner domain group. No Teacher used for a soft target has trained on that sample or its domain group. Freeze the chosen candidate/config within the outer fitting partition. Save inner fold mappings, training-ID manifests, logits/class order and transformations for every target generation context.
4. Train paired hard-only and KD Students on the same T_f. If inner held-out predictions are needed for Student tuning, generate the Teacher targets again within that inner training boundary: a target-generating Teacher may not have seen that Student evaluation fold. A single global cross-fit target file is insufficient for all nested tuning contexts.
5. Evaluate the frozen Students on H_f exactly once. A Teacher fitted on all T_f may predict H_f to report the outer Teacher benchmark, but its H_f predictions are evaluation targets only and cannot train the Student. Never use the official E2 outer OOF file as a global training-target file: Teachers for other outer folds may have seen H_f.

For the final supplementary Validation model, repeat nested train-only selection, cross-fit Teacher targets within all official Train, fit the Student on Train, freeze it, then predict Validation. Validation labels never influence Teacher selection, temperature, alpha, preprocessing or decision threshold.

Soft target contract: id, outer_fold_id, inner_context_id, teacher_candidate, positive_class=1, score/logits, temperature, feature_version, target_generation_config_hash and producer_revision, plus per-context fit-ID and domain manifests. Include full multiclass logits only if class order is explicit; for binary probability-only teachers document the temperature transform and numerical clipping epsilon selected before evaluation. Scores must be finite. Distillation loss is `(1-alpha)*BCE(y,p_student) + alpha*T^2*KL(p_teacher_T || p_student_T)` with the exact binary/two-class implementation and reductions recorded. Do not claim probability calibration from raw predict_proba.

## Evaluation and uncertainty

Report all three fold supports and TP/FP/TN/FN; mean ± sample standard deviation of per-fold AP and F1; pooled OOF AP separately. AP means average precision, never trapezoidal PR area. Report phishing Precision/Recall/F1, FPR and FP per 1,000 benign. Include PR curves and Recall–FPR curves. At a primary operating point (proposed FPR budget 1%, agreed before training), set threshold using only inner fitting/evaluation groups; carry that locked threshold into the outer held-out fold. Also report the fixed 0.5 operating point for both E1 and E2 for comparability, with candidate-specific thresholds exported separately. The E2 audit manifest can declare one threshold per candidate and context (0/1/2/-1), supported by inner-OOF predictions, selection IDs, fit-ID/domain lineage, method and hashed evidence; E1 remains fixed at 0.5. Clearly distinguish these operating points. Never tune thresholds separately on outer held-out predictions or official Validation.

Compare paired KD minus hard-only predictions on the same outer IDs/folds. Predeclare 5 paired training seeds if compute permits; otherwise record the smaller seed set before running and state the reduced evidence. Use 1,000 paired domain-cluster bootstrap replicates on OOF predictions (resample domains, retain all IDs in each draw; seeded RNG) to estimate 95% intervals for metric differences. This captures conditional evaluation variability, not full uncertainty from model/hyperparameter selection; three outer folds are not three iid experimental units. Report undefined bootstrap metrics (for example no positive support) and their count rather than replacing them with zero. Source-label confounding and class support limit subgroup inference.

Measure serialized model size in bytes and CPU latency for identical runtime/hardware/thread settings, batch size 1 and a documented bulk batch. Separate extraction latency from model inference and also report the total. Warm up 100 requests; measure at least 1,000 deterministic static/held-out inputs without network IO; report p50/p95, repeats, hardware, library versions and whether the Teacher is needed at inference. Do not compare incompatible hardware timings as speedups.

Rerun the same static robustness suite for Teacher, hard-only Student and KD Student using exact local extractors. Keep label-unknown transformations separate; no accuracy/F1 on unlabeled transformed strings. Report prediction availability, parser/feature validity, finite values, flips and score shifts with denominators.

## Negative results and acceptance

KD success requires evidence of better AP or a predeclared Recall–FPR/model-cost trade-off relative to hard-only with uncertainty and consistent support. A higher F1 at a different threshold alone is insufficient. No improvement, wider uncertainty or degraded performance is a valid result: report paired deltas and intervals, retain the hard-only baseline if appropriate, and distinguish weak Teacher signal, capacity/optimization limits, calibration and feature mismatch as hypotheses requiring further train-only experiments. Do not retune on Validation to rescue a negative result or claim source bias is solved.

Acceptance requires prediction files, fold/context and reference lineage, configs/seeds, environment/hashes, paired metrics, latency/size measurements, completed robustness and an explicit limitations/negative-results paragraph. Hưng's E2 infrastructure is evaluation readiness, not authorization to train Phúc's advanced models or official Teacher.
