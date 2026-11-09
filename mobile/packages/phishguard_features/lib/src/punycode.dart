/// Punycode (RFC 3492), không có tiền tố "xn--".
const int _base = 36, _tMin = 1, _tMax = 26, _skew = 38, _damp = 700;
const int _initialBias = 72, _initialN = 128;

int _adapt(int delta, int numPoints, bool first) {
  delta = first ? delta ~/ _damp : delta ~/ 2;
  delta += delta ~/ numPoints;
  var k = 0;
  while (delta > ((_base - _tMin) * _tMax) ~/ 2) {
    delta ~/= (_base - _tMin);
    k += _base;
  }
  return k + (((_base - _tMin + 1) * delta) ~/ (delta + _skew));
}

int _digitChar(int d) => d < 26 ? d + 97 : d + 22;

String punycodeEncode(String input) {
  final cps = input.runes.toList();
  final out = <int>[];
  for (final c in cps) {
    if (c < 128) out.add(c);
  }
  final b = out.length;
  var h = b;
  if (b > 0) out.add(0x2D);
  var n = _initialN, delta = 0, bias = _initialBias;
  while (h < cps.length) {
    var m = 0x7FFFFFFF;
    for (final c in cps) {
      if (c >= n && c < m) m = c;
    }
    delta += (m - n) * (h + 1);
    n = m;
    for (final c in cps) {
      if (c < n) delta++;
      if (c == n) {
        var q = delta;
        for (var k = _base;; k += _base) {
          final t = k <= bias ? _tMin : (k >= bias + _tMax ? _tMax : k - bias);
          if (q < t) break;
          out.add(_digitChar(t + ((q - t) % (_base - t))));
          q = (q - t) ~/ (_base - t);
        }
        out.add(_digitChar(q));
        bias = _adapt(delta, h + 1, h == b);
        delta = 0;
        h++;
      }
    }
    delta++;
    n++;
  }
  return String.fromCharCodes(out);
}

/// Trả null nếu chuỗi không phải Punycode hợp lệ.
String? punycodeDecode(String input) {
  var n = _initialN, i = 0, bias = _initialBias;
  final out = <int>[];
  final d = input.lastIndexOf('-');
  if (d > 0) {
    for (var j = 0; j < d; j++) {
      final c = input.codeUnitAt(j);
      if (c >= 128) return null;
      out.add(c);
    }
  }
  var idx = d > 0 ? d + 1 : 0;
  while (idx < input.length) {
    final oldi = i;
    var w = 1;
    for (var k = _base;; k += _base) {
      if (idx >= input.length) return null;
      final c = input.codeUnitAt(idx++);
      int digit;
      if (c >= 48 && c <= 57) {
        digit = c - 22;
      } else if (c >= 65 && c <= 90) {
        digit = c - 65;
      } else if (c >= 97 && c <= 122) {
        digit = c - 97;
      } else {
        return null;
      }
      i += digit * w;
      final t = k <= bias ? _tMin : (k >= bias + _tMax ? _tMax : k - bias);
      if (digit < t) break;
      w *= (_base - t);
    }
    bias = _adapt(i - oldi, out.length + 1, oldi == 0);
    n += i ~/ (out.length + 1);
    i %= (out.length + 1);
    if (n > 0x10FFFF) return null;
    out.insert(i, n);
    i++;
  }
  return String.fromCharCodes(out);
}
