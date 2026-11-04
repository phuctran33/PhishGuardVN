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


def test_ai_review_exact_priority_selection_and_no_human_signoff():
    human = pd.read_csv(ANNOTATIONS / 'week5_human_review.csv')
    expected = human.loc[human.priority_first_30].sort_values('suggested_review_order')
    ai = pd.read_csv(ANNOTATIONS / 'week5_ai_review.csv', keep_default_na=False)
    assert len(ai) == 30 and ai.id.is_unique
    assert list(ai.id) == list(expected.id)
    assert list(ai.suggested_review_order) == list(expected.suggested_review_order)
    assert ai.hypothesis_status.isin(['plausible_unverified', 'unsupported']).all()
    assert ai.review_status.eq('ai_review_complete').all()
    assert ai.human_verification_status.eq('PENDING').all()
    assert not {'reviewer', 'reviewed_at', 'human_verified'}.intersection(ai.columns)
    assert ai[['conclusion', 'evidence', 'limitations', 'next_verification']].ne('').all().all()
    assert not ai.url_safe.str.contains('://', regex=False).any()


def test_ai_review_sources_features_and_score_arithmetic():
    ai = pd.read_csv(ANNOTATIONS / 'week5_ai_review.csv')
    cases = pd.read_csv(TABLES / 'error_cases.csv').set_index('id')
    facts = pd.read_csv(TABLES / 'error_model_evidence.csv').set_index('id')
    terms = pd.read_csv(TABLES / 'error_feature_attributions.csv')
    notes = {r['id']: r for r in json.loads((ANNOTATIONS / 'week5_error_reviews.json').read_text())['cases']}
    for row in ai.itertuples():
        case, fact, note = cases.loc[row.id], facts.loc[row.id], notes[row.id]
        assert row.url_safe == case.url_safe and row.outcome == case.outcome
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
    ai = pd.read_csv(ANNOTATIONS / 'week5_ai_review.csv')
    verification = json.loads((TABLES / 'verification.json').read_text())['ai_review']
    assert ai.hypothesis_status.value_counts().to_dict() == verification['hypothesis_status']
    assert ai.outcome.value_counts().to_dict() == verification['outcomes']
    assert len(ai) == verification['cases'] == verification['needs_further_semantic_evidence']
    assert verification['human_file_unchanged'] is True
    # Validate committed inputs only; ignored model caches are checked in the actual local audit.
    for name in ['week5_human_review.csv', 'week5_error_reviews.json']:
        path = ANNOTATIONS / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == verification['protected_sha256'][path.relative_to(ROOT).as_posix()]
    assert hashlib.sha256((ANNOTATIONS / 'week5_ai_review.csv').read_bytes()).hexdigest() == verification['ai_review_sha256']
