/// Mô phỏng ipaddress.ip_address(s).compressed. Trả null nếu không phải IP hợp lệ.
/// Lưu ý: địa chỉ IPv4-mapped (::ffff:1.2.3.4) in ở dạng hex; Python >= 3.13 in dạng thập phân.
final RegExp _v4Part = RegExp(r'^[0-9]{1,3}$');
final RegExp _hexGroup = RegExp(r'^[0-9a-fA-F]{1,4}$');

String? parseIp(String input) {
  final pct = input.indexOf('%');
  if (pct != -1) {
    final scope = input.substring(pct + 1);
    if (scope.isEmpty || scope.contains('/') || scope.contains('%')) return null;
    final v6 = _parseV6(input.substring(0, pct));
    return v6 == null ? null : '$v6%$scope';
  }
  return input.contains(':') ? _parseV6(input) : _parseV4(input);
}

List<int>? _v4Bytes(String s) {
  final parts = s.split('.');
  if (parts.length != 4) return null;
  final nums = <int>[];
  for (final p in parts) {
    if (!_v4Part.hasMatch(p)) return null;
    if (p.length > 1 && p.startsWith('0')) return null; // Python >= 3.9.5 từ chối số 0 đứng đầu
    final v = int.parse(p);
    if (v > 255) return null;
    nums.add(v);
  }
  return nums;
}

String? _parseV4(String s) => _v4Bytes(s)?.join('.');

List<int>? _groups(List<String> parts, {required bool allowV4Last}) {
  final out = <int>[];
  for (var i = 0; i < parts.length; i++) {
    final p = parts[i];
    if (allowV4Last && i == parts.length - 1 && p.contains('.')) {
      final b = _v4Bytes(p);
      if (b == null) return null;
      out.add(b[0] * 256 + b[1]);
      out.add(b[2] * 256 + b[3]);
    } else {
      if (!_hexGroup.hasMatch(p)) return null;
      out.add(int.parse(p, radix: 16));
    }
  }
  return out;
}

String? _parseV6(String s) {
  if (!s.contains(':')) return null;
  final dc = s.indexOf('::');
  if (dc != s.lastIndexOf('::')) return null;
  List<int> groups;
  if (dc == -1) {
    final g = _groups(s.split(':'), allowV4Last: true);
    if (g == null || g.length != 8) return null;
    groups = g;
  } else {
    final h = s.substring(0, dc), t = s.substring(dc + 2);
    final head = h.isEmpty ? <int>[] : _groups(h.split(':'), allowV4Last: false);
    final tail = t.isEmpty ? <int>[] : _groups(t.split(':'), allowV4Last: true);
    if (head == null || tail == null) return null;
    final missing = 8 - head.length - tail.length;
    if (missing < 1) return null;
    groups = [...head, ...List<int>.filled(missing, 0), ...tail];
  }
  var bestStart = -1, bestLen = 0, curStart = -1, curLen = 0;
  for (var i = 0; i < 8; i++) {
    if (groups[i] == 0) {
      if (curStart == -1) {
        curStart = i;
        curLen = 0;
      }
      curLen++;
      if (curLen > bestLen) {
        bestLen = curLen;
        bestStart = curStart;
      }
    } else {
      curStart = -1;
      curLen = 0;
    }
  }
  String hex(int g) => g.toRadixString(16);
  if (bestLen > 1) {
    final left = groups.sublist(0, bestStart).map(hex).join(':');
    final right = groups.sublist(bestStart + bestLen).map(hex).join(':');
    return '$left::$right';
  }
  return groups.map(hex).join(':');
}
