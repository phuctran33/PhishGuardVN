import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:phishguard_android/main.dart';
import 'package:phishguard_android/src/bootstrap.dart';
import 'package:phishguard_android/src/extractor_loader.dart';
import 'package:phishguard_android/src/home_page.dart';
import 'package:phishguard_android/src/parity_page.dart';
import 'package:phishguard_android/src/teacher_contract.dart';
import 'package:phishguard_android/src/teacher_loader.dart';
import 'package:phishguard_android/src/url_classifier.dart';
import 'package:phishguard_features/phishguard_features.dart';

import 'support/map_bundle.dart';

E2Extractor _extractor() {
  final psl = PublicSuffixList.fromRules(['com', 'vn', 'com.vn', 'top']);
  const csv = 'brand_id,canonical_name,aliases,official_domains,official_suffixes,typo_ignore_tokens\n'
      'vcb,Vietcombank,VCB,vietcombank.com.vn,,\n';
  return E2Extractor(psl, BrandReference.fromBytes(Uint8List.fromList(utf8.encode(csv))));
}

/// Lớp giả đi qua đúng đoạn bảo vệ của GuardedClassifier; chỉ [infer] là giả.
class _FakeClassifier extends GuardedClassifier {
  _FakeClassifier(super.extractor, {this.phishing = true, this.failWith});

  final bool phishing;
  final Object? failWith;
  int inferCalls = 0;

  @override
  Classified infer(String url) {
    inferCalls++;
    final error = failWith;
    if (error != null) throw error;
    return Classified(
      phishing: phishing,
      score: phishing ? 0.91 : 0.12,
      threshold: teacherThreshold,
      decisionRule: teacherDecisionRule,
      modelVersion: teacherModelVersion,
    );
  }
}

const _teacherInfo = TeacherRuntimeInfo(
  modelVersion: teacherModelVersion,
  threshold: teacherThreshold,
  decisionRule: teacherDecisionRule,
  sourceBundleSha256: teacherSourceBundleSha256,
  svmBytes: 10,
  modelBytes: 20,
  timings: TeacherLoadTimings(
    read: Duration(milliseconds: 1),
    hash: Duration(milliseconds: 2),
    parse: Duration(milliseconds: 3),
    build: Duration(milliseconds: 4),
  ),
);

Future<void> _pumpHome(WidgetTester tester, E2Extractor extractor, UrlClassifier classifier) async {
  await tester.pumpWidget(MaterialApp(
    home: HomePage(extractor: extractor, classifier: classifier, teacherInfo: _teacherInfo),
  ));
}

Future<void> _analyze(WidgetTester tester, String url) async {
  await tester.enterText(find.byKey(const Key('url_field')), url);
  await tester.tap(find.byKey(const Key('analyze_button')));
  await tester.pump();
}

AppRuntime _runtime(E2Extractor extractor, UrlClassifier classifier) => AppRuntime(
      extractorInfo: LoadedExtractor(extractor, 4, 1, 'a' * 64),
      teacherInfo: _teacherInfo,
      classifier: classifier,
    );

Map<String, dynamic> _parityCase(E2Extractor extractor, String name, String url) {
  final r = extractor.extract(url);
  final p = r.parsed;
  return {
    'name': name,
    'group': 'test',
    'url': url,
    'parsed': {
      'is_valid': p.isValid,
      'error_reason': p.errorReason,
      'hostname': p.hostname,
      'registrable_domain': p.registrableDomain,
      'subdomain': p.subdomain,
      'path': p.path,
      'query': p.query,
      'is_ip': p.isIp,
    },
    'expected': r.isClassifiable ? r.toMap() : {for (final n in e2FeatureOrder) n: null},
  };
}

void main() {
  group('màn hình chính', () {
    testWidgets('phishing: hiển thị nhãn, điểm, ngưỡng, quy tắc, phiên bản và cảnh báo', (tester) async {
      final extractor = _extractor();
      final classifier = _FakeClassifier(extractor, phishing: true);
      await _pumpHome(tester, extractor, classifier);
      await _analyze(tester, 'https://vietcombank-login.top/verify');

      expect(find.byKey(const Key('result_teacher')), findsOneWidget);
      expect(find.text('Có dấu hiệu lừa đảo'), findsOneWidget);
      expect(find.text('Chưa phát hiện dấu hiệu lừa đảo'), findsNothing);
      expect(find.textContaining('0.910000'), findsWidgets);
      expect(find.textContaining('0.6945740700635259'), findsWidgets);
      expect(find.textContaining('score >= threshold'), findsWidgets);
      expect(find.textContaining(teacherModelVersion), findsWidgets);
      expect(find.textContaining('chưa được hiệu chuẩn'), findsOneWidget);
      expect(find.textContaining('%'), findsNothing);
      expect(classifier.inferCalls, 1);
    });

    testWidgets('benign: nhãn đúng, không khẳng định an toàn', (tester) async {
      final extractor = _extractor();
      await _pumpHome(tester, extractor, _FakeClassifier(extractor, phishing: false));
      await _analyze(tester, 'https://www.vietcombank.com.vn/');

      expect(find.byKey(const Key('result_teacher')), findsOneWidget);
      expect(find.text('Chưa phát hiện dấu hiệu lừa đảo'), findsOneWidget);
      expect(find.text('Có dấu hiệu lừa đảo'), findsNothing);
      expect(find.textContaining('không có nghĩa là website chắc chắn an toàn'), findsOneWidget);
      expect(find.textContaining('%'), findsNothing);
    });

    testWidgets('chi tiết E2: mở ra thấy đủ 20 dòng đặc trưng', (tester) async {
      final extractor = _extractor();
      await _pumpHome(tester, extractor, _FakeClassifier(extractor));
      await _analyze(tester, 'https://vietcombank-login.top/verify');

      expect(find.byKey(const Key('feature_row_url_len')), findsNothing); // đang thu gọn
      await tester.ensureVisible(find.byKey(const Key('e2_details_tile')));
      await tester.tap(find.byKey(const Key('e2_details_tile')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('result_ok')), findsOneWidget);
      for (final name in e2FeatureOrder) {
        expect(find.byKey(Key('feature_row_$name')), findsOneWidget, reason: name);
      }
    });

    testWidgets('URL không phân loại được: báo lỗi, không gọi mô hình, không có dòng đặc trưng', (tester) async {
      final extractor = _extractor();
      final classifier = _FakeClassifier(extractor);
      await _pumpHome(tester, extractor, classifier);
      await _analyze(tester, 'https://example.com:99999/');

      expect(find.byKey(const Key('result_invalid')), findsOneWidget);
      expect(find.text('Không phân loại được'), findsOneWidget);
      expect(find.byKey(const Key('result_teacher')), findsNothing);
      expect(find.byKey(const Key('e2_details_tile')), findsNothing);
      expect(find.byKey(const Key('feature_row_url_len')), findsNothing);
      expect(classifier.inferCalls, 0);
    });

    testWidgets('ô trống bị từ chối, không gọi mô hình', (tester) async {
      final extractor = _extractor();
      final classifier = _FakeClassifier(extractor);
      await _pumpHome(tester, extractor, classifier);
      await tester.tap(find.byKey(const Key('analyze_button')));
      await tester.pump();

      expect(find.byKey(const Key('result_invalid')), findsOneWidget);
      expect(find.text('Đầu vào không hợp lệ'), findsOneWidget);
      expect(classifier.inferCalls, 0);
    });

    testWidgets('khoảng trắng hai đầu bị từ chối, không trim ngầm', (tester) async {
      final extractor = _extractor();
      final classifier = _FakeClassifier(extractor);
      await _pumpHome(tester, extractor, classifier);
      await _analyze(tester, ' https://example.com/ ');

      expect(find.byKey(const Key('result_invalid')), findsOneWidget);
      expect(find.textContaining('không tự cắt bỏ'), findsOneWidget);
      expect(find.byKey(const Key('result_teacher')), findsNothing);
      expect(classifier.inferCalls, 0);
    });

    testWidgets('lỗi suy luận không bao giờ hiện như một nhãn', (tester) async {
      final extractor = _extractor();
      await _pumpHome(tester, extractor, _FakeClassifier(extractor, failWith: StateError('hỏng')));
      await _analyze(tester, 'https://vietcombank-login.top/verify');

      expect(find.byKey(const Key('result_error')), findsOneWidget);
      expect(find.text('Lỗi khi chạy mô hình'), findsOneWidget);
      expect(find.byKey(const Key('result_teacher')), findsNothing);
      expect(find.text('Có dấu hiệu lừa đảo'), findsNothing);
      expect(find.text('Chưa phát hiện dấu hiệu lừa đảo'), findsNothing);
    });

    testWidgets('chân trang hiển thị phiên bản Teacher và thời gian nạp', (tester) async {
      final extractor = _extractor();
      await _pumpHome(tester, extractor, _FakeClassifier(extractor));

      expect(find.textContaining('Teacher $teacherModelVersion'), findsOneWidget);
      expect(find.textContaining('nạp 10 ms'), findsOneWidget);
    });
  });

  group('khởi tạo ứng dụng', () {
    testWidgets('khởi tạo thành công -> vào màn hình phân tích', (tester) async {
      final extractor = _extractor();
      await tester.pumpWidget(PhishGuardApp(
        bootstrap: () async => _runtime(extractor, _FakeClassifier(extractor)),
      ));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('analyze_button')), findsOneWidget);
      expect(find.byKey(const Key('boot_error')), findsNothing);
    });

    testWidgets('Teacher không nạp được -> màn hình lỗi, không có ô phân tích', (tester) async {
      await tester.pumpWidget(PhishGuardApp(
        bootstrap: () async => throw const BootstrapFailure(
          TeacherLoadException(TeacherLoadFailure.missingAsset, 'thiếu asset thử nghiệm'),
        ),
      ));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('boot_error')), findsOneWidget);
      expect(find.byKey(const Key('retry_button')), findsOneWidget);
      expect(find.byKey(const Key('url_field')), findsNothing);
      expect(find.byKey(const Key('analyze_button')), findsNothing);
      expect(find.byKey(const Key('open_parity_button')), findsNothing);
      expect(find.textContaining('sync_assets.sh'), findsWidgets);
    });

    testWidgets('Thử lại: lần sau thành công thì vào màn hình phân tích', (tester) async {
      final extractor = _extractor();
      var calls = 0;
      await tester.pumpWidget(PhishGuardApp(
        bootstrap: () async {
          calls++;
          if (calls == 1) {
            throw const BootstrapFailure(
              TeacherLoadException(TeacherLoadFailure.hashMismatch, 'lệch thử nghiệm'),
            );
          }
          return _runtime(extractor, _FakeClassifier(extractor));
        },
      ));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('analyze_button')), findsNothing);

      await tester.tap(find.byKey(const Key('retry_button')));
      await tester.pumpAndSettle();
      expect(calls, 2);
      expect(find.byKey(const Key('analyze_button')), findsOneWidget);
    });

    testWidgets('extractor đã nạp: màn hình lỗi cho mở parity E2 (không phải dự đoán)', (tester) async {
      final extractor = _extractor();
      await tester.pumpWidget(PhishGuardApp(
        bootstrap: () async => throw BootstrapFailure(
          const TeacherLoadException(TeacherLoadFailure.contractMismatch, 'sai hợp đồng thử nghiệm'),
          extractorInfo: LoadedExtractor(extractor, 4, 1, 'a' * 64),
        ),
      ));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('analyze_button')), findsNothing);
      await tester.tap(find.byKey(const Key('open_parity_button')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('run_parity_button')), findsOneWidget);
    });
  });

  group('parity E2 không bị hồi quy', () {
    testWidgets('trang parity vẫn chạy bộ ca và báo khớp', (tester) async {
      final extractor = _extractor();
      final fixture = {
        'tolerance': 1e-6,
        'cases': [
          _parityCase(extractor, 'ok', 'https://vietcombank-login.top/verify'),
          _parityCase(extractor, 'invalid', 'https://example.com:99999/'),
        ],
      };
      final bundle = MapBundle({
        'assets/mobile_parity_cases.json': Uint8List.fromList(utf8.encode(jsonEncode(fixture))),
      });
      await tester.pumpWidget(MaterialApp(home: ParityPage(extractor: extractor, bundle: bundle)));
      await tester.tap(find.byKey(const Key('run_parity_button')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('parity_result')), findsOneWidget);
      expect(find.textContaining('2/2 ca khớp'), findsWidgets);
    });
  });
}
