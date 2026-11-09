import 'package:unorm_dart/unorm_dart.dart' as unorm;

import 'punycode.dart';
import 'py_compat.dart';

final RegExp _dots = RegExp('[\u3002\uFF0E\uFF61]');
final RegExp _lmd = RegExp(r'^[\p{L}\p{M}\p{Nd}]$', unicode: true);
final RegExp _mark = RegExp(r'^\p{M}$', unicode: true);

/// Xấp xỉ check_label của gói idna (IDNA2008): nhãn chỉ gồm chữ/dấu tổ hợp/chữ số,
/// ký tự ASCII chỉ [a-z0-9-], không bắt đầu/kết thúc bằng '-', không có '--' ở vị trí 3-4,
/// không bắt đầu bằng dấu tổ hợp. Emoji, ký hiệu, dấu câu và '_' bị từ chối (Python ném UnicodeError).
bool _validIdnaLabel(String label) {
  if (label.startsWith('xn--')) return true;
  if (label.startsWith('-') || label.endsWith('-')) return false;
  if (label.length >= 4 && label.substring(2, 4) == '--') return false;
  final runes = label.runes.toList();
  if (_mark.hasMatch(String.fromCharCode(runes.first))) return false;
  for (final r in runes) {
    if (r < 128) {
      final ok = (r >= 97 && r <= 122) || (r >= 48 && r <= 57) || r == 45;
      if (!ok) return false;
    } else if (!_lmd.hasMatch(String.fromCharCode(r))) {
      return false;
    }
  }
  return true;
}

/// Xấp xỉ idna.encode(host, uts46=True) của Python: lower + NFKC + Punycode từng nhãn.
/// Chỉ kiểm tra xấp xỉ quy tắc IDNA2008 (xem _validIdnaLabel). Chỉ cam kết khớp trên các ca parity.
/// Trả null khi lỗi (ứng với UnicodeError -> invalid_hostname).
String? hostToAscii(String host) {
  final mapped = unorm.nfkc(host.toLowerCase()).replaceAll(_dots, '.');
  final labels = mapped.split('.');
  final out = <String>[];
  for (var i = 0; i < labels.length; i++) {
    final label = labels[i];
    if (label.isEmpty) return null; // nhãn rỗng giữa host
    if (!_validIdnaLabel(label)) return null;
    final ascii = isAscii(label) ? label : 'xn--${punycodeEncode(label)}';
    if (ascii.length > 63) return null;
    out.add(ascii);
  }
  return out.join('.');
}

/// Giải Punycode từng nhãn xn--; lỗi thì giữ nguyên nhãn (như _decode_host của Python).
String decodeHost(String host) => host.split('.').map((label) {
      if (label.startsWith('xn--')) {
        return punycodeDecode(label.substring(4)) ?? label;
      }
      return label;
    }).join('.');
