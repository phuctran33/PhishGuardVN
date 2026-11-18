import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:student_android_qa/student_adapter.dart';
import 'package:student_android_qa/parity.dart';

class _NoHttp extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) =>
      throw StateError('Student QA attempted HTTP');
}

void main() {
  late Map<String, Uint8List> files;
  late Map<String, dynamic> lock, features, model, reference;
  final modes = <Map<String, dynamic>>[];
  Map<String, dynamic> copy(Map<String, dynamic> value) =>
      jsonDecode(jsonEncode(value)) as Map<String, dynamic>;
  setUpAll(() {
    files = {
      for (final file in Directory('assets').listSync().whereType<File>())
        file.uri.pathSegments.last: file.readAsBytesSync()
    };
    lock = jsonDecode(utf8.decode(files['student_lock.json']!))
        as Map<String, dynamic>;
    features = jsonDecode(utf8.decode(files['features.json']!))
        as Map<String, dynamic>;
    model = jsonDecode(utf8.decode(files['kd_mixed.json']!))
        as Map<String, dynamic>;
    reference = jsonDecode(utf8.decode(files['live_python_reference.json']!))
        as Map<String, dynamic>;
  });
  Future<LoadedStudent> load(
          {Map<String, Uint8List>? assets,
          Map<String, dynamic>? policy,
          String mode = 'kd_mixed'}) =>
      loadStudent((name) async {
        final value = (assets ?? files)[name];
        if (value == null) throw StateError('missing_asset:$name');
        return value;
      }, policy ?? lock, mode: mode);

  test('decision boundary includes equality and rejects non-finite scores', () {
    const threshold = 0.6204500086017339;
    expect(studentClass(threshold, threshold), 1);
    expect(studentClass(threshold - 1e-12, threshold), 0);
    expect(studentClass(threshold + 1e-12, threshold), 1);
    expect(() => studentClass(double.nan, threshold), throwsFormatException);
  });

  for (final mode in ['kd_mixed', 'hard_only']) {
    test('$mode: live Python feature and prediction parity, HTTP guarded',
        () async {
      await HttpOverrides.runZoned(() async {
        final loaded = await load(mode: mode);
        final result = verifyStudentParity(loaded, reference);
        expect(result['classified'], 55);
        expect(result['rejected'], 9);
        modes.add(result);
      }, createHttpClient: _NoHttp().createHttpClient);
    });
  }
  for (final name in [
    'manifest.json',
    'features.json',
    'kd_mixed.json',
    'brand_reference_v1.csv',
    'psl_icann_tldextract_5.4.0.txt'
  ]) {
    test('loader rejects missing $name', () async {
      final broken = Map<String, Uint8List>.from(files)..remove(name);
      await expectLater(
          load(assets: broken), throwsA(isA<StudentLoadException>()));
    });
    test('loader rejects changed size $name', () async {
      final broken = Map<String, Uint8List>.from(files);
      broken[name] = Uint8List.fromList([...files[name]!, 32]);
      await expectLater(
          load(assets: broken),
          throwsA(isA<StudentLoadException>()
              .having((e) => e.reason, 'reason', contains('size_mismatch'))));
    });
    test('loader rejects same-size tampering $name', () async {
      final broken = Map<String, Uint8List>.from(files);
      final bytes = Uint8List.fromList(files[name]!);
      bytes[0] ^= 1;
      broken[name] = bytes;
      await expectLater(
          load(assets: broken),
          throwsA(isA<StudentLoadException>()
              .having((e) => e.reason, 'reason', contains('sha256_mismatch'))));
    });
  }
  for (final field in [
    'selected_mode',
    'student_default',
    'threshold',
    'invalid_json'
  ]) {
    test('loader rejects manifest $field even with refreshed test hash',
        () async {
      final manifest = jsonDecode(utf8.decode(files['manifest.json']!))
          as Map<String, dynamic>;
      if (field == 'selected_mode') manifest['selected_mode'] = 'hard_only';
      if (field == 'student_default') manifest['student_default'] = true;
      if (field == 'threshold')
        manifest['models']['kd_mixed']['threshold'] = 0.5;
      final bytes = Uint8List.fromList(
          utf8.encode(field == 'invalid_json' ? '{' : jsonEncode(manifest)));
      final testLock = copy(lock);
      testLock['files']['manifest.json'] = {
        'size_bytes': bytes.length,
        'sha256': sha256.convert(bytes).toString()
      };
      await expectLater(
          load(assets: {...files, 'manifest.json': bytes}, policy: testLock),
          throwsA(isA<StudentLoadException>()));
    });
  }
  final badFeatures = <String, void Function(Map<String, dynamic>)>{
    'schema': (f) => f['schema'] = 'other',
    'feature order': (f) => (f['feature_order'] as List)[0] = 'wrong',
    'IDF length': (f) => (f['idf'] as List).removeLast(),
    'IDF positive': (f) => (f['idf'] as List)[0] = -1,
    'IDF finite': (f) => (f['idf'] as List)[0] = double.nan,
    'duplicate term': (f) => (f['terms'] as List)[1] = f['terms'][0],
    'ngram config': (f) => f['ngram_range'] = [2, 5],
    'lowercase config': (f) => f['lowercase'] = true,
    'normalization': (f) => f['normalization'] = 'other',
  };
  for (final mutation in badFeatures.entries) {
    test('model rejects ${mutation.key}', () {
      final f = copy(features);
      mutation.value(f);
      expect(() => StudentModel.fromJson(f, model), throwsFormatException);
    });
  }
  final badModels = <String, void Function(Map<String, dynamic>)>{
    'schema': (m) => m['schema'] = 'other',
    'mode': (m) => m['mode'] = 'other',
    'threshold': (m) => m['threshold'] = 0.5,
    'tree count': (m) => (m['trees'] as List).removeLast(),
    'shrinkage contract': (m) =>
        m['leaf_values_include_shrinkage_and_initial_score'] = false,
    'decision rule': (m) => m['decision_rule'] = 'score > threshold',
    'calibration': (m) => m['calibrated'] = true,
    'feature index': (m) => m['trees'][0][0]['feature'] = 8212,
    'child index': (m) => m['trees'][0][0]['left'] = -1,
    'cycle': (m) => m['trees'][0][0]['left'] = 0,
    'node value': (m) => m['trees'][0][0]['threshold'] = double.infinity,
    'leaf flag': (m) => m['trees'][0][0]['leaf'] = 'false',
  };
  for (final mutation in badModels.entries) {
    test('model rejects ${mutation.key}', () {
      final m = copy(model);
      mutation.value(m);
      expect(() => StudentModel.fromJson(features, m), throwsFormatException);
    });
  }
  test(
      'tree evaluator handles <= equality, missing zero and leaf shrinkage once',
      () {
    final tree = StudentTree([
      {
        'leaf': false,
        'feature': 0,
        'threshold': 0.5,
        'left': 1,
        'right': 2,
        'default_left': false,
        'missing_type': 'Zero'
      },
      {'leaf': true, 'value': 0.25},
      {'leaf': true, 'value': -0.75},
    ], 1);
    expect(tree.evaluate({0: 0.5}), 0.25);
    expect(tree.evaluate({0: 0.50001}), -0.75);
    expect(tree.evaluate({}), -0.75);
    expect(tree.evaluate({0: double.nan}), -0.75);
  });
  tearDownAll(() {
    const output = String.fromEnvironment('QA_STUDENT_OUTPUT');
    if (output.isNotEmpty && modes.length == 2) {
      final report = {
        'schema': 'qa-student-dart-parity-v1',
        'scope': 'laptop_flutter_test',
        'android_runtime_executed': false,
        'student_revision': reference['student_revision'],
        'runtime': Platform.version,
        'platform': Platform.operatingSystem,
        'network_scope': 'Dart HttpClient guarded; OS network not disabled',
        'modes': modes
      };
      File(output).writeAsStringSync(
          '${const JsonEncoder.withIndent('  ').convert(report)}\n');
    }
  });
}
