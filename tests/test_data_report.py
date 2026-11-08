"""Check report arithmetic and reject stale/contaminated E2 handoffs; never train models."""
import ast
import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from phishguard_vn.brand_features import E2_FEATURES, FEATURE_SCHEMA_VERSION, fold_text
from phishguard_vn.url_parser import parse_url


@pytest.fixture(scope='module')
def report_functions():
    notebook = json.loads((Path(__file__).resolve().parents[1] / 'notebooks/02_eda_and_splits.ipynb').read_text(encoding='utf-8'))
    namespace = dict(pd=pd, np=np, re=__import__('re'), fold_text=fold_text,
                     unquote=__import__('urllib.parse', fromlist=['unquote']).unquote,
                     E2_FEATURES=E2_FEATURES, FEATURE_SCHEMA_VERSION=FEATURE_SCHEMA_VERSION)
    wanted = {'describe_columns', 'checked_brand_handoff', 'strict_keyword_hits'}
    nodes = [node for cell in notebook['cells'] if cell['cell_type']=='code'
             for node in ast.parse(''.join(cell['source'])).body
             if isinstance(node, ast.FunctionDef) and node.name in wanted]
    assert {node.name for node in nodes} == wanted
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'notebook_report_functions', 'exec'), namespace)
    return namespace


def test_report_descriptives_distinguish_missing_zero_and_constant(report_functions):
    frame = pd.DataFrame({'x': [0., 2., np.nan, 4.], 'constant': [0., 0., 0., 0.]})
    result = report_functions['describe_columns'](frame, ['x', 'constant'], 'synthetic').set_index('feature')
    assert result.loc['x', ['rows', 'count', 'missing_count', 'distinct_values']].tolist() == [4, 3, 1, 3]
    assert result.loc['x', ['mean', 'median', 'std', 'variance', 'q1', 'q3', 'iqr']].tolist() == [2, 2, 2, 4, 1, 3, 2]
    assert result.loc['x', 'missing_pct'] == 25
    assert result.loc['x', 'zero_pct_of_nonmissing'] == pytest.approx(100/3)
    assert result.loc['constant', ['std', 'variance', 'iqr']].eq(0).all()
    assert result.loc['constant', 'zero_pct_of_nonmissing'] == 100
    with pytest.raises(ValueError, match='Infinite'):
        report_functions['describe_columns'](pd.DataFrame({'x': [float('inf')]}), ['x'], 'synthetic')


@pytest.mark.parametrize('defect', [None, 'v0', 'column_order', 'test_id', 'missing_id', 'duplicate_id',
                                   'reference', 'dictionary', 'unfrozen', 'nan'])
def test_report_rejects_stale_e2_and_test_rows(report_functions, defect):
    metadata = pd.DataFrame({'id': ['a', 'b', 'c', 'test'], 'label': ['benign', 'phishing', 'benign', 'phishing'],
                             'source': ['fixture']*4, 'split': ['train', 'train', 'val', 'test'],
                             'registrable_domain': ['a.example', 'b.example', 'c.example', 'test.example']})
    matrix = pd.DataFrame({'id': ['a', 'b', 'c'], **{f: [0., 0., 0.] for f in E2_FEATURES}})
    frozen = {'feature_schema_version': FEATURE_SCHEMA_VERSION, 'partition': 'trainval', 'test_excluded_from_this_artifact': True,
              'columns': ['id', *E2_FEATURES], 'frozen': True, 'git_dirty': False,
              'brand_feature_dictionary_sha256': 'brand-dict', 'e1_feature_dictionary_sha256': 'e1-dict',
              'brand_reference': {'sha256': 'reference', 'fully_verified': True}}
    local = copy.deepcopy(frozen)
    if defect=='v0': local['feature_schema_version'] = 'e2-brand-v0'
    if defect=='column_order': matrix = matrix[['id', *reversed(E2_FEATURES)]]
    if defect=='test_id': matrix.loc[2, 'id'] = 'test'
    if defect=='missing_id': matrix = matrix.iloc[:2]
    if defect=='duplicate_id': matrix.loc[2, 'id'] = 'a'
    if defect=='reference': local['brand_reference']['sha256'] = 'old-reference'
    if defect=='dictionary': local['brand_feature_dictionary_sha256'] = 'old-dictionary'
    if defect=='unfrozen': local['frozen'] = False
    if defect=='nan': matrix.loc[0, E2_FEATURES[0]] = np.nan
    if defect:
        with pytest.raises(ValueError): report_functions['checked_brand_handoff'](matrix, metadata, local, frozen)
    else:
        joined = report_functions['checked_brand_handoff'](matrix, metadata, local, frozen)
        assert set(joined.id) == {'a', 'b', 'c'} and not joined.split.eq('test').any()


def test_strict_keyword_sensitivity_deduplicates_and_preserves_token_boundaries(report_functions):
    hits = report_functions['strict_keyword_hits']
    keywords = ['login', 'otp', 'dangnhap', 'account', 'secure']
    parsed = parse_url('https://login.example.com/login/login?x=%C4%90%C4%82NGNHAP&k=OTP#secure')
    assert hits(parsed, keywords) == {'login', 'otp', 'dangnhap'}
    assert hits(parse_url('https://myaccount.example.com/securely'), keywords) == set()
