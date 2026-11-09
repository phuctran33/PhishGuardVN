/// So sánh kết quả Dart với một ca trong docs/mobile_parity_cases.json.
import 'extractor.dart';
import 'url_parser.dart';

const Set<String> continuousFeatures = {'entropy', 'brand_typo_score'};

class ParityDiff {
  final String field;
  final Object? expected;
  final Object? actual;
  const ParityDiff(this.field, this.expected, this.actual);
  @override
  String toString() => '$field: python=$expected dart=$actual';
}

List<ParityDiff> compareParsed(Map<String, dynamic> exp, ParsedUrl p) {
  final got = <String, Object?>{
    'is_valid': p.isValid,
    'error_reason': p.errorReason,
    'hostname': p.hostname,
    'registrable_domain': p.registrableDomain,
    'subdomain': p.subdomain,
    'path': p.path,
    'query': p.query,
    'is_ip': p.isIp,
  };
  return [
    for (final e in got.entries)
      if (exp[e.key] != e.value) ParityDiff('parsed.${e.key}', exp[e.key], e.value)
  ];
}

List<ParityDiff> compareFeatures(Map<String, dynamic> expected, FeatureResult r, double tol) {
  final allNull = expected.values.every((v) => v == null);
  if (allNull) {
    return r.isClassifiable ? [ParityDiff('classifiable', false, true)] : [];
  }
  final vec = r.vector;
  if (vec == null) return [ParityDiff('classifiable', true, false)];
  final diffs = <ParityDiff>[];
  for (var i = 0; i < e2FeatureOrder.length; i++) {
    final name = e2FeatureOrder[i];
    final want = (expected[name] as num).toDouble();
    final got = vec[i];
    final bad = continuousFeatures.contains(name) ? (got - want).abs() > tol : got != want;
    if (bad) diffs.add(ParityDiff(name, want, got));
  }
  return diffs;
}
