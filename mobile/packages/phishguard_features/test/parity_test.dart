import 'dart:convert';
import 'dart:io';

import 'package:phishguard_features/io.dart';
import 'package:phishguard_features/phishguard_features.dart';
import 'package:test/test.dart';

void main() {
  final root = findRepoRoot();
  Map<String, dynamic> load(String name) =>
      jsonDecode(File('$root/docs/$name').readAsStringSync()) as Map<String, dynamic>;
  final data = load('mobile_parity_cases.json');
  final tol = (data['tolerance'] as num).toDouble();
  // File extra là bộ soi sâu (không freeze); chỉ chạy nếu có.
  final suites = <String, Map<String, dynamic>>{
    'frozen': data,
    if (File('$root/docs/mobile_parity_cases_extra.json').existsSync())
      'extra': load('mobile_parity_cases_extra.json'),
  };
  late final E2Extractor ex;

  setUpAll(() => ex = loadExtractorFromRepo(root));

  group('hợp đồng', () {
    test('thứ tự 20 đặc trưng khớp file parity', () {
      expect(e2FeatureOrder, (data['feature_order'] as List).cast<String>());
      expect(e2FeatureOrder.length, 20);
      expect(data['schema_version'], featureSchemaVersion);
    });
    test('brand reference: 45 brand, đúng sha256', () {
      final meta = data['brand_reference'] as Map<String, dynamic>;
      expect(ex.reference.nBrands, 45);
      expect(ex.reference.nBrands, meta['n_brands']);
      expect(ex.reference.sha256Hex, meta['sha256']);
      expect(ex.reference.nWithOfficialSuffixes, meta['n_brands_with_official_suffixes']);
      expect(ex.reference.nWithTypoIgnore, meta['n_brands_with_typo_ignore']);
    });
  });

  for (final entry in suites.entries) {
    final cases = (entry.value['cases'] as List).cast<Map<String, dynamic>>();
    group('${entry.key}: parser trung gian', () {
      for (final c in cases) {
        test(c['name'] as String, () {
          final p = ex.parser.parse(c['url'] as String?);
          final diffs = compareParsed(c['parsed'] as Map<String, dynamic>, p);
          expect(diffs, isEmpty, reason: 'url=${jsonEncode(c['url'])}');
        });
      }
    });
    group('${entry.key}: 20 đặc trưng', () {
      for (final c in cases) {
        test('${c['group']}/${c['name']}', () {
          final r = ex.extract(c['url'] as String?);
          final diffs = compareFeatures(c['expected'] as Map<String, dynamic>, r, tol);
          expect(diffs, isEmpty, reason: 'url=${jsonEncode(c['url'])}');
        });
      }
    });
  }

  test('không văng lỗi với đầu vào xấu', () {
    for (final s in [null, '', ' ', '://', 'http://', 'http://[::1', 'http://]', '%%%', '\u0000', 'a' * 100000]) {
      expect(() => ex.extract(s), returnsNormally);
    }
  });
}
