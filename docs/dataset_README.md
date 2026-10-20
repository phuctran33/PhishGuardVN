# PhishVN v3.1.0 — Vietnamese URL Phishing Dataset (open tier)

Time-stamped Vietnamese URL phishing dataset with a CompPhish-aligned 21-feature lexical schema,
impersonation-scenario labels, gold/silver label-confidence tiers, and a group-aware temporal split.
Released 2026-08-15 under CC BY 4.0 (see LICENSE). Cite via CITATION.cff / the DOI.

## Contents
- `data/dataset_url.csv` — full record table (53116 rows).
- `data/vn_compphish.csv` — the same URLs re-featurised into the exact CompPhish schema.
- `data/splits/url_{train,val,test}.csv` — the official group-aware temporal split.
- `data/attacks/p3_paraphrase{,_band}.csv` — the 386 paraphrased lures of the evasion study and
  their Jaccard-controlled counterparts. Every lure carries the simulated link
  `http://sim.example.vn/x` and no other URL, contains no real brand token, and is stripped of
  diacritics: the set is for re-running a detector against a published attack, and resolves
  nowhere.
- `data/abuse_type.csv` — what KIND of abuse each listed domain is, where a conservative rule can
  say; 89% is `unknown` by design. See the datasheet on what the positive label means.
- `docs/` — datasheet, column schema, and data-source notes.
- `MANIFEST.txt` — SHA-256 checksums and row counts for every file.

## Composition
- Labels: {'phishing': 36706, 'benign': 16410}
- Tiers: {'silver': 9404, 'gold': 9593, 'bronze': 34119}
- Splits: {'test': 8941, 'train': 36909, 'val': 7266}
- Scenarios: other=42338, gov=7146, bank=1487, ecommerce=1359, gaming=457, social=167, telecom=71, delivery=67, tax=24

## Notes
- Benign = NCSC trusted-organisation registry (easy) + Tranco top-list sample (hard negatives).
- `is_https` is present for CompPhish compatibility but is a collection artefact — exclude it from
  modelling (all lexical features are computed on the scheme-stripped URL).
- The captured phishing HTML/screenshot subset is distributed separately as a GATED bundle
  (research-only; live malicious captures) — not part of this open tier.
- PII is redacted; no id↔PII mapping is included. Complies with Decree 13/2023/ND-CP and Vietnam's PDPL.
