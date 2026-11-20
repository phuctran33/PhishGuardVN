"""Kiểm app Student MLP của Hy trên emulator, có khôi phục trạng thái mạng."""
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
import zipfile

from prepare_student_mlp_runtime import HY_REVISION, git

PACKAGE = "com.phishguardvn.phishguard_android"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--android-root", type=Path, required=True)
    parser.add_argument("--adb", required=True)
    parser.add_argument("--flutter", default="flutter")
    parser.add_argument("--device", default="emulator-5554")
    parser.add_argument("--phase", choices=["integration", "release"], default="integration")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()
    qa = Path(__file__).resolve().parents[2]
    source, output = args.android_root.resolve(), args.output.resolve()
    if git(source, "rev-parse", "HEAD") != HY_REVISION:
        raise SystemExit("Cần đúng revision Hy đã pin trước khi chạy Android QA.")
    output.parent.mkdir(parents=True, exist_ok=True)
    adb = [args.adb, "-s", args.device]

    def shell(*parts: str) -> str:
        return subprocess.check_output([*adb, "shell", *parts], text=True, encoding="utf-8").strip()

    if shell("getprop", "ro.kernel.qemu") != "1":
        raise SystemExit("Chỉ thay đổi mạng tự động trên emulator; không dùng trên điện thoại cá nhân.")
    before = {k: shell("settings", "get", "global", k) for k in ["airplane_mode_on", "wifi_on", "mobile_data"]}
    report = {"schema": "k74-student-mlp-android-controller-v1", "status": "running", "phase": args.phase,
              "device": args.device, "android_release": shell("getprop", "ro.build.version.release"),
              "android_api": shell("getprop", "ro.build.version.sdk"), "abi": shell("getprop", "ro.product.cpu.abi"),
              "build_fingerprint": shell("getprop", "ro.build.fingerprint"), "network_before": before,
              "prediction_mocking": False, "android_source_revision": HY_REVISION}

    @contextmanager
    def offline():
        try:
            shell("cmd", "connectivity", "airplane-mode", "enable")
            shell("svc", "wifi", "disable")
            shell("svc", "data", "disable")
            time.sleep(2)
            state = {k: shell("settings", "get", "global", k) for k in before}
            state.update({"ipv4_default_route": shell("ip", "route", "show", "default"),
                          "ipv6_default_route": shell("ip", "-6", "route", "show", "default")})
            assert state["airplane_mode_on"] == "1" and state["wifi_on"] == state["mobile_data"] == "0", state
            assert not state["ipv4_default_route"] and not state["ipv6_default_route"], state
            report["network_during"] = state
            yield
        finally:
            shell("cmd", "connectivity", "airplane-mode", "enable" if before["airplane_mode_on"] == "1" else "disable")
            time.sleep(.5)
            shell("svc", "wifi", "enable" if before["wifi_on"] == "1" else "disable")
            shell("svc", "data", "enable" if before["mobile_data"] == "1" else "disable")
            for _ in range(12):
                restored = {k: shell("settings", "get", "global", k) for k in before}
                if restored == before:
                    break
                time.sleep(.5)
            report["network_restored"] = restored
            assert restored == before, "Chưa khôi phục đúng trạng thái mạng ban đầu."

    def ui() -> str:
        shell("uiautomator", "dump", "/sdcard/pgvn_mlp_qa.xml")
        return shell("cat", "/sdcard/pgvn_mlp_qa.xml")

    def wait_ui(fragment: str) -> str:
        deadline = time.monotonic() + 60
        last = ""
        while time.monotonic() < deadline:
            last = ui()
            if fragment in last:
                return last
            time.sleep(.4)
        raise AssertionError(f"Không thấy UI {fragment!r}: {last[:400]}")

    def tap_text(xml: str, text: str) -> None:
        node = next(n for n in ET.fromstring(xml).iter("node") if text in (n.attrib.get("text", "") + n.attrib.get("content-desc", "")))
        x1, y1, x2, y2 = map(int, re.findall(r"\d+", node.attrib["bounds"]))
        shell("input", "tap", str((x1 + x2) // 2), str((y1 + y2) // 2))

    try:
        if args.phase == "integration":
            harness = qa / "tests/week7/.student_mlp_android_harness"
            report["source_provenance"] = json.loads((harness / "qa_provenance.json").read_text(encoding="utf-8"))
            native_output = output.with_name(output.stem + "_results.json")
            env = dict(os.environ, QA_MLP_ANDROID_OUTPUT=str(native_output))
            executable = shutil.which(args.flutter) or args.flutter
            shell("am", "force-stop", PACKAGE)
            with offline():
                result = subprocess.run([executable, "drive", "--profile", "-d", args.device,
                                         "--driver=test_driver/mlp_driver.dart", "--target=integration_test/mlp_runtime_test.dart"],
                                        cwd=harness, env=env)
            report["flutter_exit_code"] = result.returncode
            runtime = json.loads(native_output.read_text(encoding="utf-8"))
            report["runtime"] = runtime
            assert runtime["platform"] == "android"
            assert runtime["classified_matched"] == 54 and runtime["rejected_matched"] == 9
            report["status"] = "passed" if result.returncode == 0 and runtime["status"] == "passed" else "failed"
        else:
            apk = source / "mobile/app/build/app/outputs/flutter-apk/app-release.apk"
            with zipfile.ZipFile(apk) as archive:
                manifest = json.loads(archive.read("assets/flutter_assets/assets/student_mlp_manifest.json"))
                packaged = {}
                for name, expected in [("student_mlp.json.gz", manifest["model"]),
                                       ("psl_icann_tldextract_5.4.0.txt", manifest["psl"])]:
                    raw = archive.read("assets/flutter_assets/assets/" + name)
                    actual = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                    assert actual == expected, name
                    packaged[name] = actual
                assert manifest["model_version"] == "student-mlp-kd-int8-v1" and manifest["threshold"] == 0.72961075
                report["packaged_student_assets"] = packaged
            report["apk"] = {"relative_path": "mobile/app/build/app/outputs/flutter-apk/app-release.apk",
                             "size_bytes": apk.stat().st_size, "sha256": hashlib.sha256(apk.read_bytes()).hexdigest(),
                             "application_id": PACKAGE, "source": "unmodified Hy app release entrypoint"}
            subprocess.run([*adb, "install", "-r", str(apk)], check=True)
            starts = []
            with offline():
                for _ in range(3):
                    shell("am", "force-stop", PACKAGE)
                    started = time.perf_counter()
                    activity = shell("am", "start", "-W", "-n", PACKAGE + "/.MainActivity")
                    xml = wait_ui("Student MLP")
                    assert "Student load lỗi" not in xml and "Student chưa được nạp" not in xml
                    starts.append({"pid": shell("pidof", PACKAGE), "am_start": activity,
                                   "host_observed_launch_to_ui_ms": (time.perf_counter() - started) * 1000})
                # Native touch selects a real URL; the Teacher action remains independent.
                tap_text(xml, "vietcombank.com.vn/vi-VN/")
                xml = wait_ui("Điểm của mô hình")
                for _ in range(4):
                    try:
                        tap_text(xml, "Phân tích bằng Student")
                        break
                    except (StopIteration, ValueError):
                        shell("input", "swipe", "540", "1600", "540", "600", "300")
                        xml = ui()
                xml = wait_ui("Kết quả Student MLP")
                assert "student-mlp-kd-int8-v1" in xml and "0.72961075" in xml
                report["native_ui_xml"] = xml
                report["cold_starts"] = starts
                report["memory_dumpsys"] = shell("dumpsys", "meminfo", PACKAGE)
                if args.screenshot:
                    args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                    args.screenshot.write_bytes(subprocess.check_output([*adb, "exec-out", "screencap", "-p"]))
            report["status"] = "passed"
            report["scope"] = "Process cold starts retain filesystem/shader caches; ADB polling time includes host overhead."
    except Exception as error:
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
        raise
    finally:
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "phase": args.phase, "output": str(output)}))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
