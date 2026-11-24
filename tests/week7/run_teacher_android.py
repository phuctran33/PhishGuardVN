"""Chạy Teacher QA trên emulator thật; khôi phục trạng thái mạng sau kiểm thử."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET

PACKAGE = "com.phishguardvn.phishguard_android"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--android-root", type=Path, required=True)
    parser.add_argument("--adb", required=True)
    parser.add_argument("--device", required=True)
    parser.add_argument("--flutter", default="flutter")
    parser.add_argument("--phase", choices=["integration", "release"], default="integration")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()
    qa = Path(__file__).resolve().parents[2]
    source = args.android_root.resolve()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    adb = [str(Path(args.adb).resolve()), "-s", args.device]

    def shell(*parts: str) -> str:
        return subprocess.check_output([*adb, "shell", *parts], text=True, encoding="utf-8").strip()

    if shell("getprop", "ro.kernel.qemu") != "1":
        raise SystemExit("Lệnh tự thay đổi mạng này chỉ dành cho emulator.")
    before = {k: shell("settings", "get", "global", k) for k in ["airplane_mode_on", "wifi_on", "mobile_data"]}
    report = {"schema": "k73-android-controller-v1", "status": "running", "phase": args.phase,
              "device": args.device, "android_release": shell("getprop", "ro.build.version.release"),
              "android_api": shell("getprop", "ro.build.version.sdk"), "abi": shell("getprop", "ro.product.cpu.abi"),
              "build_fingerprint": shell("getprop", "ro.build.fingerprint"), "network_before": before,
              "prediction_mocking": False}

    @contextmanager
    def offline():
        try:
            shell("cmd", "connectivity", "airplane-mode", "enable")
            shell("svc", "wifi", "disable")
            shell("svc", "data", "disable")
            time.sleep(2)
            state = {k: shell("settings", "get", "global", k) for k in before}
            state["ipv4_default_route"] = shell("ip", "route", "show", "default")
            state["ipv6_default_route"] = shell("ip", "-6", "route", "show", "default")
            assert state["airplane_mode_on"] == "1" and state["wifi_on"] == "0" and state["mobile_data"] == "0", state
            assert not state["ipv4_default_route"] and not state["ipv6_default_route"], state
            report["network_during"] = state
            yield
        finally:
            shell("cmd", "connectivity", "airplane-mode", "enable" if before["airplane_mode_on"] == "1" else "disable")
            time.sleep(0.5)
            shell("svc", "wifi", "enable" if before["wifi_on"] == "1" else "disable")
            shell("svc", "data", "enable" if before["mobile_data"] == "1" else "disable")
            for _ in range(12):
                restored = {k: shell("settings", "get", "global", k) for k in before}
                if restored == before:
                    break
                time.sleep(0.5)
            report["network_restored"] = restored
            assert restored == before, "Không khôi phục được đúng trạng thái mạng ban đầu."

    def ui() -> str:
        shell("uiautomator", "dump", "/sdcard/pgvn_teacher_qa.xml")
        return shell("cat", "/sdcard/pgvn_teacher_qa.xml")

    def wait_ui(fragment: str) -> str:
        deadline = time.monotonic() + 60
        last = ""
        while time.monotonic() < deadline:
            last = ui()
            if fragment in last:
                return last
            time.sleep(0.4)
        raise AssertionError(f"Không thấy UI {fragment!r}: {last[:400]}")

    try:
        if args.phase == "integration":
            harness = qa / "tests/week7/.teacher_android_harness"
            provenance = json.loads((harness / "qa_provenance.json").read_text(encoding="utf-8"))
            report["source_provenance"] = provenance
            executable = shutil.which(args.flutter) or args.flutter
            native_output = output.with_name(output.stem + "_results.json")
            env = dict(os.environ, QA_TEACHER_ANDROID_OUTPUT=str(native_output))
            shell("am", "force-stop", PACKAGE)
            with offline():
                subprocess.run([executable, "drive", "--profile", "-d", args.device,
                                "--driver=test_driver/teacher_driver.dart", "--target=integration_test/teacher_runtime_test.dart"],
                               cwd=harness, env=env, check=True)
            result = json.loads(native_output.read_text(encoding="utf-8"))
            assert result["status"] == "passed" and result["platform"] == "android", result
            assert result["parity"]["classified_matched"] == 47 and result["parity"]["rejected_matched"] == 9
            assert result["application_tests_passed"] == 3
            report["runtime"] = result
        else:
            apk = source / "mobile/app/build/app/outputs/flutter-apk/app-release.apk"
            sdk = Path(args.adb).resolve().parents[1]
            aapt = sorted((sdk / "build-tools").glob("*/aapt2.exe" if os.name == "nt" else "*/aapt2"))[-1]
            badging = subprocess.check_output([str(aapt), "dump", "badging", str(apk)], text=True, encoding="utf-8")
            assert f"package: name='{PACKAGE}'" in badging, "APK không phải app Teacher Hy."
            assert "x86_64" in badging, "APK không có ABI emulator đang kiểm."
            report["apk"] = {"relative_path": "mobile/app/build/app/outputs/flutter-apk/app-release.apk",
                             "sha256": hashlib.sha256(apk.read_bytes()).hexdigest(), "size_bytes": apk.stat().st_size,
                             "application_id": PACKAGE, "source": "unmodified Hy release app, not QA integration entrypoint"}
            subprocess.run([*adb, "install", "-r", str(apk)], check=True)
            starts = []
            with offline():
                for _ in range(3):
                    shell("am", "force-stop", PACKAGE)
                    started = time.perf_counter()
                    activity = shell("am", "start", "-W", "-n", PACKAGE + "/.MainActivity")
                    xml = wait_ui("Phân tích URL")
                    assert "Chưa sẵn sàng phân tích" not in xml
                    starts.append({"pid": shell("pidof", PACKAGE), "am_start": activity,
                                   "host_observed_launch_to_ui_ms": (time.perf_counter() - started) * 1000})
                nodes = list(ET.fromstring(xml).iter("node"))
                sample = next(n for n in nodes if "vietcombank.com.vn/vi-VN/" in (n.attrib.get("text", "") + n.attrib.get("content-desc", "")))
                x1, y1, x2, y2 = map(int, re.findall(r"\d+", sample.attrib["bounds"]))
                shell("input", "tap", str((x1+x2)//2), str((y1+y2)//2))
                xml = wait_ui("Điểm của mô hình")
                texts = [n.attrib.get("text", "") + n.attrib.get("content-desc", "") for n in ET.fromstring(xml).iter("node") if n.attrib.get("text") or n.attrib.get("content-desc")]
                assert any("Chưa phát hiện dấu hiệu lừa đảo" in t for t in texts), texts
                assert any("teacher-stacking-v2" in t for t in texts)
                assert any("0.6945740700635259" in t for t in texts)
                if args.screenshot:
                    args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                    args.screenshot.write_bytes(subprocess.check_output([*adb, "exec-out", "screencap", "-p"]))
                report["cold_starts"] = starts
                report["native_ui"] = {"url": "https://www.vietcombank.com.vn/vi-VN/", "label": "benign", "visible_text": texts}
                report["timing_limit"] = "Host ADB/UI polling overhead included; process cold starts retain filesystem/shader caches."
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "phase": args.phase, "output": str(output)}))


if __name__ == "__main__":
    main()
