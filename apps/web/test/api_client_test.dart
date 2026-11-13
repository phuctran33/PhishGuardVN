// Synthetic HTTP fixtures only. Real-browser demo uses the actual backend/model.
import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:phishguard_web/api_client.dart';

Map<String, dynamic> predictionFixture({
  String kind = 'probability',
  double score = .49,
}) => {
  'label': 'benign',
  'model': 'synthetic_fixture',
  'score': score,
  'score_kind': kind,
  'score_definition': 'Synthetic test fixture',
  'decision_rule': 'estimator.predict',
  'protocol': 'test_only',
};

http.Response jsonResponse(Object value, [int status = 200]) => http.Response(
  jsonEncode(value),
  status,
  headers: {'Content-Type': 'application/json; charset=utf-8'},
);

void main() {
  test('released stacking rule preserves the backend label and threshold', () {
    final row = Prediction.fromJson({
      ...predictionFixture(score: .6),
      'decision_rule': 'score >= threshold',
      'threshold': .7,
    });
    expect(row.label, 'benign');
    expect(row.threshold, .7);
    expect(row.decisionRule, 'score >= threshold');
  });
  for (final bad in [null, '0.7', double.nan, double.infinity, -.1, 2]) {
    test('rejects invalid stacking threshold: $bad', () {
      expect(
        () => Prediction.fromJson({
          ...predictionFixture(),
          'decision_rule': 'score >= threshold',
          'threshold': bad,
        }),
        throwsFormatException,
      );
    });
  }
  test('rejects unknown rule or threshold on estimator.predict', () {
    for (final changes in [
      {'decision_rule': 'arbitrary'},
      {'threshold': .7},
      {
        'decision_rule': 'score >= threshold',
        'threshold': .7,
        'score_kind': 'decision_function',
      },
    ]) {
      expect(
        () => Prediction.fromJson({...predictionFixture(), ...changes}),
        throwsFormatException,
      );
    }
  });
  test('POST sends only URL and parses v1 probability response', () async {
    final api = PredictionApi(
      baseUrl: 'http://localhost:8000/',
      client: MockClient((r) async {
        expect(r.method, 'POST');
        expect(r.url.path, '/predict');
        expect(jsonDecode(r.body), {'url': 'example.com'});
        return jsonResponse(predictionFixture());
      }),
    );
    final result = await api.predict('example.com');
    expect(result.scoreKind, 'probability');
    expect(result.score, .49);
    api.close();
  });
  test('margin can exceed one without probability conversion', () async {
    final api = PredictionApi(
      baseUrl: 'http://localhost',
      client: MockClient(
        (_) async => jsonResponse(
          predictionFixture(kind: 'decision_function', score: 1.25),
        ),
      ),
    );
    expect((await api.predict('example.com')).score, 1.25);
    api.close();
  });
  test(
    'model-unavailable response is friendly and does not echo server details',
    () async {
      final api = PredictionApi(
        baseUrl: 'http://localhost',
        client: MockClient(
          (_) async => jsonResponse({
            'error': {
              'code': 'MODEL_UNAVAILABLE',
              'message': '/private/model/path',
              'reason': 'artifact_missing',
            },
          }, 503),
        ),
      );
      await expectLater(
        api.predict('example.com'),
        throwsA(
          isA<ApiFailure>()
              .having((e) => e.code, 'code', 'MODEL_UNAVAILABLE')
              .having(
                (e) => e.message.contains('/private'),
                'does not expose path',
                false,
              ),
        ),
      );
      api.close();
    },
  );
  test('malformed upstream body is rejected rather than shown', () async {
    final api = PredictionApi(
      baseUrl: 'http://localhost',
      client: MockClient((_) async => http.Response('<traceback>', 500)),
    );
    await expectLater(
      api.predict('example.com'),
      throwsA(
        isA<ApiFailure>().having((e) => e.code, 'code', 'INVALID_RESPONSE'),
      ),
    );
    api.close();
  });
  for (final defect in ['score_range', 'unknown_label', 'unknown_kind']) {
    test('rejects incompatible response: $defect', () async {
      final value = predictionFixture();
      if (defect == 'score_range') value['score'] = 2;
      if (defect == 'unknown_label') value['label'] = 'safe';
      if (defect == 'unknown_kind') value['score_kind'] = 'confidence';
      final api = PredictionApi(
        baseUrl: 'http://localhost',
        client: MockClient((_) async => jsonResponse(value)),
      );
      await expectLater(
        api.predict('example.com'),
        throwsA(
          isA<ApiFailure>().having((e) => e.code, 'code', 'INVALID_RESPONSE'),
        ),
      );
      api.close();
    });
  }
  test('timeout is actionable', () async {
    final pending = Completer<http.Response>();
    final api = PredictionApi(
      baseUrl: 'http://localhost',
      timeout: const Duration(milliseconds: 1),
      client: MockClient((_) => pending.future),
    );
    await expectLater(
      api.predict('example.com'),
      throwsA(isA<ApiFailure>().having((e) => e.code, 'code', 'TIMEOUT')),
    );
    pending.complete(jsonResponse(predictionFixture()));
    api.close();
  });
  test('offline failure is actionable', () async {
    final api = PredictionApi(
      baseUrl: 'http://localhost',
      client: MockClient(
        (_) async => throw http.ClientException('connection refused'),
      ),
    );
    await expectLater(
      api.predict('example.com'),
      throwsA(isA<ApiFailure>().having((e) => e.code, 'code', 'NETWORK_ERROR')),
    );
    api.close();
  });
}
