import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/testing.dart';
import 'package:phishguard_web/api_client.dart';
import 'package:phishguard_web/capture_image.dart';
import 'package:phishguard_web/capture_urls.dart';
import 'package:phishguard_web/main.dart';

import 'api_client_test.dart' show jsonResponse, predictionFixture;

void main() {
  test('detects complete URLs and preserves message offsets and case', () {
    const message =
        '📦 Kiểm tra (https://ExAmPle.org/Login?Q=A.) rồi mở ‘napas.com.vn’.';
    final links = captureUrls(message);
    expect(links.map((link) => link.url), [
      'https://ExAmPle.org/Login?Q=A.',
      'napas.com.vn',
    ]);
    expect(
      links.map((link) => message.substring(link.start, link.end)),
      links.map((link) => link.url),
    );
    expect(links.map((link) => link.host), ['example.org', 'napas.com.vn']);
  });

  test('skips email, embedded credentials and unsupported schemes', () {
    final links = captureUrls(
      'contact@example.org ftp://example.org mailto:example.net '
      'https://name:secret@example.org example.com:bad https://example.net:443/',
    );
    expect(links.map((link) => link.url), ['https://example.net:443/']);
  });

  test('a link cut by the input limit is not offered', () {
    final message = 'x' * (messageLimit - 20) + ' https://example.org/path';
    expect(captureUrls(message), isEmpty);
  });

  test(
    'compares actual host labels and preserves uncertainty for IDN variants',
    () {
      expect(captureHost('https://EXAMPLE.org.:8443/docs'), 'example.org');
      expect(
        compareCaptureHosts('example.org', 'example.org'),
        HostComparison.same,
      );
      expect(
        compareCaptureHosts('sub.example.org', 'example.org'),
        HostComparison.different,
      );
      expect(
        compareCaptureHosts('bücher.de', 'xn--bcher-kva.de'),
        HostComparison.reviewIdna,
      );
    },
  );

  test(
    'reads a real QR and its bounds from the redacted comparison fixture',
    () {
      final image = readCaptureImage(
        File('test/fixtures/message_image_compare.png').readAsBytesSync(),
      );
      expect(image.qr, 'https://example.com/Login?Q=A');
      expect(image.width, 880);
      expect(image.height, 740);
      expect(image.qrRegion!.left, greaterThan(500));
      expect(image.qrRegion!.top, greaterThan(400));
    },
  );

  testWidgets('message selection fills the normal form before any POST', (
    tester,
  ) async {
    final posted = <String>[];
    final api = PredictionApi(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        if (request.method == 'GET') return jsonResponse({'model_ready': true});
        posted.add(request.body);
        return jsonResponse(predictionFixture());
      }),
    );
    await tester.pumpWidget(PhishGuardApp(api: api));
    await tester.pumpAndSettle();
    final action = find.byKey(const Key('capture-message'));
    await tester.ensureVisible(action);
    await tester.tap(action);
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const Key('message-input')),
      'Nội dung riêng tư. Kiểm tra (https://example.org/Login?Q=A).',
    );
    await tester.pumpAndSettle();
    expect(posted, isEmpty);
    await tester.tap(find.text('example.org'));
    await tester.pumpAndSettle();

    final field = tester.widget<TextFormField>(
      find.byKey(const Key('url-input')),
    );
    expect(field.controller!.text, 'https://example.org/Login?Q=A');
    expect(find.byKey(const Key('message-input')), findsNothing);
    expect(posted, isEmpty);
    final check = find.byKey(const Key('check-button'));
    await tester.ensureVisible(check);
    await tester.tap(check);
    await tester.pumpAndSettle();
    expect(posted, ['{"url":"https://example.org/Login?Q=A"}']);
  });

  testWidgets('image mode keeps QR usable when OCR cannot load', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 720);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final api = PredictionApi(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        expect(request.method, 'GET');
        return jsonResponse({'model_ready': true});
      }),
    );
    await tester.pumpWidget(
      PhishGuardApp(
        api: api,
        imagePicker: () async =>
            File('test/fixtures/message_image_compare.png').readAsBytesSync(),
      ),
    );
    await tester.pumpAndSettle();
    final action = find.byKey(const Key('capture-image'));
    await tester.ensureVisible(action);
    await tester.tap(action);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('capture-image-select')));
    await tester.pump();
    await tester.runAsync(
      () async => Future<void>.delayed(const Duration(milliseconds: 350)),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('Bộ đọc chữ chưa khả dụng'), findsOneWidget);
    final printed = find.byKey(const Key('capture-printed-url'));
    await tester.ensureVisible(printed);
    await tester.enterText(printed, 'example.org');
    await tester.pumpAndSettle();
    expect(find.text('Hai địa chỉ máy chủ khác nhau'), findsOneWidget);
    await tester.enterText(printed, 'EXAMPLE.com');
    await tester.pumpAndSettle();
    expect(find.text('Cùng địa chỉ máy chủ'), findsOneWidget);
    final use = find.byKey(const Key('capture-use-qr'));
    await tester.ensureVisible(use);
    await tester.tap(use);
    await tester.pumpAndSettle();
    final field = tester.widget<TextFormField>(
      find.byKey(const Key('url-input')),
    );
    expect(field.controller!.text, 'https://example.com/Login?Q=A');
    expect(tester.takeException(), isNull);
  });
}
