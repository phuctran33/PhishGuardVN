import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:phishguard_android/src/home_page.dart';
import 'package:phishguard_features/phishguard_features.dart';

E2Extractor _extractor() {
  final psl = PublicSuffixList.fromRules(['com', 'vn', 'com.vn', 'top']);
  const csv = 'brand_id,canonical_name,aliases,official_domains,official_suffixes,typo_ignore_tokens\n'
      'vcb,Vietcombank,VCB,vietcombank.com.vn,,\n';
  return E2Extractor(psl, BrandReference.fromBytes(Uint8List.fromList(utf8.encode(csv))));
}

Future<void> _pump(WidgetTester tester) async {
  await tester.pumpWidget(MaterialApp(home: HomePage(extractor: _extractor())));
}

void main() {
  testWidgets('URL hợp lệ hiển thị đủ 20 dòng đặc trưng', (tester) async {
    await _pump(tester);
    await tester.enterText(find.byKey(const Key('url_field')), 'https://vietcombank-login.top/verify');
    await tester.tap(find.byKey(const Key('analyze_button')));
    await tester.pump();
    expect(find.byKey(const Key('result_ok')), findsOneWidget);
    for (final name in e2FeatureOrder) {
      expect(find.byKey(Key('feature_row_$name')), findsOneWidget, reason: name);
    }
  });

  testWidgets('URL lỗi báo "Không phân loại được", không có dòng đặc trưng', (tester) async {
    await _pump(tester);
    await tester.enterText(find.byKey(const Key('url_field')), 'https://example.com:99999/');
    await tester.tap(find.byKey(const Key('analyze_button')));
    await tester.pump();
    expect(find.byKey(const Key('result_invalid')), findsOneWidget);
    expect(find.text('Không phân loại được'), findsOneWidget);
    expect(find.byKey(const Key('feature_row_url_len')), findsNothing);
  });

  testWidgets('ô trống không làm app lỗi', (tester) async {
    await _pump(tester);
    await tester.tap(find.byKey(const Key('analyze_button')));
    await tester.pump();
    expect(find.byKey(const Key('result_invalid')), findsOneWidget);
  });
}
