"""Sinh app QA Android riêng trong thư mục ignored; không sửa ứng dụng của Hy."""
import argparse
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--flutter', default='flutter')
    args = parser.parse_args()
    flutter_command = shutil.which(args.flutter) or args.flutter
    package = Path(__file__).resolve().parent / 'student_android'
    runtime = package / '.android_harness'
    if not (package/'assets/live_python_reference.json').is_file():
        raise SystemExit('Run prepare_student_android.py first')
    if not (runtime/'android').is_dir():
        subprocess.run([flutter_command, 'create', '--empty', '--platforms=android',
                        '--org=vn.phishguard.qa', '--project-name=student_android_runtime_qa',
                        '--no-pub', str(runtime)], check=True)
    # Flutter 3.47's template uses the built-in Kotlin DSL but opts out in
    # gradle.properties. Keep those generated QA files consistent (AGP 9+).
    # https://docs.flutter.dev/release/breaking-changes/migrate-to-built-in-kotlin/for-app-developers
    properties_path = runtime/'android/gradle.properties'
    properties = properties_path.read_text(encoding='utf-8')
    properties = properties.replace('android.builtInKotlin=false', 'android.builtInKotlin=true')
    if 'android.builtInKotlin=true' not in properties:
        properties += '\nandroid.builtInKotlin=true\n'
    properties_path.write_text(properties, encoding='utf-8')
    (runtime/'pubspec.yaml').write_text('''name: student_android_runtime_qa
publish_to: none
version: 0.1.0+1
environment:
  sdk: '>=3.0.0 <4.0.0'
dependencies:
  flutter:
    sdk: flutter
  student_android_qa:
    path: ..
dev_dependencies:
  flutter_test:
    sdk: flutter
  integration_test:
    sdk: flutter
  flutter_lints: ^6.0.0
flutter:
  uses-material-design: true
''', encoding='utf-8')
    for source, target in [('main.dart.in', 'lib/main.dart'),
                           ('student_runtime_test.dart.in', 'integration_test/student_runtime_test.dart'),
                           ('integration_driver.dart.in', 'test_driver/integration_driver.dart'),
                           ('bootstrap_test.dart.in', 'test/bootstrap_test.dart')]:
        destination = runtime/target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(package/'runtime'/source, destination)
    shutil.copyfile(package/'runtime/pubspec.lock', runtime/'pubspec.lock')
    print('Prepared ignored Android QA app:', runtime)
    print('Teacher app/source/default engine unchanged. No APK built or installed by this step.')


if __name__ == '__main__':
    main()
