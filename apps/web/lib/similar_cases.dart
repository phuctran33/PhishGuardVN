/// Proposed #36 display contract. Offsets index Unicode code points in the
/// final redacted display string, with an inclusive start and exclusive end.
class SimilarCase {
  const SimilarCase._(
    this.id,
    this.displayUrl,
    this.source,
    this.similarity,
    this.highlights,
  );

  final String id, displayUrl, source;
  final double similarity;
  final List<({int start, int end})> highlights;

  static final _unsafeText = RegExp(
    r'[\u0000-\u001f\u007f\u202a-\u202e\u2066-\u2069]',
  );
  static final _displayPattern = RegExp(
    r'^hxxps?://([^\s/?#]+)(/[^?#]*)?(?:\?([^#]+))?$',
  );
  static final _defangedAuthority = RegExp(
    r'^[a-zA-Z0-9_-]+(?:\[\.\][a-zA-Z0-9_-]+)+(?::[0-9]{1,5})?$',
  );
  static final _ipv6Authority = RegExp(r'^\[[0-9A-Fa-f:]+\](?::[0-9]{1,5})?$');
  static final _redactedQueryParameter = RegExp(
    r'^[a-zA-Z0-9_%.\[\]-]+=\[redacted\]$',
  );

  static bool _safeUrl(String url) {
    final parts = _displayPattern.firstMatch(url);
    if (parts == null || _unsafeText.hasMatch(url) || url.contains(r'\')) {
      return false;
    }
    final authority = parts.group(1)!;
    if (!_defangedAuthority.hasMatch(authority) &&
        !_ipv6Authority.hasMatch(authority)) {
      return false;
    }
    final networkAuthority = authority.replaceAll('[.]', '.');
    final parsedAuthority = Uri.tryParse('http://$networkAuthority');
    if (parsedAuthority == null || parsedAuthority.port > 65535) return false;
    final query = parts.group(3);
    return query == null ||
        query.split('&').every(_redactedQueryParameter.hasMatch);
  }

  factory SimilarCase._fromJson(Map<String, dynamic> json) {
    final id = json['case_id'];
    final url = json['display_url'];
    final source = json['source'];
    final similarity = json['cosine_similarity'];
    final ranges = json['highlights'];
    if (id is! String ||
        id.trim().isEmpty ||
        _unsafeText.hasMatch(id) ||
        url is! String ||
        url.length > 8192 ||
        !_safeUrl(url) ||
        source is! String ||
        source.trim().isEmpty ||
        _unsafeText.hasMatch(source) ||
        similarity is! num ||
        !similarity.isFinite ||
        similarity < 0 ||
        similarity > 1 ||
        ranges is! List) {
      throw const FormatException('Invalid similar case');
    }

    final charCount = url.runes.length;
    final highlights = <({int start, int end})>[];
    var previousEnd = 0;
    for (final range in ranges) {
      if (range is! Map<String, dynamic>) {
        throw const FormatException('Invalid highlight range');
      }
      final start = range['start'];
      final end = range['end'];
      if (start is! int ||
          end is! int ||
          start < previousEnd ||
          end <= start ||
          end > charCount) {
        throw const FormatException('Invalid highlight offset');
      }
      highlights.add((start: start, end: end));
      previousEnd = end;
    }
    return SimilarCase._(
      id,
      url,
      source,
      similarity.toDouble(),
      List.unmodifiable(highlights),
    );
  }

  static List<SimilarCase> decode(Map<String, dynamic> json) {
    final raw = json['cases'];
    final status = json['status'];
    if (raw is! List ||
        raw.length > 5 ||
        (raw.isEmpty ? status != 'empty' : status != 'ok')) {
      throw const FormatException('Invalid similar cases response');
    }
    final ids = <String, String>{};
    final urls = <String>{};
    final cases = <SimilarCase>[];
    for (final row in raw) {
      if (row is! Map<String, dynamic>) {
        throw const FormatException('Invalid similar case object');
      }
      final item = SimilarCase._fromJson(row);
      final previousUrl = ids[item.id];
      if (previousUrl != null && previousUrl != item.displayUrl) {
        throw const FormatException('Conflicting case ID');
      }
      ids[item.id] = item.displayUrl;
      if (urls.add(item.displayUrl)) cases.add(item);
    }
    return List.unmodifiable(cases);
  }

  List<({String text, bool highlighted})> get segments {
    final chars = displayUrl.runes.toList();
    final result = <({String text, bool highlighted})>[];
    var cursor = 0;
    for (final range in highlights) {
      if (range.start != cursor) {
        result.add((
          text: String.fromCharCodes(chars, cursor, range.start),
          highlighted: false,
        ));
      }
      result.add((
        text: String.fromCharCodes(chars, range.start, range.end),
        highlighted: true,
      ));
      cursor = range.end;
    }
    if (cursor < chars.length) {
      result.add((
        text: String.fromCharCodes(chars, cursor),
        highlighted: false,
      ));
    }
    return result;
  }
}
