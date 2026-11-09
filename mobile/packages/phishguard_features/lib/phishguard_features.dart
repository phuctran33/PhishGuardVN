/// Extractor E2 v1 (schema `e2-brand-v1`) cho mobile. Nguồn chuẩn: code Python trong
/// src/phishguard_vn/{url_parser,features,brand_features}.py và docs/mobile_feature_contract.md.
library phishguard_features;

export 'src/brand.dart' show BrandReference, Brand, brandFeatureOrder;
export 'src/extractor.dart';
export 'src/features.dart' show lexicalFeatureOrder;
export 'src/parity.dart';
export 'src/psl.dart' show PublicSuffixList;
export 'src/url_parser.dart' show ParsedUrl, UrlParser;
