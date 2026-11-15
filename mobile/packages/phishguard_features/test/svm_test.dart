import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:phishguard_features/phishguard_features.dart';
import 'package:test/test.dart';

Map<String, dynamic> tinyModel({
  Map<String, int>? vocabulary,
  List<double>? idf,
  List<double>? coefficients,
  double intercept = -0.63500013,
  bool canonical = false,
}) =>
    {
      'schema_version': 'dart-svm-v1',
      'model_version': 'teacher-stacking-v2',
      'config': {
        'analyzer': 'char',
        'ngram_range': [2, 5],
        'min_df': 2,
        'sublinear_tf': true,
        'use_idf': true,
        'norm': 'l2',
        'lowercase': false,
        'canonical_enabled': canonical,
      },
      'vocabulary': vocabulary ?? {'ab': 0, 'abc': 1, 'bc': 2},
      'idf': idf ?? [1.0, 1.0, 1.0],
      'coefficients': coefficients ?? [1.0, 2.0, 3.0],
      'intercept': intercept,
    };

void main() {
  group('Teacher SVM JSON model', () {
    test('validates model metadata, dimensions, and vocabulary indices', () {
      final model = SvmModel.fromJson(tinyModel());
      expect(model.vocabulary.length, 3);
      expect(model.intercept, closeTo(-0.63500013, 1e-12));
      expect(
          () => SvmModel.fromJson({...tinyModel(), 'model_version': 'other'}),
          throwsFormatException);
      expect(
        () => SvmModel.fromJson({
          ...tinyModel(),
          'coefficients': [1.0]
        }),
        throwsFormatException,
      );
      expect(
        () => SvmModel.fromJson(tinyModel(vocabulary: {'ab': 1, 'bc': 1})),
        throwsFormatException,
      );
    });

    test('counts overlapping n-grams, sublinear TF, IDF, and L2-normalizes',
        () {
      // "abab" has two occurrences of "ab"; normalized TF is 1 + ln(2).
      final model = SvmModel.fromJson(tinyModel(
        vocabulary: {'ab': 0},
        idf: [2.0],
        coefficients: [3.0],
        intercept: 0,
      ));
      expect(model.predictMargin('abab'), closeTo(3.0, 1e-14));
    });

    test('character n-gram boundaries and unknown terms', () {
      final model = SvmModel.fromJson(tinyModel(
        vocabulary: {'ab': 0, 'abc': 1, 'bc': 2},
        idf: [1, 1, 1],
        coefficients: [1, 2, 3],
        intercept: 0,
      ));
      // For "abc", all terms are present and normalized by sqrt(1+4+9).
      expect(model.predictMargin('abc'), closeTo(6 / math.sqrt(3), 1e-14));
      expect(model.predictMargin('a'), 0);
      expect(model.predictMargin('zzzz'), 0);
    });

    test('character slicing uses Unicode code points, not UTF-16 code units',
        () {
      final model = SvmModel.fromJson(tinyModel(
        vocabulary: {'😀a': 0, 'a😀': 1},
        idf: [1, 1],
        coefficients: [1, -1],
        intercept: 0,
      ));
      expect(model.predictMargin('😀a'), closeTo(1.0, 1e-14));
    });

    test(
        'sklearn char analyzer whitespace collapsing preserves singleton spaces',
        () {
      expect(normalizeSklearnCharWhitespace('a\t b'), 'a b');
      expect(normalizeSklearnCharWhitespace('a\tb'), 'a\tb');
      expect(normalizeSklearnCharWhitespace('  a\n\n b  '), ' a b ');
      expect(normalizeSklearnCharWhitespace('😀\u00a0\u00a0x'), '😀 x');
    });
  });

  group('Teacher CanonicalText contract examples', () {
    const cases = <String, String>{
      'https://EXAMPLE.com:443/A%2Fb?Q=Z#frag': 'example.com/A%2Fb?Q=Z',
      'http://user:pass@EXAMPLE.com:80/A?Q=a#login': 'example.com/A?Q=a',
      'https://EXAMPLE.com:8443/Case': 'example.com:8443/Case',
      '//EXAMPLE.com/A': 'example.com/A',
      'example.com/A?Q=%2F': 'example.com/A?Q=%2F',
      'http://[::1]:80/A': '[::1]/A',
      'https://BÜCHER.de/A': 'xn--bcher-kva.de/A',
    };
    for (final entry in cases.entries) {
      test(entry.key, () {
        expect(canonicalizeTeacherUrl(entry.key), entry.value);
      });
    }

    test(
        'userinfo uses final @ and preserves path/query while dropping fragment',
        () {
      expect(
        canonicalizeTeacherUrl(
            'https://user@name:pass@EXAMPLE.com:443/a;b?q=1#x'),
        'example.com/a;b?q=1',
      );
    });

    test('explicit empty port follows urllib SplitResult.port behavior', () {
      expect(canonicalizeTeacherUrl('https://example.com:/a'), 'example.com/a');
    });
  });

  test('Python Teacher SVM reference margins parity for all fixture cases', () {
    // Run from this package directory. The exporter writes both files consumed
    // here, so the parity test cannot silently use a nonexistent fixture/model.
    final root = Directory('../../../artifacts/teacher_v2_android');
    final modelFile = File('${root.path}/dart_svm_model.json');
    final fixtureFile = File('test/fixtures/svm_reference_margins.json');
    expect(modelFile.existsSync(), isTrue,
        reason:
            'Run scripts/export_teacher_v2_android.py from repo root first.');
    expect(fixtureFile.existsSync(), isTrue,
        reason:
            'Run scripts/export_teacher_v2_android.py from repo root first.');
    final model = SvmModel.fromJson(
        jsonDecode(modelFile.readAsStringSync()) as Map<String, dynamic>);
    final data =
        jsonDecode(fixtureFile.readAsStringSync()) as Map<String, dynamic>;
    expect(data['model_version'], 'teacher-stacking-v2');
    expect(data['absolute_tolerance'], 1e-6);
    final cases = (data['cases'] as List<dynamic>).cast<Map<String, dynamic>>();
    expect(cases, isNotEmpty);
    var passed = 0;
    var maxError = 0.0;
    final failures = <String>[];
    for (final item in cases) {
      final actual = model.predictMargin(item['url'] as String);
      final expected = (item['margin'] as num).toDouble();
      final error = (actual - expected).abs();
      if (error <= 1e-6) {
        passed++;
      } else {
        failures.add('${item['name']}: error=$error');
      }
      if (error > maxError) maxError = error;
    }
    // `dart test -r expanded` reports this diagnostic in test output.
    // ignore: avoid_print
    print(
        'SVM parity: $passed/${cases.length} passed; max abs error=$maxError; failures=$failures');
    expect(failures, isEmpty);
    expect(passed, cases.length);
  });
}
