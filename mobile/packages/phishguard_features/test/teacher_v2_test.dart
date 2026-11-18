import 'dart:convert';
import 'dart:io';

import 'package:phishguard_features/io.dart';
import 'package:phishguard_features/phishguard_features.dart';
import 'package:test/test.dart';

Map<String, dynamic> _readJson(File file) =>
    jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;

void main() {
  final repoRoot = Directory('../../../').absolute;
  final artifactDir = Directory(
    '${repoRoot.path}/artifacts/teacher_v2_android',
  );
  final svmFile = File('${artifactDir.path}/dart_svm_model.json');
  final fullFile = File('${artifactDir.path}/dart_teacher_v2_model.json');
  final fixtureFile = File(
    '${Directory.current.path}/test/fixtures/teacher_v2_pipeline_reference.json',
  );

  test('official full Teacher pipeline parity (required release gate)', () {
    expect(svmFile.existsSync(), isTrue,
        reason:
            'Run the official CPython 3.11 exporter first: ${svmFile.path}');
    expect(fullFile.existsSync(), isTrue,
        reason: 'Missing full Teacher artifact: ${fullFile.path}');
    expect(fixtureFile.existsSync(), isTrue,
        reason: 'Missing official Python golden fixture: ${fixtureFile.path}');

    final model = TeacherV2OfflineModel.fromJson(
      svmJson: _readJson(svmFile),
      teacherJson: _readJson(fullFile),
    );
    final fixture = _readJson(fixtureFile);
    expect(fixture['schema_version'], 'teacher-v2-full-reference-v1');
    final cases = (fixture['cases'] as List).cast<Map<String, dynamic>>();
    expect(cases, isNotEmpty);

    final extractor = loadExtractorFromRepo(repoRoot.path);
    var svmPass = 0;
    var histRawPass = 0;
    var histProbabilityPass = 0;
    var metaRawPass = 0;
    var metaProbabilityPass = 0;
    var classPass = 0;
    var maxErrors = <String, double>{
      'svm': 0,
      'hist_raw': 0,
      'hist_probability': 0,
      'meta_raw': 0,
      'meta_probability': 0,
      'e2': 0,
    };
    final failures = <String>[];

    for (final item in cases) {
      final name = item['name'] as String;
      final url = item['url'] as String;
      final extracted = extractor.extract(url);
      if (extracted.vector == null) {
        failures.add('$name: Dart extractor rejected Python-valid fixture URL');
        continue;
      }
      final pythonE2 = (item['e2'] as List)
          .map((value) => (value as num).toDouble())
          .toList(growable: false);
      final dartE2 = extracted.vector!;
      if (dartE2.length != pythonE2.length) {
        failures.add('$name: E2 vector length mismatch');
        continue;
      }
      var e2Error = 0.0;
      for (var i = 0; i < pythonE2.length; i++) {
        final error = (dartE2[i] - pythonE2[i]).abs();
        if (error > e2Error) e2Error = error;
      }
      if (e2Error > 1e-6) failures.add('$name: E2 vector mismatch ($e2Error)');
      if (e2Error > maxErrors['e2']!) maxErrors['e2'] = e2Error;

      final svm = model.svm.predictMargin(url);
      final histRaw = model.histRawScore(dartE2);
      final histProbability = model.histProbability(dartE2);
      final metaRaw = model.metaRawScore(svm, histProbability);
      final metaProbability = model.metaScore(svm, histProbability);
      final prediction = model.predict(url, extractor);

      final expected = <String, double>{
        'svm': (item['svm_margin'] as num).toDouble(),
        'hist_raw': (item['hist_raw_score'] as num).toDouble(),
        'hist_probability': (item['hist_probability'] as num).toDouble(),
        'meta_raw': (item['meta_raw_score'] as num).toDouble(),
        'meta_probability': (item['meta_probability'] as num).toDouble(),
      };
      final actual = <String, double>{
        'svm': svm,
        'hist_raw': histRaw,
        'hist_probability': histProbability,
        'meta_raw': metaRaw,
        'meta_probability': metaProbability,
      };
      for (final key in expected.keys) {
        final error = (actual[key]! - expected[key]!).abs();
        if (error > maxErrors[key]!) maxErrors[key] = error;
        if (error > 1e-6) failures.add('$name: $key mismatch ($error)');
      }
      if ((svm - expected['svm']!).abs() <= 1e-6) svmPass++;
      if ((histRaw - expected['hist_raw']!).abs() <= 1e-6) histRawPass++;
      if ((histProbability - expected['hist_probability']!).abs() <= 1e-6) {
        histProbabilityPass++;
      }
      if ((metaRaw - expected['meta_raw']!).abs() <= 1e-6) metaRawPass++;
      if ((metaProbability - expected['meta_probability']!).abs() <= 1e-6) {
        metaProbabilityPass++;
      }

      final expectedScore = (item['final_score'] as num).toDouble();
      final expectedClass = item['class_id'] as int;
      final expectedLabel = item['label'] as String;
      if (prediction.finalScore == null ||
          (prediction.finalScore! - expectedScore).abs() > 1e-6 ||
          prediction.classId != expectedClass ||
          prediction.label != expectedLabel) {
        failures.add('$name: final prediction mismatch');
      } else {
        classPass++;
      }
    }

    // ignore: avoid_print
    print('Teacher full parity n=${cases.length}; '
        'SVM=$svmPass HistRaw=$histRawPass HistProb=$histProbabilityPass '
        'MetaRaw=$metaRawPass MetaProb=$metaProbabilityPass '
        'Final=$classPass maxErrors=$maxErrors failures=$failures');

    expect(failures, isEmpty);
    expect(svmPass, cases.length);
    expect(histRawPass, cases.length);
    expect(histProbabilityPass, cases.length);
    expect(metaRawPass, cases.length);
    expect(metaProbabilityPass, cases.length);
    expect(classPass, cases.length);
  });

  test('frozen E2 feature order and HistGB tree count', () {
    expect(svmFile.existsSync(), isTrue);
    expect(fullFile.existsSync(), isTrue);
    final model = TeacherV2OfflineModel.fromJson(
      svmJson: _readJson(svmFile),
      teacherJson: _readJson(fullFile),
    );
    expect(model.featureOrder, teacherV2FeatureOrder);
    expect(model.histTreeCount, 300);
  });

  test('actual model classifier uses inclusive frozen threshold', () {
    expect(svmFile.existsSync(), isTrue);
    expect(fullFile.existsSync(), isTrue);
    final model = TeacherV2OfflineModel.fromJson(
      svmJson: _readJson(svmFile),
      teacherJson: _readJson(fullFile),
    );
    expect(model.classifyScore(model.threshold - 1e-12), 0);
    expect(model.classifyScore(model.threshold), 1);
    expect(model.classifyScore(model.threshold + 1e-12), 1);
  });

  test('Teacher loader rejects corrupted schema, feature order and threshold',
      () {
    final svm = _readJson(svmFile);
    final original = _readJson(fullFile);

    void expectRejected(void Function(Map<String, dynamic>) corrupt) {
      final broken = jsonDecode(jsonEncode(original)) as Map<String, dynamic>;
      corrupt(broken);
      expect(
        () => TeacherV2OfflineModel.fromJson(
          svmJson: svm,
          teacherJson: broken,
        ),
        throwsA(isA<FormatException>()),
      );
    }

    expectRejected((json) {
      json['schema_version'] = 'unknown-schema';
    });

    expectRejected((json) {
      final order = List<dynamic>.from(json['feature_order'] as List);
      order[0] = 'tampered_feature';
      json['feature_order'] = order;
    });

    expectRejected((json) {
      json['threshold'] = 0.5;
    });

    expectRejected((json) {
      json['source_bundle_sha256'] = '0' * 64;
    });
  });

  test('Teacher loader rejects malformed HistGB tree links', () {
    final svm = _readJson(svmFile);
    final broken = _readJson(fullFile);
    final hist = broken['hist'] as Map<String, dynamic>;
    final trees = hist['trees'] as List;
    final firstTree = trees.first as List;

    final internalIndex = firstTree.indexWhere(
      (node) => (node as Map<String, dynamic>)['is_leaf'] == false,
    );
    expect(internalIndex, greaterThanOrEqualTo(0));

    final internalNode = firstTree[internalIndex] as Map<String, dynamic>;
    internalNode['left'] = internalIndex;

    expect(
      () => TeacherV2OfflineModel.fromJson(
        svmJson: svm,
        teacherJson: broken,
      ),
      throwsA(isA<FormatException>()),
    );
  });
}
