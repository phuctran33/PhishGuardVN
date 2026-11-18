import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:phishguard_features/io.dart';
import 'package:phishguard_features/phishguard_features.dart';

import 'package:phishguard_android/src/teacher_contract.dart';
import 'package:phishguard_android/src/teacher_url_classifier.dart';
import 'package:phishguard_android/src/url_classifier.dart';

Map<String, dynamic> _readJson(File file) {
  return jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
}

void main() {
  final repoRoot = Directory('../..').absolute;

  final artifactDir = Directory(
    '${repoRoot.path}/artifacts/teacher_v2_android',
  );

  final fixtureFile = File(
    '${repoRoot.path}/mobile/packages/phishguard_features/'
    'test/fixtures/teacher_v2_pipeline_reference.json',
  );

  test('TeacherUrlClassifier matches all frozen Python reference cases', () {
    final svmFile = File('${artifactDir.path}/dart_svm_model.json');
    final teacherFile = File(
      '${artifactDir.path}/dart_teacher_v2_model.json',
    );

    expect(svmFile.existsSync(), isTrue,
        reason: 'Missing SVM artifact: ${svmFile.path}');
    expect(teacherFile.existsSync(), isTrue,
        reason: 'Missing Teacher artifact: ${teacherFile.path}');
    expect(fixtureFile.existsSync(), isTrue,
        reason: 'Missing Python reference fixture: ${fixtureFile.path}');

    final model = TeacherV2OfflineModel.fromJson(
      svmJson: _readJson(svmFile),
      teacherJson: _readJson(teacherFile),
    );

    final extractor = loadExtractorFromRepo(repoRoot.path);

    final classifier = TeacherUrlClassifier(
      extractor: extractor,
      model: model,
    );

    final fixture = _readJson(fixtureFile);

    expect(
      fixture['schema_version'],
      'teacher-v2-full-reference-v1',
    );

    final cases = (fixture['cases'] as List).cast<Map<String, dynamic>>();

    expect(cases, isNotEmpty);

    final failures = <String>[];
    var passed = 0;
    var phishingCount = 0;
    var benignCount = 0;

    for (final item in cases) {
      final name = item['name'] as String;
      final url = item['url'] as String;

      final expectedScore = (item['final_score'] as num).toDouble();
      final expectedClass = item['class_id'] as int;
      final expectedLabel = item['label'] as String;

      final outcome = classifier.classify(url);

      if (outcome is! Classified) {
        failures.add(
          '$name: expected Classified, got ${outcome.runtimeType}',
        );
        continue;
      }

      final expectedPhishing = expectedClass == 1;

      final scoreMatches = (outcome.score - expectedScore).abs() <= 1e-6;

      final classificationMatches = outcome.phishing == expectedPhishing;
      final actualLabel = outcome.phishing ? 'phishing' : 'benign';
      final labelMatches = actualLabel == expectedLabel;

      if (!labelMatches) {
        failures.add(
          '$name: label mismatch; '
          'expected=$expectedLabel actual=$actualLabel',
        );
      }

      final versionMatches = outcome.modelVersion == teacherModelVersion;

      final thresholdMatches =
          (outcome.threshold - teacherThreshold).abs() <= 1e-12;

      final decisionRuleMatches = outcome.decisionRule == teacherDecisionRule;

      if (!scoreMatches) {
        failures.add(
          '$name: score mismatch; '
          'expected=$expectedScore actual=${outcome.score}',
        );
      }

      if (!classificationMatches) {
        failures.add(
          '$name: phishing mismatch; '
          'expected=$expectedPhishing actual=${outcome.phishing}',
        );
      }

      if (!versionMatches) {
        failures.add(
          '$name: model version mismatch; '
          'expected=$teacherModelVersion actual=${outcome.modelVersion}',
        );
      }

      if (!thresholdMatches) {
        failures.add(
          '$name: threshold mismatch; '
          'expected=$teacherThreshold actual=${outcome.threshold}',
        );
      }

      if (!decisionRuleMatches) {
        failures.add(
          '$name: decision rule mismatch; '
          'expected=$teacherDecisionRule actual=${outcome.decisionRule}',
        );
      }

      if (scoreMatches &&
          classificationMatches &&
          versionMatches &&
          thresholdMatches &&
          decisionRuleMatches &&
          labelMatches) {
        passed++;

        if (outcome.phishing) {
          phishingCount++;
        } else {
          benignCount++;
        }
      }
    }

    // ignore: avoid_print
    print(
      'Teacher adapter parity: '
      'passed=$passed/${cases.length}, '
      'phishing=$phishingCount, '
      'benign=$benignCount, '
      'failures=$failures',
    );

    expect(
      failures,
      isEmpty,
      reason: 'Teacher adapter differs from frozen Python references',
    );

    expect(passed, cases.length);
    expect(phishingCount, greaterThan(0));
    expect(benignCount, greaterThan(0));
  });
}
