/// Port của url_parser.py. Tự tách URL theo ngữ nghĩa urllib.parse.urlsplit (không dùng Uri.parse
/// của Dart vì khác hành vi: port lỗi, userinfo, ;params, host rỗng...).
import 'idna.dart';
import 'ip.dart';
import 'psl.dart';
import 'py_compat.dart';

final RegExp schemeRe = RegExp(r'^[a-zA-Z][a-zA-Z0-9+.\-]*://');
final RegExp schemeStripRe = RegExp(r'^(?:[a-zA-Z][a-zA-Z0-9+.\-]*:)?//');
final RegExp _schemePrefix = RegExp(r'^[a-zA-Z][a-zA-Z0-9+.\-]*:');
final RegExp _digitsOnly = RegExp(r'^[0-9]+$');
final RegExp _ipvFuture = RegExp(r'^v[a-fA-F0-9]+\..+$');

class ParsedUrl {
  final String rawUrl;
  final String hostname;
  final String? registrableDomain;
  final String subdomain;
  final String path;
  final String query;
  final int? port;
  final bool schemeWasAdded;
  final bool isIp;
  final bool isValid;
  final String? errorReason;

  const ParsedUrl({
    required this.rawUrl,
    this.hostname = '',
    this.registrableDomain,
    this.subdomain = '',
    this.path = '',
    this.query = '',
    this.port,
    this.schemeWasAdded = false,
    this.isIp = false,
    this.isValid = false,
    this.errorReason,
  });
}

class _ValueError implements Exception {
  final String message;
  _ValueError(this.message);
}

class _Split {
  final String netloc, path, query;
  _Split(this.netloc, this.path, this.query);
}

_Split _urlsplit(String url) {
  final u = url.replaceAll(RegExp(r'[\t\r\n]'), '');
  final m = _schemePrefix.firstMatch(u);
  var rest = m == null ? u : u.substring(m.end);
  var netloc = '';
  if (rest.startsWith('//')) {
    var end = rest.length;
    for (final ch in const ['/', '?', '#']) {
      final i = rest.indexOf(ch, 2);
      if (i != -1 && i < end) end = i;
    }
    netloc = rest.substring(2, end);
    rest = rest.substring(end);
    if (netloc.contains('[') != netloc.contains(']')) {
      throw _ValueError('Invalid IPv6 URL');
    }
    if (netloc.contains('[')) {
      final inner = netloc.substring(netloc.indexOf('[') + 1).split(']').first;
      if (inner.startsWith('v')) {
        if (!_ipvFuture.hasMatch(inner)) throw _ValueError('Invalid IPvFuture');
      } else {
        final ip = parseIp(inner);
        if (ip == null || !ip.contains(':')) throw _ValueError('Invalid IPv6');
      }
    }
  }
  final h = rest.indexOf('#');
  if (h != -1) rest = rest.substring(0, h);
  var query = '';
  final q = rest.indexOf('?');
  if (q != -1) {
    query = rest.substring(q + 1);
    rest = rest.substring(0, q);
  }
  return _Split(netloc, rest, query);
}

/// (hostname, port) theo SplitResult._hostinfo; hostname = null nếu rỗng.
(String?, String?) _hostinfo(String netloc) {
  final at = netloc.lastIndexOf('@');
  final hostinfo = at == -1 ? netloc : netloc.substring(at + 1);
  String hostname, port;
  final ob = hostinfo.indexOf('[');
  if (ob != -1) {
    final bracketed = hostinfo.substring(ob + 1);
    final cb = bracketed.indexOf(']');
    hostname = cb == -1 ? bracketed : bracketed.substring(0, cb);
    final after = cb == -1 ? '' : bracketed.substring(cb + 1);
    final c = after.indexOf(':');
    port = c == -1 ? '' : after.substring(c + 1);
  } else {
    final c = hostinfo.indexOf(':');
    hostname = c == -1 ? hostinfo : hostinfo.substring(0, c);
    port = c == -1 ? '' : hostinfo.substring(c + 1);
  }
  if (hostname.isEmpty) return (null, port.isEmpty ? null : port);
  final pct = hostname.indexOf('%');
  final lowered = pct == -1
      ? hostname.toLowerCase()
      : hostname.substring(0, pct).toLowerCase() + hostname.substring(pct);
  return (lowered, port.isEmpty ? null : port);
}

int? _checkedPort(String? port) {
  if (port == null) return null;
  if (!_digitsOnly.hasMatch(port)) throw _ValueError('Port could not be cast to integer');
  final p = int.tryParse(port);
  if (p == null || p > 65535) throw _ValueError('Port out of range 0-65535');
  return p;
}

String _stripChars(String s, String chars) {
  var a = 0, b = s.length;
  while (a < b && chars.contains(s[a])) {
    a++;
  }
  while (b > a && chars.contains(s[b - 1])) {
    b--;
  }
  return s.substring(a, b);
}

/// null nếu IDN không hợp lệ (UnicodeError trong Python).
({String host, bool isIp})? _normalizeHost(String host) {
  var h = _stripChars(host, '[]');
  var end = h.length;
  while (end > 0 && h[end - 1] == '.') {
    end--;
  }
  h = h.substring(0, end);
  final ip = parseIp(h);
  if (ip != null) return (host: ip, isIp: true);
  if (isAscii(h)) return (host: h.toLowerCase(), isIp: false);
  final a = hostToAscii(h);
  if (a == null) return null;
  return (host: a.toLowerCase(), isIp: false);
}

class UrlParser {
  final PublicSuffixList psl;
  const UrlParser(this.psl);

  ParsedUrl parse(String? rawUrl) {
    if (rawUrl == null) return const ParsedUrl(rawUrl: '', errorReason: 'missing_url');
    final stripped = pyStrip(rawUrl);
    if (stripped.isEmpty) return const ParsedUrl(rawUrl: '', errorReason: 'empty_url');

    String working;
    bool added;
    if (schemeRe.hasMatch(stripped)) {
      working = stripped;
      added = false;
    } else if (stripped.startsWith('//')) {
      working = 'http:$stripped';
      added = true;
    } else {
      working = 'http://$stripped';
      added = true;
    }

    try {
      final sp = _urlsplit(working);
      final (rawHost, rawPort) = _hostinfo(sp.netloc);
      ParsedUrl fail(String reason, {String hostname = '', int? port, String subdomain = ''}) =>
          ParsedUrl(
              rawUrl: stripped,
              path: sp.path,
              query: sp.query,
              schemeWasAdded: added,
              hostname: hostname,
              port: port,
              subdomain: subdomain,
              errorReason: reason);

      int? port;
      try {
        port = _checkedPort(rawPort);
      } on _ValueError {
        return fail('invalid_port', hostname: rawHost ?? '');
      }

      if (rawHost == null || rawHost.isEmpty || hasPySpace(rawHost)) {
        return fail('invalid_hostname', hostname: rawHost ?? '', port: port);
      }

      final norm = _normalizeHost(rawHost);
      if (norm == null) return fail('invalid_hostname', hostname: rawHost, port: port);
      final host = norm.host;

      if (norm.isIp) {
        return ParsedUrl(
            rawUrl: stripped,
            path: sp.path,
            query: sp.query,
            schemeWasAdded: added,
            hostname: host,
            port: port,
            isIp: true,
            isValid: true,
            errorReason: 'is_ip_no_domain');
      }

      final labels = host.split('.');
      final idx = psl.suffixIndex(labels);
      // idx == labels.length: không có suffix; idx == 0: host chính là suffix -> không có domain.
      if (idx >= labels.length || idx == 0) {
        // tldextract: không có suffix -> domain = nhãn cuối, subdomain = các nhãn trước đó;
        // host chính là suffix -> không có domain và subdomain rỗng.
        final sub = idx >= labels.length ? labels.sublist(0, labels.length - 1).join('.') : '';
        return fail('unresolved_domain', hostname: host, port: port, subdomain: sub.toLowerCase());
      }
      final reg = '${labels[idx - 1]}.${labels.sublist(idx).join('.')}'.toLowerCase();
      final sub = labels.sublist(0, idx - 1).join('.').toLowerCase();
      return ParsedUrl(
          rawUrl: stripped,
          path: sp.path,
          query: sp.query,
          schemeWasAdded: added,
          hostname: host,
          registrableDomain: reg,
          subdomain: sub,
          port: port,
          isValid: true);
    } on _ValueError {
      return ParsedUrl(rawUrl: stripped, schemeWasAdded: added, errorReason: 'parsing_error:ValueError');
    } catch (e) {
      return ParsedUrl(
          rawUrl: stripped, schemeWasAdded: added, errorReason: 'parsing_error:${e.runtimeType}');
    }
  }
}
