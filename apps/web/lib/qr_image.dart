import 'dart:typed_data';

import 'package:file_selector/file_selector.dart';
import 'package:image/image.dart' as img;
import 'package:zxing2/qrcode.dart';

class QrFailure implements Exception {
  const QrFailure(this.message);
  final String message;
}

Future<Uint8List?> chooseQrImage() async {
  final file = await openFile(
    acceptedTypeGroups: const [
      XTypeGroup(
        label: 'Ảnh QR',
        extensions: ['png', 'jpg', 'jpeg', 'webp'],
        mimeTypes: ['image/png', 'image/jpeg', 'image/webp'],
      ),
    ],
  );
  if (file == null) return null;
  if (await file.length() > 8 * 1024 * 1024) {
    throw const QrFailure('Ảnh tối đa 8 MB. Hãy chọn ảnh nhỏ hơn.');
  }
  return file.readAsBytes();
}

String decodeQrImage(Uint8List bytes) {
  if (bytes.isEmpty || bytes.length > 8 * 1024 * 1024) {
    throw const QrFailure('Ảnh rỗng hoặc quá 8 MB. Hãy chọn ảnh khác.');
  }
  img.Image? image;
  try {
    final decoder = img.findDecoderForData(bytes);
    final info = decoder?.startDecode(bytes);
    if (info == null) throw const FormatException();
    if (info.width * info.height > 4 * 1024 * 1024) {
      throw const QrFailure(
        'Ảnh tối đa 4 megapixel. Hãy thu nhỏ ảnh rồi thử lại.',
      );
    }
    image = decoder!.decodeFrame(0);
  } on QrFailure {
    rethrow;
  } catch (_) {
    throw const QrFailure(
      'Không đọc được ảnh. Chọn ảnh PNG, JPEG hoặc WebP hợp lệ.',
    );
  }
  if (image == null) {
    throw const QrFailure('Không đọc được ảnh. Hãy chọn ảnh khác.');
  }
  String text;
  try {
    final pixels = image
        .convert(format: img.Format.uint8, numChannels: 4)
        .getBytes(order: img.ChannelOrder.abgr);
    final bitmap = BinaryBitmap(
      HybridBinarizer(
        RGBLuminanceSource(
          image.width,
          image.height,
          pixels.buffer.asInt32List(),
        ),
      ),
    );
    text = QRCodeReader().decode(bitmap).text.trim();
  } catch (_) {
    throw const QrFailure(
      'Không tìm thấy QR đọc được. Dùng ảnh rõ, chứa một mã QR.',
    );
  }
  if (!looksLikeWebUrl(text)) {
    throw const QrFailure(
      'QR không chứa URL web hợp lệ. Chỉ hỗ trợ http(s) hoặc tên miền.',
    );
  }
  return text;
}

// Preliminary QR-content check only. The unchanged backend parser is authoritative.
bool looksLikeWebUrl(String text) {
  if (text.isEmpty ||
      text.runes.length > 4096 ||
      RegExp(r'[\s\x00-\x1f\x7f]').hasMatch(text)) {
    return false;
  }
  try {
    final hasScheme = text.contains('://');
    if (!hasScheme && text.contains('@')) return false;
    final uri = Uri.parse(
      hasScheme
          ? text
          : text.startsWith('//')
          ? 'http:$text'
          : 'http://$text',
    );
    return {'http', 'https'}.contains(uri.scheme.toLowerCase()) &&
        uri.host.isNotEmpty &&
        (uri.host.contains('.') || uri.host.contains(':')) &&
        uri.port <= 65535;
  } on FormatException {
    return false;
  }
}
