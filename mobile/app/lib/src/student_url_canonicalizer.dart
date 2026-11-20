import 'package:phishguard_features/phishguard_features.dart'
    show UrlParser, hostToAscii, parseIp;

import 'input_validation.dart';

/// Python student_text() URL validation and canonicalization.
///
/// The output intentionally excludes scheme, userinfo and fragment.
/// It preserves path and query.
class StudentUrlCanonicalizer {
  StudentUrlCanonicalizer(this._parser);

  final UrlParser _parser;

  static final RegExp _scheme =
      RegExp(r'^[a-zA-Z][a-zA-Z0-9+.\-]*://');

  String canonicalize(String input) {
    final issue = validateUrlInput(input);
    if (issue != null) {
      throw FormatException('Invalid Student URL input: $issue');
    }

    // Python validate_urls() requires parse_url(...).is_valid.
    final parsed = _parser.parse(input);
    if (!parsed.isValid) {
      throw FormatException(
        'Invalid Student URL: ${parsed.errorReason ?? "invalid_url"}',
      );
    }

    var working = input;
    if (!_scheme.hasMatch(working)) {
      working = working.startsWith('//')
          ? 'http:$working'
          : '//$working';
    }

    final schemeMatch = _scheme.firstMatch(working);
    final scheme = schemeMatch == null
        ? ''
        : working.substring(0, schemeMatch.end - 3).toLowerCase();

    late String rest;

    if (schemeMatch != null) {
    // Scheme regex đã tiêu thụ cả "://".
    rest = working.substring(schemeMatch.end);
    } else if (working.startsWith('//')) {
    // URL dạng //example.com khi không có scheme.
    rest = working.substring(2);
    } else {
    throw const FormatException('URL has no authority');
    }

    // Split authority from path/query/fragment.
    var authorityEnd = rest.length;
    for (final delimiter in const ['/', '?', '#']) {
      final index = rest.indexOf(delimiter);
      if (index >= 0 && index < authorityEnd) {
        authorityEnd = index;
      }
    }

    final authority = rest.substring(0, authorityEnd);
    final suffix = rest.substring(authorityEnd);

    // Remove fragment, then split path and query.
    final fragmentIndex = suffix.indexOf('#');
    final withoutFragment = fragmentIndex < 0
        ? suffix
        : suffix.substring(0, fragmentIndex);

    final queryIndex = withoutFragment.indexOf('?');
    final path = queryIndex < 0
        ? withoutFragment
        : withoutFragment.substring(0, queryIndex);

    final query = queryIndex < 0
        ? ''
        : withoutFragment.substring(queryIndex + 1);

    // Python urlsplit(...).hostname excludes userinfo.
    final at = authority.lastIndexOf('@');
    final hostPort = at < 0
        ? authority
        : authority.substring(at + 1);

    if (hostPort.isEmpty) {
      throw const FormatException('URL has no hostname');
    }

    String rawHost;
    String? rawPort;

    if (hostPort.startsWith('[')) {
      final close = hostPort.indexOf(']');
      if (close < 0) {
        throw const FormatException('Invalid IPv6 URL');
      }

      rawHost = hostPort.substring(1, close);
      final after = hostPort.substring(close + 1);

      if (after.isNotEmpty) {
        if (!after.startsWith(':')) {
          throw const FormatException('Invalid URL authority');
        }
        rawPort = after.substring(1);
      }
    } else {
      final colon = hostPort.indexOf(':');

      if (colon < 0) {
        rawHost = hostPort;
      } else {
        rawHost = hostPort.substring(0, colon);
        rawPort = hostPort.substring(colon + 1);

        // Unbracketed IPv6 is not accepted as a valid authority.
        if (rawHost.contains(':')) {
          throw const FormatException('Invalid IPv6 URL');
        }
      }
    }

    if (rawHost.isEmpty) {
      throw const FormatException('URL has no hostname');
    }

    int? port;
    if (rawPort != null && rawPort.isNotEmpty) {
      if (!RegExp(r'^[0-9]+$').hasMatch(rawPort)) {
        throw const FormatException('Invalid URL port');
      }

      port = int.tryParse(rawPort);
      if (port == null || port < 0 || port > 65535) {
        throw const FormatException('URL port out of range');
      }
    }

    // Canonicalize IP or IDNA hostname.
    final ip = parseIp(rawHost);
    String host;

    if (ip != null) {
      host = ip;
    } else {
      // IDNA UTS46 allows a trailing root dot.
      final trailingDot = rawHost.endsWith('.');
      final hostWithoutDot =
          trailingDot ? rawHost.substring(0, rawHost.length - 1) : rawHost;

      final ascii = hostToAscii(hostWithoutDot);
      if (ascii == null) {
        throw const FormatException('Invalid IDNA hostname');
      }

      host = ascii.toLowerCase();
      if (trailingDot) host += '.';
    }

    if (host.contains(':')) {
      host = '[$host]';
    }

    // Python canonical_url() removes only HTTP/HTTPS default ports.
    final isDefaultPort =
        (scheme == 'http' && port == 80) ||
        (scheme == 'https' && port == 443);

    final portSuffix = port != null && !isDefaultPort
        ? ':$port'
        : '';

    return '$host$portSuffix$path'
        '${queryIndex >= 0 ? '?$query' : ''}';
  }

  /// Python student_text(): canonical URL followed by whitespace collapse.
  String studentText(String input) {
    final canonical = canonicalize(input);
    return canonical.replaceAll(RegExp(r'\s\s+'), ' ');
  }
}
