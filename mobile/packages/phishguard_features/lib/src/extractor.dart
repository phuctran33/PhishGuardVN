import 'brand.dart';
import 'features.dart';
import 'psl.dart';
import 'url_parser.dart';

/// Thứ tự cố định của 20 đặc trưng (docs/mobile_feature_contract.md mục 1).
const List<String> e2FeatureOrder = [...lexicalFeatureOrder, ...brandFeatureOrder];
const String featureSchemaVersion = 'e2-brand-v1';

class FeatureResult {
  final ParsedUrl parsed;

  /// 20 số theo [e2FeatureOrder]; null nếu URL không hợp lệ ("không phân loại được").
  final List<double>? vector;
  const FeatureResult(this.parsed, this.vector);

  bool get isClassifiable => vector != null;

  /// Chỉ có giá trị khi URL không hợp lệ (URL là IP hợp lệ vẫn có vector).
  String? get errorReason => parsed.isValid ? null : parsed.errorReason;

  Map<String, double>? toMap() {
    final v = vector;
    if (v == null) return null;
    return {for (var i = 0; i < e2FeatureOrder.length; i++) e2FeatureOrder[i]: v[i]};
  }
}

class E2Extractor {
  final UrlParser parser;
  final BrandReference reference;
  E2Extractor(PublicSuffixList psl, this.reference) : parser = UrlParser(psl);

  /// Không bao giờ ném lỗi với đầu vào bất kỳ; URL lỗi -> vector = null kèm errorReason.
  FeatureResult extract(String? url) {
    final parsed = parser.parse(url);
    if (!parsed.isValid) return FeatureResult(parsed, null);
    final lex = extractLexical(parsed)!;
    final brand = scanBrandFeatures(parsed, reference);
    return FeatureResult(parsed, [...lex, ...brand]);
  }
}
