import 'dart:ui' show ImageFilter;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';

import 'api_client.dart';
import 'qr_image.dart';

// Semantic tokens: design-system/phishguardvn/MASTER.md.
const navy = Color(0xFF081321);
const surface = Color(0xFF132536);
const ink = Color(0xFFEDF5FC);
const teal = Color(0xFF65DECF);
const muted = Color(0xFFADC0D0);
const line = Color(0xFF385266);
const controlBorder = Color(0xFF668598);
const danger = Color(0xFFFF9BA3);
const dangerSurface = Color(0xFF34232F);
const benignSurface = Color(0xFF133534);
const warning = Color(0xFFEBC283);

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
  const PhishGuardApp({super.key, required this.api, this.imagePicker});
  final PredictionApi api;
  final Future<Uint8List?> Function()? imagePicker;
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'PhishGuard VN — Kiểm tra URL',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      useMaterial3: true,
      fontFamily: 'GuardRoboto',
      brightness: Brightness.dark,
      colorScheme: const ColorScheme.dark(
        primary: teal,
        onPrimary: navy,
        surface: surface,
        onSurface: ink,
        onSurfaceVariant: muted,
        error: danger,
        onError: navy,
        outline: line,
      ),
      scaffoldBackgroundColor: navy,
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(minimumSize: const Size(48, 48)),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: navy,
        labelStyle: const TextStyle(color: muted),
        hintStyle: const TextStyle(color: muted),
        prefixIconColor: muted,
        errorMaxLines: 3,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: controlBorder),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: controlBorder),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: teal, width: 2),
        ),
        contentPadding: const EdgeInsets.all(18),
      ),
    ),
    home: UrlCheckPage(api: api, imagePicker: imagePicker),
  );
}

class UrlCheckPage extends StatefulWidget {
  const UrlCheckPage({super.key, required this.api, this.imagePicker});
  final PredictionApi api;
  final Future<Uint8List?> Function()? imagePicker;
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
  int _revision = 0;
  String _inputText = '';
  Inspection? _inspection;
  ApiFailure? _inspectionFailure;
  bool _inspecting = false;
  bool _qrBusy = false;
  String? _qrCandidate, _qrFailure;

  @override
  void initState() {
    super.initState();
    _semantics = SemanticsBinding.instance.ensureSemantics();
    _url.addListener(_inputChanged);
    _health();
  }

  @override
  void dispose() {
    _semantics.dispose();
    _url.removeListener(_inputChanged);
    _url.dispose();
    widget.api.close();
    super.dispose();
  }

  void _inputChanged() {
    // Controller notifications also include selection/focus changes. Those do
    // not invalidate a response for the same URL.
    if (_url.text == _inputText) return;
    _inputText = _url.text;
    _revision++;
    if (_prediction == null &&
        _failure == null &&
        _inspection == null &&
        _inspectionFailure == null &&
        _qrCandidate == null &&
        _qrFailure == null) {
      return;
    }
    setState(() {
      _prediction = null;
      _failure = null;
      _inspection = null;
      _inspectionFailure = null;
      _qrCandidate = null;
      _qrFailure = null;
    });
  }

  Future<void> _pickQr() async {
    if (_qrBusy || _busy) return;
    final revision = _revision;
    setState(() {
      _qrBusy = true;
      _qrFailure = null;
      _qrCandidate = null;
    });
    try {
      final bytes = await (widget.imagePicker ?? chooseQrImage)();
      if (bytes == null) return;
      final candidate = await compute(decodeQrImage, bytes);
      if (mounted && revision == _revision) {
        setState(() => _qrCandidate = candidate);
      }
    } on QrFailure catch (e) {
      if (mounted && revision == _revision) {
        setState(() => _qrFailure = e.message);
      }
    } catch (_) {
      if (mounted && revision == _revision) {
        setState(
          () => _qrFailure = 'Không thể chọn hoặc đọc ảnh. Hãy chọn ảnh khác.',
        );
      }
    } finally {
      if (mounted) setState(() => _qrBusy = false);
    }
  }

  Future<void> _inspect() async {
    if (_inspecting || !_form.currentState!.validate()) return;
    final revision = _revision;
    final url = _url.text.trim();
    setState(() {
      _inspecting = true;
      _inspection = null;
      _inspectionFailure = null;
    });
    try {
      final result = await widget.api.inspect(url);
      if (mounted && revision == _revision) {
        setState(() => _inspection = result);
      }
    } on ApiFailure catch (e) {
      if (mounted && revision == _revision) {
        setState(() => _inspectionFailure = e);
      }
    } finally {
      if (mounted) setState(() => _inspecting = false);
    }
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
    final revision = _revision;
    setState(() {
      _busy = true;
      _prediction = null;
      _failure = null;
    });
    try {
      final result = await widget.api.predict(_url.text.trim());
      if (mounted && revision == _revision) {
        setState(() {
          _prediction = result;
          _ready = true;
          _healthChecked = true;
        });
      }
    } on ApiFailure catch (e) {
      if (mounted && revision == _revision) setState(() => _failure = e);
      _health();
    } finally {
      if (mounted) {
        setState(() => _busy = false);
        WidgetsBinding.instance.addPostFrameCallback((_) {
          final feedbackContext = _feedback.currentContext;
          if (mounted &&
              revision == _revision &&
              feedbackContext != null &&
              MediaQuery.sizeOf(context).width < 860) {
            Scrollable.ensureVisible(
              feedbackContext,
              duration: MediaQuery.disableAnimationsOf(context)
                  ? Duration.zero
                  : const Duration(milliseconds: 250),
              alignment: .15,
            );
          }
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: DecoratedBox(
      decoration: const BoxDecoration(
        gradient: RadialGradient(
          center: Alignment(.8, -.4),
          radius: 1.2,
          colors: [Color(0xFF153346), navy],
        ),
      ),
      child: SafeArea(
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
                        // Keep the card's accessibility order independent of
                        // the hero. Reordering the web semantics DOM can move
                        // the focused input's form and blur the native editor.
                        final card = Semantics(
                          container: true,
                          explicitChildNodes: true,
                          child: _card(),
                        );
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
                                    Expanded(flex: 11, child: card),
                                  ],
                                )
                              : Column(
                                  crossAxisAlignment:
                                      CrossAxisAlignment.stretch,
                                  children: [
                                    _hero(false),
                                    const SizedBox(height: 28),
                                    card,
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
    ),
  );

  Widget _header() => Padding(
    padding: const EdgeInsets.symmetric(vertical: 24),
    child: Wrap(
      alignment: WrapAlignment.spaceBetween,
      crossAxisAlignment: WrapCrossAlignment.center,
      spacing: 24,
      runSpacing: 16,
      children: [
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 42,
              height: 42,
              decoration: BoxDecoration(
                color: teal,
                borderRadius: BorderRadius.circular(13),
              ),
              child: const Icon(Icons.shield_outlined, color: navy, size: 25),
            ),
            const SizedBox(width: 11),
            const Flexible(
              child: Text.rich(
                TextSpan(
                  text: 'PhishGuard ',
                  children: [
                    TextSpan(
                      text: 'VN',
                      style: TextStyle(color: teal),
                    ),
                  ],
                ),
                style: TextStyle(
                  fontSize: 21,
                  fontWeight: FontWeight.w700,
                  color: ink,
                  letterSpacing: -.6,
                ),
              ),
            ),
          ],
        ),
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
                  color: _ready == true ? teal : warning,
                ),
              ),
              const SizedBox(width: 7),
              Flexible(
                child: Text(
                  !_healthChecked
                      ? 'Đang kết nối'
                      : _ready == true
                      ? 'API sẵn sàng'
                      : _ready == false
                      ? 'API chờ model'
                      : 'Chưa kết nối',
                  style: const TextStyle(fontSize: 12, color: muted),
                ),
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
          color: benignSurface,
          borderRadius: BorderRadius.circular(20),
        ),
        child: const Text(
          'KIỂM TRA URL',
          style: TextStyle(
            color: teal,
            fontSize: 12,
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
        style: TextStyle(color: muted, fontSize: 16, height: 1.6),
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
            fontSize: 12,
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

  Widget _card() => ClipRRect(
    borderRadius: BorderRadius.circular(24),
    child: BackdropFilter(
      filter: ImageFilter.blur(sigmaX: 12, sigmaY: 12),
      child: Container(
        padding: EdgeInsets.all(
          MediaQuery.sizeOf(context).width < 600 ? 20 : 32,
        ),
        decoration: BoxDecoration(
          color: surface.withValues(alpha: .88),
          border: Border.all(color: line),
          borderRadius: BorderRadius.circular(24),
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
              style: TextStyle(color: muted, fontSize: 16, height: 1.5),
            ),
            const SizedBox(height: 24),
            OutlinedButton.icon(
              key: const Key('qr-upload'),
              onPressed: _qrBusy || _busy ? null : _pickQr,
              icon: const Icon(Icons.qr_code_rounded),
              label: Text(_qrBusy ? 'Đang đọc ảnh QR…' : 'Chọn ảnh QR'),
              style: OutlinedButton.styleFrom(minimumSize: const Size(48, 48)),
            ),
            const SizedBox(height: 8),
            const Text(
              'PNG/JPEG/WebP · tối đa 8 MB, 4 triệu pixel. Một mã QR/ảnh; chưa hỗ trợ nhiều mã. Ảnh được đọc tại máy, không upload lên máy chủ.',
              style: TextStyle(color: muted, fontSize: 12, height: 1.5),
            ),
            if (_qrFailure != null)
              Semantics(
                liveRegion: true,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _qrFailure!,
                      key: const Key('qr-error'),
                      style: const TextStyle(color: danger, height: 1.5),
                    ),
                    TextButton(
                      onPressed: _pickQr,
                      child: const Text('Chọn ảnh khác'),
                    ),
                  ],
                ),
              ),
            if (_qrCandidate != null)
              Semantics(
                liveRegion: true,
                child: Container(
                  key: const Key('qr-preview'),
                  margin: const EdgeInsets.only(top: 16),
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: benignSurface,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Text(
                        'URL đọc từ QR — chưa gửi phân tích',
                        style: TextStyle(
                          color: teal,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        _qrCandidate!,
                        style: const TextStyle(color: ink, height: 1.5),
                      ),
                      TextButton(
                        key: const Key('qr-confirm'),
                        onPressed: _busy
                            ? null
                            : () {
                                final candidate = _qrCandidate!;
                                _url.text = candidate;
                                _submit();
                              },
                        child: const Text('Xác nhận và phân tích'),
                      ),
                      TextButton(
                        onPressed: () => setState(() => _qrCandidate = null),
                        child: const Text('Hủy'),
                      ),
                    ],
                  ),
                ),
              ),
            const SizedBox(height: 24),
            Form(
              key: _form,
              child: TextFormField(
                key: const Key('url-input'),
                controller: _url,
                keyboardType: TextInputType.url,
                autocorrect: false,
                enableSuggestions: false,
                textInputAction: TextInputAction.go,
                decoration: const InputDecoration(
                  labelText: 'URL cần kiểm tra',
                  hintText: 'https://example.com',
                  prefixIcon: Icon(Icons.link_rounded, size: 20),
                ),
                style: const TextStyle(fontSize: 16),
                validator: (text) {
                  if (text == null || text.trim().isEmpty) {
                    return 'Vui lòng nhập một URL.';
                  }
                  if (text.runes.length > 4096) return 'URL tối đa 4096 ký tự.';
                  return null;
                },
                onFieldSubmitted: (_) => _submit(),
              ),
            ),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              key: const Key('inspect-button'),
              onPressed: _inspecting ? null : _inspect,
              icon: const Icon(Icons.travel_explore_rounded),
              label: Text(
                _inspecting
                    ? 'Đang kiểm tra quy tắc…'
                    : 'Brand Detector & URL X-Ray',
              ),
              style: OutlinedButton.styleFrom(minimumSize: const Size(48, 48)),
            ),
            const SizedBox(height: 10),
            const Text(
              'Có thể nhập tên miền không có http:// hoặc https://.',
              style: TextStyle(fontSize: 12, color: muted, height: 1.5),
            ),
            const SizedBox(height: 20),
            FilledButton(
              key: const Key('check-button'),
              onPressed: _busy ? null : _submit,
              style: FilledButton.styleFrom(
                backgroundColor: teal,
                foregroundColor: navy,
                minimumSize: const Size(48, 56),
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
                    SizedBox(
                      width: 16,
                      height: 16,
                      child: MediaQuery.disableAnimationsOf(context)
                          ? const Icon(Icons.hourglass_empty_rounded, size: 16)
                          : const CircularProgressIndicator(strokeWidth: 2),
                    ),
                    const SizedBox(width: 10),
                  ],
                  Flexible(
                    child: Text(
                      _busy ? 'Đang phân tích…' : 'Kiểm tra URL',
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        fontWeight: FontWeight.w700,
                        fontSize: 16,
                      ),
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
            if (_inspection != null) ...[
              const SizedBox(height: 24),
              _inspectionView(_inspection!),
            ],
            if (_inspectionFailure != null)
              Semantics(
                liveRegion: true,
                child: Column(
                  children: [
                    const SizedBox(height: 16),
                    Text(
                      _inspectionFailure!.message,
                      key: const Key('inspect-error'),
                      style: const TextStyle(color: danger),
                    ),
                    TextButton(
                      onPressed: _inspect,
                      child: const Text('Thử lại quy tắc'),
                    ),
                  ],
                ),
              ),
            const SizedBox(height: 24),
            const Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(Icons.info_outline_rounded, size: 15, color: muted),
                SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'Kết quả chỉ mang tính tham khảo, không phải chứng nhận URL an toàn. Không nhập đường dẫn chứa mật khẩu hoặc token riêng tư.',
                    style: TextStyle(color: muted, fontSize: 12, height: 1.6),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    ),
  );

  Widget _inspectionView(Inspection i) {
    const ruleNames = {
      'brand_in_domain': 'Thương hiệu trong domain',
      'brand_in_subdomain': 'Thương hiệu trong subdomain',
      'brand_in_path': 'Thương hiệu trong path/query',
      'brand_domain_mismatch': 'Tên thương hiệu khác domain tham chiếu',
      'brand_typo_score': 'Chuỗi gần giống thương hiệu',
      'homoglyph_brand_hit': 'Ký tự có thể gây nhầm lẫn',
      'susp_token': 'Từ khóa theo quy tắc',
    };
    return Semantics(
      liveRegion: true,
      child: Container(
        key: const Key('inspection-result'),
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: navy,
          border: Border.all(color: line),
          borderRadius: BorderRadius.circular(14),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'URL X-RAY',
              style: TextStyle(
                color: teal,
                fontWeight: FontWeight.bold,
                letterSpacing: 1.2,
              ),
            ),
            const SizedBox(height: 12),
            Text(
              'Domain đăng ký thực tế: ${i.domain ?? 'Không có (IP hoặc hostname không có domain đăng ký)'}',
              style: const TextStyle(
                color: ink,
                fontWeight: FontWeight.bold,
                height: 1.5,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Hostname: ${i.hostname}\nSubdomain: ${i.subdomain.isEmpty ? '—' : i.subdomain}\nPath: ${i.path.isEmpty ? '/' : i.path}',
              style: const TextStyle(color: muted, height: 1.6),
            ),
            if (i.isIp)
              const Text(
                'Địa chỉ IP; không có danh tính thương hiệu được xác minh.',
                style: TextStyle(color: warning, height: 1.5),
              ),
            if (i.features['idna_flag'] == 1)
              const Text(
                'IDNA/Punycode hiện diện. Đây là tín hiệu định dạng, không phải kết luận độc hại.',
                style: TextStyle(color: warning, height: 1.5),
              ),
            const Divider(color: line, height: 32),
            const Text(
              'BRAND DETECTOR · QUY TẮC',
              style: TextStyle(color: teal, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Text(
              i.officialBrands.isEmpty
                  ? 'Không khớp domain chính thức trong reference.'
                  : 'Khớp domain tham chiếu: ${i.officialBrands.join(', ')}. Không chứng nhận an toàn hoặc quyền sở hữu hiện tại.',
              style: const TextStyle(color: muted, height: 1.5),
            ),
            if (i.matches.isEmpty)
              const Text(
                'Không có tín hiệu phù hợp trong 45 thương hiệu; không có nghĩa là URL an toàn.',
                style: TextStyle(color: muted, height: 1.5),
              ),
            for (final m in i.matches)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(
                  '${ruleNames[m['rule']] ?? m['rule']} · ${m['brand_name'] == '' ? m['key'] : m['brand_name']}\nChuỗi đối chiếu: ${m['text']}${m['distance'] == null ? '' : '\nKhoảng cách chỉnh sửa: ${m['distance']}'}',
                  style: const TextStyle(color: ink, height: 1.5),
                ),
              ),
            const SizedBox(height: 16),
            const Text(
              'Quy tắc chuỗi URL, không phải dự đoán hay giải thích nội tại ML. Mismatch/typo không chứng minh phishing. Evidence được chuẩn hóa; vùng path bao gồm query. Không truy cập trang đích.',
              style: TextStyle(color: warning, fontSize: 12, height: 1.6),
            ),
            const SizedBox(height: 8),
            Text(
              'Reference 45 thương hiệu · SHA256 ${i.referenceSha}',
              style: const TextStyle(color: muted, fontSize: 11, height: 1.5),
            ),
          ],
        ),
      ),
    );
  }

  Widget _result(Prediction p) {
    final flagged = p.label == 'phishing';
    final color = flagged ? danger : teal;
    final probability = p.scoreKind == 'probability';
    return Semantics(
      liveRegion: true,
      child: Container(
        key: const Key('prediction-result'),
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: flagged ? dangerSurface : benignSurface,
          border: Border.all(color: color.withValues(alpha: .5)),
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
              style: const TextStyle(color: muted, fontSize: 12),
            ),
            const SizedBox(height: 4),
            Text(
              probability
                  ? p.threshold != null
                        ? p.score.toStringAsFixed(6)
                        : '${(p.score * 100).toStringAsFixed(2)}%'
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
                  ? p.threshold != null
                        ? 'Meta-LR score · chưa hiệu chuẩn nguy cơ thực tế'
                        : 'predict_proba · chưa hiệu chuẩn nguy cơ thực tế'
                  : 'Decision margin · không phải xác suất',
              style: const TextStyle(color: muted, fontSize: 12, height: 1.5),
            ),
            if (p.threshold != null) ...[
              const SizedBox(height: 8),
              Text(
                'Quy tắc backend: score ≥ ${p.threshold}',
                style: const TextStyle(color: muted, fontSize: 12, height: 1.5),
              ),
            ],
            const SizedBox(height: 18),
            const Divider(color: line, height: 1),
            const SizedBox(height: 14),
            const Text(
              'MODEL',
              style: TextStyle(
                fontSize: 12,
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
                style: TextStyle(fontSize: 12, color: muted),
              ),
            ],
            const SizedBox(height: 12),
            Text(
              flagged
                  ? 'Cân nhắc dừng truy cập và xác minh nguồn gửi đường dẫn.'
                  : 'Nhãn benign không bảo đảm website an toàn. Vẫn cần kiểm tra nguồn và nội dung.',
              style: const TextStyle(fontSize: 12, height: 1.6, color: muted),
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
        color: dangerSurface,
        border: Border.all(color: danger.withValues(alpha: .5)),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Chưa thể kiểm tra đường dẫn',
            style: TextStyle(
              fontWeight: FontWeight.w700,
              color: danger,
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
      Flexible(
        child: Text(label, style: const TextStyle(color: muted, fontSize: 12)),
      ),
    ],
  );
}
