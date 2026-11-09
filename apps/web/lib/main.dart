import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';

import 'api_client.dart';

const ink = Color(0xFF142C35);
const teal = Color(0xFF087E78);
const muted = Color(0xFF60737B);
const line = Color(0xFFDFE7EA);

void main() => runApp(
  PhishGuardApp(
    api: PredictionApi(
      baseUrl: const String.fromEnvironment(
        'API_BASE_URL',
        defaultValue: 'http://127.0.0.1:8000',
      ),
    ),
  ),
);

class PhishGuardApp extends StatelessWidget {
  const PhishGuardApp({super.key, required this.api});
  final PredictionApi api;
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'PhishGuard VN — Kiểm tra URL',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      useMaterial3: true,
      fontFamily: 'GuardRoboto',
      colorScheme: ColorScheme.fromSeed(seedColor: teal, surface: Colors.white),
      scaffoldBackgroundColor: const Color(0xFFF4F7F8),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: const Color(0xFFFAFCFC),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: line),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: line),
        ),
        contentPadding: const EdgeInsets.all(18),
      ),
    ),
    home: UrlCheckPage(api: api),
  );
}

class UrlCheckPage extends StatefulWidget {
  const UrlCheckPage({super.key, required this.api});
  final PredictionApi api;
  @override
  State<UrlCheckPage> createState() => _UrlCheckPageState();
}

class _UrlCheckPageState extends State<UrlCheckPage> {
  final _form = GlobalKey<FormState>();
  final _feedback = GlobalKey();
  final _url = TextEditingController();
  late final SemanticsHandle _semantics;
  Prediction? _prediction;
  ApiFailure? _failure;
  bool _busy = false;
  bool? _ready;
  bool _healthChecked = false;

  @override
  void initState() {
    super.initState();
    _semantics = SemanticsBinding.instance.ensureSemantics();
    _health();
  }

  @override
  void dispose() {
    _semantics.dispose();
    _url.dispose();
    widget.api.close();
    super.dispose();
  }

  Future<void> _health() async {
    bool? ready;
    try {
      ready = await widget.api.health();
    } on ApiFailure {
      ready = null;
    }
    if (mounted) {
      setState(() {
        _ready = ready;
        _healthChecked = true;
      });
    }
  }

  Future<void> _submit() async {
    if (_busy || !_form.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _prediction = null;
      _failure = null;
    });
    try {
      final result = await widget.api.predict(_url.text.trim());
      if (mounted) {
        setState(() {
          _prediction = result;
          _ready = true;
          _healthChecked = true;
        });
      }
    } on ApiFailure catch (e) {
      if (mounted) setState(() => _failure = e);
      _health();
    } finally {
      if (mounted) {
        setState(() => _busy = false);
        WidgetsBinding.instance.addPostFrameCallback((_) {
          final feedbackContext = _feedback.currentContext;
          if (mounted &&
              feedbackContext != null &&
              MediaQuery.sizeOf(context).width < 860) {
            Scrollable.ensureVisible(
              feedbackContext,
              duration: const Duration(milliseconds: 250),
              alignment: .15,
            );
          }
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(
      child: SingleChildScrollView(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1180),
            child: Padding(
              padding: EdgeInsets.symmetric(
                horizontal: MediaQuery.sizeOf(context).width < 600 ? 20 : 40,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _header(),
                  const Divider(color: line, height: 1),
                  LayoutBuilder(
                    builder: (context, constraints) {
                      final desktop = constraints.maxWidth >= 860;
                      return Padding(
                        padding: EdgeInsets.symmetric(
                          vertical: desktop ? 72 : 32,
                        ),
                        child: desktop
                            ? Row(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Expanded(flex: 9, child: _hero(true)),
                                  const SizedBox(width: 56),
                                  Expanded(flex: 11, child: _card()),
                                ],
                              )
                            : Column(
                                crossAxisAlignment: CrossAxisAlignment.stretch,
                                children: [
                                  _hero(false),
                                  const SizedBox(height: 28),
                                  _card(),
                                ],
                              ),
                      );
                    },
                  ),
                  const Divider(color: line, height: 1),
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 24),
                    child: Wrap(
                      spacing: 20,
                      runSpacing: 10,
                      children: [
                        Text(
                          'PhishGuardVN · Đồ án học máy',
                          style: TextStyle(color: muted, fontSize: 12),
                        ),
                        Text(
                          'Không mở trang đích. Không lưu lịch sử URL.',
                          style: TextStyle(color: muted, fontSize: 12),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    ),
  );

  Widget _header() => Padding(
    padding: const EdgeInsets.symmetric(vertical: 24),
    child: Row(
      children: [
        Container(
          width: 42,
          height: 42,
          decoration: BoxDecoration(
            color: teal,
            borderRadius: BorderRadius.circular(13),
          ),
          child: const Icon(
            Icons.shield_outlined,
            color: Colors.white,
            size: 25,
          ),
        ),
        const SizedBox(width: 11),
        const Text(
          'PhishGuard',
          style: TextStyle(
            fontSize: 21,
            fontWeight: FontWeight.w700,
            color: ink,
            letterSpacing: -.6,
          ),
        ),
        const SizedBox(width: 7),
        const Text(
          'VN',
          style: TextStyle(
            color: teal,
            fontWeight: FontWeight.w700,
            fontSize: 12,
          ),
        ),
        const Spacer(),
        Semantics(
          liveRegion: true,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 7,
                height: 7,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: _ready == true ? teal : const Color(0xFFA07B42),
                ),
              ),
              const SizedBox(width: 7),
              Text(
                !_healthChecked
                    ? 'Đang kết nối'
                    : _ready == true
                    ? 'API sẵn sàng'
                    : _ready == false
                    ? 'API chờ model'
                    : 'Chưa kết nối',
                style: const TextStyle(fontSize: 11, color: muted),
              ),
            ],
          ),
        ),
      ],
    ),
  );

  Widget _hero(bool desktop) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
        decoration: BoxDecoration(
          color: const Color(0xFFE3F1EF),
          borderRadius: BorderRadius.circular(20),
        ),
        child: const Text(
          'KIỂM TRA URL',
          style: TextStyle(
            color: teal,
            fontSize: 10,
            fontWeight: FontWeight.w700,
            letterSpacing: 1.5,
          ),
        ),
      ),
      const SizedBox(height: 22),
      Text(
        'Nhìn kỹ đường dẫn.\nCẩn trọng trước khi mở.',
        style: TextStyle(
          fontSize: desktop ? 44 : 32,
          height: 1.16,
          letterSpacing: -1.7,
          fontWeight: FontWeight.w700,
          color: ink,
        ),
      ),
      const SizedBox(height: 22),
      const Text(
        'Phân tích dấu hiệu phishing từ cấu trúc URL bằng mô hình học máy, trước khi bạn quyết định truy cập.',
        style: TextStyle(color: muted, fontSize: 15, height: 1.7),
      ),
      const SizedBox(height: 26),
      const Wrap(
        spacing: 18,
        runSpacing: 12,
        children: [
          _TrustNote(icon: Icons.link_off_rounded, label: 'Không mở website'),
          _TrustNote(
            icon: Icons.history_toggle_off_rounded,
            label: 'Không lưu lịch sử',
          ),
        ],
      ),
      if (desktop) ...[
        const SizedBox(height: 40),
        const Text(
          'CÁCH THỨC HOẠT ĐỘNG',
          style: TextStyle(
            fontSize: 10,
            letterSpacing: 1.5,
            color: muted,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 16),
        const Text(
          '01   Nhập đường dẫn\n02   Mô hình phân tích đặc trưng\n03   Xem kết quả và cân nhắc rủi ro',
          style: TextStyle(color: muted, fontSize: 13, height: 2.1),
        ),
      ],
    ],
  );

  Widget _card() => Container(
    padding: EdgeInsets.all(MediaQuery.sizeOf(context).width < 600 ? 22 : 30),
    decoration: BoxDecoration(
      color: Colors.white,
      border: Border.all(color: line),
      borderRadius: BorderRadius.circular(22),
      boxShadow: [
        BoxShadow(
          color: ink.withValues(alpha: .04),
          blurRadius: 28,
          offset: const Offset(0, 12),
        ),
      ],
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(
          'Kiểm tra một đường dẫn',
          style: TextStyle(
            fontSize: 22,
            fontWeight: FontWeight.w700,
            color: ink,
            letterSpacing: -.5,
          ),
        ),
        const SizedBox(height: 8),
        const Text(
          'Dán URL bạn muốn kiểm tra bên dưới.',
          style: TextStyle(color: muted, fontSize: 13, height: 1.5),
        ),
        const SizedBox(height: 24),
        Form(
          key: _form,
          child: TextFormField(
            key: const Key('url-input'),
            controller: _url,
            readOnly: _busy,
            keyboardType: TextInputType.url,
            autocorrect: false,
            enableSuggestions: false,
            textInputAction: TextInputAction.go,
            decoration: const InputDecoration(
              labelText: 'URL cần kiểm tra',
              hintText: 'https://example.com',
              prefixIcon: Icon(Icons.link_rounded, size: 20),
            ),
            style: const TextStyle(fontSize: 14),
            validator: (text) {
              if (text == null || text.trim().isEmpty) {
                return 'Vui lòng nhập một URL.';
              }
              if (text.runes.length > 4096) return 'URL tối đa 4096 ký tự.';
              return null;
            },
            onChanged: (_) {
              if (_prediction != null || _failure != null) {
                setState(() {
                  _prediction = null;
                  _failure = null;
                });
              }
            },
            onFieldSubmitted: (_) => _submit(),
          ),
        ),
        const SizedBox(height: 10),
        const Text(
          'Có thể nhập tên miền không có http:// hoặc https://.',
          style: TextStyle(fontSize: 11, color: muted, height: 1.5),
        ),
        const SizedBox(height: 20),
        FilledButton(
          key: const Key('check-button'),
          onPressed: _busy ? null : _submit,
          style: FilledButton.styleFrom(
            backgroundColor: teal,
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(vertical: 20),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            mainAxisSize: MainAxisSize.min,
            children: [
              if (_busy) ...[
                const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2, color: teal),
                ),
                const SizedBox(width: 10),
              ],
              Text(
                _busy ? 'Đang phân tích…' : 'Kiểm tra URL',
                style: const TextStyle(
                  fontWeight: FontWeight.w700,
                  fontSize: 14,
                ),
              ),
              if (!_busy) ...[
                const SizedBox(width: 10),
                const Icon(Icons.arrow_forward_rounded, size: 18),
              ],
            ],
          ),
        ),
        if (_busy) ...[
          const SizedBox(height: 20),
          Semantics(
            liveRegion: true,
            child: const Text(
              'Đang phân tích cấu trúc URL…',
              style: TextStyle(color: muted, fontSize: 12),
            ),
          ),
        ],
        if (_prediction != null || _failure != null) ...[
          const SizedBox(height: 24),
          KeyedSubtree(
            key: _feedback,
            child: _prediction != null
                ? _result(_prediction!)
                : _error(_failure!),
          ),
        ],
        const SizedBox(height: 24),
        const Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(Icons.info_outline_rounded, size: 15, color: muted),
            SizedBox(width: 8),
            Expanded(
              child: Text(
                'Kết quả chỉ mang tính tham khảo, không phải chứng nhận URL an toàn. Không nhập đường dẫn chứa mật khẩu hoặc token riêng tư.',
                style: TextStyle(color: muted, fontSize: 11, height: 1.6),
              ),
            ),
          ],
        ),
      ],
    ),
  );

  Widget _result(Prediction p) {
    final flagged = p.label == 'phishing';
    final color = flagged ? const Color(0xFF9C5A16) : teal;
    final probability = p.scoreKind == 'probability';
    return Semantics(
      liveRegion: true,
      child: Container(
        key: const Key('prediction-result'),
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: flagged ? const Color(0xFFFFF3E5) : const Color(0xFFEAF5F1),
          borderRadius: BorderRadius.circular(14),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(
                  flagged
                      ? Icons.warning_amber_rounded
                      : Icons.manage_search_rounded,
                  color: color,
                  size: 22,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    flagged
                        ? 'Có dấu hiệu phishing'
                        : 'Chưa phát hiện dấu hiệu phishing',
                    style: TextStyle(
                      color: color,
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                      height: 1.4,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              'Nhãn mô hình: ${p.label}',
              style: const TextStyle(fontSize: 12, color: muted),
            ),
            const SizedBox(height: 20),
            Text(
              probability ? 'Điểm phishing' : 'Biên quyết định',
              style: const TextStyle(color: muted, fontSize: 11),
            ),
            const SizedBox(height: 4),
            Text(
              probability
                  ? '${(p.score * 100).toStringAsFixed(2)}%'
                  : p.score.toStringAsFixed(4),
              key: const Key('score-value'),
              style: TextStyle(
                color: color,
                fontSize: 30,
                fontWeight: FontWeight.w700,
                letterSpacing: -.7,
              ),
            ),
            Text(
              probability
                  ? 'predict_proba · chưa hiệu chuẩn nguy cơ thực tế'
                  : 'Decision margin · không phải xác suất',
              style: const TextStyle(color: muted, fontSize: 11, height: 1.5),
            ),
            const SizedBox(height: 18),
            const Divider(color: line, height: 1),
            const SizedBox(height: 14),
            const Text(
              'MODEL',
              style: TextStyle(
                fontSize: 9,
                fontWeight: FontWeight.w700,
                letterSpacing: 1.2,
                color: muted,
              ),
            ),
            const SizedBox(height: 5),
            Text(p.model, style: const TextStyle(fontSize: 12, color: ink)),
            if (p.protocol == 'week5_e1_audit') ...[
              const SizedBox(height: 6),
              const Text(
                'E1 lexical hiện tại · chưa phải Teacher v1',
                style: TextStyle(fontSize: 10, color: muted),
              ),
            ],
            const SizedBox(height: 12),
            Text(
              flagged
                  ? 'Cân nhắc dừng truy cập và xác minh nguồn gửi đường dẫn.'
                  : 'Nhãn benign không bảo đảm website an toàn. Vẫn cần kiểm tra nguồn và nội dung.',
              style: const TextStyle(fontSize: 11, height: 1.6, color: muted),
            ),
          ],
        ),
      ),
    );
  }

  Widget _error(ApiFailure failure) => Semantics(
    liveRegion: true,
    child: Container(
      key: const Key('prediction-error'),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF3E9),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Chưa thể kiểm tra đường dẫn',
            style: TextStyle(
              fontWeight: FontWeight.w700,
              color: Color(0xFF975523),
              fontSize: 15,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            failure.message,
            style: const TextStyle(color: muted, fontSize: 12, height: 1.6),
          ),
          const SizedBox(height: 10),
          TextButton.icon(
            key: const Key('retry-button'),
            onPressed: _submit,
            icon: const Icon(Icons.refresh_rounded, size: 17),
            label: const Text('Thử lại'),
          ),
        ],
      ),
    ),
  );
}

class _TrustNote extends StatelessWidget {
  const _TrustNote({required this.icon, required this.label});
  final IconData icon;
  final String label;
  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Icon(icon, size: 15, color: teal),
      const SizedBox(width: 6),
      Text(label, style: const TextStyle(color: muted, fontSize: 11)),
    ],
  );
}
