import 'dart:convert';
import 'dart:math' as math;
import 'dart:typed_data';

/// Runtime inference core for PhishGuardVN Student MLP int8 v1.
///
/// This class intentionally accepts already-canonicalized Student text.
/// URL validation/canonicalization and asset loading live in separate layers.
class StudentMlpV1 {
  StudentMlpV1._({
    required this.modelVersion,
    required this.threshold,
    required this.terms,
    required this.idf,
    required this.weights,
    required this.hiddenScales,
    required this.hiddenBias,
    required this.outputWeight,
    required this.outputBias,
  }) : _termIndex = <String, int>{
          for (var i = 0; i < terms.length; i++) terms[i]: i,
        };

  static const schema = 'android-student-char-tfidf-mlp-int8-v1';
  static const expectedModelVersion = 'student-mlp-kd-int8-v1';
  static const expectedDecisionRule = 'score >= threshold';
  static const expectedWeightLayout = 'row_major_term_then_hidden';
  static const hiddenUnits = 64;
  static const vocabularySize = 4096;

  final String modelVersion;
  final double threshold;
  final List<String> terms;
  final List<double> idf;
  final Int8List weights;
  final List<double> hiddenScales;
  final List<double> hiddenBias;
  final List<double> outputWeight;
  final double outputBias;
  final Map<String, int> _termIndex;

  factory StudentMlpV1.fromJson(Map<String, dynamic> json) {
    Never fail(String message) => throw FormatException(
          'Student model contract mismatch: $message',
        );

    if (json['schema'] != schema) fail('schema');
    if (json['model_version'] != expectedModelVersion) {
      fail('model_version');
    }
    if (json['decision_rule'] != expectedDecisionRule) {
      fail('decision_rule');
    }
    if (json['weight_layout'] != expectedWeightLayout) {
      fail('weight_layout');
    }
    final range = json['ngram_range'];
    if (range is! List || range.length != 2 || range[0] != 3 || range[1] != 5) {
      fail('ngram_range');
    }
    if (json['hidden_units'] != hiddenUnits) fail('hidden_units');

    final rawTerms = json['terms'];
    if (rawTerms is! List || rawTerms.length != vocabularySize ||
        rawTerms.any((e) => e is! String)) {
      fail('terms must contain exactly $vocabularySize strings');
    }
    final terms = rawTerms.cast<String>();
    final seen = <String>{};
    for (final term in terms) {
      final length = term.runes.length;
      if (length < 3 || length > 5 || !seen.add(term)) {
        fail('invalid or duplicate vocabulary term');
      }
    }

    List<double> numberList(String key, int expectedLength) {
      final raw = json[key];
      if (raw is! List || raw.length != expectedLength) {
        fail('$key length');
      }
      final values = <double>[];
      for (final value in raw) {
        if (value is! num || !value.toDouble().isFinite) {
          fail('$key contains a non-finite/non-numeric value');
        }
        values.add(value.toDouble());
      }
      return values;
    }

    final idf = numberList('idf', vocabularySize);
    if (idf.any((v) => v <= 0)) fail('idf must be positive');
    final scales = numberList('hidden_scales', hiddenUnits);
    if (scales.any((v) => v <= 0)) fail('hidden_scales must be positive');
    final hiddenBias = numberList('hidden_bias', hiddenUnits);
    final outputWeight = numberList('output_weight', hiddenUnits);

    final rawThreshold = json['threshold'];
    final rawOutputBias = json['output_bias'];
    if (rawThreshold is! num ||
        !rawThreshold.toDouble().isFinite ||
        rawThreshold < 0 ||
        rawThreshold > 1) {
      fail('threshold');
    }
    if (rawOutputBias is! num || !rawOutputBias.toDouble().isFinite) {
      fail('output_bias');
    }

    final encoded = json['weights_int8_base64'];
    if (encoded is! String) fail('weights_int8_base64');
    final Uint8List decoded;
    try {
      decoded = base64.decode(encoded);
    } on FormatException {
      fail('weights_int8_base64 is invalid base64');
    }
    const expectedBytes = vocabularySize * hiddenUnits;
    if (decoded.length != expectedBytes) {
      fail('weights byte length ${decoded.length}, expected $expectedBytes');
    }
    final signed = Int8List(decoded.length);
    for (var i = 0; i < decoded.length; i++) {
      signed[i] = decoded[i] >= 128 ? decoded[i] - 256 : decoded[i];
    }

    return StudentMlpV1._(
      modelVersion: expectedModelVersion,
      threshold: rawThreshold.toDouble(),
      terms: List<String>.unmodifiable(terms),
      idf: List<double>.unmodifiable(idf),
      weights: signed,
      hiddenScales: List<double>.unmodifiable(scales),
      hiddenBias: List<double>.unmodifiable(hiddenBias),
      outputWeight: List<double>.unmodifiable(outputWeight),
      outputBias: rawOutputBias.toDouble(),
    );
  }

  /// Score a canonical Student text string. The caller must apply Python's
  /// student_text(url) contract before calling this method.
  double scoreCanonicalText(String text) {
    final codePoints = text.runes.toList(growable: false);
    final counts = <int, int>{};

    for (var n = 3; n <= 5; n++) {
      for (var start = 0; start + n <= codePoints.length; start++) {
        final gram = String.fromCharCodes(codePoints.sublist(start, start + n));
        final index = _termIndex[gram];
        if (index != null) counts.update(index, (v) => v + 1, ifAbsent: () => 1);
      }
    }

    // Match Python's sorted vocabulary-index order before the dense int8 dot.
    final indices = counts.keys.toList()..sort();
    final weighted = <double>[];
    var normSquared = 0.0;
    for (final index in indices) {
      final value = (1.0 + math.log(counts[index]!.toDouble())) * idf[index];
      weighted.add(value);
      normSquared += value * value;
    }

    final norm = math.sqrt(normSquared);
    final hidden = List<double>.filled(hiddenUnits, 0.0);

    if (indices.isNotEmpty && norm > 0) {
      for (var j = 0; j < hiddenUnits; j++) {
        var dot = 0.0;
        for (var k = 0; k < indices.length; k++) {
          final weight = weights[indices[k] * hiddenUnits + j];
          dot += weighted[k] * weight;
        }
        final activation = (dot / norm) * hiddenScales[j] + hiddenBias[j];
        hidden[j] = activation > 0 ? activation : 0.0;
      }
    } else {
      for (var j = 0; j < hiddenUnits; j++) {
        hidden[j] = hiddenBias[j] > 0 ? hiddenBias[j] : 0.0;
      }
    }

    var logit = outputBias;
    for (var j = 0; j < hiddenUnits; j++) {
      logit += hidden[j] * outputWeight[j];
    }

    // Numerically stable sigmoid.
    if (logit >= 0) {
      final z = math.exp(-logit);
      return 1.0 / (1.0 + z);
    }
    final z = math.exp(logit);
    return z / (1.0 + z);
  }

  Map<String, Object> predictCanonicalText(String text) {
    final score = scoreCanonicalText(text);
    return <String, Object>{
      'model_version': modelVersion,
      'decision_rule': expectedDecisionRule,
      'score_kind': 'uncalibrated_sigmoid',
      'score': score,
      'threshold': threshold,
      'class_id': score >= threshold ? 1 : 0,
    };
  }
}
