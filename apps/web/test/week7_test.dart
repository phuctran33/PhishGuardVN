import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart' show LogicalKeyboardKey;
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:phishguard_web/api_client.dart';
import 'package:phishguard_web/main.dart';
import 'package:phishguard_web/qr_image.dart';

import 'api_client_test.dart' show predictionFixture, jsonResponse;

Map<String, dynamic> inspectionFixture() => {
  'scope': 'rule_based_url_inspection',
  'hostname': 'vietcombank.example.com',
  'registrable_domain': 'example.com',
  'subdomain': 'vietcombank',
  'path': '/login',
  'is_ip': false,
  'reference_sha256': 'fixture-only',
  'reference_brands': 45,
  'official_brand_ids': <String>[],
  'features': {'brand_domain_mismatch': 1},
  'matches': [
    {
      'rule': 'brand_domain_mismatch',
      'brand_id': 'vietcombank',
      'brand_name': 'Vietcombank',
      'key': 'vietcombank',
      'text': 'vietcombank',
      'value': 1,
    },
  ],
};
Uint8List fixture(String name) => File('test/fixtures/$name').readAsBytesSync();
void main() {
  test(
    'real QR pixels preserve path query and case',
    () => expect(
      decodeQrImage(fixture('qr_url.png')),
      'https://example.com/Login?Q=A',
    ),
  );
  for (final format in ['jpg', 'webp']) {
    test('real QR decoder supports $format', () {
      expect(
        decodeQrImage(fixture('qr_url.$format')),
        'https://example.com/Login?Q=A',
      );
    });
  }
  test('reject excessive image dimensions before frame allocation', () {
    expect(
      () => decodeQrImage(fixture('oversized_dimensions.png')),
      throwsA(
        isA<QrFailure>().having(
          (e) => e.message,
          'dimension limit',
          contains('megapixel'),
        ),
      ),
    );
  });
  for (final name in [
    'qr_text.png',
    'qr_bad_scheme.png',
    'no_qr.png',
    'broken.png',
  ]) {
    test(
      'reject real image/content $name',
      () =>
          expect(() => decodeQrImage(fixture(name)), throwsA(isA<QrFailure>())),
    );
  }
  test('empty and oversized image rejected', () {
    expect(() => decodeQrImage(Uint8List(0)), throwsA(isA<QrFailure>()));
    expect(
      () => decodeQrImage(Uint8List(8 * 1024 * 1024 + 1)),
      throwsA(isA<QrFailure>()),
    );
  });
  test('QR preliminary syntax handles nonweb Unicode IP', () {
    for (final v in [
      'mailto:user@example.com',
      'hello world',
      'javascript:alert(1)',
      'http://example.com:99999',
      'user@example.com',
    ]) {
      expect(looksLikeWebUrl(v), false, reason: v);
    }
    for (final v in [
      'example.com/Case?Q=A',
      'https://bücher.de/Path',
      'http://[::1]/',
    ]) {
      expect(looksLikeWebUrl(v), true, reason: v);
    }
  });
  test('inspect request and evidence contract', () async {
    final api = PredictionApi(
      baseUrl: 'http://localhost',
      client: MockClient((r) async {
        expect(r.url.path, '/inspect');
        expect(r.body, '{"url":"EXAMPLE.com/Case?Q=A"}');
        return jsonResponse(inspectionFixture());
      }),
    );
    expect((await api.inspect('EXAMPLE.com/Case?Q=A')).domain, 'example.com');
    expect(
      () => Inspection.fromJson({
        ...inspectionFixture(),
        'matches': [
          {'value': 1},
        ],
      }),
      throwsFormatException,
    );
    api.close();
  });
  test('inspect timeout unavailable and retry', () async {
    var n = 0;
    final api = PredictionApi(
      baseUrl: 'http://localhost',
      timeout: const Duration(milliseconds: 5),
      client: MockClient((r) async {
        n++;
        if (n == 1) {
          await Future<void>.delayed(const Duration(milliseconds: 50));
        }
        if (n == 2) {
          return jsonResponse({
            'error': {'code': 'INSPECTION_UNAVAILABLE'},
          }, 503);
        }
        return jsonResponse(inspectionFixture());
      }),
    );
    await expectLater(
      api.inspect('example.com'),
      throwsA(isA<ApiFailure>().having((e) => e.code, 'code', 'TIMEOUT')),
    );
    await expectLater(
      api.inspect('example.com'),
      throwsA(
        isA<ApiFailure>().having(
          (e) => e.code,
          'code',
          'INSPECTION_UNAVAILABLE',
        ),
      ),
    );
    expect((await api.inspect('example.com')).domain, 'example.com');
    api.close();
  });
  Future<void> start(
    WidgetTester t,
    Future<http.Response> Function(http.Request) handler, {
    Future<Uint8List?> Function()? picker,
  }) async {
    await t.pumpWidget(
      PhishGuardApp(
        api: PredictionApi(
          baseUrl: 'http://localhost',
          client: MockClient(
            (r) async => r.method == 'GET'
                ? jsonResponse({'model_ready': true})
                : handler(r),
          ),
        ),
        imagePicker: picker,
      ),
    );
    await t.pumpAndSettle();
  }

  Future<void> tap(WidgetTester t, String key) async {
    await t.ensureVisible(find.byKey(Key(key)));
    await t.tap(find.byKey(Key(key)));
    await t.pump();
  }

  testWidgets('deleting a URL after a broken QR keeps the input focused', (
    t,
  ) async {
    t.view.physicalSize = const Size(1440, 1100);
    t.view.devicePixelRatio = 1;
    addTearDown(t.view.resetPhysicalSize);
    addTearDown(t.view.resetDevicePixelRatio);
    final input = find.byKey(const Key('url-input'));
    final qrError = find.byKey(const Key('qr-error'));
    final editable = find.descendant(
      of: input,
      matching: find.byType(EditableText),
    );
    final broken = fixture('broken.png');
    await start(t, (request) async {
      return jsonResponse(
        request.url.path == '/inspect'
            ? inspectionFixture()
            : predictionFixture(),
      );
    }, picker: () async => broken);
    const original = 'example.com';
    await t.enterText(input, original);
    await tap(t, 'check-button');
    await t.pumpAndSettle();
    await tap(t, 'inspect-button');
    await t.pumpAndSettle();
    await tap(t, 'qr-upload');
    await t.runAsync(
      () async => Future<void>.delayed(const Duration(milliseconds: 200)),
    );
    await t.pumpAndSettle();
    await tap(t, 'url-input');
    final field = t.widget<EditableText>(editable);
    final focus = field.focusNode;
    final selection = TextSelection(
      baseOffset: 0,
      extentOffset: original.length,
    );
    expect(focus.hasFocus, isTrue);

    // Drive the existing input connection, as a browser would for select-all.
    t.testTextInput.updateEditingValue(
      TextEditingValue(text: original, selection: selection),
    );
    await t.pump();
    expect(field.controller.selection, selection);
    expect(qrError, findsOneWidget);
    expect(find.byKey(const Key('prediction-result')), findsOneWidget);
    expect(find.byKey(const Key('inspection-result')), findsOneWidget);

    List<int> siblingOrder() => t
        .getSemantics(editable)
        .parent!
        .parent!
        .debugListChildrenInOrder(DebugSemanticsDumpOrder.traversalOrder)
        .map((node) => node.id)
        .toList();
    final before = siblingOrder();

    await t.sendKeyEvent(LogicalKeyboardKey.backspace);
    await t.pumpAndSettle();
    expect(field.controller.text, isEmpty);
    expect(focus.hasFocus, isTrue, reason: 'Backspace must preserve focus');
    expect(t.widget<EditableText>(editable).focusNode, same(focus));
    expect(qrError, findsNothing);
    expect(find.byKey(const Key('prediction-result')), findsNothing);
    expect(find.byKey(const Key('inspection-result')), findsNothing);

    // Flutter Web reorders the accessibility DOM when surviving siblings
    // change traversal order. Moving the focused input's ancestor blurs it.
    final after = siblingOrder();
    expect(
      after.where(before.contains),
      orderedEquals(before.where(after.contains)),
      reason: 'QR removal must not reorder surviving input siblings',
    );

    // Do not use WidgetTester.enterText here, since that focuses the field.
    const replacement = 'example.org';
    t.testTextInput.updateEditingValue(
      TextEditingValue(
        text: replacement,
        selection: TextSelection.collapsed(offset: replacement.length),
      ),
    );
    await t.pump();
    expect(field.controller.text, replacement);
    expect(focus.hasFocus, isTrue);
  });

  testWidgets('QR real fixture waits for confirmation before POST', (t) async {
    var posts = 0;
    await start(t, (r) async {
      posts++;
      expect(r.url.path, '/predict');
      expect(r.body, '{"url":"https://example.com/Login?Q=A"}');
      return jsonResponse(predictionFixture());
    }, picker: () async => fixture('qr_url.png'));
    await tap(t, 'qr-upload');
    await t.runAsync(
      () async => Future<void>.delayed(const Duration(milliseconds: 200)),
    );
    await t.pumpAndSettle();
    expect(find.byKey(const Key('qr-preview')), findsOneWidget);
    expect(posts, 0);
    await tap(t, 'qr-confirm');
    await t.pumpAndSettle();
    expect(posts, 1);
    expect(find.byKey(const Key('qr-preview')), findsNothing);
    await tap(t, 'qr-upload');
    await t.runAsync(
      () async => Future<void>.delayed(const Duration(milliseconds: 200)),
    );
    await t.pumpAndSettle();
    expect(find.byKey(const Key('qr-preview')), findsOneWidget);
    expect(posts, 1);
    await tap(t, 'qr-confirm');
    await t.pumpAndSettle();
    expect(posts, 2);
    expect(find.byKey(const Key('qr-preview')), findsNothing);
  });
  testWidgets('QR corrupt retry cancel', (t) async {
    var count = 0, posts = 0;
    await start(
      t,
      (_) async {
        posts++;
        return jsonResponse(predictionFixture());
      },
      picker: () async {
        count++;
        return switch (count) {
          1 => fixture('broken.png'),
          2 => fixture('qr_url.png'),
          _ => null,
        };
      },
    );
    final input = find.byKey(const Key('url-input'));
    final controller = t.widget<TextFormField>(input).controller!;
    await t.enterText(input, 'example.org');
    await tap(t, 'qr-upload');
    await t.runAsync(
      () async => Future<void>.delayed(const Duration(milliseconds: 200)),
    );
    await t.pumpAndSettle();
    expect(find.byKey(const Key('qr-error')), findsOneWidget);
    await tap(t, 'qr-upload');
    await t.runAsync(
      () async => Future<void>.delayed(const Duration(milliseconds: 200)),
    );
    await t.pumpAndSettle();
    expect(find.byKey(const Key('qr-preview')), findsOneWidget);
    await t.ensureVisible(find.text('Hủy'));
    await t.tap(find.text('Hủy'));
    await t.pump();
    expect(find.byKey(const Key('qr-preview')), findsNothing);
    expect(find.byKey(const Key('qr-error')), findsNothing);
    await tap(t, 'qr-upload');
    await t.pumpAndSettle();
    expect(find.byKey(const Key('qr-preview')), findsNothing);
    expect(find.byKey(const Key('qr-error')), findsNothing);
    expect(controller.text, 'example.org');
    expect(posts, 0);
  });
  testWidgets(
    'selection-only notifications preserve in-flight and rendered results',
    (t) async {
      final response = Completer<http.Response>();
      await start(t, (_) => response.future);
      await t.enterText(find.byKey(const Key('url-input')), 'example.com');
      await tap(t, 'check-button');
      final controller = t
          .widget<TextFormField>(find.byKey(const Key('url-input')))
          .controller!;
      controller.selection = const TextSelection.collapsed(offset: 2);
      response.complete(jsonResponse(predictionFixture()));
      await t.pumpAndSettle();
      expect(find.byKey(const Key('prediction-result')), findsOneWidget);
      controller.selection = const TextSelection.collapsed(offset: 5);
      await t.pump();
      expect(find.byKey(const Key('prediction-result')), findsOneWidget);
    },
  );
  for (final kind in ['predict', 'inspect']) {
    testWidgets(
      '$kind allows a changed URL and discards stale or duplicate requests',
      (t) async {
        t.view.physicalSize = const Size(1440, 1050);
        t.view.devicePixelRatio = 1;
        addTearDown(t.view.resetPhysicalSize);
        addTearDown(t.view.resetDevicePixelRatio);
        final response = Completer<http.Response>();
        final nextResponse = Completer<http.Response>();
        var calls = 0;
        await start(t, (_) {
          calls++;
          return calls == 1 ? response.future : nextResponse.future;
        });
        await t.enterText(find.byKey(const Key('url-input')), 'example.com');
        final key = kind == 'predict' ? 'check-button' : 'inspect-button';
        final action = find.byKey(Key(key));
        await tap(t, key);
        expect(t.widget<ButtonStyleButton>(action).onPressed, isNull);
        expect(calls, 1);
        await t.enterText(find.byKey(const Key('url-input')), 'example.org');
        await t.pump();
        await tap(t, key);
        expect(calls, 2);
        final fixture = kind == 'predict'
            ? predictionFixture()
            : inspectionFixture();
        final result = find.byKey(
          Key(kind == 'predict' ? 'prediction-result' : 'inspection-result'),
        );
        response.complete(jsonResponse(fixture));
        await t.pump();
        expect(result, findsNothing);
        expect(t.widget<ButtonStyleButton>(action).onPressed, isNull);
        expect(calls, 2);
        nextResponse.complete(jsonResponse(fixture));
        await t.pumpAndSettle();
        expect(result, findsOneWidget);
      },
    );
  }
  testWidgets('stale QR upload discarded after editing', (t) async {
    final picker = Completer<Uint8List?>();
    await start(
      t,
      (_) async => jsonResponse(predictionFixture()),
      picker: () => picker.future,
    );
    await tap(t, 'qr-upload');
    await t.enterText(find.byKey(const Key('url-input')), 'example.org');
    picker.complete(fixture('qr_url.png'));
    await t.runAsync(
      () async => Future<void>.delayed(const Duration(milliseconds: 200)),
    );
    await t.pumpAndSettle();
    expect(find.byKey(const Key('qr-preview')), findsNothing);
  });
  testWidgets('rule evidence shows domain separately from ML on 320px', (
    t,
  ) async {
    t.view.physicalSize = const Size(320, 1000);
    t.view.devicePixelRatio = 1;
    addTearDown(t.view.resetPhysicalSize);
    addTearDown(t.view.resetDevicePixelRatio);
    t.platformDispatcher.textScaleFactorTestValue = 2;
    addTearDown(t.platformDispatcher.clearTextScaleFactorTestValue);
    await start(t, (_) async => jsonResponse(inspectionFixture()));
    await t.enterText(
      find.byKey(const Key('url-input')),
      'vietcombank.example.com/login',
    );
    await tap(t, 'inspect-button');
    await t.pumpAndSettle();
    expect(
      find.textContaining('Domain đăng ký thực tế: example.com'),
      findsOneWidget,
    );
    expect(
      find.textContaining('không phải dự đoán hay giải thích nội tại ML'),
      findsOneWidget,
    );
    expect(find.byKey(const Key('prediction-result')), findsNothing);
    expect(t.takeException(), isNull);
  });
}
