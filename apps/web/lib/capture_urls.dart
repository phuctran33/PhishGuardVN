import 'qr_image.dart';

const messageLimit = 8000;
const maxCaptureUrls = 12;

class CapturedUrl {
  const CapturedUrl(this.url, this.host, this.start);

  final String url;
  final String host;
  final int start;
  int get end => start + url.length;
}

final _urls = RegExp(
  r'''https?://[^\s<>"'“”‘’]+|(?:[\p{L}\p{N}-]{1,63}\.)+[\p{L}][\p{L}\p{N}-]{1,62}(?::[0-9]+)?(?:[/?#][^\s<>"'“”‘’]*)?''',
  caseSensitive: false,
  unicode: true,
);
final _prefix = RegExp(r'[\p{L}\p{N}.@_/\-=?#]', unicode: true);
final _otherScheme = RegExp(
  r'\b(?:about|blob|data|file|ftp|javascript|mailto|sms|tel|wss?):$',
  caseSensitive: false,
);
final _suffix = RegExp(r'[.,;!]+$');
final _afterWrapper = RegExp(r'^[.,;!]*$');
final _asciiHost = RegExp(r'^[a-z0-9.:\-]+$');
final _domainLabel = RegExp(
  r'^[\p{L}\p{N}](?:[\p{L}\p{N}-]*[\p{L}\p{N}])?$',
  unicode: true,
);

/// The host shown during capture. The chosen URL is kept intact for the API.
String? captureHost(String url) {
  final uri = parseWebUrl(url);
  if (uri == null || uri.authority.contains('@')) return null;
  try {
    final host = Uri.decodeComponent(uri.host)
        .toLowerCase()
        .replaceFirst(RegExp(r'\.$'), '');
    if (host.contains(':')) return host; // Uri validated the IPv6 literal.
    if (host.isEmpty || !host.split('.').every(_domainLabel.hasMatch)) {
      return null;
    }
    return host;
  } on FormatException {
    return null;
  }
}

List<CapturedUrl> captureUrls(String text) {
  final input = text.length > messageLimit
      ? text.substring(0, messageLimit)
      : text;
  final hits = <CapturedUrl>[];
  for (final match in _urls.allMatches(input)) {
    if (text.length > input.length && match.end == input.length) break;
    if (match.start > 0 && _prefix.hasMatch(input[match.start - 1])) continue;
    if (match.start > 0 &&
        input[match.start - 1] == ':' &&
        _otherScheme.hasMatch(input.substring(0, match.start))) {
      continue;
    }
    var value = match.group(0)!;
    if (match.start > 0) {
      final opening = input[match.start - 1];
      final closing = const {'(': ')', '[': ']', '{': '}'}[opening];
      final wrapperEnd = closing == null ? -1 : value.lastIndexOf(closing);
      if (closing != null &&
          wrapperEnd >= 0 &&
          _afterWrapper.hasMatch(value.substring(wrapperEnd + 1))) {
        final inside = value.substring(0, wrapperEnd);
        if (closing.allMatches(inside).length >=
            opening.allMatches(inside).length) {
          value = inside;
        }
      }
    }
    final authority = value.contains('://')
        ? value.split('://').skip(1).join('://')
        : value;
    if (!authority.contains(RegExp(r'[/#?]'))) {
      value = value.replaceFirst(_suffix, '');
    }
    if (match.end < input.length && input[match.end] == '@') continue;
    if (match.end + 1 < input.length &&
        input[match.end] == ':' &&
        !RegExp(r'\s').hasMatch(input[match.end + 1])) {
      continue;
    }
    final host = captureHost(value);
    if (host != null) hits.add(CapturedUrl(value, host, match.start));
    if (hits.length >= maxCaptureUrls) break;
  }
  return hits;
}

enum HostComparison { same, different, reviewIdna }

HostComparison compareCaptureHosts(String left, String right) {
  if (left == right) return HostComparison.same;
  // Unicode and Punycode may be two representations of a single hostname.
  bool ordinary(String host) =>
      _asciiHost.hasMatch(host) &&
      !host.split('.').any((label) => label.startsWith('xn--'));
  return ordinary(left) && ordinary(right)
      ? HostComparison.different
      : HostComparison.reviewIdna;
}
