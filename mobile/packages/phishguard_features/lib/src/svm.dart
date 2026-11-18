/// Pure-Dart inference for the frozen Teacher v2 character TF-IDF LinearSVC branch.
///
/// Model files are JSON exports from scripts/export_teacher_v2_android.py. This
/// class intentionally implements only the SVM branch; HistGB/meta inference is
/// out of scope.
library;

import 'dart:math' as math;

import 'idna.dart' show hostToAscii;
import 'py_compat.dart' show isPySpaceCode;

const String _modelVersion = 'teacher-stacking-v2';

/// CanonicalText from src/phishguard_vn/stacking.py for hierarchical URLs.
/// It omits scheme, userinfo and fragment; IDNA-encodes the host, removes
/// default HTTP(S) ports, and retains path/query text.
///
/// IMPORTANT: [hostToAscii] is the package's existing UTS-46 approximation.
/// It is not proven equivalent to Python's `idna.encode(..., uts46: true)` for
/// all Unicode hosts. See reports/mobile_svm_inference.md; do not claim exact
/// canonicalization parity for untested IDNA cases.
String canonicalizeTeacherUrl(String value) {
  final schemeMatch = RegExp(r'^[a-zA-Z][a-zA-Z0-9+.\-]*://').firstMatch(value);
  final working = schemeMatch != null
      ? value
      : value.startsWith('//')
          ? 'http:$value'
          : '//$value';

  // urllib.parse.urlsplit removes ASCII TAB/CR/LF anywhere in its input.
  final input = working.replaceAll(RegExp(r'[\t\r\n]'), '');
  final scheme =
      RegExp(r'^([a-zA-Z][a-zA-Z0-9+.\-]*):').firstMatch(input)?.group(1) ?? '';
  var rest = scheme.isEmpty ? input : input.substring(scheme.length + 1);
  if (!rest.startsWith('//')) {
    throw FormatException('URL has no hostname');
  }
  rest = rest.substring(2);
  var authorityEnd = rest.length;
  for (final separator in const ['/', '?', '#']) {
    final index = rest.indexOf(separator);
    if (index >= 0 && index < authorityEnd) authorityEnd = index;
  }
  final authority = rest.substring(0, authorityEnd);
  var suffix = rest.substring(authorityEnd);
  final fragment = suffix.indexOf('#');
  if (fragment >= 0) suffix = suffix.substring(0, fragment);
  final queryAt = suffix.indexOf('?');
  final path = queryAt < 0 ? suffix : suffix.substring(0, queryAt);
  final query = queryAt < 0 ? '' : suffix.substring(queryAt + 1);

  // SplitResult.hostname discards userinfo and uses the portion after the last @.
  final at = authority.lastIndexOf('@');
  final hostInfo = at < 0 ? authority : authority.substring(at + 1);
  String rawHost;
  String? portText;
  if (hostInfo.startsWith('[')) {
    final close = hostInfo.indexOf(']');
    if (close < 0) throw FormatException('Invalid bracketed host');
    rawHost = hostInfo.substring(1, close);
    final tail = hostInfo.substring(close + 1);
    if (tail.isNotEmpty) {
      if (!tail.startsWith(':')) throw FormatException('Invalid host suffix');
      portText = tail.substring(1);
    }
  } else {
    final colon = hostInfo.indexOf(':');
    rawHost = colon < 0 ? hostInfo : hostInfo.substring(0, colon);
    if (colon >= 0) portText = hostInfo.substring(colon + 1);
  }
  if (rawHost.isEmpty) throw FormatException('URL has no hostname');

  int? port;
  // urllib.parse.SplitResult.port treats an empty port as None.
  if (portText != null && portText.isNotEmpty) {
    if (!RegExp(r'^[0-9]+$').hasMatch(portText)) {
      throw FormatException('Invalid URL port');
    }
    port = int.tryParse(portText);
    if (port == null || port > 65535) throw FormatException('Invalid URL port');
  }

  // Python catches idna.IDNAError and falls back to lowercasing the original
  // hostname. IPv6 literals fail IDNA, so preserve/lowercase their colon form.
  var host = rawHost.contains(':')
      ? rawHost.toLowerCase()
      : (hostToAscii(rawHost) ?? rawHost.toLowerCase());
  host = host.toLowerCase();
  final bracketedHost = host.contains(':') ? '[$host]' : host;
  final lowerScheme = scheme.toLowerCase();
  final isDefaultPort = (lowerScheme == 'http' && port == 80) ||
      (lowerScheme == 'https' && port == 443);
  final netloc =
      bracketedHost + (port != null && !isDefaultPort ? ':$port' : '');
  return netloc + path + (query.isNotEmpty ? '?$query' : '');
}

/// Frozen character TF-IDF + binary LinearSVC model.
class SvmModel {
  SvmModel._({
    required Map<String, int> vocabulary,
    required List<double> idf,
    required List<double> coefficients,
    required this.intercept,
    required this.canonicalEnabled,
    required this.minNgram,
    required this.maxNgram,
  })  : vocabulary = Map.unmodifiable(vocabulary),
        idf = List.unmodifiable(idf),
        coefficients = List.unmodifiable(coefficients);

  final Map<String, int> vocabulary;
  final List<double> idf;
  final List<double> coefficients;
  final double intercept;
  final bool canonicalEnabled;
  final int minNgram;
  final int maxNgram;

  /// Load the `dart-svm-v1` JSON object emitted by the Python exporter.
  factory SvmModel.fromJson(Map<String, dynamic> json) {
    if (json['schema_version'] != 'dart-svm-v1' ||
        json['model_version'] != _modelVersion) {
      throw FormatException('Unsupported Teacher SVM model schema/version');
    }
    final config = json['config'];
    if (config is! Map<String, dynamic> ||
        config['analyzer'] != 'char' ||
        config['sublinear_tf'] != true ||
        config['use_idf'] != true ||
        config['norm'] != 'l2' ||
        config['lowercase'] != false ||
        config['min_df'] != 2) {
      throw FormatException('Unsupported SVM vectorizer configuration');
    }
    final range = config['ngram_range'];
    if (range is! List || range.length != 2 || range[0] != 2 || range[1] != 5) {
      throw FormatException('Expected char ngram range [2, 5]');
    }
    final rawVocabulary = json['vocabulary'];
    if (rawVocabulary is! Map) throw FormatException('Missing vocabulary map');
    final vocabulary = <String, int>{};
    for (final entry in rawVocabulary.entries) {
      if (entry.key is! String || entry.value is! int) {
        throw FormatException('Vocabulary must map strings to integer indices');
      }
      vocabulary[entry.key as String] = entry.value as int;
    }
    final idf = _numberList(json['idf'], 'idf');
    final coefficients = _numberList(json['coefficients'], 'coefficients');
    final interceptValue = json['intercept'];
    if (interceptValue is! num || !interceptValue.toDouble().isFinite) {
      throw FormatException('Invalid SVM intercept');
    }
    final featureCount = vocabulary.length;
    if (idf.length != featureCount || coefficients.length != featureCount) {
      throw FormatException('Vocabulary/IDF/coefficient lengths differ');
    }
    final seen = List<bool>.filled(featureCount, false);
    for (final index in vocabulary.values) {
      if (index < 0 || index >= featureCount || seen[index]) {
        throw FormatException(
            'Vocabulary indices must be unique and contiguous');
      }
      seen[index] = true;
    }
    if (seen.any((present) => !present)) {
      throw FormatException('Vocabulary indices must be contiguous');
    }
    return SvmModel._(
      vocabulary: vocabulary,
      idf: idf,
      coefficients: coefficients,
      intercept: interceptValue.toDouble(),
      canonicalEnabled: config['canonical_enabled'] == true,
      minNgram: 2,
      maxNgram: 5,
    );
  }

  static List<double> _numberList(dynamic value, String name) {
    if (value is! List) throw FormatException('Missing $name array');
    return value.map((item) {
      if (item is! num || !item.toDouble().isFinite) {
        throw FormatException('Invalid number in $name');
      }
      return item.toDouble();
    }).toList(growable: false);
  }

  /// Compute sklearn LinearSVC's signed decision margin:
  /// `dot(l2_normalized_tfidf, coef_) + intercept_`.
  double predictMargin(String url) {
    final text = canonicalEnabled ? canonicalizeTeacherUrl(url) : url;
    final normalized = _sklearnWhitespaceNormalization(text);
    final codePoints = normalized.runes.toList(growable: false);
    final counts = <int, int>{};
    for (var n = minNgram; n <= maxNgram; n++) {
      for (var start = 0; start + n <= codePoints.length; start++) {
        final gram = String.fromCharCodes(codePoints.sublist(start, start + n));
        final index = vocabulary[gram];
        if (index != null)
          counts.update(index, (count) => count + 1, ifAbsent: () => 1);
      }
    }

    final weighted = <int, double>{};
    var squaredNorm = 0.0;
    for (final entry in counts.entries) {
      final value = (1.0 + math.log(entry.value)) * idf[entry.key];
      weighted[entry.key] = value;
      squaredNorm += value * value;
    }
    var dot = 0.0;
    if (squaredNorm > 0) {
      final inverseNorm = 1.0 / math.sqrt(squaredNorm);
      // sklearn builds a sparse row sorted by vocabulary index, normalizes
      // each stored value, then its sparse dot accumulates in index order.
      final indices = weighted.keys.toList()..sort();
      for (final index in indices) {
        final normalizedValue = weighted[index]! * inverseNorm;
        dot += normalizedValue * coefficients[index];
      }
    }
    return dot + intercept;
  }
}

/// sklearn's char analyzer replaces every run of two or more Unicode
/// whitespace characters with one ASCII space. A single whitespace character
/// is preserved as-is; unlike word analyzers, this does not trim the string.
String _sklearnWhitespaceNormalization(String text) {
  final runes = text.runes.toList(growable: false);
  final output = <int>[];
  var index = 0;
  while (index < runes.length) {
    if (!isPySpaceCode(runes[index])) {
      output.add(runes[index++]);
      continue;
    }
    var end = index + 1;
    while (end < runes.length && isPySpaceCode(runes[end])) {
      end++;
    }
    if (end - index == 1) {
      output.add(runes[index]);
    } else {
      output.add(0x20);
    }
    index = end;
  }
  return String.fromCharCodes(output);
}

/// Exposed for focused analyzer tests and diagnostics.
String normalizeSklearnCharWhitespace(String text) =>
    _sklearnWhitespaceNormalization(text);
