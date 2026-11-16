// Sinh báo cáo parity Python-Dart: dart run bin/parity_report.dart [--out-dir <thư mục>]
// Ghi: <out-dir>/mobile_parity_report.md và <out-dir>/tables/mobile_parity_diffs.csv
import 'dart:convert';
import 'dart:io';

import 'package:phishguard_features/io.dart';
import 'package:phishguard_features/phishguard_features.dart';

String _cell(Object? v) => '$v'.replaceAll('|', r'\|').replaceAll('\n', ' ');
String _csv(Object? v) => '"${'$v'.replaceAll('"', '""')}"';

int main(List<String> args) {
  final root = findRepoRoot();
  final i = args.indexOf('--out-dir');
  final outDir = i >= 0 && i + 1 < args.length ? args[i + 1] : '$root/reports';
  final data = jsonDecode(File('$root/docs/mobile_parity_cases.json').readAsStringSync())
      as Map<String, dynamic>;
  final tol = (data['tolerance'] as num).toDouble();
  final cases = (data['cases'] as List).cast<Map<String, dynamic>>();
  final extraFile = File('$root/docs/mobile_parity_cases_extra.json');
  if (extraFile.existsSync()) {
    // Ca bổ sung (không freeze): nhóm có tiền tố "extra:" để phân biệt trong báo cáo.
    final extra = jsonDecode(extraFile.readAsStringSync()) as Map<String, dynamic>;
    for (final c in (extra['cases'] as List).cast<Map<String, dynamic>>()) {
      cases.add({...c, 'group': 'extra:${c['group']}'});
    }
  }
  final ex = loadExtractorFromRepo(root);

  final byGroup = <String, List<int>>{}; // group -> [tổng, đạt]
  final rows = <List<Object?>>[]; // case, group, url, field, python, dart
  var passAll = 0;
  for (final c in cases) {
    final url = c['url'] as String?;
    final r = ex.extract(url);
    final diffs = [
      ...compareParsed(c['parsed'] as Map<String, dynamic>, r.parsed),
      ...compareFeatures(c['expected'] as Map<String, dynamic>, r, tol),
    ];
    final g = byGroup.putIfAbsent(c['group'] as String, () => [0, 0]);
    g[0]++;
    if (diffs.isEmpty) {
      g[1]++;
      passAll++;
    }
    for (final d in diffs) {
      rows.add([c['name'], c['group'], url, d.field, d.expected, d.actual]);
    }
  }

  final md = StringBuffer()
    ..writeln('# Báo cáo parity Python–Dart (E2 v1)')
    ..writeln()
    ..writeln('- schema: `${data['schema_version']}` · tldextract (Python): `${data['tldextract_version']}`')
    ..writeln('- brand reference sha256: `${ex.reference.sha256Hex}` (${ex.reference.nBrands} brand)')
    ..writeln('- tolerance cột liên tục: $tol; cột đếm/cờ: bằng tuyệt đối')
    ..writeln('- kết quả: **$passAll/${cases.length}** ca khớp hoàn toàn (parser trung gian + 20 đặc trưng)')
    ..writeln()
    ..writeln('| Nhóm | Số ca | Khớp |')
    ..writeln('| --- | ---: | ---: |');
  for (final e in byGroup.entries) {
    md.writeln('| ${e.key} | ${e.value[0]} | ${e.value[1]} |');
  }
  md
    ..writeln()
    ..writeln('## Chênh lệch')
    ..writeln();
  if (rows.isEmpty) {
    md.writeln('Không có chênh lệch.');
  } else {
    md
      ..writeln('| Ca | URL | Trường | Python | Dart | Nguyên nhân | Trạng thái |')
      ..writeln('| --- | --- | --- | --- | --- | --- | --- |');
    for (final r in rows) {
      md.writeln('| ${_cell(r[0])} | `${_cell(r[2])}` | ${_cell(r[3])} | ${_cell(r[4])} | ${_cell(r[5])} |  | mở |');
    }
  }
  md
    ..writeln()
    ..writeln('## Tái lập')
    ..writeln()
    ..writeln('```')
    ..writeln('cd mobile/packages/phishguard_features && dart pub get')
    ..writeln('dart test && dart run bin/parity_report.dart')
    ..writeln('```');

  Directory('$outDir/tables').createSync(recursive: true);
  File('$outDir/mobile_parity_report.md').writeAsStringSync(md.toString());
  final csv = StringBuffer('case,group,url,field,python,dart\n');
  for (final r in rows) {
    csv.writeln(r.map(_csv).join(','));
  }
  File('$outDir/tables/mobile_parity_diffs.csv').writeAsStringSync(csv.toString());
  stdout.writeln('Khớp $passAll/${cases.length} ca; ${rows.length} chênh lệch -> $outDir');
  return rows.isEmpty ? 0 : 1;
}
