"""Đo APK QA release trên emulator: process cold-start, loader, RAM và offline.

Không dùng thay benchmark điện thoại thật. Chỉ cài đúng application ID QA riêng.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET

PACKAGE = 'vn.phishguard.qa.student_android_runtime_qa'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', type=Path, required=True)
    parser.add_argument('--device', required=True)
    parser.add_argument('--apk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--screenshot', type=Path, required=True)
    args = parser.parse_args()

    def run(command, binary=False):
        result = subprocess.run(command, capture_output=True, check=True, timeout=90)
        return result.stdout if binary else result.stdout.decode('utf-8', errors='replace').strip()

    def adb(*command, binary=False):
        return run([str(args.adb), '-s', args.device, *command], binary=binary)

    assert adb('shell', 'getprop', 'ro.kernel.qemu') == '1', 'Helper chỉ đổi mạng của emulator, không thao tác điện thoại mượn.'
    sdk = args.adb.resolve().parent.parent
    aapt = sdk/'build-tools/36.0.0'/('aapt2.exe' if os.name == 'nt' else 'aapt2')
    badging = run([str(aapt), 'dump', 'badging', str(args.apk)])
    assert f"package: name='{PACKAGE}'" in badging, 'Không cài APK khác application ID QA'
    assert "native-code: 'x86_64'" in badging, 'Lượt đo này dùng release x86_64'
    adb('install', '-r', str(args.apk.resolve()))
    original = {key: adb('shell', 'settings', 'get', 'global', key)
                for key in ['airplane_mode_on', 'wifi_on', 'mobile_data']}
    samples = []
    try:
        adb('shell', 'cmd', 'connectivity', 'airplane-mode', 'enable')
        adb('shell', 'svc', 'wifi', 'disable')
        adb('shell', 'svc', 'data', 'disable')
        time.sleep(2)
        offline = {key: adb('shell', 'settings', 'get', 'global', key) for key in original}
        routes = adb('shell', 'ip', 'route')
        assert offline == {'airplane_mode_on': '1', 'wifi_on': '0', 'mobile_data': '0'}
        assert 'default ' not in routes, 'Emulator còn default route'
        for _ in range(3):
            adb('shell', 'am', 'force-stop', PACKAGE)
            start = time.perf_counter()
            launch = adb('shell', 'am', 'start', '-W', '-n', f'{PACKAGE}/.MainActivity')
            assert 'Status: ok' in launch
            ready = None
            for _ in range(60):
                pid = adb('shell', 'pidof', PACKAGE).strip()
                logs = adb('logcat', '-d', f'--pid={pid}', '-s', 'flutter:I', '*:S') if pid else ''
                hits = re.findall(r'QA_STUDENT_READY (\{[^\n]+\})', logs)
                if hits:
                    ready = json.loads(hits[-1])
                    break
                time.sleep(.2)
            assert ready is not None, 'Không có marker model readiness sau cold start'
            samples.append({'pid': pid, 'model_version': ready['model_version'],
                            'loader_ms': ready['load_ms'],
                            'launch_to_ready_host_observed_ms': (time.perf_counter()-start)*1000,
                            'activity_total_ms': int(re.search(r'TotalTime:\s*(\d+)', launch).group(1))})
        # Chạm nút native bằng bounds từ accessibility; không fake model/keyboard.
        def ui():
            adb('shell', 'uiautomator', 'dump', '/sdcard/pgvn-student-qa.xml')
            return ET.fromstring(adb('shell', 'cat', '/sdcard/pgvn-student-qa.xml'))

        tree = ui()
        button = next(n for n in tree.iter('node') if 'Predict Student' in (n.get('text', '') + n.get('content-desc', '')))
        x1, y1, x2, y2 = map(int, re.findall(r'\d+', button.get('bounds')))
        adb('shell', 'input', 'tap', str((x1+x2)//2), str((y1+y2)//2))
        tree = ui()
        text = '\n'.join(n.get('text', '') + n.get('content-desc', '') for n in tree.iter('node'))
        assert '"label": "benign"' in text and 'lightgbm-student-kd_mixed' in text, 'Native UI chưa hiển thị prediction mặc định example.com'
        memory = adb('shell', 'dumpsys', 'meminfo', PACKAGE)
        pss = re.search(r'TOTAL PSS:\s*(\d+)', memory)
        assert pss, 'Thiếu số đo TOTAL PSS'
        args.screenshot.parent.mkdir(parents=True, exist_ok=True)
        args.screenshot.write_bytes(adb('exec-out', 'screencap', '-p', binary=True))
        result = {'schema': 'qa-student-android-release-measurement-v1', 'status': 'passed',
                  'device': args.device, 'android_release': adb('shell', 'getprop', 'ro.build.version.release'),
                  'api': adb('shell', 'getprop', 'ro.build.version.sdk'),
                  'abi': adb('shell', 'getprop', 'ro.product.cpu.abi'), 'emulator': True,
                  'build_mode': 'release', 'apk_bytes': args.apk.stat().st_size,
                  'apk_sha256': hashlib.sha256(args.apk.read_bytes()).hexdigest(),
                  'package': PACKAGE, 'offline_state': offline, 'routes': routes.splitlines(),
                  'process_cold_start_samples': samples, 'total_pss_after_native_prediction_kb': int(pss.group(1)),
                  'native_ui': {'input': 'example.com', 'expected_label': 'benign', 'status': 'passed', 'interaction': 'ADB native touch; no keyboard input'},
                  'limitations': ['3 lần force-stop; filesystem/shader cache không xóa.',
                                  'Launch-to-ready đo tại host gồm overhead ADB/polling; không phải timing Android thuần.',
                                  'Activity TotalTime và loader time là hai chỉ số riêng.',
                                  'RAM là snapshot QA app có thêm hard-only/fixtures trong APK; không phải budget production.',
                                  'Chỉ emulator x86_64, chưa phải điện thoại thật.']}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(json.dumps({'status': 'passed', 'cold_start_samples': 3, 'native_offline_prediction': 'passed', 'pss_kb': int(pss.group(1))}))
    finally:
        if original['airplane_mode_on'] == '0':
            adb('shell', 'cmd', 'connectivity', 'airplane-mode', 'disable')
        if original['wifi_on'] == '1':
            adb('shell', 'svc', 'wifi', 'enable')
        if original['mobile_data'] == '1':
            adb('shell', 'svc', 'data', 'enable')


if __name__ == '__main__':
    main()
