import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';

import 'api_client.dart';
import 'qr_image.dart';
import 'similar_cases.dart';

// Semantic tokens: design-system/phishguardvn/MASTER.md.
const navy = Color(0xFF081321);
const surface = Color(0xFF132536);
const glassTop = Color(0xFF192E40);
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
  static final _buttonFocus = WidgetStateProperty.resolveWith<BorderSide?>(
    (states) => states.contains(WidgetState.focused)
        ? const BorderSide(color: ink, width: 2)
        : null,
  );

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
      filledButtonTheme: FilledButtonThemeData(
        style: ButtonStyle(side: _buttonFocus),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          minimumSize: const Size(48, 48),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
          ),
        ).copyWith(side: _buttonFocus),
      ),
      iconButtonTheme: IconButtonThemeData(
        style: ButtonStyle(side: _buttonFocus),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: navy,
        labelStyle: const TextStyle(color: muted),
        hintStyle: const TextStyle(color: muted),
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
  static const _desktopBreakpoint = 960.0;
  final _form = GlobalKey<FormState>();
  final _feedback = GlobalKey();
  final _inspectionFeedback = GlobalKey();
  final _similarFeedback = GlobalKey();
  final _url = TextEditingController();
  final _urlFocus = FocusNode();
  late final SemanticsHandle _semantics;
  Prediction? _prediction;
  ApiFailure? _failure;
  int? _predictionRequestRevision;
  bool? _ready;
  bool _healthChecked = false;
  int _healthRevision = 0;
  int _revision = 0;
  String _inputText = '';
  Inspection? _inspection;
  ApiFailure? _inspectionFailure;
  int? _inspectionRequestRevision;
  List<SimilarCase>? _similarCases;
  ApiFailure? _similarFailure;
  int? _similarRequestRevision;
  bool _qrBusy = false;
  String? _qrCandidate, _qrFailure;
  bool _pasting = false;
  String? _pasteMessage;

  bool get _busy => _predictionRequestRevision != null;
  bool get _inspecting => _inspectionRequestRevision != null;

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
    _urlFocus.dispose();
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
        !_busy &&
        _inspection == null &&
        _inspectionFailure == null &&
        !_inspecting &&
        _similarCases == null &&
        _similarFailure == null &&
        _similarRequestRevision == null &&
        _qrCandidate == null &&
        _qrFailure == null &&
        _pasteMessage == null) {
      return;
    }
    setState(() {
      _prediction = null;
      _failure = null;
      _predictionRequestRevision = null;
      _inspection = null;
      _inspectionFailure = null;
      _inspectionRequestRevision = null;
      _similarCases = null;
      _similarFailure = null;
      _similarRequestRevision = null;
      _qrCandidate = null;
      _qrFailure = null;
      _pasteMessage = null;
    });
  }

  void _setUrl(String value) {
    _url.value = TextEditingValue(
      text: value,
      selection: TextSelection.collapsed(offset: value.length),
    );
  }

  Future<void> _paste() async {
    if (_pasting) return;
    final revision = _revision;
    // Release the current editor while the browser handles clipboard access.
    _urlFocus.unfocus();
    setState(() {
      _pasting = true;
      _pasteMessage = null;
    });
    String? value;
    String? message;
    try {
      value = (await Clipboard.getData(Clipboard.kTextPlain))?.text;
      if (value == null || value.trim().isEmpty) {
        message = 'Bộ nhớ tạm chưa có văn bản.';
      }
    } on PlatformException {
      message = 'Hãy dán trực tiếp vào ô URL.';
    }
    if (!mounted) return;
    setState(() => _pasting = false);
    if (revision != _revision) return;
    if (message != null) {
      setState(() => _pasteMessage = message);
      return;
    }
    _setUrl(value!.trim());
    _urlFocus.requestFocus();
  }

  String? _validateInput() {
    if (!_form.currentState!.validate()) {
      _urlFocus.requestFocus();
      return null;
    }
    _urlFocus.unfocus();
    return _url.text.trim();
  }

  void _editUrl() {
    final revision = _revision;
    _urlFocus.unfocus();
    _url.selection = TextSelection(
      baseOffset: 0,
      extentOffset: _url.text.length,
    );
    // Restore the editor after Flutter Web finishes the button's DOM focus event.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && revision == _revision) _urlFocus.requestFocus();
    });
    WidgetsBinding.instance.ensureVisualUpdate();
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
    if (_inspecting) return;
    final url = _validateInput();
    if (url == null) return;
    final revision = _revision;
    setState(() {
      _inspectionRequestRevision = revision;
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
      if (mounted && revision == _revision) {
        setState(() => _inspectionRequestRevision = null);
        _reveal(_inspectionFeedback, revision);
      }
    }
  }

  Future<void> _findSimilar() async {
    if (_similarRequestRevision != null) return;
    final url = _validateInput();
    if (url == null) return;
    final revision = _revision;
    setState(() {
      _similarRequestRevision = revision;
      _similarCases = null;
      _similarFailure = null;
    });
    try {
      final cases = await widget.api.similarCases(url);
      if (mounted && revision == _revision) {
        setState(() => _similarCases = cases);
      }
    } on ApiFailure catch (e) {
      if (mounted && revision == _revision) {
        setState(() => _similarFailure = e);
      }
    } finally {
      if (mounted && revision == _revision) {
        setState(() => _similarRequestRevision = null);
        _reveal(_similarFeedback, revision);
      }
    }
  }

  Future<void> _health() async {
    final revision = ++_healthRevision;
    bool? ready;
    try {
      ready = await widget.api.health();
    } on ApiFailure {
      ready = null;
    }
    if (mounted && revision == _healthRevision) {
      setState(() {
        _ready = ready;
        _healthChecked = true;
      });
    }
  }

  Future<void> _submit() async {
    if (_busy) return;
    final url = _validateInput();
    if (url == null) return;
    final revision = _revision;
    setState(() {
      _predictionRequestRevision = revision;
      _prediction = null;
      _failure = null;
    });
    try {
      final result = await widget.api.predict(url);
      if (mounted && revision == _revision) {
        _healthRevision++;
        setState(() {
          _prediction = result;
          _ready = true;
          _healthChecked = true;
        });
      }
    } on ApiFailure catch (e) {
      if (mounted && revision == _revision) {
        setState(() => _failure = e);
        if (!_inputFailure(e)) _health();
      }
    } finally {
      if (mounted && revision == _revision) {
        setState(() => _predictionRequestRevision = null);
        _reveal(_feedback, revision);
      }
    }
  }

  bool _inputFailure(ApiFailure failure) =>
      failure.code == 'INVALID_URL' || failure.code == 'INVALID_REQUEST';

  void _reveal(GlobalKey section, int revision) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final target = section.currentContext;
      if (!mounted || revision != _revision || target == null) {
        return;
      }
      final box = target.findRenderObject();
      if (box is! RenderBox || !box.hasSize) return;
      final viewport = MediaQuery.of(context);
      if (viewport.size.width >= _desktopBreakpoint) return;
      final top = box.localToGlobal(Offset.zero).dy;
      final bottom =
          viewport.size.height -
          viewport.padding.bottom -
          viewport.viewInsets.bottom;
      if (top >= viewport.padding.top && top + box.size.height <= bottom) {
        return;
      }
      _urlFocus.unfocus();
      Scrollable.ensureVisible(
        target,
        duration: viewport.disableAnimations
            ? Duration.zero
            : const Duration(milliseconds: 220),
        alignment: .08,
        curve: Curves.easeOut,
      );
    });
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SizedBox.expand(
      child: DecoratedBox(
        decoration: const BoxDecoration(
          gradient: RadialGradient(
            center: Alignment(-.76, -.2),
            radius: 1.0,
            colors: [Color(0xFF132E40), navy],
          ),
        ),
        child: SafeArea(
          child: LayoutBuilder(
            builder: (context, viewport) {
              final desktop = viewport.maxWidth >= _desktopBreakpoint;
              final gutter = desktop
                  ? 40.0
                  : (viewport.maxWidth >= 600 ? 28.0 : 16.0);
              return SingleChildScrollView(
                child: Center(
                  child: ConstrainedBox(
                    constraints: BoxConstraints(
                      maxWidth: desktop ? 1220 : 730,
                      minHeight: viewport.maxHeight,
                    ),
                    child: Padding(
                      padding: EdgeInsets.symmetric(horizontal: gutter),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              _header(),
                              Padding(
                                padding: EdgeInsets.only(
                                  top: desktop ? 72 : 24,
                                  bottom: desktop ? 48 : 28,
                                ),
                                child: desktop
                                    ? Row(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.start,
                                        children: [
                                          Expanded(flex: 9, child: _hero(true)),
                                          const SizedBox(width: 54),
                                          Expanded(
                                            flex: 11,
                                            child: _workspace(),
                                          ),
                                        ],
                                      )
                                    : Column(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.stretch,
                                        children: [
                                          _hero(false),
                                          const SizedBox(height: 24),
                                          _workspace(),
                                        ],
                                      ),
                              ),
                            ],
                          ),
                          _footer(),
                        ],
                      ),
                    ),
                  ),
                ),
              );
            },
          ),
        ),
      ),
    ),
  );

  Widget _header() {
    final status = !_healthChecked
        ? 'Đang kết nối'
        : _ready == true
        ? 'API sẵn sàng'
        : _ready == false
        ? 'API chờ model'
        : 'Chưa kết nối';
    final statusColor = !_healthChecked
        ? muted
        : (_ready == true ? teal : warning);
    return DecoratedBox(
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: line)),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 17),
        child: Wrap(
          alignment: WrapAlignment.spaceBetween,
          crossAxisAlignment: WrapCrossAlignment.center,
          spacing: 14,
          runSpacing: 10,
          children: [
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 38,
                  height: 38,
                  decoration: BoxDecoration(
                    color: teal,
                    borderRadius: BorderRadius.circular(11),
                  ),
                  child: const Icon(
                    Icons.shield_outlined,
                    color: navy,
                    size: 22,
                  ),
                ),
                const SizedBox(width: 10),
                const Flexible(
                  child: Text.rich(
                    TextSpan(
                      text: 'PhishGuard',
                      children: [
                        TextSpan(
                          text: 'VN',
                          style: TextStyle(color: teal),
                        ),
                      ],
                    ),
                    style: TextStyle(
                      fontSize: 19,
                      fontWeight: FontWeight.w700,
                      color: ink,
                      letterSpacing: -.45,
                    ),
                  ),
                ),
              ],
            ),
            Semantics(
              liveRegion: true,
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 8,
                ),
                decoration: BoxDecoration(
                  color: navy.withValues(alpha: .65),
                  border: Border.all(color: line),
                  borderRadius: BorderRadius.circular(24),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.circle, size: 7, color: statusColor),
                    const SizedBox(width: 8),
                    Flexible(
                      child: Text(
                        status,
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: statusColor,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _hero(bool desktop) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Semantics(
        header: true,
        headingLevel: 1,
        child: Text.rich(
          const TextSpan(
            text: 'Kiểm tra link\n',
            children: [
              TextSpan(
                text: 'trước khi mở.',
                style: TextStyle(color: teal),
              ),
            ],
          ),
          style: TextStyle(
            color: ink,
            fontSize: desktop ? 58 : 36,
            height: 1.08,
            letterSpacing: desktop ? -2.2 : -1.1,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
      const SizedBox(height: 16),
      ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 410),
        child: const Text(
          'Nhận diện dấu hiệu lừa đảo từ đường dẫn và mã QR.',
          style: TextStyle(color: muted, fontSize: 17, height: 1.5),
        ),
      ),
      if (desktop) ...[
        const SizedBox(height: 10),
        AspectRatio(
          aspectRatio: 1.64,
          child: Image.asset(
            'assets/images/scan-shield.webp',
            fit: BoxFit.contain,
            excludeFromSemantics: true,
          ),
        ),
        const Wrap(
          spacing: 18,
          runSpacing: 10,
          children: [
            _TrustNote(
              icon: Icons.link_off_rounded,
              label: 'Không mở trang đích',
            ),
            _TrustNote(
              icon: Icons.qr_code_rounded,
              label: 'Đọc QR tại thiết bị',
            ),
          ],
        ),
      ],
    ],
  );

  Widget _footer() => const DecoratedBox(
    decoration: BoxDecoration(
      border: Border(top: BorderSide(color: line)),
    ),
    child: Padding(
      padding: EdgeInsets.symmetric(vertical: 20),
      child: Wrap(
        alignment: WrapAlignment.spaceBetween,
        spacing: 16,
        runSpacing: 8,
        children: [
          Text(
            'PhishGuardVN · Đồ án học máy',
            style: TextStyle(fontSize: 13, color: muted),
          ),
          Text(
            'Không lưu lịch sử kiểm tra',
            style: TextStyle(fontSize: 13, color: muted),
          ),
        ],
      ),
    ),
  );

  Widget _workspace() => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Semantics(container: true, explicitChildNodes: true, child: _scanForm()),
      if (_prediction != null || _failure != null) ...[
        const SizedBox(height: 16),
        KeyedSubtree(
          key: _feedback,
          child: _prediction != null
              ? _result(_prediction!)
              : _error(_failure!),
        ),
      ],
      const SizedBox(height: 20),
      _inspectionTools(),
    ],
  );

  Widget _scanForm() => Container(
    padding: EdgeInsets.all(MediaQuery.sizeOf(context).width < 600 ? 18 : 28),
    decoration: BoxDecoration(
      gradient: const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [glassTop, surface],
      ),
      border: Border.all(color: line),
      borderRadius: BorderRadius.circular(22),
      boxShadow: const [
        BoxShadow(
          color: Color(0x4502070D),
          blurRadius: 34,
          offset: Offset(0, 16),
        ),
      ],
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: benignSurface,
                border: Border.all(color: teal.withValues(alpha: .26)),
                borderRadius: BorderRadius.circular(11),
              ),
              child: const Icon(Icons.link_rounded, color: teal, size: 22),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Semantics(
                header: true,
                child: const Text(
                  'Quét đường dẫn',
                  style: TextStyle(
                    color: ink,
                    fontWeight: FontWeight.w700,
                    fontSize: 23,
                    height: 1.25,
                    letterSpacing: -.4,
                  ),
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 24),
        Form(
          key: _form,
          child: TextFormField(
            key: const Key('url-input'),
            controller: _url,
            focusNode: _urlFocus,
            keyboardType: TextInputType.url,
            autocorrect: false,
            enableSuggestions: false,
            autovalidateMode: AutovalidateMode.onUserInteractionIfError,
            textInputAction: TextInputAction.go,
            decoration: InputDecoration(
              labelText: 'URL cần kiểm tra',
              hintText: 'https://example.com',
              floatingLabelBehavior: FloatingLabelBehavior.always,
              suffixIcon: ValueListenableBuilder(
                valueListenable: _url,
                builder: (context, value, child) => value.text.isEmpty
                    ? const SizedBox.shrink()
                    : IconButton(
                        key: const Key('clear-url'),
                        tooltip: 'Xóa URL',
                        onPressed: () {
                          _url.clear();
                          _urlFocus.requestFocus();
                        },
                        icon: const Icon(Icons.close_rounded, size: 20),
                      ),
              ),
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
        const SizedBox(height: 10),
        const Text(
          'Bạn có thể nhập tên miền mà không cần https://.',
          style: TextStyle(color: muted, fontSize: 13, height: 1.45),
        ),
        const SizedBox(height: 16),
        _scanButton(),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 4,
          children: [
            TextButton.icon(
              key: const Key('paste-url'),
              onPressed: _pasting ? null : _paste,
              icon: const Icon(Icons.content_paste_rounded, size: 17),
              label: Text(_pasting ? 'Đang dán…' : 'Dán URL'),
            ),
            Tooltip(
              message:
                  'PNG, JPEG hoặc WebP · 8 MB, 4 triệu pixel · một mã QR/ảnh',
              excludeFromSemantics: true,
              child: TextButton.icon(
                key: const Key('qr-upload'),
                onPressed: _qrBusy || _busy ? null : _pickQr,
                icon: const Icon(Icons.qr_code_rounded, size: 19),
                label: Text(_qrBusy ? 'Đang đọc ảnh QR…' : 'Chọn ảnh QR'),
              ),
            ),
          ],
        ),
        if (_pasteMessage != null)
          Semantics(
            liveRegion: true,
            child: Text(
              _pasteMessage!,
              style: const TextStyle(color: warning, fontSize: 13),
            ),
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
        if (_qrCandidate != null) _qrPreview(_qrCandidate!),
        const Divider(color: line, height: 26),
        const _TrustNote(
          icon: Icons.lock_outline_rounded,
          label: 'Máy chủ chỉ nhận URL để phân tích. Tránh gửi liên kết có mật khẩu hoặc mã riêng tư.',
        ),
      ],
    ),
  );

  Widget _scanButton() => FilledButton(
    key: const Key('check-button'),
    onPressed: _busy ? null : _submit,
    style: FilledButton.styleFrom(
      backgroundColor: teal,
      foregroundColor: navy,
      minimumSize: const Size(48, 54),
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ),
    child: Row(
      mainAxisAlignment: MainAxisAlignment.center,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (_busy) ...[
          SizedBox.square(
            dimension: 16,
            child: MediaQuery.disableAnimationsOf(context)
                ? const Icon(Icons.hourglass_empty_rounded, size: 16)
                : const CircularProgressIndicator(strokeWidth: 2),
          ),
          const SizedBox(width: 10),
        ],
        Flexible(
          child: Semantics(
            liveRegion: _busy,
            child: Text(
              _busy ? 'Đang phân tích…' : 'Kiểm tra URL',
              textAlign: TextAlign.center,
              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
            ),
          ),
        ),
        if (!_busy) ...[
          const SizedBox(width: 10),
          const Icon(Icons.arrow_forward_rounded, size: 18),
        ],
      ],
    ),
  );

  Widget _qrPreview(String candidate) => Semantics(
    liveRegion: true,
    child: Container(
      key: const Key('qr-preview'),
      margin: const EdgeInsets.only(top: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: benignSurface,
        border: Border.all(color: teal.withValues(alpha: .35)),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'URL đọc từ QR — chưa gửi phân tích',
            style: TextStyle(color: teal, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          Text(candidate, style: const TextStyle(color: ink, height: 1.5)),
          const SizedBox(height: 4),
          Wrap(
            spacing: 8,
            children: [
              TextButton(
                key: const Key('qr-confirm'),
                onPressed: _busy
                    ? null
                    : () {
                        _setUrl(candidate);
                        // The image can contain the same text as the current input.
                        setState(() => _qrCandidate = null);
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
        ],
      ),
    ),
  );

  Widget _inspectionTools() => Container(
    padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(
      color: surface.withValues(alpha: .55),
      border: Border.all(color: line),
      borderRadius: BorderRadius.circular(18),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Semantics(
          header: true,
          child: const Text(
            'Phân tích bổ sung',
            style: TextStyle(
              color: ink,
              fontWeight: FontWeight.w700,
              fontSize: 15,
            ),
          ),
        ),
        const SizedBox(height: 8),
        TextButton.icon(
          key: const Key('inspect-button'),
          onPressed: _inspecting ? null : _inspect,
          icon: const Icon(Icons.travel_explore_rounded, size: 20),
          label: Text(
            _inspecting
                ? 'Đang kiểm tra quy tắc…'
                : 'Brand Detector & URL X-Ray',
            textAlign: TextAlign.start,
          ),
          style: TextButton.styleFrom(alignment: Alignment.centerLeft),
        ),
        if (_inspection != null)
          KeyedSubtree(
            key: _inspectionFeedback,
            child: _inspectionView(_inspection!),
          ),
        if (_inspectionFailure != null)
          KeyedSubtree(
            key: _inspectionFeedback,
            child: Semantics(
              liveRegion: true,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _inspectionFailure!.message,
                    key: const Key('inspect-error'),
                    style: const TextStyle(color: danger),
                  ),
                  TextButton(
                    onPressed: _inputFailure(_inspectionFailure!)
                        ? _editUrl
                        : _inspect,
                    child: Text(
                      _inputFailure(_inspectionFailure!)
                          ? 'Chỉnh URL'
                          : 'Thử lại quy tắc',
                    ),
                  ),
                ],
              ),
            ),
          ),
        const Divider(color: line, height: 9),
        TextButton.icon(
          key: const Key('similar-button'),
          onPressed: _similarRequestRevision != null ? null : _findSimilar,
          icon: const Icon(Icons.manage_search_rounded, size: 20),
          label: const Text(
            'Tìm ca phishing tương tự',
            textAlign: TextAlign.start,
          ),
          style: TextButton.styleFrom(alignment: Alignment.centerLeft),
        ),
        if (_similarRequestRevision != null ||
            _similarCases != null ||
            _similarFailure != null)
          KeyedSubtree(key: _similarFeedback, child: _similarView()),
      ],
    ),
  );

  Widget _similarView() {
    final cases = _similarCases;
    return Semantics(
      liveRegion: true,
      child: Container(
        key: const Key('similar-result'),
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
              'Ca phishing tương tự',
              style: TextStyle(color: teal, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            if (_similarRequestRevision != null)
              const Text(
                'Đang tra cứu ca lịch sử…',
                style: TextStyle(color: muted),
              )
            else if (_similarFailure != null) ...[
              Text(
                _similarFailure!.message,
                style: const TextStyle(color: danger),
              ),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton(
                  key: const Key('similar-retry'),
                  onPressed: _findSimilar,
                  child: const Text('Thử lại tra cứu'),
                ),
              ),
            ] else if (cases != null && cases.isEmpty)
              const Text(
                'Chưa tìm thấy ca lịch sử đủ tương tự.',
                style: TextStyle(color: muted),
              )
            else if (cases != null) ...[
              const Text(
                'Cosine đo độ gần của chuỗi URL. Nhãn của URL đang kiểm tra đến từ Teacher.',
                style: TextStyle(color: muted, height: 1.5),
              ),
              for (final item in cases) ...[
                const Divider(color: line, height: 24),
                Text.rich(
                  TextSpan(
                    children: [
                      for (final segment in item.segments)
                        TextSpan(
                          text: segment.text,
                          style: segment.highlighted
                              ? const TextStyle(
                                  color: teal,
                                  backgroundColor: benignSurface,
                                  fontWeight: FontWeight.bold,
                                )
                              : null,
                        ),
                    ],
                  ),
                  key: ValueKey('historical-${item.id}'),
                  style: const TextStyle(color: ink, height: 1.5),
                ),
                const SizedBox(height: 6),
                Text(
                  'Nguồn: ${item.source} · Cosine: ${item.similarity}',
                  style: const TextStyle(color: muted, height: 1.5),
                ),
              ],
            ],
          ],
        ),
      ),
    );
  }

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
              '${i.catalogVersion} · ${i.referenceBrands} thương hiệu',
              style: const TextStyle(color: muted, height: 1.5),
            ),
            if (i.catalogStatus == 'expanded')
              const Text(
                'Danh mục cho người dùng Việt Nam',
                style: TextStyle(color: muted, height: 1.5),
              ),
            if (i.catalogStatus == 'fallback_v1')
              const Text(
                'Danh mục mở rộng chưa khả dụng. Đang dùng reference gốc.',
                style: TextStyle(color: warning, height: 1.5),
              ),
            const SizedBox(height: 8),
            if (i.officialBrands.isEmpty)
              const Text(
                'Không khớp domain chính thức trong danh mục.',
                style: TextStyle(color: muted, height: 1.5),
              )
            else if (i.officialDetails.isEmpty)
              Text('Khớp domain tham chiếu: ${i.officialBrands.join(', ')}')
            else
              for (final brand in i.officialDetails)
                Text(
                  'Khớp domain chính thức · ${brand['brand_name']} (${(brand['official_domains'] as List).join(', ')})',
                  style: const TextStyle(color: ink, height: 1.5),
                ),
            if (i.matches.isEmpty && i.officialBrands.isEmpty)
              const Text(
                'Chưa nhận diện được tín hiệu thương hiệu.',
                style: TextStyle(color: muted, height: 1.5),
              ),
            for (final m in i.matches)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(
                  '${m['zone'] == 'query' && m['rule'] == 'brand_in_path' ? 'Thương hiệu trong query' : ruleNames[m['rule']] ?? m['rule']} · ${m['brand_name'] == '' ? m['key'] : m['brand_name']}\nChuỗi đối chiếu: ${m['text']}${m['distance'] == null ? '' : '\nKhoảng cách chỉnh sửa: ${m['distance']}'}${m['rule'] == 'brand_domain_mismatch' && (m['official_domains'] as List?)?.isNotEmpty == true ? '\nDomain tham chiếu: ${(m['official_domains'] as List).join(', ')}' : ''}',
                  style: const TextStyle(color: ink, height: 1.5),
                ),
              ),
            const SizedBox(height: 16),
            const Text(
              'Các tín hiệu quy tắc không phải dự đoán hay giải thích nội tại ML. Tên xuất hiện trong path hoặc query có thể không liên quan đến chủ domain.',
              style: TextStyle(color: warning, fontSize: 12, height: 1.6),
            ),
            const SizedBox(height: 8),
            Text(
              'SHA-256 danh mục · ${i.referenceSha}',
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
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: .12),
                    borderRadius: BorderRadius.circular(11),
                  ),
                  child: Icon(
                    flagged
                        ? Icons.warning_amber_rounded
                        : Icons.manage_search_rounded,
                    color: color,
                    size: 22,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Semantics(
                    header: true,
                    child: Text(
                      flagged
                          ? 'Có dấu hiệu phishing'
                          : 'Chưa phát hiện dấu hiệu phishing',
                      style: TextStyle(
                        color: color,
                        fontSize: 19,
                        fontWeight: FontWeight.w700,
                        height: 1.25,
                      ),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              'Nhãn mô hình: ${p.label}',
              style: const TextStyle(fontSize: 13, color: muted),
            ),
            const SizedBox(height: 8),
            Text(
              flagged
                  ? 'Cân nhắc dừng truy cập và xác minh nguồn gửi đường dẫn.'
                  : 'Nhãn benign không bảo đảm website an toàn. Vẫn cần kiểm tra nguồn và nội dung.',
              style: const TextStyle(fontSize: 14, height: 1.5, color: ink),
            ),
            const Divider(color: line, height: 26),
            Text(
              probability ? 'Điểm phishing' : 'Biên quyết định',
              style: const TextStyle(color: muted, fontSize: 13),
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
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 4,
              children: [
                const Text(
                  'Mô hình',
                  style: TextStyle(color: muted, fontSize: 12),
                ),
                Text(
                  p.model,
                  style: const TextStyle(
                    fontSize: 12,
                    color: ink,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
            if (p.protocol == 'week5_e1_audit') ...[
              const SizedBox(height: 6),
              const Text(
                'E1 lexical · mô hình đối chiếu',
                style: TextStyle(fontSize: 12, color: muted),
              ),
            ],
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
          const Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.error_outline_rounded, color: danger, size: 22),
              SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Chưa thể kiểm tra đường dẫn',
                  style: TextStyle(
                    fontWeight: FontWeight.w700,
                    color: danger,
                    fontSize: 18,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            failure.message,
            style: const TextStyle(color: ink, fontSize: 14, height: 1.5),
          ),
          const SizedBox(height: 10),
          if (_inputFailure(failure))
            TextButton.icon(
              key: const Key('edit-url-button'),
              onPressed: _editUrl,
              icon: const Icon(Icons.edit_outlined, size: 17),
              label: const Text('Chỉnh URL'),
            )
          else
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
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Padding(
        padding: const EdgeInsets.only(top: 2),
        child: Icon(icon, size: 16, color: teal),
      ),
      const SizedBox(width: 8),
      Flexible(
        child: Text(
          label,
          style: const TextStyle(color: muted, fontSize: 13, height: 1.45),
        ),
      ),
    ],
  );
}
