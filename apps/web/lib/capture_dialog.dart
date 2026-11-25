import 'dart:convert';
import 'dart:math' as math;

import 'package:desktop_drop/desktop_drop.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'capture_image.dart';
import 'capture_urls.dart';
import 'image_text_stub.dart'
    if (dart.library.js_interop) 'image_text_web.dart';
import 'qr_image.dart';

enum CaptureKind { message, image }

class CaptureDialog extends StatelessWidget {
  const CaptureDialog({
    super.key,
    required this.kind,
    required this.imagePicker,
  });

  final CaptureKind kind;
  final Future<Uint8List?> Function() imagePicker;

  @override
  Widget build(BuildContext context) {
    final fromMessage = kind == CaptureKind.message;
    final scheme = Theme.of(context).colorScheme;
    return Dialog(
      backgroundColor: scheme.surface,
      clipBehavior: Clip.antiAlias,
      insetPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 18),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(22),
        side: BorderSide(color: scheme.outline),
      ),
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: fromMessage ? 620 : 884),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(18, 16, 10, 12),
              child: Row(
                children: [
                  _PanelIcon(
                    fromMessage
                        ? Icons.chat_bubble_outline_rounded
                        : Icons.document_scanner_outlined,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Semantics(
                      header: true,
                      headingLevel: 2,
                      child: Text(
                        fromMessage
                            ? 'Kiểm tra tin nhắn'
                            : 'Kiểm tra ảnh và QR',
                        style: Theme.of(context).textTheme.titleLarge
                            ?.copyWith(fontWeight: FontWeight.w700),
                      ),
                    ),
                  ),
                  IconButton(
                    constraints: const BoxConstraints.tightFor(
                      width: 48,
                      height: 48,
                    ),
                    tooltip: 'Đóng',
                    onPressed: () => Navigator.of(context).pop(),
                    icon: const Icon(Icons.close_rounded),
                  ),
                ],
              ),
            ),
            Divider(height: 1, color: scheme.outline),
            Flexible(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(18),
                child: fromMessage
                    ? const _MessageCapture()
                    : _ImageCapture(imagePicker: imagePicker),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PanelIcon extends StatelessWidget {
  const _PanelIcon(this.icon);

  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.primary;
    return Container(
      width: 44,
      height: 44,
      decoration: BoxDecoration(
        color: color.withValues(alpha: .10),
        border: Border.all(color: color.withValues(alpha: .32)),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Icon(icon, color: color, size: 22),
    );
  }
}

class _MessageController extends TextEditingController {
  @override
  TextSpan buildTextSpan({
    required BuildContext context,
    TextStyle? style,
    required bool withComposing,
  }) {
    if (withComposing &&
        value.isComposingRangeValid &&
        !value.composing.isCollapsed) {
      return super.buildTextSpan(
        context: context,
        style: style,
        withComposing: withComposing,
      );
    }
    final color = Theme.of(context).colorScheme.primary;
    var offset = 0;
    final spans = <TextSpan>[];
    for (final link in captureUrls(text)) {
      spans.addAll([
        TextSpan(text: text.substring(offset, link.start)),
        TextSpan(
          text: link.url,
          style: TextStyle(
            color: color,
            backgroundColor: color.withValues(alpha: .14),
          ),
        ),
      ]);
      offset = link.end;
    }
    spans.add(TextSpan(text: text.substring(offset)));
    return TextSpan(style: style, children: spans);
  }
}

class _MessageCapture extends StatefulWidget {
  const _MessageCapture();

  @override
  State<_MessageCapture> createState() => _MessageCaptureState();
}

class _MessageCaptureState extends State<_MessageCapture> {
  final _message = _MessageController();
  List<CapturedUrl> _links = [];

  @override
  void dispose() {
    _message.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final count = _links.length;
    final empty = _message.text.trim().isEmpty;
    final scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(
          'Dán nội dung SMS, Zalo hoặc email. Tin nhắn được đọc trên thiết bị của bạn.',
        ),
        const SizedBox(height: 14),
        TextField(
          key: const Key('message-input'),
          controller: _message,
          minLines: 4,
          maxLines: 6,
          maxLength: messageLimit,
          autofocus: true,
          autocorrect: false,
          enableSuggestions: false,
          keyboardType: TextInputType.multiline,
          onChanged: (value) {
            final unique = <String, CapturedUrl>{
              for (final link in captureUrls(value)) link.url: link,
            };
            setState(() => _links = unique.values.toList());
          },
          decoration: const InputDecoration(
            labelText: 'Nội dung tin nhắn',
            alignLabelWithHint: true,
            hintText: 'Dán tin nhắn bạn vừa nhận…',
          ),
        ),
        if (!empty)
          Semantics(
            liveRegion: true,
            child: Text(
              count == 0
                  ? 'Chưa tìm thấy địa chỉ web trong tin nhắn.'
                  : 'Địa chỉ tìm được ($count)',
              style: TextStyle(color: scheme.onSurfaceVariant, height: 1.5),
            ),
          ),
        for (final link in _links) ...[
          const SizedBox(height: 8),
          OutlinedButton(
            onPressed: () => Navigator.of(context).pop(link.url),
            style: OutlinedButton.styleFrom(
              alignment: Alignment.centerLeft,
              minimumSize: const Size(48, 54),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              side: BorderSide(color: scheme.outline),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
            child: Row(
              children: [
                const Icon(Icons.link_rounded, size: 18),
                const SizedBox(width: 9),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        link.host,
                        style: const TextStyle(fontWeight: FontWeight.w700),
                      ),
                      if (link.url != link.host)
                        Text(
                          link.url,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            color: scheme.onSurfaceVariant,
                            fontSize: 13,
                          ),
                        ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                const Icon(Icons.arrow_forward_rounded, size: 18),
              ],
            ),
          ),
        ],
      ],
    );
  }
}

class _ImageCapture extends StatefulWidget {
  const _ImageCapture({required this.imagePicker});

  final Future<Uint8List?> Function() imagePicker;

  @override
  State<_ImageCapture> createState() => _ImageCaptureState();
}

class _PrintedUrl {
  const _PrintedUrl(this.link, this.region);

  final CapturedUrl link;
  final ImageRegion? region;
}

List<_PrintedUrl> _printedUrls(String json) {
  final links = <String, _PrintedUrl>{};
  for (final line in jsonDecode(json) as List<dynamic>) {
    final box = line['box'] as Map<String, dynamic>?;
    ImageRegion? region;
    if (box?['x0'] is num &&
        box?['y0'] is num &&
        box?['x1'] is num &&
        box?['y1'] is num) {
      final x = (box!['x0'] as num).toDouble();
      final y = (box['y0'] as num).toDouble();
      region = (
        left: x,
        top: y,
        width: (box['x1'] as num).toDouble() - x,
        height: (box['y1'] as num).toDouble() - y,
      );
    }
    for (final link in captureUrls(line['text'] as String)) {
      links.putIfAbsent(link.url, () => _PrintedUrl(link, region));
      if (links.length == maxCaptureUrls) return links.values.toList();
    }
  }
  return links.values.toList();
}

class _ImageCaptureState extends State<_ImageCapture> {
  static const _textColor = Color(0xFFB8CAFF);
  static const _noticeColor = Color(0xFFEBC283);
  final _printed = TextEditingController();
  CaptureImage? _image;
  List<_PrintedUrl> _links = [];
  String? _error;
  bool _reading = false;
  bool _dragging = false;
  bool _textFailed = false;
  bool _editingText = false;
  VoidCallback? _cancelOcr;

  @override
  void dispose() {
    _cancelOcr?.call();
    _printed.dispose();
    super.dispose();
  }

  void _clearImage() {
    setState(() {
      _image = null;
      _links = [];
      _printed.clear();
      _error = null;
      _textFailed = false;
      _editingText = false;
    });
  }

  Future<void> _read(Future<Uint8List?> Function() pick) async {
    if (_reading) return;
    setState(() {
      _reading = true;
      _dragging = false;
      _error = null;
    });
    try {
      final bytes = await pick();
      if (!mounted || bytes == null) return;
      _clearImage();
      await WidgetsBinding.instance.endOfFrame;
      if (!mounted) return;
      final image = await compute(readCaptureImage, bytes);
      if (!mounted) return;
      setState(() => _image = image);
      try {
        final output = await recognizeImageText(image.bytes, (cancel) {
          if (mounted) {
            _cancelOcr = cancel;
          } else {
            cancel();
          }
        });
        if (!mounted) return;
        final matches = _printedUrls(output);
        setState(() {
          _links = matches;
          if (matches.length == 1) _printed.text = matches.single.link.url;
        });
      } catch (_) {
        if (mounted) setState(() => _textFailed = true);
      }
    } on QrFailure catch (error) {
      if (mounted) setState(() => _error = error.message);
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'Không thể đọc ảnh. Hãy chọn ảnh khác.');
      }
    } finally {
      _cancelOcr = null;
      if (mounted) setState(() => _reading = false);
    }
  }

  void _drop(DropDoneDetails details) {
    if (_reading) return;
    if (details.files.length != 1) {
      setState(() {
        _dragging = false;
        _error = 'Mỗi lượt kiểm tra một ảnh.';
      });
      return;
    }
    _read(() => readImageFile(details.files.single));
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final image = _image;
    return DropTarget(
      onDragEntered: (_) {
        if (!_reading) setState(() => _dragging = true);
      },
      onDragExited: (_) {
        if (_dragging) setState(() => _dragging = false);
      },
      onDragDone: _drop,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (image == null)
            _dropZone(scheme)
          else ...[
            Wrap(
              alignment: WrapAlignment.spaceBetween,
              crossAxisAlignment: WrapCrossAlignment.center,
              spacing: 8,
              children: [
                Text(
                  'Xem trước và đối chiếu',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                Wrap(
                  children: [
                    TextButton.icon(
                      onPressed: _reading
                          ? null
                          : () => _read(widget.imagePicker),
                      icon: const Icon(
                        Icons.add_photo_alternate_outlined,
                        size: 18,
                      ),
                      label: const Text('Ảnh khác'),
                    ),
                    TextButton(
                      onPressed: _reading ? null : _clearImage,
                      child: const Text('Xóa ảnh'),
                    ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 8),
            LayoutBuilder(
              builder: (context, bounds) {
                final preview = _preview(scheme, image);
                final evidence = _evidence(scheme, image);
                if (bounds.maxWidth >= 610) {
                  return Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(child: preview),
                      const SizedBox(width: 16),
                      Expanded(child: evidence),
                    ],
                  );
                }
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [preview, const SizedBox(height: 14), evidence],
                );
              },
            ),
          ],
          if (_error != null) ...[
            const SizedBox(height: 10),
            Semantics(
              liveRegion: true,
              child: Text(_error!, style: TextStyle(color: scheme.error)),
            ),
          ],
        ],
      ),
    );
  }

  Widget _dropZone(ColorScheme scheme) => Container(
    padding: const EdgeInsets.all(20),
    decoration: BoxDecoration(
      gradient: LinearGradient(
        colors: [scheme.primary.withValues(alpha: .13), scheme.surface],
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
      ),
      borderRadius: BorderRadius.circular(18),
      border: Border.all(
        color: _dragging ? scheme.primary : scheme.outline,
        width: _dragging ? 2 : 1,
      ),
    ),
    child: Column(
      children: [
        const _PanelIcon(Icons.add_photo_alternate_outlined),
        const SizedBox(height: 14),
        Text(
          _reading ? 'Đang mở ảnh…' : 'Chọn hoặc thả ảnh chụp',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.titleLarge
              ?.copyWith(fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 6),
        Text(
          'PNG, JPEG, WebP · Tối đa 8 MB và 4 megapixel',
          textAlign: TextAlign.center,
          style: TextStyle(color: scheme.onSurfaceVariant),
        ),
        const SizedBox(height: 16),
        FilledButton.icon(
          key: const Key('capture-image-select'),
          onPressed: _reading ? null : () => _read(widget.imagePicker),
          icon: const Icon(Icons.image_outlined),
          label: const Text('Chọn ảnh'),
        ),
        const SizedBox(height: 8),
        const Text(
          'Chữ và QR được đọc trên thiết bị.',
          textAlign: TextAlign.center,
        ),
      ],
    ),
  );

  Widget _preview(ColorScheme scheme, CaptureImage image) {
    ImageRegion? textRegion;
    for (final link in _links) {
      if (link.link.url == _printed.text) textRegion = link.region;
    }
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: scheme.shadow.withValues(alpha: .25),
        border: Border.all(color: _dragging ? scheme.primary : scheme.outline),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        children: [
          LayoutBuilder(
            builder: (context, bounds) {
              final scale = math.min(
                bounds.maxWidth / image.width,
                338 / image.height,
              );
              return Center(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(8),
                  child: SizedBox(
                    width: image.width * scale,
                    height: image.height * scale,
                    child: Stack(
                      fit: StackFit.expand,
                      children: [
                        Image.memory(
                          image.bytes,
                          fit: BoxFit.fill,
                          excludeFromSemantics: true,
                        ),
                        if (textRegion != null)
                          _outline(textRegion, scale, _textColor, 'chữ'),
                        if (image.qrRegion != null)
                          _outline(
                            image.qrRegion!,
                            scale,
                            scheme.primary,
                            'mã QR',
                          ),
                      ],
                    ),
                  ),
                ),
              );
            },
          ),
          if (textRegion != null || image.qrRegion != null) ...[
            const SizedBox(height: 10),
            Wrap(
              spacing: 12,
              children: [
                if (textRegion != null)
                  const Text(
                    'Chữ tìm được',
                    style: TextStyle(color: _textColor),
                  ),
                if (image.qrRegion != null)
                  Text('Mã QR', style: TextStyle(color: scheme.primary)),
              ],
            ),
          ],
        ],
      ),
    );
  }

  Widget _outline(
    ImageRegion region,
    double scale,
    Color color,
    String label,
  ) => Positioned(
    left: region.left * scale,
    top: region.top * scale,
    width: math.max(0, region.width * scale),
    height: math.max(0, region.height * scale),
    child: IgnorePointer(
      child: Semantics(
        label: 'Vùng $label trên ảnh',
        child: DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(4),
            border: Border.all(color: color, width: 2),
            color: color.withValues(alpha: .10),
          ),
        ),
      ),
    ),
  );

  Widget _evidence(ColorScheme scheme, CaptureImage image) {
    final typed = _printed.text.trim();
    final fromText = captureHost(typed);
    final fromQr = image.qr == null ? null : captureHost(image.qr!);
    final editText = _editingText || _links.isEmpty;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (fromText != null && fromQr != null) ...[
          _comparison(scheme, fromText, fromQr),
          const SizedBox(height: 12),
        ],
        _card(scheme, _textColor, Icons.text_fields_rounded, 'Chữ trong ảnh', [
          if (_reading) ...[
            Semantics(
              liveRegion: true,
              child: const Text('Đang đọc chữ trên thiết bị…'),
            ),
            if (!MediaQuery.disableAnimationsOf(context)) ...[
              const SizedBox(height: 8),
              const LinearProgressIndicator(minHeight: 2),
            ],
          ] else ...[
            if (_textFailed)
              const Text(
                'Bộ đọc chữ chưa khả dụng. Bạn có thể nhập địa chỉ thấy trên ảnh.',
              ),
            if (!_textFailed && _links.isEmpty)
              const Text(
                'Chưa đọc được địa chỉ từ ảnh. Bạn có thể nhập lại để đối chiếu.',
              ),
            if (_links.length > 1)
              Wrap(
                spacing: 8,
                runSpacing: 4,
                children: [
                  for (final candidate in _links)
                    ChoiceChip(
                      label: Text(candidate.link.host),
                      selected: _printed.text == candidate.link.url,
                      onSelected: (_) =>
                          setState(() => _printed.text = candidate.link.url),
                    ),
                ],
              ),
            if (editText) ...[
              const SizedBox(height: 8),
              TextField(
                key: const Key('capture-printed-url'),
                controller: _printed,
                autofocus: _editingText,
                maxLength: 4096,
                keyboardType: TextInputType.url,
                autocorrect: false,
                enableSuggestions: false,
                onChanged: (_) => setState(() {}),
                decoration: InputDecoration(
                  counterText: '',
                  labelText: 'Địa chỉ đọc từ ảnh',
                  hintText: 'Ví dụ example.org',
                  errorText: typed.isNotEmpty && fromText == null
                      ? 'Hãy kiểm tra lại ký tự trong địa chỉ.'
                      : null,
                ),
              ),
            ] else if (fromText != null)
              Text(
                fromText,
                style: Theme.of(context).textTheme.titleMedium
                    ?.copyWith(fontWeight: FontWeight.w700),
              ),
            Wrap(
              spacing: 6,
              children: [
                if (!editText)
                  TextButton(
                    onPressed: () => setState(() => _editingText = true),
                    child: const Text('Sửa URL đọc được'),
                  ),
                if (fromText != null)
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(typed),
                    child: const Text('Dùng URL trong ảnh'),
                  ),
              ],
            ),
          ],
        ]),
        const SizedBox(height: 10),
        _card(
          scheme,
          scheme.primary,
          Icons.qr_code_rounded,
          'Địa chỉ trong QR',
          [
            if (fromQr != null) ...[
              Text(
                fromQr,
                style: Theme.of(context).textTheme.titleMedium
                    ?.copyWith(fontWeight: FontWeight.w700),
              ),
              FilledButton.icon(
                key: const Key('capture-use-qr'),
                onPressed: () => Navigator.of(context).pop(image.qr!),
                icon: const Icon(Icons.arrow_forward_rounded, size: 17),
                label: const Text('Dùng URL từ QR'),
              ),
            ] else
              Text(
                image.qr == null
                    ? 'Chưa tìm thấy mã QR đọc được.'
                    : 'QR chứa dữ liệu khác địa chỉ web.',
              ),
          ],
        ),
      ],
    );
  }

  Widget _comparison(ColorScheme scheme, String fromText, String fromQr) {
    final comparison = compareCaptureHosts(fromText, fromQr);
    final same = comparison == HostComparison.same;
    final color = same ? scheme.primary : _noticeColor;
    final title = switch (comparison) {
      HostComparison.same => 'Cùng địa chỉ máy chủ',
      HostComparison.different => 'Hai địa chỉ máy chủ khác nhau',
      HostComparison.reviewIdna => 'Cần đối chiếu cách viết',
    };
    return Semantics(
      key: const Key('capture-comparison'),
      liveRegion: true,
      child: _card(scheme, color, Icons.compare_arrows_rounded, title, [
        Wrap(
          spacing: 14,
          runSpacing: 4,
          children: [
            Text(
              'Ảnh · $fromText',
              style: const TextStyle(
                color: _textColor,
                fontWeight: FontWeight.w700,
              ),
            ),
            Text(
              'QR · $fromQr',
              style: TextStyle(
                color: scheme.primary,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),
        if (comparison == HostComparison.reviewIdna)
          const Text(
            'Địa chỉ có Unicode hoặc dạng Punycode. Hãy kiểm tra lại phần chữ.',
          ),
      ], emphasis: true),
    );
  }

  Widget _card(
    ColorScheme scheme,
    Color color,
    IconData icon,
    String title,
    List<Widget> children, {
    bool emphasis = false,
  }) => Container(
    padding: const EdgeInsets.all(13),
    decoration: BoxDecoration(
      color: emphasis ? color.withValues(alpha: .10) : null,
      borderRadius: BorderRadius.circular(14),
      border: Border.all(
        color: emphasis ? color.withValues(alpha: .46) : scheme.outline,
      ),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Icon(icon, color: color, size: 20),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                title,
                style: TextStyle(color: color, fontWeight: FontWeight.w700),
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        ...children,
      ],
    ),
  );
}
