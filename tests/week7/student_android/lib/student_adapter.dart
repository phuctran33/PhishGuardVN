// K7.4: adapter inference thử nghiệm, không thay engine Teacher của ứng dụng.
import 'dart:convert';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:phishguard_features/phishguard_features.dart';

int studentClass(double score, double threshold) {
  if (!score.isFinite ||
      score < 0 ||
      score > 1 ||
      !threshold.isFinite ||
      threshold < 0 ||
      threshold > 1) {
    throw const FormatException('Invalid score/threshold');
  }
  return score >= threshold ? 1 : 0;
}

class StudentInputException implements Exception {
  const StudentInputException(this.reason);
  final String reason;
  @override
  String toString() => 'StudentInputException: $reason';
}

class StudentLoadException implements Exception {
  const StudentLoadException(this.reason);
  final String reason;
  @override
  String toString() => 'StudentLoadException: $reason';
}

bool _space(int c) =>
    (c >= 9 && c <= 13) ||
    (c >= 28 && c <= 32) ||
    c == 0x85 ||
    c == 0xa0 ||
    c == 0x1680 ||
    (c >= 0x2000 && c <= 0x200a) ||
    c == 0x2028 ||
    c == 0x2029 ||
    c == 0x202f ||
    c == 0x205f ||
    c == 0x3000;

double _number(Object? value) {
  if (value is! num || !value.toDouble().isFinite) {
    throw const FormatException('Expected finite number');
  }
  return value.toDouble();
}

void _equal(Object? value, Object? expected, String field) {
  if (jsonEncode(value) != jsonEncode(expected)) {
    throw FormatException('Student contract mismatch: $field');
  }
}

class StudentTree {
  StudentTree(List<dynamic> nodes, int dimensions)
      : nodes = nodes.map((n) => Map<String, dynamic>.from(n as Map)).toList() {
    if (nodes.isEmpty) throw const FormatException('Empty tree');
    final visited = <int>{};
    final active = <int>{};
    void visit(int index) {
      if (index < 0 || index >= nodes.length || active.contains(index)) {
        throw const FormatException('Invalid child index/cyclic tree');
      }
      if (visited.contains(index)) {
        throw const FormatException('Shared child in tree');
      }
      active.add(index);
      visited.add(index);
      final node = this.nodes[index];
      if (node['leaf'] == true) {
        _number(node['value']);
      } else if (node['leaf'] == false) {
        final feature = node['feature'];
        if (feature is! int ||
            feature < 0 ||
            feature >= dimensions ||
            node['left'] is! int ||
            node['right'] is! int ||
            node['default_left'] is! bool ||
            !['None', 'NaN', 'Zero'].contains(node['missing_type'])) {
          throw const FormatException('Invalid split node');
        }
        _number(node['threshold']);
        visit(node['left'] as int);
        visit(node['right'] as int);
      } else {
        throw const FormatException('Invalid leaf flag');
      }
      active.remove(index);
    }

    visit(0);
    if (visited.length != nodes.length) {
      throw const FormatException('Unreachable tree node');
    }
  }
  final List<Map<String, dynamic>> nodes;

  double evaluate(Map<int, double> row) {
    var index = 0;
    for (var step = 0; step < nodes.length; step++) {
      final node = nodes[index];
      if (node['leaf'] == true) return _number(node['value']);
      final value = row[node['feature']] ?? 0.0;
      final missing =
          value.isNaN || (node['missing_type'] == 'Zero' && value == 0);
      final left = missing
          ? node['default_left'] as bool
          : value <= _number(node['threshold']);
      index = node[left ? 'left' : 'right'] as int;
    }
    throw const FormatException('Invalid cyclic tree');
  }
}

class StudentVector {
  StudentVector(this.text, this.e2, this.row);
  final String text;
  final List<double> e2;
  final Map<int, double> row;
}

class StudentModel {
  StudentModel.fromJson(
      Map<String, dynamic> features, Map<String, dynamic> model)
      : mode = model['mode'] as String,
        threshold = _number(model['threshold']),
        version = model['model_version'] as String {
    const thresholds = {
      'kd_mixed': 0.6204500086017339,
      'hard_only': 0.6157178977907972
    };
    if (!thresholds.containsKey(mode))
      throw const FormatException('Invalid mode');
    for (final entry in <String, Object>{
      'schema': 'hybrid-lightgbm-student-v1',
      'objective': 'cross_entropy',
      'leaf_values_include_shrinkage_and_initial_score': true,
      'sigmoid': 1.0,
      'release_status': 'experimental',
      'calibrated': false,
      'decision_rule': 'score >= threshold',
      'class_mapping': {'benign': 0, 'phishing': 1},
      'python_runtime': 'CPython 3.11',
      'numpy_version': '2.4.6',
      'idna_version': '3.20',
      'tldextract_version': '5.4.0',
      'tree_count': 400,
      'model_version': 'lightgbm-student-$mode',
      'threshold': thresholds[mode]!,
    }.entries) {
      _equal(model[entry.key], entry.value, entry.key);
    }
    for (final entry in <String, Object>{
      'schema': 'hybrid-student-features-v1',
      'feature_order': e2FeatureOrder,
      'normalization': 'canonical-reference-v1; whitespace-collapse-v1',
      'ngram_range': [3, 5],
      'sublinear_tf': true,
      'lowercase': false,
      'norm': 'l2',
    }.entries) {
      _equal(features[entry.key], entry.value, entry.key);
    }
    terms = (features['terms'] as List).cast<String>();
    idf = (features['idf'] as List).map(_number).toList();
    if (terms.length != 8192 ||
        terms.toSet().length != terms.length ||
        idf.length != terms.length ||
        idf.any((v) => v <= 0)) {
      throw const FormatException('Invalid vocabulary/IDF dimensions');
    }
    vocabulary = {for (var i = 0; i < terms.length; i++) terms[i]: i};
    trees = (model['trees'] as List)
        .map((t) => StudentTree(t as List, terms.length + 20))
        .toList();
    if (trees.length != 400) throw const FormatException('Invalid tree count');
  }
  final String mode, version;
  final double threshold;
  late final List<String> terms;
  late final List<double> idf;
  late final Map<String, int> vocabulary;
  late final List<StudentTree> trees;

  StudentVector vector(Object? input, E2Extractor extractor) {
    if (input is! String) throw const StudentInputException('not_string');
    final runes = input.runes.toList();
    if (runes.isEmpty || runes.every(_space))
      throw const StudentInputException('blank');
    if (runes.any((c) => c < 32))
      throw const StudentInputException('control_character');
    if (_space(runes.first) || _space(runes.last)) {
      throw const StudentInputException('surrounding_whitespace');
    }
    final extraction = extractor.extract(input);
    if (!extraction.isClassifiable) {
      throw StudentInputException(extraction.errorReason ?? 'invalid_url');
    }
    final e2 = extraction.vector!;
    if (e2.length != 20 || e2.any((v) => !v.isFinite)) {
      throw const FormatException('Invalid E2 output');
    }
    final text = normalizeSklearnCharWhitespace(canonicalizeTeacherUrl(input));
    final characters =
        text.runes.toList(); // Python slices Unicode code points.
    final counts = <int, int>{};
    for (var n = 3; n <= 5; n++) {
      for (var i = 0; i <= characters.length - n; i++) {
        final index =
            vocabulary[String.fromCharCodes(characters.sublist(i, i + n))];
        if (index != null) counts[index] = (counts[index] ?? 0) + 1;
      }
    }
    final row = <int, double>{};
    var normSquared = 0.0;
    for (final index in counts.keys.toList()..sort()) {
      final weight = (1 + math.log(counts[index]!)) * idf[index];
      row[index] = weight;
      normSquared += weight * weight;
    }
    if (row.isNotEmpty) {
      final norm = math.sqrt(normSquared);
      for (final index in row.keys.toList()) {
        row[index] = row[index]! / norm;
      }
    }
    for (var i = 0; i < e2.length; i++) {
      row[terms.length + i] = e2[i];
    }
    return StudentVector(text, e2, row);
  }

  Map<String, dynamic> predict(Object? url, E2Extractor extractor) {
    final values = vector(url, extractor);
    final margin =
        trees.fold<double>(0, (sum, tree) => sum + tree.evaluate(values.row));
    final exp = math.exp(margin >= 0 ? -margin : margin);
    final score = margin >= 0 ? 1 / (1 + exp) : exp / (1 + exp);
    final classId = studentClass(score, threshold);
    return {
      'score': score,
      'label': classId == 1 ? 'phishing' : 'benign',
      'class_id': classId,
      'threshold': threshold,
      'model_version': version,
      'mode': mode,
      'decision_rule': 'score >= threshold',
      'score_kind': 'uncalibrated_sigmoid',
      'calibrated': false,
      'release_status': 'experimental'
    };
  }
}

class LoadedStudent {
  LoadedStudent(this.model, this.extractor);
  final StudentModel model;
  final E2Extractor extractor;
}

typedef StudentAssetReader = Future<Uint8List> Function(String name);

Future<LoadedStudent> loadStudent(
    StudentAssetReader read, Map<String, dynamic> trustedLock,
    {String mode = 'kd_mixed'}) async {
  try {
    if (!['kd_mixed', 'hard_only'].contains(mode))
      throw const FormatException('Invalid mode');
    Future<Uint8List> checked(String name) async {
      final spec = trustedLock['files'][name] as Map;
      final bytes = await read(name);
      if (bytes.length != spec['size_bytes'])
        throw FormatException('size_mismatch:$name');
      if (sha256.convert(bytes).toString() != spec['sha256']) {
        throw FormatException('sha256_mismatch:$name');
      }
      return bytes;
    }

    final manifest =
        jsonDecode(utf8.decode(await checked('manifest.json'))) as Map;
    _equal(manifest['selected_mode'], 'kd_mixed', 'selected_mode');
    _equal(manifest['student_default'], false, 'student_default');
    _equal(manifest['teacher_retrained'], false, 'teacher_retrained');
    final spec = manifest['models'][mode] as Map;
    final modelName = '$mode.json';
    _equal(spec['json'], modelName, 'model_file');
    _equal(spec['seed'], 42, 'seed');
    _equal(spec['tree_count'], 400, 'tree_count');
    _equal(spec['json_sha256'], trustedLock['files'][modelName]['sha256'],
        'model_hash');
    final features = jsonDecode(utf8.decode(await checked('features.json')))
        as Map<String, dynamic>;
    final model = jsonDecode(utf8.decode(await checked(modelName)))
        as Map<String, dynamic>;
    _equal(spec['threshold'], model['threshold'], 'manifest_threshold');
    final reference = await checked('brand_reference_v1.csv');
    final psl = await checked('psl_icann_tldextract_5.4.0.txt');
    return LoadedStudent(
        StudentModel.fromJson(features, model),
        E2Extractor(PublicSuffixList.fromText(utf8.decode(psl)),
            BrandReference.fromBytes(reference)));
  } on StudentLoadException {
    rethrow;
  } catch (error) {
    throw StudentLoadException(error.toString());
  }
}
