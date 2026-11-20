"""K7.4: chuẩn bị assets QA và reference Python thật, không train/copy vào app Hy."""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
from unittest.mock import patch

STUDENT_REVISION = '1cad94c88195ebea6e4737bbfc863cbe4b2ff384'
MANIFEST_SHA = '09c8e23a95af862debe423adfde237a375a0dd0958f333f49a6502067981bc9c'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--student-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.student_root.resolve()
    package = Path(__file__).resolve().parent / 'student_android'
    revision = subprocess.check_output(['git', '-c', f'safe.directory={root.as_posix()}',
                                      '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != STUDENT_REVISION:
        raise ValueError('Student revision changed; review handoff before updating QA lock')
    folder = root / 'artifacts/student_lightgbm'
    if digest(folder / 'manifest.json') != MANIFEST_SHA:
        raise ValueError('Untrusted manifest')
    read = lambda p: json.loads(p.read_text(encoding='utf-8'))
    manifest = read(folder / 'manifest.json')
    assert manifest['selected_mode'] == 'kd_mixed' and not manifest['student_default']
    assets = package / 'assets'
    assets.mkdir(parents=True, exist_ok=True)
    files = {'manifest.json': {'sha256': MANIFEST_SHA, 'size_bytes': (folder/'manifest.json').stat().st_size}}
    for name in ['features.json', 'kd_mixed.json', 'hard_only.json', 'brand_reference_v1.csv',
                 'psl_icann_tldextract_5.4.0.txt', 'python_reference.json']:
        path = folder / name
        assert digest(path) == manifest['bundle_files_sha256'][name], name
        files[name] = {'sha256': digest(path), 'size_bytes': path.stat().st_size}
    lock = {'schema': 'qa-student-android-lock-v1', 'student_revision': revision, 'files': files}
    lock_path = package / 'student_lock.json'
    if read(lock_path) != lock:
        raise ValueError('QA file sizes/hashes differ from reviewed lock')
    for name in files:
        shutil.copyfile(folder / name, assets / name)
    shutil.copyfile(lock_path, assets / 'student_lock.json')

    # Ensure Dart uses the exact frozen extractor port reviewed with Hy.
    qa_root = package.parents[2]
    assert digest(qa_root/'src/phishguard_vn/resources/brand_reference_v1.csv') == files['brand_reference_v1.csv']['sha256']
    assert digest(qa_root/'mobile/packages/phishguard_features/assets/psl_icann_tldextract_5.4.0.txt') == files['psl_icann_tldextract_5.4.0.txt']['sha256']
    sys.path.insert(0, str(root / 'src'))
    from phishguard_vn.student_lightgbm import load_lightgbm_student
    from phishguard_vn.student_comparison import e2_matrix
    from phishguard_vn.student import student_text

    frozen = read(folder / 'python_reference.json')
    inputs = [(c['name'], c['url'], 'frozen') for c in frozen['cases']]
    inputs += [(f'qa_{i}', url, 'qa_synthetic') for i, url in enumerate([
        'https://example.com/😀/Đăng-nhập?Q=𐍈',
        'https://bücher.de/A%2Fb?Q=ĐăngNhập',
        'https://example.com/a\u00a0\u00a0b?q=X',
        'https://example.com/a\x00b', ' example.com', 'example.com ',
    ])]

    def forbidden(*a, **kw):
        raise AssertionError('Student Python attempted network access')

    cases = []
    with ExitStack() as stack:
        for target in ['socket.getaddrinfo', 'socket.socket.connect', 'socket.socket.connect_ex']:
            stack.enter_context(patch(target, forbidden))
        models = {m: load_lightgbm_student(root, m) for m in ['kd_mixed', 'hard_only']}
        for name, url, origin in inputs:
            case = {'name': name, 'url': url, 'origin': origin}
            try:
                e2 = e2_matrix([url])[0]
                vector = models['kd_mixed'].vector(url, e2)
                text_row = {i: v for i, v in vector.items() if i < 8192}
                case.update(status='classified', canonical_text=student_text(url), e2=e2.tolist(),
                            text_indices=sorted(text_row), text_values=[text_row[i] for i in sorted(text_row)],
                            expected={mode: model.predict_one(url) for mode, model in models.items()})
                if origin == 'frozen':
                    saved = next(c for c in frozen['cases'] if c['name'] == name)
                    assert saved['status'] == 'classified' and saved['canonical_text'] == case['canonical_text']
                    for mode in models:
                        assert abs(saved['expected'][mode]['score'] - case['expected'][mode]['score']) <= 1e-12
                        assert saved['expected'][mode]['label'] == case['expected'][mode]['label']
            except (ValueError, TypeError) as error:
                case.update(status='rejected', error_type=type(error).__name__)
                if origin == 'frozen':
                    assert next(c for c in frozen['cases'] if c['name'] == name)['status'] != 'classified'
            cases.append(case)
    result = {'schema': 'qa-student-live-python-v1', 'student_revision': revision,
              'python': platform.python_version(), 'platform': platform.platform(),
              'network_guards': ['DNS', 'connect', 'connect_ex'],
              'asset_lock_sha256': digest(lock_path), 'cases': cases}
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    output.write_text(content, encoding='utf-8')
    (assets/'live_python_reference.json').write_text(content, encoding='utf-8')
    print(json.dumps({'classified': sum(c['status']=='classified' for c in cases),
                      'rejected': sum(c['status']=='rejected' for c in cases),
                      'copied_assets': len(files), 'student_revision': revision}))


if __name__ == '__main__':
    main()
