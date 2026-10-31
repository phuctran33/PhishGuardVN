# Week 5 — Static URL robustness

Predictor: logistic_regression_balanced.

Six static reserved-example URLs × 24 deterministic transformations; no network requests. No ground-truth labels are assigned to stress strings.

Host case and scheme-default ports preserve the HTTP resource under the stated specification. All other transformations are label-unknown, including fragments (client-side routing may change semantics).
Validity is the existing parser/extractor contract, not browser acceptance or an RFC compliance claim. IPv4/IPv6 are feature-valid although domain-group training excluded IPs.

| transformation | label_policy | n_cases | parser_valid_rate | expected_validity_pass_rate | finite_feature_coverage | paired_predictions | prediction_flip_rate | stability | mean_score_shift | mean_abs_score_shift | max_abs_score_shift | predictor_errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| host_case | label-preserving | 6 | 1.0000 | 1.0000 | 1.0000 | 6 | 0.0000 | 1.0000 | 0.0167 | 0.0167 | 0.0393 | 0 |
| default_port | label-preserving | 6 | 1.0000 | 1.0000 | 1.0000 | 6 | 0.0000 | 1.0000 | 0.1094 | 0.1094 | 0.2434 | 0 |
| subdomain | label-unknown | 6 | 1.0000 | 1.0000 | 1.0000 | 6 | 0.1667 | 0.8333 | 0.2155 | 0.2155 | 0.4801 | 0 |
| deep_subdomain | label-unknown | 6 | 1.0000 | 1.0000 | 1.0000 | 6 | 0.1667 | 0.8333 | 0.3023 | 0.3023 | 0.9774 | 0 |
| path_query | label-unknown | 6 | 1.0000 | 1.0000 | 1.0000 | 6 | 0.0000 | 1.0000 | 0.2002 | 0.2002 | 0.3972 | 0 |
| long_path | label-unknown | 6 | 1.0000 | 1.0000 | 1.0000 | 6 | 0.1667 | 0.8333 | 0.3023 | 0.3023 | 0.9774 | 0 |
| long_query | label-unknown | 6 | 1.0000 | 1.0000 | 1.0000 | 6 | 0.1667 | 0.8333 | 0.3023 | 0.3023 | 0.9774 | 0 |
| percent_encoding | label-unknown | 6 | 1.0000 | 1.0000 | 1.0000 | 6 | 0.1667 | 0.8333 | 0.2978 | 0.2978 | 0.9718 | 0 |
| double_encoding | label-unknown | 6 | 1.0000 | 1.0000 | 1.0000 | 6 | 0.1667 | 0.8333 | 0.2919 | 0.2919 | 0.9642 | 0 |
| unicode_idna | label-unknown | 6 | 1.0000 | 1.0000 | 1.0000 | 6 | 0.0000 | 1.0000 | 0.1226 | 0.1295 | 0.2650 | 0 |
| punycode | label-unknown | 6 | 1.0000 | 1.0000 | 1.0000 | 6 | 0.1667 | 0.8333 | 0.2414 | 0.2414 | 0.6316 | 0 |
| homoglyph | label-unknown | 6 | 1.0000 | 1.0000 | 1.0000 | 6 | 0.0000 | 1.0000 | 0.1181 | 0.1245 | 0.2544 | 0 |
| brand_token | label-unknown | 6 | 1.0000 | 1.0000 | 1.0000 | 6 | 0.1667 | 0.8333 | 0.2942 | 0.2942 | 0.9703 | 0 |
| shortener_pattern | label-unknown | 6 | 1.0000 | 1.0000 | 1.0000 | 6 | 0.1667 | 0.8333 | 0.2953 | 0.2953 | 0.9711 | 0 |
| ipv4 | label-unknown | 6 | 1.0000 | 1.0000 | 1.0000 | 6 | 0.8333 | 0.1667 | -0.6958 | 0.6958 | 0.9450 | 0 |
| ipv6 | label-unknown | 6 | 1.0000 | 1.0000 | 1.0000 | 6 | 0.1667 | 0.8333 | 0.3019 | 0.3019 | 0.9750 | 0 |
| userinfo | label-unknown | 6 | 1.0000 | 1.0000 | 1.0000 | 6 | 0.8333 | 0.1667 | -0.6925 | 0.6925 | 0.9312 | 0 |
| fragment | label-unknown | 6 | 1.0000 | 1.0000 | 1.0000 | 6 | 0.0000 | 1.0000 | -0.0823 | 0.0823 | 0.1526 | 0 |
| unicode_path | label-unknown | 6 | 1.0000 | 1.0000 | 1.0000 | 6 | 0.1667 | 0.8333 | 0.2712 | 0.2712 | 0.9381 | 0 |
| bad_port | label-unknown | 6 | 0.0000 | 1.0000 | 0.0000 | 0 | undefined | undefined | undefined | undefined | undefined | 0 |
| bad_ipv6 | label-unknown | 6 | 0.0000 | 1.0000 | 0.0000 | 0 | undefined | undefined | undefined | undefined | undefined | 0 |
| missing_host | label-unknown | 6 | 0.0000 | 1.0000 | 0.0000 | 0 | undefined | undefined | undefined | undefined | undefined | 0 |
| host_whitespace | label-unknown | 6 | 0.0000 | 1.0000 | 0.0000 | 0 | undefined | undefined | undefined | undefined | undefined | 0 |
| unresolved_suffix | label-unknown | 6 | 0.0000 | 1.0000 | 0.0000 | 0 | undefined | undefined | undefined | undefined | undefined | 0 |

Largest observed flip rates (small unlabeled suite; not error rates):

| transformation | paired_predictions | prediction_flip_rate | mean_abs_score_shift |
|---|---|---|---|
| ipv4 | 6 | 0.8333 | 0.6958 |
| userinfo | 6 | 0.8333 | 0.6925 |
| unicode_path | 6 | 0.1667 | 0.2712 |

Finite-feature coverage uses all transformed cases as denominator; malformed cases correctly yield missing features. Expected-validity pass rate distinguishes intended rejection from failures. Paired-prediction denominators are explicit; undefined flip/shift means no valid prediction pair.

Flip rate is threshold stability, not classification error. Scores are uncalibrated and no accuracy/F1 is computed. Six synthetic bases are a small stress suite, not an estimate of real-world robustness. Some malformed transformations generate the same string for multiple bases, so 144 rows are not 144 independent inputs. Long paths and IPs probe inputs uncommon or absent in E1 training. Encoding may change server routing; no label preservation is asserted for it.

Full specifications, safe strings, parser reasons and paired scores: tables/week5/robustness_cases.csv. Reuse run_robustness(predictor) with any local E2 score adapter; do not perform network lookups.
