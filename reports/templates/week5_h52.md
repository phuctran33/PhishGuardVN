## H5.2 — $method

$case_count FP/FN cases selected using seed=42, SHA256-ranked IDs, round robin across partition/fold/type/source/tier and then distinct domains within queues. No ranking by score; selection is a diversity sample, not a population estimate. Sampling pool, coverage and limitations are recorded; if a stratum has no errors it contributes no cases.

$support_table

$taxonomy_table

Each case has static observations, an explicitly unverified hypothesis, offline next verification, original labels and review status. Safe URL text is fully defanged and prefixed to prevent spreadsheet formulas; no suspicious URL was visited. Source effects and label uncertainty have explicit review fields; zero direct cue counts do not assert absence of those phenomena. No model output verifies a label error or individual causal mechanism.

All $case_count cases now have case-specific offline engineering notes, preserved read-only in [durable annotations](annotations/week5_error_reviews.json). Case signatures bind notes to ID, context, original label, URL, score and all 12 features; changed evidence fails as stale instead of silently reusing a review. Taxonomy describes observed representations, not verified root causes; independent verification of website behavior, label correctness and root causes remains pending.

Exact correct-context LR arithmetic is verified for every case. Opposite-label full-vector collisions in fitting data are observed for $all_collisions/$case_count cases (absolute feature tolerance 1e-12). The selected model is refitted only in its three existing fitting folds for explanation when those models are unavailable; no new model selection, thresholds or baseline experiments are introduced. Validation explanations use the original full-Train pipeline. Contributions are relative to each fitting mean, with correlated dot/subdomain/length terms often cancelling; they are not independent causal effects.

Evidence: error_model_evidence.csv (reconstructed logits/scores, fitting-ID hashes and collision supports) and error_feature_attributions.csv (all 12 raw/scaled terms per case). Collision searches use fitting IDs only, not held-out labels. The coarse representation can be ambiguous under original labels, but this does not verify maliciousness, label correctness or a source shortcut.

Case-level annotations: tables/week5/error_cases.csv; pool: error_sampling_pool.csv; taxonomy: error_taxonomy.csv. Original labels are retained; independent semantic/label verification remains pending. Offline human review is recorded separately in the checklist.

$human_summary

### Separate AI review of the 30 priority cases

$ai_intro

$assessment_table

The plausible and evidence-needed rows overlap: every plausible hypothesis remains unverified. No factual/numerical inconsistency was found in the $priority_count observations. Dataset labels describe the retained source annotation, not independently established website behavior.

The audit rejoined durable notes, cases, fitting-context evidence and all 12 attribution rows by ID. Original metadata/URL features and case signatures were rechecked offline. Every standardized value, coefficient multiplication, intercept and sigmoid score was recomputed; maximum score reconstruction error is $score_error. The existing trusted local explanation cache passed its recorded hash check; coefficients/scaler/intercepts matched without fitting a model. Fitting-only ID hashes, exact-vector matches and opposite-label counts were independently recounted from the existing Train metadata; no held-out label enters a fitting count.

**$priority_collisions/$priority_count** have opposite-label fitting collisions; **$no_matches** have no exact fitting match and **$same_label_only** have matches only with the same original label. These findings constrain the individual conclusions: an opposite-label collision explanation is unsupported for the latter $no_opposites cases. This does not make their existing hypotheses unsupported, because those hypotheses explicitly avoid claiming such collisions. Correlated feature terms explain the model arithmetic but do not establish independent causal effects or imply that extra token/suffix features would fix an error.

Additional precision in the AI ledger: hostname lengths for tuantaynguyen/dltp include their suffixes; repeated x in xfcf includes the xyz suffix. For abo2sadam, removing a digit also changes lengths and entropy, so the suggested future check cannot be interpreted as changing only `digit_cnt`. No perturbation experiment or model training was run here.

$scope_note

The AI-prepared ledger and human checklist are preserved as separate input artifacts. This section is rendered from the controlled UTF-8/LF template `reports/templates/week5_h52.md`, case evidence, checklist and ID-scoped confirmation data. Regeneration preserves human review fields. Original AI-review hashes remain historical; current annotation hashes and executed checks are in verification.json. Model arithmetic and human review do not establish website behavior or label/root-cause correctness.

### H5.2 handoff, conclusions and acceptance

$method_note

The [same $priority_count-row ledger](annotations/week5_ai_review.csv) now serves as the H5.2 handoff table, with explicit `id`, `fold`, `source`, `label`, `prediction`, `score`, `observation`, `hypothesis`, `next_check`, plus partition/tier, defanged URL, evidence, limitations and review status. `label` and `prediction` use phishing=1/benign=0. A blank `fold` means official Validation (full-Train prediction), not an extra CV fold. `next_check` replaces the former `next_verification` column in this AI ledger only; original durable annotations/checklist retain their schemas.

All $priority_count observations, hypotheses and next checks are case-specific Vietnamese text. Numeric observations were rejoined to all 12 attribution rows and original metadata; label/prediction/outcome/score/context and the full standardized-LR arithmetic were checked again. Re-audit preserves the same priority IDs and order. Corrections tighten two conclusions: abo2sadam's positive digit contribution is relative to the fitting mean and does not establish the effect of adding/removing a digit; vieclambencat's 22 fitting matches are all benign, so no opposite-label collision is claimed. The next check for abo2sadam explicitly recalculates all features when changing a digit. No perturbation run, refit or threshold selection was performed.

Priority selection remains a round-robin subset of the original fixed diversity sample, with no score-based selection. Source supports: $source_counts. Coverage is:

$priority_support_table

The error patterns overlap; their counts are descriptive of this selected sample, not population error rates:

$priority_taxonomy_table

$pattern_summary

#### Testable hypotheses (proposed, not executed here)

1. **H52-A — mixed-label lexical vectors concentrate errors.** Evidence: $priority_collisions reviewed cases have opposite-label fitting collisions, including the dieniex/gateswq/wefinex and winbank/daubao groups. Check: on existing Train OOF only, assign each held-out record collision status using its own fitting folds, then compare FP/FN rates and supports for mixed-label versus unambiguous vectors within predeclared length/entropy/source strata; account for domain dependence and report unsupported single-class strata. A similar or lower error rate after matched-support comparisons weakens the concentration hypothesis. This tests a distributional association; it cannot identify an individual URL's cause or establish that adding a token feature would fix it.
2. **H52-B — correlated hierarchy counts contribute to high benign scores.** Evidence: $hierarchy_fp reviewed hierarchy FPs have large positive subdomain terms; the banking-like hierarchy is a counterexample with a low FN score. Check: predeclare benign Train OOF records with www/one subdomain and matched bare-host controls, inspect the complete logit balance and, if performing a separate sensitivity study, recompute all 12 features under a www-removal string perturbation (resource and label equivalence unknown) with the same cached fitting-context model. Report score/logit deltas and parser checks, without assigning transformed ground truth. No systematic matched-group difference or consistently contrary deltas would weaken the hypothesis. Do not isolate one correlated term as a causal effect.
3. **H52-C — near-boundary errors are sensitive to the lexical balance.** Evidence: $near_count/$priority_count lie within 0.05 of 0.5; dltp is 0.000805 below the boundary. Check: use the full predeclared Train OOF pool to compare the share of FP/FN versus correct predictions inside the same margin band, within class and fold, and report denominator supports. No enrichment of errors in the band would weaken this population hypothesis. Keep E1's 0.5 threshold fixed; the present diversity sample cannot estimate that enrichment, and proximity is not calibrated uncertainty or evidence of a wrong label.
4. **H52-D — source/label confounding limits transport of these explanations.** Evidence: all $fn_count reviewed FNs are from tinnhiemmang while FP sources carry benign labels. Check: request an independently reviewed, provenance-recorded pilot with both classes represented across sources, predeclare prevalence/source matching and evaluate the unchanged E1; report AP, FPR and class supports without selecting features/thresholds. If the proposed performance/lexical association gaps do not persist under matching, that weakens a transport-gap explanation. Current single-label sources cannot separate source from label effects; no independent pilot experiment is claimed.

#### Acceptance against the supplied Week-5 H5.2 plan

| Criterion | Assessment and evidence |
|---|---|
| At least $minimum_reviews reproducibly selected FP/FN | PASS — $priority_count exact priority IDs; $fp_count FP, $fn_count FN; observed coverage shown above |
| ID, split/fold, source/tier, label, prediction, score, safe URL | PASS — explicit columns and ID joins in the handoff ledger |
| Per-case observation, hypothesis, next check, review status | PASS — $priority_count distinct case-specific rows; hypotheses remain plausible_unverified |
| Taxonomy and summary without forced coverage | PASS — all declared categories shown; zero counts retained and overlapping counts disclosed |
| Original evidence, model arithmetic and provenance | PASS — all $term_count attribution terms rechecked; max score error $score_error; source/case/model hashes retained |
| Conclusions, limitations and at least three testable hypotheses | PASS — four falsifiable protocols above; no experiments/results invented |
| Regression checks and no baseline/robustness/model-audit changes | Execution results and unchanged-artifact checks are recorded in verification.json |
| Human-assessed/human-verified acceptance | $human_acceptance |

$conclusion
