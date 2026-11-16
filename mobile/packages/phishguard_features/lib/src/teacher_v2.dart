import 'dart:math' as math;

import 'extractor.dart';
import 'svm.dart';

const String _fullModelSchema = 'teacher-v2-dart-full-v1';
const double _expectedThreshold = 0.6945740700635259;
const String _expectedBundleSha =
    '63199c925b28492765019de84c178bd3f8b935a0031f6c960b5db6c31a57c4f1';
const String _expectedBrandReferenceSha =
    '6d434533e479f0f2e1d2602af72f54a1d15677961540684834536ae5d94fbee6';

const List<String> teacherV2FeatureOrder = [
  'url_len',
  'dom_len',
  'is_ip',
  'subdom_cnt',
  'letter_cnt',
  'digit_cnt',
  'dot_cnt',
  'dash_cnt',
  'under_cnt',
  'slash_cnt',
  'entropy',
  'path_len',
  'brand_in_domain',
  'brand_in_subdomain',
  'brand_in_path',
  'brand_domain_mismatch',
  'brand_typo_score',
  'susp_token_cnt',
  'idna_flag',
  'homoglyph_brand_hit',
];

class _HistNode {
  const _HistNode({
    required this.isLeaf,
    required this.featureIndex,
    required this.threshold,
    required this.left,
    required this.right,
    required this.missingGoToLeft,
    required this.value,
  });

  final bool isLeaf;
  final int featureIndex;
  final double threshold;
  final int left;
  final int right;
  final bool missingGoToLeft;
  final double value;

  factory _HistNode.fromJson(Map<String, dynamic> json) {
    final leaf = json['is_leaf'];
    final rawValue = json['value'];
    if (leaf is! bool || rawValue is! num || !rawValue.toDouble().isFinite) {
      throw const FormatException('Invalid HistGB node value/type');
    }
    if (leaf) {
      if (json.containsKey('left') ||
          json.containsKey('right') ||
          json.containsKey('feature_idx') ||
          json.containsKey('num_threshold')) {
        throw const FormatException(
            'HistGB leaf must not contain child/split fields');
      }
      return _HistNode(
        isLeaf: true,
        featureIndex: -1,
        threshold: 0,
        left: -1,
        right: -1,
        missingGoToLeft: false,
        value: rawValue.toDouble(),
      );
    }

    final feature = json['feature_idx'];
    final rawThreshold = json['num_threshold'];
    final left = json['left'];
    final right = json['right'];
    final missingLeft = json['missing_go_to_left'];
    if (feature is! int ||
        rawThreshold is! num ||
        !rawThreshold.toDouble().isFinite ||
        left is! int ||
        right is! int ||
        missingLeft is! bool) {
      throw const FormatException('Invalid HistGB internal node');
    }
    return _HistNode(
      isLeaf: false,
      featureIndex: feature,
      threshold: rawThreshold.toDouble(),
      left: left,
      right: right,
      missingGoToLeft: missingLeft,
      value: rawValue.toDouble(),
    );
  }
}

/// Offline reconstruction of the frozen Teacher v2 stack.
class TeacherV2OfflineModel {
  TeacherV2OfflineModel._({
    required this.svm,
    required this.histBaseline,
    required List<List<_HistNode>> histTrees,
    required this.scalerMean,
    required this.scalerScale,
    required this.metaCoefficients,
    required this.metaIntercept,
    required this.threshold,
    required this.featureOrder,
  }) : _histTrees = List.unmodifiable(
          histTrees.map((tree) => List<_HistNode>.unmodifiable(tree)),
        );

  final SvmModel svm;
  final double histBaseline;
  final List<List<_HistNode>> _histTrees;
  final List<double> scalerMean;
  final List<double> scalerScale;
  final List<double> metaCoefficients;
  final double metaIntercept;
  final double threshold;
  final List<String> featureOrder;

  /// Public diagnostic that does not leak the private node representation.
  int get histTreeCount => _histTrees.length;

  factory TeacherV2OfflineModel.fromJson({
    required Map<String, dynamic> svmJson,
    required Map<String, dynamic> teacherJson,
  }) {
    if (teacherJson['schema_version'] != _fullModelSchema ||
        teacherJson['model_version'] != 'teacher-stacking-v2' ||
        teacherJson['decision_rule'] != 'score >= threshold') {
      throw const FormatException(
          'Unsupported full Teacher model schema/version');
    }
    _expectStringList(
        teacherJson['members_order'], const ['svm', 'hist'], 'members_order');
    _expectStringList(
        teacherJson['class_order'], const ['0', '1'], 'class_order',
        allowNumbers: true);
    _expectStringList(teacherJson['meta_input_order'], const ['svm', 'hist'],
        'meta_input_order');
    _expectStringList(
        teacherJson['feature_order'], teacherV2FeatureOrder, 'feature_order');

    if (teacherJson['source_bundle_sha256'] != _expectedBundleSha ||
        teacherJson['brand_reference_sha256'] != _expectedBrandReferenceSha) {
      throw const FormatException(
          'Teacher source bundle or brand reference SHA mismatch');
    }
    if (teacherJson['leaf_values_include_shrinkage'] != true) {
      throw const FormatException('Unexpected HistGB leaf-value convention');
    }

    final hist = teacherJson['hist'];
    final meta = teacherJson['meta'];
    if (hist is! Map<String, dynamic> || meta is! Map<String, dynamic>) {
      throw const FormatException('Missing HistGB or Meta LR parameters');
    }
    _expectStringList(
        meta['input_order'], const ['svm', 'hist'], 'meta.input_order');

    final baseline = _finiteNumber(hist['baseline'], 'HistGB baseline');
    final iterations = hist['iterations'];
    final rawTrees = hist['trees'];
    final learningRate = _finiteNumber(hist['learning_rate'], 'learning_rate');
    if (iterations != 300 ||
        rawTrees is! List ||
        rawTrees.length != 300 ||
        learningRate != 0.05) {
      throw const FormatException(
          'HistGB must contain 300 iterations at learning_rate 0.05');
    }

    final trees = <List<_HistNode>>[];
    for (var treeIndex = 0; treeIndex < rawTrees.length; treeIndex++) {
      final rawTree = rawTrees[treeIndex];
      if (rawTree is! List || rawTree.isEmpty) {
        throw FormatException('Invalid HistGB tree $treeIndex');
      }
      final nodes = <_HistNode>[];
      for (final rawNode in rawTree) {
        if (rawNode is! Map<String, dynamic>) {
          throw FormatException('Invalid node in HistGB tree $treeIndex');
        }
        nodes.add(_HistNode.fromJson(rawNode));
      }
      _validateTree(nodes, treeIndex);
      trees.add(nodes);
    }

    final mean = _numbers(meta['scaler_mean'], 'scaler_mean');
    final scale = _numbers(meta['scaler_scale'], 'scaler_scale');
    final coefficients = _numbers(meta['coefficients'], 'meta coefficients');
    final intercept = _finiteNumber(meta['intercept'], 'meta intercept');
    final threshold = _finiteNumber(teacherJson['threshold'], 'threshold');
    if (mean.length != 2 ||
        scale.length != 2 ||
        coefficients.length != 2 ||
        scale.any((v) => v == 0)) {
      throw const FormatException(
          'Invalid Meta LR scaler/coefficient dimensions');
    }
    if (threshold != _expectedThreshold) {
      throw const FormatException(
          'Teacher threshold differs from the frozen threshold');
    }

    return TeacherV2OfflineModel._(
      svm: SvmModel.fromJson(svmJson),
      histBaseline: baseline,
      histTrees: trees,
      scalerMean: List.unmodifiable(mean),
      scalerScale: List.unmodifiable(scale),
      metaCoefficients: List.unmodifiable(coefficients),
      metaIntercept: intercept,
      threshold: threshold,
      featureOrder: List.unmodifiable(teacherV2FeatureOrder),
    );
  }

  static void _expectStringList(
    dynamic actual,
    List<String> expected,
    String name, {
    bool allowNumbers = false,
  }) {
    if (actual is! List || actual.length != expected.length) {
      throw FormatException('Invalid $name');
    }
    for (var i = 0; i < expected.length; i++) {
      final value = actual[i];
      final normalized =
          allowNumbers && value is num ? value.toString() : value;
      if (normalized != expected[i]) {
        throw FormatException('Unexpected $name at index $i');
      }
    }
  }

  static double _finiteNumber(dynamic value, String name) {
    if (value is! num || !value.toDouble().isFinite) {
      throw FormatException('Invalid $name');
    }
    return value.toDouble();
  }

  static List<double> _numbers(dynamic raw, String name) {
    if (raw is! List) throw FormatException('Missing $name');
    return raw
        .map((value) => _finiteNumber(value, name))
        .toList(growable: false);
  }

  static void _validateTree(List<_HistNode> nodes, int treeIndex) {
    final count = nodes.length;
    for (var i = 0; i < count; i++) {
      final node = nodes[i];
      if (node.isLeaf) continue;
      if (node.featureIndex < 0 ||
          node.featureIndex >= 20 ||
          node.left < 0 ||
          node.left >= count ||
          node.right < 0 ||
          node.right >= count ||
          node.left == node.right ||
          node.left == i ||
          node.right == i) {
        throw FormatException(
            'Invalid split links in HistGB tree $treeIndex node $i');
      }
    }

    // Iterative DFS validates acyclicity and that every serialized node is reachable.
    final parentCounts = List<int>.filled(count, 0);
    for (final node in nodes) {
      if (!node.isLeaf) {
        parentCounts[node.left]++;
        parentCounts[node.right]++;
      }
    }
    if (parentCounts[0] != 0 ||
        parentCounts.skip(1).any((parents) => parents != 1)) {
      throw FormatException(
          'HistGB tree $treeIndex is not a single rooted tree');
    }

    final state = List<int>.filled(count, 0);
    final stack = <(int, bool)>[(0, false)];
    while (stack.isNotEmpty) {
      final (index, exiting) = stack.removeLast();
      if (exiting) {
        state[index] = 2;
        continue;
      }
      if (state[index] == 1) {
        throw FormatException('Cycle in HistGB tree $treeIndex');
      }
      if (state[index] == 2) continue;
      state[index] = 1;
      stack.add((index, true));
      final node = nodes[index];
      if (!node.isLeaf) {
        if (state[node.right] == 1 || state[node.left] == 1) {
          throw FormatException('Cycle in HistGB tree $treeIndex');
        }
        stack.add((node.right, false));
        stack.add((node.left, false));
      }
    }
    if (state.any((value) => value != 2)) {
      throw FormatException('Unreachable node in HistGB tree $treeIndex');
    }
  }

  /// Raw HistGB decision score. Exported leaf values already include shrinkage.
  double histRawScore(List<double> e2Features) {
    if (e2Features.length != 20) {
      throw ArgumentError.value(
          e2Features.length, 'e2Features.length', 'must be 20');
    }
    for (final value in e2Features) {
      if (value.isInfinite)
        throw ArgumentError('E2 feature cannot be infinite');
    }
    var raw = histBaseline;
    for (final tree in _histTrees) {
      var nodeIndex = 0;
      while (true) {
        final node = tree[nodeIndex];
        if (node.isLeaf) {
          raw += node.value;
          break;
        }
        final value = e2Features[node.featureIndex];
        final goLeft =
            value.isNaN ? node.missingGoToLeft : value <= node.threshold;
        nodeIndex = goLeft ? node.left : node.right;
      }
    }
    return raw;
  }

  double histProbability(List<double> e2Features) =>
      _sigmoid(histRawScore(e2Features));

  /// Raw LogisticRegression decision function (logit).
  double metaRawScore(double svmMargin, double histProbability) {
    if (!svmMargin.isFinite || !histProbability.isFinite) {
      throw ArgumentError('Meta inputs must be finite');
    }
    final svmScaled = (svmMargin - scalerMean[0]) / scalerScale[0];
    final histScaled = (histProbability - scalerMean[1]) / scalerScale[1];
    return svmScaled * metaCoefficients[0] +
        histScaled * metaCoefficients[1] +
        metaIntercept;
  }

  /// Final uncalibrated meta-LR probability-like score, not a safety percentage.
  double metaScore(double svmMargin, double histProbability) =>
      _sigmoid(metaRawScore(svmMargin, histProbability));

  int classifyScore(double score) {
    if (!score.isFinite)
      throw ArgumentError.value(score, 'score', 'must be finite');
    return score >= threshold ? 1 : 0;
  }

  TeacherV2Prediction predict(String url, E2Extractor extractor) {
    final extracted = extractor.extract(url);
    final features = extracted.vector;
    if (features == null) {
      return TeacherV2Prediction.unclassifiable(extracted.errorReason);
    }
    final margin = svm.predictMargin(url);
    final histRaw = histRawScore(features);
    final histScore = _sigmoid(histRaw);
    final rawMeta = metaRawScore(margin, histScore);
    final finalScore = _sigmoid(rawMeta);
    final classId = classifyScore(finalScore);
    return TeacherV2Prediction(
      classifiable: true,
      errorReason: null,
      svmMargin: margin,
      histRawScore: histRaw,
      histProbability: histScore,
      metaRawScore: rawMeta,
      finalScore: finalScore,
      classId: classId,
      threshold: threshold,
    );
  }
}

class TeacherV2Prediction {
  const TeacherV2Prediction({
    required this.classifiable,
    required this.errorReason,
    this.svmMargin,
    this.histRawScore,
    this.histProbability,
    this.metaRawScore,
    this.finalScore,
    this.classId,
    this.threshold,
  });

  const TeacherV2Prediction.unclassifiable(String? reason)
      : this(classifiable: false, errorReason: reason);

  final bool classifiable;
  final String? errorReason;
  final double? svmMargin;
  final double? histRawScore;
  final double? histProbability;
  final double? metaRawScore;
  final double? finalScore;
  final int? classId;
  final double? threshold;

  String? get label => classId == null
      ? null
      : classId == 1
          ? 'phishing'
          : 'benign';
}

double _sigmoid(double value) {
  if (value >= 0) return 1.0 / (1.0 + math.exp(-value));
  final expValue = math.exp(value);
  return expValue / (1.0 + expValue);
}
