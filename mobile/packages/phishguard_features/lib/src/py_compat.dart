/// Các hàm mô phỏng hành vi chuỗi của Python (str) mà contract phụ thuộc vào.
import 'dart:convert';

/// Ký tự mà str.isspace() của Python coi là khoảng trắng.
bool isPySpaceCode(int c) =>
    (c >= 0x09 && c <= 0x0D) ||
    (c >= 0x1C && c <= 0x20) ||
    c == 0x85 ||
    c == 0xA0 ||
    c == 0x1680 ||
    (c >= 0x2000 && c <= 0x200A) ||
    c == 0x2028 ||
    c == 0x2029 ||
    c == 0x202F ||
    c == 0x205F ||
    c == 0x3000;

/// str.strip() của Python.
String pyStrip(String s) {
  final r = s.runes.toList();
  var a = 0;
  var b = r.length;
  while (a < b && isPySpaceCode(r[a])) {
    a++;
  }
  while (b > a && isPySpaceCode(r[b - 1])) {
    b--;
  }
  return String.fromCharCodes(r.sublist(a, b));
}

bool hasPySpace(String s) => s.runes.any(isPySpaceCode);

/// len() của Python = số code point (không phải số đơn vị UTF-16 như String.length của Dart).
int pyLen(String s) => s.runes.length;

bool isAscii(String s) => s.codeUnits.every((c) => c < 128);

final RegExp _alphaRe = RegExp(r'^\p{L}$', unicode: true);
final RegExp _ndRe = RegExp(r'^\p{Nd}$', unicode: true);

/// str.isalpha() cho một code point (Python: nhóm Unicode L*).
bool pyIsAlpha(int r) {
  if (r < 128) return (r >= 65 && r <= 90) || (r >= 97 && r <= 122);
  return _alphaRe.hasMatch(String.fromCharCode(r));
}

/// str.isdigit() cho một code point: Nd cộng các chữ số dạng No hay gặp (mũ, chỉ số dưới, số trong vòng...).
/// Xấp xỉ: ký tự hiếm ngoài danh sách này có thể lệch với Python (ghi vào báo cáo parity nếu gặp).
bool pyIsDigit(int r) {
  if (r < 128) return r >= 48 && r <= 57;
  if (_ndRe.hasMatch(String.fromCharCode(r))) return true;
  return r == 0xB2 ||
      r == 0xB3 ||
      r == 0xB9 ||
      r == 0x2070 ||
      (r >= 0x2074 && r <= 0x2079) ||
      (r >= 0x2080 && r <= 0x2089) ||
      (r >= 0x2460 && r <= 0x2468) ||
      (r >= 0x2474 && r <= 0x247C) ||
      (r >= 0x2488 && r <= 0x2490) ||
      (r >= 0x2776 && r <= 0x277E) ||
      (r >= 0x2780 && r <= 0x2788) ||
      (r >= 0x278A && r <= 0x2792);
}

final RegExp _pctRun = RegExp(r'(?:%[0-9a-fA-F]{2})+');

/// urllib.parse.unquote: giải %XX theo UTF-8, byte sai -> U+FFFD.
String unquote(String s) => s.replaceAllMapped(_pctRun, (m) {
      final t = m[0]!;
      final bytes = <int>[];
      for (var i = 0; i < t.length; i += 3) {
        bytes.add(int.parse(t.substring(i + 1, i + 3), radix: 16));
      }
      return utf8.decode(bytes, allowMalformed: true);
    });
