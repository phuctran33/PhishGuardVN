/// Port của brand_features.py (8 brand features, schema e2-brand-v1).
import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:unorm_dart/unorm_dart.dart' as unorm;

import 'idna.dart';
import 'py_compat.dart';
import 'url_parser.dart';

const List<String> brandFeatureOrder = [
  'brand_in_domain', 'brand_in_subdomain', 'brand_in_path', 'brand_domain_mismatch',
  'brand_typo_score', 'susp_token_cnt', 'idna_flag', 'homoglyph_brand_hit',
];

// --- Tham số công thức (đổi = đổi FEATURE_SCHEMA_VERSION bên Python) ---
const int minAliasLen = 3;
const int substringMinLen = 5;
const int typoMinLen = 5;
const int typoMaxDist = 2;
const double typoMaxRatio = 0.25;

const Set<String> stoplist = {
  'bank', 'ngan', 'hang', 'viet', 'vietnam', 'online', 'mobile', 'pay', 'shop', 'store',
  'app', 'web', 'www', 'com', 'net', 'org', 'gov', 'vnn', 'the', 'and', 'bao', 'tin',
};

const List<String> suspiciousTokens = [
  'login', 'signin', 'verify', 'secure', 'security', 'account', 'update', 'confirm',
  'wallet', 'otp', 'bonus', 'gift', 'promo', 'refund', 'support', 'helpdesk',
  'ebanking', 'internetbanking', 'payment', 'billing',
  'dangnhap', 'xacminh', 'xacthuc', 'taikhoan', 'baomat', 'capnhat', 'khuyenmai',
  'uudai', 'trungthuong', 'nhanqua', 'hoantien', 'thanhtoan', 'hotro',
];

const Map<String, String> _confusable = {
  '0': 'o', '1': 'l', 'i': 'l', '3': 'e', '4': 'a', '5': 's', '7': 't', '8': 'b',
};

final RegExp _tokenRe = RegExp(r'[a-z0-9]+');
final RegExp _combining = RegExp(r'\p{M}', unicode: true);

/// casefold + NFKD + bỏ dấu tổ hợp + đ -> d. Casefold xấp xỉ bằng toLowerCase + ß->ss
/// (sau bước này mọi ký tự không phải [a-z0-9] đều bị bỏ khi tách token).
String foldText(String text) {
  var t = text.toLowerCase().replaceAll('ß', 'ss');
  t = unorm.nfkd(t).replaceAll('đ', 'd');
  return t.replaceAll(_combining, '');
}

String confusableFold(String text) {
  final t = text.replaceAll('rn', 'm').replaceAll('vv', 'w');
  final sb = StringBuffer();
  for (final ch in t.split('')) {
    sb.write(_confusable[ch] ?? ch);
  }
  return sb.toString();
}

List<String> tokensOf(String text) =>
    _tokenRe.allMatches(foldText(text)).map((m) => m[0]!).toList();

class _Zone {
  final List<String> tokens;
  final String joined;
  final List<String> cfTokens;
  final String cfJoined;
  _Zone(this.tokens, this.joined, this.cfTokens, this.cfJoined);
}

_Zone _makeZone(String text) {
  final toks = tokensOf(text);
  final cf = toks.map(confusableFold).toList();
  return _Zone(toks, toks.join(), cf, cf.join());
}

bool _keyHit(String key, List<String> tokens, String joined) =>
    key.length >= substringMinLen ? joined.contains(key) : tokens.contains(key);

String? _firstHit(List<String> keys, List<String> tokens, String joined) {
  for (final k in keys) {
    if (_keyHit(k, tokens, joined)) return k;
  }
  return null;
}

/// Optimal string alignment (Levenshtein + hoán vị hai ký tự liền kề). Đầu vào là token ASCII.
int osaDistance(String a, String b) {
  final la = a.length, lb = b.length;
  List<int>? prev2;
  var prev = List<int>.generate(lb + 1, (j) => j);
  for (var i = 1; i <= la; i++) {
    final cur = List<int>.filled(lb + 1, 0);
    cur[0] = i;
    for (var j = 1; j <= lb; j++) {
      final cost = a.codeUnitAt(i - 1) == b.codeUnitAt(j - 1) ? 0 : 1;
      var v = prev[j] + 1;
      if (cur[j - 1] + 1 < v) v = cur[j - 1] + 1;
      if (prev[j - 1] + cost < v) v = prev[j - 1] + cost;
      if (i > 1 &&
          j > 1 &&
          a.codeUnitAt(i - 1) == b.codeUnitAt(j - 2) &&
          a.codeUnitAt(i - 2) == b.codeUnitAt(j - 1)) {
        if (prev2![j - 2] + 1 < v) v = prev2![j - 2] + 1;
      }
      cur[j] = v;
    }
    prev2 = prev;
    prev = cur;
  }
  return prev[lb];
}

class Brand {
  final String brandId;
  final String canonicalName;
  final Set<String> officialDomains;
  final List<String> keys;
  final List<String> cfKeys;
  final List<String> officialSuffixes;
  final Set<String> typoIgnore;
  Brand(this.brandId, this.canonicalName, this.officialDomains, this.keys, this.cfKeys,
      this.officialSuffixes, this.typoIgnore);
}

List<String> _splitPipe(String? v) =>
    (v ?? '').split('|').map((e) => e.trim()).where((e) => e.isNotEmpty).toList();

/// CSV RFC 4180 tối giản: dấu nháy kép, "" thoát, xuống dòng trong ô.
List<Map<String, String>> parseCsv(String text) {
  final rows = <List<String>>[];
  var row = <String>[];
  final field = StringBuffer();
  var inQuotes = false;
  for (var i = 0; i < text.length; i++) {
    final c = text[i];
    if (inQuotes) {
      if (c == '"') {
        if (i + 1 < text.length && text[i + 1] == '"') {
          field.write('"');
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        field.write(c);
      }
    } else if (c == '"') {
      inQuotes = true;
    } else if (c == ',') {
      row.add(field.toString());
      field.clear();
    } else if (c == '\n' || c == '\r') {
      if (c == '\r' && i + 1 < text.length && text[i + 1] == '\n') i++;
      row.add(field.toString());
      field.clear();
      rows.add(row);
      row = <String>[];
    } else {
      field.write(c);
    }
  }
  if (field.isNotEmpty || row.isNotEmpty) {
    row.add(field.toString());
    rows.add(row);
  }
  final nonEmpty = rows.where((r) => !(r.length == 1 && r[0].isEmpty)).toList();
  if (nonEmpty.isEmpty) return [];
  final header = nonEmpty.first;
  return [
    for (final r in nonEmpty.skip(1))
      {for (var i = 0; i < header.length; i++) header[i]: i < r.length ? r[i] : ''}
  ];
}

class BrandReference {
  final List<Brand> brands;
  final Set<String> allKeys;
  final Set<String> allOfficialDomains;
  final String sha256Hex;

  BrandReference._(this.brands, this.allKeys, this.allOfficialDomains, this.sha256Hex);

  /// Nạp từ byte của brand_reference_v1.csv; sha256 tính trên byte thô (khớp hash trong file parity).
  factory BrandReference.fromBytes(Uint8List bytes) {
    final sha = sha256.convert(bytes).toString();
    final rows = parseCsv(utf8.decode(bytes));
    final brands = <Brand>[];
    final seen = <String>{};
    final keyOwner = <String, String>{};
    for (final row in rows) {
      final bid = (row['brand_id'] ?? '').trim();
      if (bid.isEmpty || !seen.add(bid)) {
        throw FormatException('brand_id trống hoặc trùng: "$bid"');
      }
      final domains = _splitPipe(row['official_domains']).map((d) => d.toLowerCase()).toSet();
      if (domains.isEmpty) throw FormatException('$bid: thiếu official_domains');
      final keys = <String>[];
      for (final alias in [row['canonical_name'] ?? '', ..._splitPipe(row['aliases'])]) {
        final key = tokensOf(alias).join();
        if (key.length < minAliasLen) {
          throw FormatException('$bid: alias "$alias" ngắn hơn $minAliasLen ký tự');
        }
        if (stoplist.contains(key)) throw FormatException('$bid: alias "$alias" nằm trong STOPLIST');
        if (keyOwner.containsKey(key) && keyOwner[key] != bid) {
          throw FormatException('alias "$key" va chạm giữa ${keyOwner[key]} và $bid');
        }
        keyOwner[key] = bid;
        if (!keys.contains(key)) keys.add(key);
      }
      final suffixes = _splitPipe(row['official_suffixes']).map((x) => x.toLowerCase()).toList();
      if (suffixes.any((x) => !x.startsWith('.'))) {
        throw FormatException("$bid: official_suffixes phải bắt đầu bằng '.'");
      }
      final ignore = _splitPipe(row['typo_ignore_tokens']).map((x) => tokensOf(x).join()).toSet();
      brands.add(Brand(bid, (row['canonical_name'] ?? '').trim(), domains, keys,
          keys.map(confusableFold).toList(), suffixes, ignore));
    }
    return BrandReference._(
      brands,
      keyOwner.keys.toSet(),
      {for (final b in brands) ...b.officialDomains},
      sha,
    );
  }

  int get nBrands => brands.length;
  int get nWithOfficialSuffixes => brands.where((b) => b.officialSuffixes.isNotEmpty).length;
  int get nWithTypoIgnore => brands.where((b) => b.typoIgnore.isNotEmpty).length;
}

/// Lõi logic (tương ứng _scan). Thứ tự trả về = [brandFeatureOrder]. Gọi khi parsed.isValid.
List<double> scanBrandFeatures(ParsedUrl parsed, BrandReference ref) {
  final reg = parsed.registrableDomain; // null với URL là IP
  final sld = reg != null ? decodeHost(reg).split('.').first : '';
  final sub = parsed.subdomain.isNotEmpty ? decodeHost(parsed.subdomain) : '';
  final zoneDom = _makeZone(sld);
  final zoneSub = _makeZone(sub);
  final zonePath = _makeZone('${unquote(parsed.path)} ${unquote(parsed.query)}');

  var inDom = false, inSub = false, inPath = false, mismatch = false, homoglyph = false;
  var typo = 0.0;
  final onKnownOfficial = reg != null && ref.allOfficialDomains.contains(reg);
  final nearTokens = [
    for (final t in [...zoneDom.tokens, ...zoneSub.tokens])
      if (t.length >= typoMinLen && !ref.allKeys.contains(t)) t
  ];

  for (final brand in ref.brands) {
    final hitD = _firstHit(brand.keys, zoneDom.tokens, zoneDom.joined) != null;
    final hitS = _firstHit(brand.keys, zoneSub.tokens, zoneSub.joined) != null;
    final hitP = _firstHit(brand.keys, zonePath.tokens, zonePath.joined) != null;
    inDom = inDom || hitD;
    inSub = inSub || hitS;
    inPath = inPath || hitP;

    final suffixOk = reg != null &&
        brand.officialSuffixes.isNotEmpty &&
        brand.officialSuffixes.any(reg.endsWith) &&
        hitS &&
        !hitD &&
        !hitP;
    if ((hitD || hitS || hitP) &&
        !onKnownOfficial &&
        !(reg != null && brand.officialDomains.contains(reg)) &&
        !suffixOk) {
      mismatch = true;
    }
    if (onKnownOfficial) continue;
    if (!(hitD || hitS)) {
      final cf = _firstHit(brand.cfKeys, zoneDom.cfTokens, zoneDom.cfJoined) ??
          _firstHit(brand.cfKeys, zoneSub.cfTokens, zoneSub.cfJoined);
      if (cf != null) homoglyph = true;
    }
    for (final token in nearTokens) {
      if (brand.typoIgnore.contains(token)) continue;
      for (final key in brand.keys) {
        if (key.length < typoMinLen || (token.length - key.length).abs() > typoMaxDist) continue;
        final dist = osaDistance(token, key);
        if (dist >= 1 && dist <= typoMaxDist && dist / key.length <= typoMaxRatio) {
          final score = 1.0 - dist / key.length;
          if (score > typo) typo = score;
        }
      }
    }
  }

  var susp = 0;
  for (final kw in suspiciousTokens) {
    final zones = [zoneDom, zoneSub, zonePath];
    if (zones.any((z) => _keyHit(kw, z.tokens, z.joined))) susp++;
  }
  final idnaFlag = parsed.hostname.split('.').any((l) => l.startsWith('xn--'));

  return <double>[
    inDom ? 1.0 : 0.0,
    inSub ? 1.0 : 0.0,
    inPath ? 1.0 : 0.0,
    mismatch ? 1.0 : 0.0,
    typo,
    susp.toDouble(),
    idnaFlag ? 1.0 : 0.0,
    homoglyph ? 1.0 : 0.0,
  ];
}
