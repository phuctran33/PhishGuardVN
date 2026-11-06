"""Regression coverage for UTF-8/LF and regenerating the actual H5.2 handoff."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess

import pandas as pd
import pytest

from phishguard_vn.e2_audit import sha256
from phishguard_vn.error_analysis import update_human_checklist
from phishguard_vn.week5 import _json, _report

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def report_inputs(tmp_path):
    for name in ['reports/annotations/week5_human_review.csv', 'reports/annotations/week5_ai_review.csv',
                 'reports/tables/week5/verification.json', 'reports/tables/week5/error_model_evidence.csv',
                 'reports/templates/week5_h52.md']:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / name).read_bytes())
    tables = ROOT / 'reports/tables/week5'
    names = dict(metrics='metrics', folds_metric='fold_metrics', cases='error_cases', taxonomy='error_taxonomy',
                 robust='robustness_summary', shift='distribution_shift', numerical_shift='numerical_shift')
    args = {key: pd.read_csv(tables / (name + '.csv'), encoding='utf-8') for key, name in names.items()}
    manifest = json.loads((tables / 'run_manifest.json').read_text(encoding='utf-8'))
    manifest['native_model_audit'] = None  # This fixture exercises reporting, not a producer model handoff.
    return dict(root=tmp_path, **args, manifest=manifest, e2_status=manifest['e2_status'])


def assert_h52_narrative(text):
    section = text.split('## H5.2', 1)[1].split('## H5.3', 1)[0]
    for required in ['H52-A', 'H52-B', 'H52-C', 'H52-D', '**Conclusion:**',
                     'Acceptance against the supplied Week-5 H5.2 plan', 'plausible_unverified',
                     'error_model_evidence.csv', 'error_feature_attributions.csv', 'next_check']:
        assert required in section
    assert '$' not in section


def test_report_regeneration_preserves_confirmations_and_full_narrative(report_inputs):
    root = report_inputs['root']
    protected = [root / 'reports/annotations' / name for name in ['week5_human_review.csv', 'week5_ai_review.csv']]
    before = [p.read_bytes() for p in protected]
    _report(**report_inputs)
    report = root / 'reports/week5_evaluation.md'
    first = report.read_bytes()
    _report(**report_inputs)
    assert report.read_bytes() == first
    assert [p.read_bytes() for p in protected] == before
    text = first.decode('utf-8')
    assert 'H5.2 DONE / HUMAN VERIFIED OFFLINE (30/40)' in text
    assert '30 human_verified, 10 pending' in text
    assert 'HUMAN REVIEW PENDING' not in text
    assert_h52_narrative(text)


@pytest.mark.parametrize('verified_count', [0, 29])
def test_report_does_not_promote_incomplete_checklist(report_inputs, verified_count):
    path = report_inputs['root'] / 'reports/annotations/week5_human_review.csv'
    human = pd.read_csv(path, dtype=str, keep_default_na=False, encoding='utf-8')
    to_clear = human.index[human.review_status.eq('human_verified')][verified_count:]
    human.loc[to_clear, 'review_status'] = 'pending'
    human.loc[to_clear, ['reviewer', 'reviewed_at', 'observation_checked', 'hypothesis_assessed', 'evidence_checked', 'notes']] = ''
    human.to_csv(path, index=False, encoding='utf-8', lineterminator='\n')
    before = path.read_bytes()
    _report(**report_inputs)  # The AI ledger and old confirmation record still contain 30: neither overrides this checklist.
    first = (report_inputs['root'] / 'reports/week5_evaluation.md').read_bytes()
    _report(**report_inputs)
    assert (report_inputs['root'] / 'reports/week5_evaluation.md').read_bytes() == first
    text = first.decode('utf-8')
    assert 'H5.2 DONE' not in text
    assert f'HUMAN REVIEW PENDING ({verified_count}/30 verified; {40-verified_count} pending)' in text
    assert f'PENDING — only {verified_count}/30 ID-backed human offline reviews' in text
    assert path.read_bytes() == before
    assert_h52_narrative(text)


@pytest.mark.parametrize('defect', ['id', 'reviewer', 'timestamp', 'confirmation_ids'])
def test_report_rejects_unbacked_human_review(report_inputs, defect):
    root = report_inputs['root']
    path = root / 'reports/annotations/week5_human_review.csv'
    human = pd.read_csv(path, dtype=str, keep_default_na=False, encoding='utf-8')
    index = human.index[human.review_status.eq('human_verified')][0]
    if defect == 'id': human.loc[index, 'id'] = 'unconfirmed-id'
    if defect == 'reviewer': human.loc[index, 'reviewer'] = 'unconfirmed reviewer'
    if defect == 'timestamp': human.loc[index, 'reviewed_at'] = '1900-01-01'
    if defect == 'confirmation_ids':
        metadata = root / 'reports/tables/week5/verification.json'
        record = json.loads(metadata.read_text(encoding='utf-8'))
        record['human_review']['confirmed_ids'].remove(human.loc[index, 'id'])
        metadata.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8', newline='\n')
    human.to_csv(path, index=False, encoding='utf-8', lineterminator='\n')
    with pytest.raises(ValueError, match='H5.2'):
        _report(**report_inputs)


def test_utf8_lf_generation_under_simulated_windows_defaults(report_inputs, monkeypatch):
    root = report_inputs['root']
    original_read, original_write = Path.read_text, Path.write_text
    monkeypatch.setattr(os, 'linesep', '\r\n')
    monkeypatch.setattr(Path, 'read_text', lambda self, encoding=None, errors=None: original_read(
        self, encoding=encoding or 'cp1252', errors=errors))
    def legacy_write(self, data, encoding=None, errors=None, newline=None):
        if newline is None: data = data.replace('\n', '\r\n')
        return original_write(self, data, encoding=encoding or 'cp1252', errors=errors, newline='\n')
    monkeypatch.setattr(Path, 'write_text', legacy_write)
    value = {'reviewer': 'Hưng', 'observation': 'Tiếng Việt: Phúc, Đặng'}
    path = root / 'utf8.json'
    _json(path, value)
    assert json.loads(path.read_text(encoding='utf-8')) == value
    assert b'\r' not in path.read_bytes() and 'Hưng'.encode('utf-8') in path.read_bytes()
    human_path = root / 'reports/annotations/week5_human_review.csv'
    before = pd.read_csv(human_path, dtype=str, keep_default_na=False, encoding='utf-8')
    evidence = pd.read_csv(root / 'reports/tables/week5/error_model_evidence.csv', encoding='utf-8')
    for _ in range(2):
        update_human_checklist(report_inputs['cases'], evidence, human_path)
        _report(**report_inputs)
    after = pd.read_csv(human_path, dtype=str, keep_default_na=False, encoding='utf-8')
    fields = ['id', 'reviewer', 'reviewed_at', 'observation_checked', 'hypothesis_assessed', 'evidence_checked', 'notes', 'review_status']
    pd.testing.assert_frame_equal(before[fields], after[fields])
    assert b'\r' not in human_path.read_bytes()
    assert b'\r' not in (root / 'reports/week5_evaluation.md').read_bytes()
    assert_h52_narrative((root / 'reports/week5_evaluation.md').read_text(encoding='utf-8'))


@pytest.mark.parametrize('autocrlf', ['true', 'false'])
def test_git_checkout_keeps_annotation_hashes_lf_and_dataset_raw(tmp_path, autocrlf):
    if not shutil.which('git'): pytest.skip('Git is needed to exercise checkout attributes')
    def git(*args):
        return subprocess.run(['git', *args], cwd=tmp_path, check=True, capture_output=True)
    git('init', '-q')
    git('config', 'core.autocrlf', autocrlf)
    (tmp_path / '.gitattributes').write_bytes((ROOT / '.gitattributes').read_bytes())
    files = []
    expected = 'reviewer,Hưng\nstatus,human_verified\n'.encode('utf-8')
    for name in ['week5_human_review.csv', 'week5_ai_review.csv', 'week5_error_reviews.json']:
        path = tmp_path / 'reports/annotations' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(expected.replace(b'\n', b'\r\n'))
        files.append(path.relative_to(tmp_path).as_posix())
    dataset = tmp_path / 'data/dataset_url.csv'
    dataset.parent.mkdir()
    dataset.write_bytes(b'id,url\r\nfixture,example.test\r\n')
    dataset_before = dataset.read_bytes()
    git('add', '.gitattributes', *files, 'data/dataset_url.csv')
    for name in files:
        assert git('show', ':' + name).stdout == expected
        (tmp_path / name).unlink()  # Force an actual checkout, not the index stat-cache fast path.
    dataset.unlink()
    git('checkout-index', '--force', '--', *files, 'data/dataset_url.csv')
    for name in files:
        assert (tmp_path / name).read_bytes() == expected
        assert sha256(tmp_path / name) == hashlib.sha256(expected).hexdigest()
    assert dataset.read_bytes() == dataset_before
    # Hashing itself remains raw-byte hashing; no blanket CRLF normalization is introduced.
    raw = tmp_path / 'model.joblib'
    raw.write_bytes(b'\x80\x00\r\n\xff')
    assert sha256(raw) == hashlib.sha256(raw.read_bytes()).hexdigest()
    assert sha256(raw) != hashlib.sha256(raw.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
