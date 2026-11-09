/// Port của features.py: 12 lexical features (E1).
import 'dart:math' as math;

import 'py_compat.dart';
import 'url_parser.dart';

const List<String> lexicalFeatureOrder = [
  'url_len', 'dom_len', 'is_ip', 'subdom_cnt',
  'letter_cnt', 'digit_cnt', 'dot_cnt', 'dash_cnt',
  'under_cnt', 'slash_cnt', 'entropy', 'path_len',
];

double _entropy(String text) {
  final runes = text.runes.toList();
  if (runes.isEmpty) return 0.0;
  final counts = <int, int>{}; // Map của Dart giữ thứ tự chèn, giống Counter của Python
  for (final r in runes) {
    counts[r] = (counts[r] ?? 0) + 1;
  }
  final n = runes.length;
  var sum = 0.0;
  for (final c in counts.values) {
    final p = c / n;
    sum += p * (math.log(p) / math.ln2);
  }
  return -sum;
}

int _count(String text, bool Function(int) pred) {
  var k = 0;
  for (final r in text.runes) {
    if (pred(r)) k++;
  }
  return k;
}

int _countChar(String text, int code) => _count(text, (r) => r == code);

/// null nếu URL không hợp lệ. Thứ tự trả về = [lexicalFeatureOrder].
List<double>? extractLexical(ParsedUrl p) {
  if (!p.isValid) return null;
  final text = p.rawUrl.replaceFirst(schemeStripRe, '');
  final domainText = p.registrableDomain ?? p.hostname;
  return <double>[
    pyLen(text).toDouble(),
    pyLen(domainText).toDouble(),
    p.isIp ? 1.0 : 0.0,
    (p.subdomain.isNotEmpty ? p.subdomain.split('.').length : 0).toDouble(),
    _count(text, pyIsAlpha).toDouble(),
    _count(text, pyIsDigit).toDouble(),
    _countChar(text, 0x2E).toDouble(), // .
    _countChar(text, 0x2D).toDouble(), // -
    _countChar(text, 0x5F).toDouble(), // _
    _countChar(text, 0x2F).toDouble(), // /
    _entropy(text),
    pyLen(p.path).toDouble(),
  ];
}
