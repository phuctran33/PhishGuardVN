import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:phishguard_web/api_client.dart';
import 'package:phishguard_web/main.dart';
import 'package:phishguard_web/similar_cases.dart';

const _empty = {'status': 'empty', 'cases': []};
const _button = Key('similar-button');
const _panel = Key('similar-result');

Map<String, dynamic> fixture() =>
    jsonDecode(File('test/fixtures/similar_cases.json').readAsStringSync())
        as Map<String, dynamic>;

http.Response response(Object body, [int status = 200]) =>
    http.Response.bytes(utf8.encode(jsonEncode(body)), status);

void main() {
  test('retains URL, source, cosine and Unicode half-open offsets', () {
    final data = fixture();
    final raw = (data['cases'] as List).first;
    final result = SimilarCase.decode(data);
    expect(result, hasLength(2));
    expect(result.first.displayUrl, raw['display_url']);
    expect(result.first.source, raw['source']);
    expect(result.first.similarity, raw['cosine_similarity']);
    expect(
      result.first.segments.where((s) => s.highlighted).map((s) => s.text),
      ['đổi🔒', 'help'],
    );
    expect(
      result.first.segments.map((s) => s.text).join(),
      result.first.displayUrl,
    );
  });

  test('deduplicates in rank order, and rejects conflicting IDs', () {
    final data = fixture();
    final rows = data['cases'] as List;
    rows.insert(1, Map<String, dynamic>.from(rows.first as Map));
    expect(SimilarCase.decode(data).map((c) => c.id), [
      'fixture-only-001',
      'fixture-only-002',
    ]);
    (rows[1] as Map)['display_url'] = 'hxxps://a[.]example[.]net/';
    (rows[1] as Map)['highlights'] = [];
    expect(() => SimilarCase.decode(data), throwsFormatException);
  });

  test(
    'empty is explicit and malformed, oversized and unsafe payloads fail',
    () {
      expect(SimilarCase.decode(_empty), isEmpty);
      expect(
        () => SimilarCase.decode({'status': 'ok', 'cases': []}),
        throwsFormatException,
      );
      final data = fixture();
      final rows = data['cases'] as List;
      expect(
        () => SimilarCase.decode({
          'status': 'ok',
          'cases': List.filled(6, rows.first),
        }),
        throwsFormatException,
      );
      for (final patch in [
        {'display_url': 'https://example.net/active'},
        {'display_url': 'hxxps://example.net/undeclared'},
        {'display_url': 'hxxps://name:pass@example[.]net/'},
        {'display_url': 'hxxps://name%40example[.]net/'},
        {'display_url': 'hxxps://example[.]net/?session=raw-secret'},
        {'display_url': 'hxxps://example[.]net/?x=[redacted]&y=raw'},
        {'display_url': 'hxxps://example[.]net/#private'},
        {'source': ''},
        {'cosine_similarity': 1.1},
        {
          'highlights': [
            {'start': 0, 'end': 9999},
          ],
        },
        {
          'highlights': [
            {'start': 0, 'end': 5},
            {'start': 4, 'end': 9},
          ],
        },
      ]) {
        expect(
          () => SimilarCase.decode({
            'status': 'ok',
            'cases': [
              {...(rows.first as Map), ...patch},
            ],
          }),
          throwsFormatException,
          reason: patch.toString(),
        );
      }
    },
  );

  test('API sends the URL unchanged, distinguishes 404/422/503', () async {
    var status = 200;
    const input = 'https://example.com/Path?token=demo';
    final api = PredictionApi(
      baseUrl: 'http://localhost:8000',
      client: MockClient((req) async {
        expect(req.method, 'POST');
        expect(req.url.path, '/similar-cases');
        expect(jsonDecode(req.body), {'url': input});
        return response(status == 200 ? fixture() : {}, status);
      }),
    );
    addTearDown(api.close);
    expect(await api.similarCases(input), hasLength(2));
    for (final code in [404, 422, 503]) {
      status = code;
      await expectLater(
        api.similarCases(input),
        throwsA(
          isA<ApiFailure>().having(
            (e) => e.code,
            'code',
            code == 422 ? 'INVALID_URL' : 'SIMILAR_UNAVAILABLE',
          ),
        ),
      );
    }
  });

  test('client reports timeout and rejects malformed JSON', () async {
    final api = PredictionApi(
      baseUrl: 'http://localhost:8000',
      timeout: const Duration(milliseconds: 10),
      client: MockClient((_) => Completer<http.Response>().future),
    );
    addTearDown(api.close);
    await expectLater(
      api.similarCases('example.com'),
      throwsA(isA<ApiFailure>().having((e) => e.code, 'code', 'TIMEOUT')),
    );
    final malformed = PredictionApi(
      baseUrl: 'http://localhost:8000',
      client: MockClient((_) async => http.Response('test-only HTML', 200)),
    );
    addTearDown(malformed.close);
    await expectLater(
      malformed.similarCases('example.com'),
      throwsA(
        isA<ApiFailure>().having((e) => e.code, 'code', 'INVALID_RESPONSE'),
      ),
    );
  });

  testWidgets('stale lookup is ignored, new URL can start immediately', (
    tester,
  ) async {
    final obsolete = Completer<http.Response>();
    final client = MockClient((req) async {
      if (req.url.path == '/health') return response({'model_ready': true});
      final url = (jsonDecode(req.body) as Map)['url'];
      return url == 'example.com' ? obsolete.future : response(_empty);
    });
    await tester.pumpWidget(
      PhishGuardApp(
        api: PredictionApi(baseUrl: 'http://localhost:8000', client: client),
      ),
    );
    final input = find.byKey(const Key('url-input'));
    final button = find.byKey(_button);
    await tester.enterText(input, 'example.com');
    await tester.ensureVisible(button);
    await tester.tap(button);
    await tester.pump();
    expect(find.text('Đang tra cứu ca lịch sử…'), findsOneWidget);
    await tester.enterText(input, 'example.net');
    await tester.pumpAndSettle();
    expect(find.byKey(_panel), findsNothing);
    await tester.tap(button);
    await tester.pumpAndSettle();
    expect(find.text('Chưa tìm thấy ca lịch sử đủ tương tự.'), findsOneWidget);

    obsolete.complete(response(fixture()));
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('historical-fixture-only-001')),
      findsNothing,
    );
    expect(find.text('Chưa tìm thấy ca lịch sử đủ tương tự.'), findsOneWidget);
  });

  testWidgets(
    'lookup retry with a source and highlighted plain text, preserving other results',
    (tester) async {
      var lookups = 0;
      final client = MockClient((req) async {
        switch (req.url.path) {
          case '/health':
            return response({'model_ready': true});
          case '/predict':
            return response({
              'label': 'benign',
              'model': 'fixture-model',
              'score': 0.2,
              'score_kind': 'probability',
              'score_definition': 'test-only',
              'protocol': 'test-only',
              'decision_rule': 'score >= threshold',
              'threshold': 0.7,
            });
          case '/inspect':
            return response({
              'scope': 'rule_based_url_inspection',
              'hostname': 'example.com',
              'registrable_domain': 'example.com',
              'subdomain': '',
              'path': '/',
              'is_ip': false,
              'reference_sha256': 'fixture-only',
              'reference_brands': 1001,
              'catalog_version': 'test-catalog',
              'catalog_status': 'expanded',
              'matches': [],
              'official_brand_ids': [],
              'features': {},
            });
          default:
            lookups++;
            return lookups == 1 ? response({}, 503) : response(fixture());
        }
      });
      await tester.pumpWidget(
        PhishGuardApp(
          api: PredictionApi(baseUrl: 'http://localhost:8000', client: client),
        ),
      );
      final input = find.byKey(const Key('url-input'));
      await tester.enterText(input, 'example.com');
      for (final key in [
        const Key('check-button'),
        const Key('inspect-button'),
        _button,
      ]) {
        final action = find.byKey(key);
        await tester.ensureVisible(action);
        await tester.tap(action);
        await tester.pumpAndSettle();
      }
      expect(find.byKey(const Key('prediction-result')), findsOneWidget);
      expect(find.byKey(const Key('inspection-result')), findsOneWidget);
      expect(find.text('test-catalog · 1001 thương hiệu'), findsOneWidget);

      final retry = find.byKey(const Key('similar-retry'));
      expect(retry, findsOneWidget);
      await tester.ensureVisible(retry);
      await tester.tap(retry);
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('prediction-result')), findsOneWidget);
      expect(find.byKey(const Key('inspection-result')), findsOneWidget);
      final text = tester.widget<Text>(
        find.byKey(const ValueKey('historical-fixture-only-001')),
      );
      expect(
        text.textSpan?.toPlainText(),
        fixture()['cases'][0]['display_url'],
      );
      final spans = (text.textSpan as TextSpan).children!.cast<TextSpan>();
      expect(
        spans.where((span) => span.style != null).map((span) => span.text),
        ['đổi🔒', 'help'],
      );
      expect(spans.every((span) => span.recognizer == null), isTrue);
      expect(
        find.text('Nguồn: Fixture kiểm thử #36 · Cosine: 0.821'),
        findsOneWidget,
      );

      // Selection changes are not edits.
      tester.widget<TextFormField>(input).controller!.selection =
          const TextSelection.collapsed(offset: 3);
      await tester.pumpAndSettle();
      expect(find.byKey(_panel), findsOneWidget);
    },
  );
}
