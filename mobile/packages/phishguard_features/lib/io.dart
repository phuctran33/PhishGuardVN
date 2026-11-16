/// Tiện ích chạy trên Dart VM (test, bin/): đọc file trong repo. KHÔNG import từ app Flutter.
library phishguard_features_io;

import 'dart:io';

import 'phishguard_features.dart';

const pslAssetName = 'psl_icann_tldextract_5.4.0.txt';

/// Đi ngược từ thư mục hiện tại đến khi thấy docs/mobile_parity_cases.json (hoặc dùng PHISHGUARD_ROOT).
String findRepoRoot() {
  final env = Platform.environment['PHISHGUARD_ROOT'];
  if (env != null && env.isNotEmpty) return env;
  var dir = Directory.current.absolute;
  while (true) {
    if (File('${dir.path}/docs/mobile_parity_cases.json').existsSync()) return dir.path;
    final parent = dir.parent;
    if (parent.path == dir.path) {
      throw StateError('Không tìm thấy docs/mobile_parity_cases.json; đặt PHISHGUARD_ROOT.');
    }
    dir = parent;
  }
}

String pslAssetPath(String root) =>
    '$root/mobile/packages/phishguard_features/assets/$pslAssetName';

String brandReferencePath(String root) =>
    '$root/src/phishguard_vn/resources/brand_reference_v1.csv';

E2Extractor loadExtractorFromRepo([String? root]) {
  root ??= findRepoRoot();
  final pslFile = File(pslAssetPath(root));
  if (!pslFile.existsSync()) {
    throw StateError('Thiếu ${pslFile.path}. Chạy scripts/export_psl_for_dart.py (tldextract 5.4.0) '
        'rồi chép file vào assets/.');
  }
  final psl = PublicSuffixList.fromText(pslFile.readAsStringSync());
  final ref = BrandReference.fromBytes(File(brandReferencePath(root)).readAsBytesSync());
  return E2Extractor(psl, ref);
}
