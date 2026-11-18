import 'package:flutter/material.dart';

import 'src/bootstrap.dart';
import 'src/home_page.dart';
import 'src/parity_page.dart';

void main() => runApp(const PhishGuardApp());

class PhishGuardApp extends StatelessWidget {
  const PhishGuardApp({super.key, this.bootstrap = bootstrapApp});

  /// Có thể thay trong test để dựng các trạng thái khởi tạo khác nhau.
  final Future<AppRuntime> Function() bootstrap;

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'PhishGuard VN',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(colorSchemeSeed: Colors.indigo, useMaterial3: true),
        home: _Boot(bootstrap: bootstrap),
      );
}

/// Nạp PSL, brand reference và Teacher v2 trước khi vào màn hình chính.
/// Lỗi bất kỳ -> màn hình lỗi; không bao giờ vào màn hình phân tích khi Teacher chưa nạp thành công.
class _Boot extends StatefulWidget {
  const _Boot({required this.bootstrap});

  final Future<AppRuntime> Function() bootstrap;

  @override
  State<_Boot> createState() => _BootState();
}

class _BootState extends State<_Boot> {
  late Future<AppRuntime> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.bootstrap();
  }

  void _retry() {
    final future = widget.bootstrap();

    setState(() {
      _future = future;
    });
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<AppRuntime>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Scaffold(
                body: Center(child: CircularProgressIndicator()));
          }
          if (snap.hasError) {
            return _BootError(error: snap.error!, onRetry: _retry);
          }
          final runtime = snap.data!;
          return HomePage(
            extractor: runtime.extractor,
            classifier: runtime.classifier,
            info: runtime.extractorInfo,
            teacherInfo: runtime.teacherInfo,
          );
        },
      );
}

class _BootError extends StatelessWidget {
  const _BootError({required this.error, required this.onRetry});

  final Object error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final extractorInfo = error is BootstrapFailure
        ? (error as BootstrapFailure).extractorInfo
        : null;
    return Scaffold(
      appBar: AppBar(title: const Text('Chưa sẵn sàng phân tích')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            key: const Key('boot_error'),
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Không khởi tạo được mô hình Teacher v2. Ứng dụng sẽ không đưa ra kết quả phân loại.',
              ),
              const SizedBox(height: 12),
              SelectableText(describeBootError(error)),
              const SizedBox(height: 16),
              FilledButton.icon(
                key: const Key('retry_button'),
                onPressed: onRetry,
                icon: const Icon(Icons.refresh),
                label: const Text('Thử lại'),
              ),
              if (extractorInfo != null) ...[
                const SizedBox(height: 8),
                OutlinedButton.icon(
                  key: const Key('open_parity_button'),
                  onPressed: () =>
                      Navigator.of(context).push(MaterialPageRoute<void>(
                    builder: (_) =>
                        ParityPage(extractor: extractorInfo.extractor),
                  )),
                  icon: const Icon(Icons.fact_check_outlined),
                  label:
                      const Text('Mở kiểm tra parity E2 (không phải dự đoán)'),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
