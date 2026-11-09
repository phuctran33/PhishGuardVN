import 'punycode.dart';

/// Public Suffix List (phần ICANN) theo snapshot của tldextract 5.4.0.
/// Một dòng/quy tắc, có thể bắt đầu bằng "*." (wildcard) hoặc "!" (ngoại lệ).
class PublicSuffixList {
  final Set<String> _rules;
  PublicSuffixList._(this._rules);

  factory PublicSuffixList.fromText(String text) {
    final rules = <String>{};
    for (final raw in text.split('\n')) {
      final line = raw.trim();
      if (line.isEmpty || line.startsWith('//')) continue;
      rules.add(line.toLowerCase());
    }
    return PublicSuffixList._(rules);
  }

  factory PublicSuffixList.fromRules(Iterable<String> rules) =>
      PublicSuffixList._(rules.map((r) => r.toLowerCase()).toSet());

  int get size => _rules.length;

  static String _decodeLabel(String l) =>
      l.startsWith('xn--') ? (punycodeDecode(l.substring(4)) ?? l) : l;

  /// Chỉ số nhãn đầu tiên của public suffix trong [labels] (suffix = labels[idx:]).
  /// Trả labels.length nếu không có quy tắc nào khớp (tldextract không áp dụng quy tắc mặc định "*").
  int suffixIndex(List<String> labels) {
    final n = labels.length;
    final decoded = labels.map(_decodeLabel).toList();
    for (var i = 0; i < n; i++) {
      for (final seq in [labels, decoded]) {
        final cand = seq.sublist(i).join('.');
        if (_rules.contains('!$cand')) return i + 1;
        if (_rules.contains(cand)) return i;
        if (i + 1 < n && _rules.contains('*.${seq.sublist(i + 1).join('.')}')) return i;
      }
    }
    return n;
  }
}
