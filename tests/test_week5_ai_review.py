"""Check the published AI review against offline evidence; never train or visit URLs."""
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd
from scipy.special import expit

from phishguard_vn.error_analysis import case_signature, defang_url
from phishguard_vn.features import CANDIDATE_FEATURES, extract_features

ROOT = Path(__file__).resolve().parents[1]
ANNOTATIONS = ROOT / 'reports/annotations'
TABLES = ROOT / 'reports/tables/week5'


def test_ai_review_exact_priority_selection_and_explicit_human_confirmation():
    human = pd.read_csv(ANNOTATIONS / 'week5_human_review.csv', keep_default_na=False, encoding="utf-8")
    expected = human.loc[human.priority_first_30].sort_values('suggested_review_order')
    ai = pd.read_csv(ANNOTATIONS / 'week5_ai_review.csv', keep_default_na=False, encoding="utf-8")
    assert len(ai) == 30 and ai.id.is_unique
    assert list(ai.id) == list(expected.id)
    assert list(ai.suggested_review_order) == list(expected.suggested_review_order)
    assert ai.hypothesis_status.isin(['plausible_unverified', 'unsupported']).all()
    assert ai.review_status.eq('ai_review_complete').all()
    confirmation = json.loads((TABLES / 'verification.json').read_text(encoding="utf-8"))['human_review']
    verified = human.loc[human.review_status.eq('human_verified')]
    assert set(verified.id) == set(ai.id) == set(confirmation['confirmed_ids'])
    assert len(verified) == confirmation['verified'] == 30
    assert verified.reviewer.eq(confirmation['reviewer']).all()
    assert verified.reviewed_at.eq(confirmation['confirmation_recorded_at_utc']).all()
    assert pd.to_datetime(verified.reviewed_at, utc=True).notna().all()
    assert verified[['observation_checked', 'hypothesis_assessed', 'evidence_checked', 'notes']].ne('').all().all()
    remaining = human.loc[~human.id.isin(ai.id)]
    assert len(remaining) == confirmation['pending'] == 10
    assert remaining.review_status.eq('pending').all() and remaining.reviewer.eq('').all() and remaining.reviewed_at.eq('').all()
    assert ai.human_verification_status.eq('human_verified').all()
    assert not {'reviewer', 'reviewed_at', 'human_verified'}.intersection(ai.columns)
    required = ['id', 'fold', 'source', 'label', 'prediction', 'score', 'observation', 'hypothesis', 'next_check']
    assert set(required).issubset(ai.columns)
    assert ai[['observation', 'hypothesis', 'next_check', 'conclusion', 'evidence', 'limitations']].ne('').all().all()
    assert ai.analysis_method.eq('Human-assessed offline error analysis (AI-assisted preparation)').all()
    assert not ai.url_safe.str.contains('://', regex=False).any()


def test_ai_review_sources_features_and_score_arithmetic():
    ai = pd.read_csv(ANNOTATIONS / 'week5_ai_review.csv', encoding="utf-8")
    cases = pd.read_csv(TABLES / 'error_cases.csv', encoding="utf-8").set_index('id')
    facts = pd.read_csv(TABLES / 'error_model_evidence.csv', encoding="utf-8").set_index('id')
    terms = pd.read_csv(TABLES / 'error_feature_attributions.csv', encoding="utf-8")
    notes = {r['id']: r for r in json.loads((ANNOTATIONS / 'week5_error_reviews.json').read_text(encoding="utf-8"))['cases']}
    for row in ai.itertuples():
        case, fact, note = cases.loc[row.id], facts.loc[row.id], notes[row.id]
        assert row.url_safe == case.url_safe and row.outcome == case.outcome
        assert row.evaluation_partition == case.evaluation_partition
        assert row.source == case.source and row.tier == case.tier
        assert row.label == case.true_label and row.prediction == case.predicted_label
        if case.evaluation_partition == 'official_validation':
            assert pd.isna(row.fold)
        else:
            assert row.fold == case.fold_id and row.fold in (0, 1, 2)
        assert abs(row.score - case.score) < 1e-12
        assert case.outcome == ('FN' if (case.true_label, case.predicted_label) == (1, 0) else 'FP')
        assert case.true_label != case.predicted_label and case.predicted_label == int(case.score >= .5)
        assert note['hypothesis'] == case.hypothesis and case.observation.startswith(note['observation'])
        assert row.case_signature == case.case_signature == fact.case_signature == note['case_signature']
        raw = row.url_safe.removeprefix('URL_TEXT: ').replace('[.]', '.').replace('[:]//', '://')
        assert defang_url(raw) == row.url_safe
        features = extract_features(raw)  # Bundled offline PSL, no network.
        source = pd.Series({'id': row.id, **case.to_dict(), 'url': raw,
                            'label': 'phishing' if case.true_label else 'benign', **features})
        assert case_signature(source) == row.case_signature
        block = terms.loc[terms.id.eq(row.id)].set_index('feature')
        assert len(block) == 12 and set(block.index) == set(CANDIDATE_FEATURES)
        block = block.loc[list(CANDIDATE_FEATURES)]
        assert np.allclose(block.raw_value, [features[n] for n in CANDIDATE_FEATURES], rtol=0, atol=1e-12)
        for name in ['url_len', 'dom_len', 'subdom_cnt', 'digit_cnt', 'dot_cnt', 'entropy', 'path_len']:
            assert f'{name}={features[name]:.4f}' in row.observation
        context = -1 if case.evaluation_partition == 'official_validation' else int(case.fold_id)
        assert block.context.eq(context).all() and fact.context == context
        assert block.fitting_scale.gt(0).all()
        standardized = (block.raw_value - block.fitting_mean) / block.fitting_scale
        assert np.allclose(standardized, block.standardized_value, rtol=0, atol=1e-12)
        assert np.allclose(standardized * block.coefficient, block.logit_contribution, rtol=0, atol=1e-12)
        logit = fact.intercept + block.logit_contribution.sum()
        assert abs(logit - fact.logit) < 1e-12 and abs(expit(logit) - case.score) < 1e-12
        assert abs(fact.reconstructed_score - case.score) < 1e-12
        assert row.arithmetic_status == 'verified_offline'


def test_ai_review_verification_counts_and_protected_inputs():
    ai = pd.read_csv(ANNOTATIONS / 'week5_ai_review.csv', encoding="utf-8")
    verification = json.loads((TABLES / 'verification.json').read_text(encoding="utf-8"))['ai_review']
    assert ai.hypothesis_status.value_counts().to_dict() == verification['hypothesis_status']
    assert ai.outcome.value_counts().to_dict() == verification['outcomes']
    assert len(ai) == verification['cases'] == verification['needs_further_semantic_evidence']
    assert verification['human_file_unchanged'] is False
    human_confirmation = json.loads((TABLES / 'verification.json').read_text(encoding="utf-8"))['human_review']
    assert human_confirmation['confirmation_quote']
    assert human_confirmation['previous_checklist_sha256'] == verification['protected_sha256']['reports/annotations/week5_human_review.csv']
    # Validate committed inputs only; ignored model caches are checked in the actual local audit.
    for name in ['week5_error_reviews.json']:
        path = ANNOTATIONS / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == verification['protected_sha256'][path.relative_to(ROOT).as_posix()]
    assert hashlib.sha256((ANNOTATIONS / 'week5_human_review.csv').read_bytes()).hexdigest() == human_confirmation['sha256']
    assert hashlib.sha256((ANNOTATIONS / 'week5_ai_review.csv').read_bytes()).hexdigest() == verification['ai_review_sha256']
