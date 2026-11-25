import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:phishguard_web/api_client.dart';
import 'package:phishguard_web/main.dart';

import 'api_client_test.dart' show predictionFixture, jsonResponse;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() async {
    final loader = FontLoader('GuardRoboto')
      ..addFont(rootBundle.load('assets/fonts/Roboto-Regular.ttf'));
    await loader.load();
  });
  Future<void> start(
    WidgetTester tester,
    Future<http.Response> Function(http.Request) post,
  ) async {
    final api = PredictionApi(
      baseUrl: 'http://localhost:8000',
      client: MockClient(
        (r) async => r.method == 'GET'
            ? jsonResponse({'model_ready': true})
            : await post(r),
      ),
    );
    await tester.pumpWidget(PhishGuardApp(api: api));
    await tester.pumpAndSettle();
  }

  Future<void> check(WidgetTester tester) async {
    final button = find.byKey(const Key('check-button'));
    await tester.ensureVisible(button);
    await tester.tap(button);
    await tester.pumpAndSettle();
  }

  bool urlFocused(WidgetTester tester) =>
      tester.widget<EditableText>(find.byType(EditableText)).focusNode.hasFocus;

  testWidgets('empty URL is validated locally without POST', (tester) async {
    var requests = 0;
    await start(tester, (_) async {
      requests++;
      return jsonResponse(predictionFixture());
    });
    await check(tester);
    expect(find.text('Vui lòng nhập một URL.'), findsOneWidget);
    expect(requests, 0);
    final input = find.byKey(const Key('url-input'));
    expect(urlFocused(tester), isTrue);
    await tester.enterText(input, 'example.com');
    await tester.pumpAndSettle();
    expect(find.text('Vui lòng nhập một URL.'), findsNothing);
    expect(requests, 0);
  });

  testWidgets('paste fills the field, Enter scans and clear drops the result', (
    tester,
  ) async {
    final messenger = tester.binding.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
      return call.method == 'Clipboard.getData'
          ? {'text': '  example.com/Login?Q=A  '}
          : null;
    });
    addTearDown(
      () => messenger.setMockMethodCallHandler(SystemChannels.platform, null),
    );
    var requests = 0;
    await start(tester, (request) async {
      requests++;
      expect(request.body, '{"url":"example.com/Login?Q=A"}');
      return jsonResponse(predictionFixture());
    });
    final paste = find.byKey(const Key('paste-url'));
    await tester.ensureVisible(paste);
    await tester.tap(paste);
    await tester.pumpAndSettle();
    final field = tester.widget<TextFormField>(
      find.byKey(const Key('url-input')),
    );
    expect(field.controller!.text, 'example.com/Login?Q=A');
    expect(urlFocused(tester), isTrue);
    expect(requests, 0);
    await tester.testTextInput.receiveAction(TextInputAction.go);
    await tester.pumpAndSettle();
    final result = find.byKey(const Key('prediction-result'));
    expect(result, findsOneWidget);
    expect(requests, 1);
    final clear = find.byKey(const Key('clear-url'));
    await tester.ensureVisible(clear);
    await tester.tap(clear);
    await tester.pumpAndSettle();
    expect(field.controller!.text, isEmpty);
    expect(urlFocused(tester), isTrue);
    expect(result, findsNothing);
    expect(requests, 1);
  });

  testWidgets('late clipboard response cannot replace freshly typed text', (
    tester,
  ) async {
    final clipboard = Completer<Map<String, String>>();
    final messenger = tester.binding.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
      return call.method == 'Clipboard.getData' ? await clipboard.future : null;
    });
    addTearDown(
      () => messenger.setMockMethodCallHandler(SystemChannels.platform, null),
    );
    await start(tester, (_) async => throw StateError('Unexpected scan'));
    final paste = find.byKey(const Key('paste-url'));
    await tester.ensureVisible(paste);
    await tester.tap(paste);
    await tester.pump();
    final input = find.byKey(const Key('url-input'));
    await tester.enterText(input, 'example.org');
    clipboard.complete({'text': 'example.com'});
    await tester.pumpAndSettle();
    expect(tester.widget<TextFormField>(input).controller!.text, 'example.org');
  });

  testWidgets('late startup health cannot overwrite a successful prediction', (
    tester,
  ) async {
    final health = Completer<http.Response>();
    final api = PredictionApi(
      baseUrl: 'http://localhost:8000',
      client: MockClient(
        (request) async => request.method == 'GET'
            ? await health.future
            : jsonResponse(predictionFixture()),
      ),
    );
    await tester.pumpWidget(PhishGuardApp(api: api));
    await tester.enterText(find.byKey(const Key('url-input')), 'example.com');
    await check(tester);
    expect(find.text('API sẵn sàng'), findsOneWidget);
    health.complete(jsonResponse({'model_ready': false}));
    await tester.pumpAndSettle();
    expect(find.text('API sẵn sàng'), findsOneWidget);
    expect(find.text('API chờ model'), findsNothing);
  });
  testWidgets(
    'missing scheme is sent unchanged and label/model/score are displayed',
    (tester) async {
      await start(tester, (r) async {
        expect(r.body, '{"url":"example.com"}');
        return jsonResponse(predictionFixture());
      });
      await tester.enterText(find.byKey(const Key('url-input')), 'example.com');
      await check(tester);
      expect(find.text('Nhãn mô hình: benign'), findsOneWidget);
      expect(find.text('49.00%'), findsOneWidget);
      expect(find.text('synthetic_fixture'), findsOneWidget);
      expect(
        find.textContaining('không bảo đảm website an toàn'),
        findsOneWidget,
      );
    },
  );
  testWidgets('margin UI never uses percentage', (tester) async {
    await start(
      tester,
      (_) async => jsonResponse(
        predictionFixture(kind: 'decision_function', score: 1.25),
      ),
    );
    await tester.enterText(
      find.byKey(const Key('url-input')),
      'https://example.com',
    );
    await check(tester);
    expect(find.text('1.2500'), findsOneWidget);
    expect(find.text('Biên quyết định'), findsOneWidget);
    expect(find.text('Decision margin · không phải xác suất'), findsOneWidget);
    expect(
      tester
          .widget<Text>(find.byKey(const Key('score-value')))
          .data!
          .contains('%'),
      false,
    );
  });
  testWidgets(
    'stacking shows backend benign above .5 without inferring a label',
    (tester) async {
      await start(
        tester,
        (_) async => jsonResponse({
          ...predictionFixture(score: .6),
          'model': 'teacher_fixture',
          'decision_rule': 'score >= threshold',
          'threshold': .7,
        }),
      );
      await tester.enterText(find.byKey(const Key('url-input')), 'example.com');
      await check(tester);
      expect(find.text('Nhãn mô hình: benign'), findsOneWidget);
      expect(find.text('0.600000'), findsOneWidget);
      expect(find.text('Quy tắc backend: score ≥ 0.7'), findsOneWidget);
      expect(find.textContaining('Meta-LR score'), findsOneWidget);
      expect(find.text('Có dấu hiệu phishing'), findsNothing);
    },
  );
  testWidgets('invalid URL error keeps input editable', (tester) async {
    await start(
      tester,
      (_) async => jsonResponse({
        'error': {
          'code': 'INVALID_URL',
          'message': 'invalid',
          'reason': 'invalid_port',
        },
      }, 422),
    );
    await tester.enterText(
      find.byKey(const Key('url-input')),
      'http://example.com:99999',
    );
    await check(tester);
    expect(find.byKey(const Key('prediction-error')), findsOneWidget);
    final edit = find.byKey(const Key('edit-url-button'));
    await tester.ensureVisible(edit);
    await tester.tap(edit);
    await tester.pumpAndSettle();
    expect(urlFocused(tester), isTrue);
    await tester.enterText(find.byKey(const Key('url-input')), 'example.com');
    await tester.pump();
    expect(find.byKey(const Key('prediction-error')), findsNothing);
  });
  testWidgets('offline then retry recovers without rebuilding app', (
    tester,
  ) async {
    var attempts = 0;
    await start(tester, (_) async {
      if (++attempts == 1) throw http.ClientException('offline');
      return jsonResponse(predictionFixture());
    });
    await tester.enterText(find.byKey(const Key('url-input')), 'example.com');
    await check(tester);
    expect(find.textContaining('Không kết nối được máy chủ'), findsOneWidget);
    final retry = find.byKey(const Key('retry-button'));
    await tester.ensureVisible(retry);
    await tester.tap(retry);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('prediction-result')), findsOneWidget);
    expect(attempts, 2);
  });
  testWidgets('loading disables duplicate requests', (tester) async {
    final pending = Completer<http.Response>();
    await start(tester, (_) => pending.future);
    await tester.enterText(find.byKey(const Key('url-input')), 'example.com');
    final button = find.byKey(const Key('check-button'));
    await tester.ensureVisible(button);
    await tester.tap(button);
    await tester.pump();
    expect(tester.widget<FilledButton>(button).onPressed, isNull);
    expect(find.text('Đang phân tích…'), findsOneWidget);
    pending.complete(jsonResponse(predictionFixture()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('prediction-result')), findsOneWidget);
  });
  testWidgets('320px mobile layout has no overflow', (tester) async {
    tester.view.physicalSize = const Size(320, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await start(tester, (_) async => jsonResponse(predictionFixture()));
    await tester.enterText(find.byKey(const Key('url-input')), 'example.com');
    await check(tester);
    expect(tester.takeException(), isNull);
    final result = find.byKey(const Key('prediction-result'));
    expect(tester.getTopLeft(result).dy, greaterThanOrEqualTo(0));
    expect(tester.getBottomRight(result).dy, lessThanOrEqualTo(844));
  });
  testWidgets('phishing warning has explicit text, icon and red emphasis', (
    tester,
  ) async {
    await start(
      tester,
      (_) async =>
          jsonResponse({...predictionFixture(score: .9), 'label': 'phishing'}),
    );
    await tester.enterText(find.byKey(const Key('url-input')), 'example.com');
    await check(tester);
    final warningText = find.text('Có dấu hiệu phishing');
    expect(warningText, findsOneWidget);
    expect(tester.widget<Text>(warningText).style!.color, danger);
    expect(find.byIcon(Icons.warning_amber_rounded), findsOneWidget);
    expect(find.textContaining('Cân nhắc dừng truy cập'), findsOneWidget);
  });
  testWidgets(
    '200% text at 320px and reduced motion retain controls without overflow',
    (tester) async {
      tester.view.physicalSize = const Size(320, 844);
      tester.view.devicePixelRatio = 1;
      tester.platformDispatcher.textScaleFactorTestValue = 2;
      tester.platformDispatcher.accessibilityFeaturesTestValue =
          const FakeAccessibilityFeatures(disableAnimations: true);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      addTearDown(
        tester.platformDispatcher.clearAccessibilityFeaturesTestValue,
      );
      await start(tester, (_) async => jsonResponse(predictionFixture()));
      await tester.enterText(find.byKey(const Key('url-input')), 'example.com');
      await check(tester);
      expect(find.byKey(const Key('prediction-result')), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
  test('dark semantic text and control colors meet minimum contrast', () {
    double contrast(Color a, Color b) {
      final first = a.computeLuminance();
      final second = b.computeLuminance();
      return first > second
          ? (first + .05) / (second + .05)
          : (second + .05) / (first + .05);
    }

    for (final bg in [navy, surface, glassTop, dangerSurface, benignSurface]) {
      for (final fg in [ink, muted]) {
        expect(contrast(fg, bg), greaterThanOrEqualTo(4.5));
      }
    }
    expect(contrast(navy, teal), greaterThanOrEqualTo(4.5));
    expect(contrast(danger, dangerSurface), greaterThanOrEqualTo(4.5));
    expect(contrast(teal, benignSurface), greaterThanOrEqualTo(4.5));
    expect(contrast(controlBorder, navy), greaterThanOrEqualTo(3));
  });
}
