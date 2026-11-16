import 'package:flutter/services.dart';
import 'package:phishguard_features/phishguard_features.dart';

const pslAsset = 'assets/psl_icann_tldextract_5.4.0.txt';
const brandAsset = 'assets/brand_reference_v1.csv';

/// sha256 của brand_reference_v1.csv ghi trong docs/mobile_parity_cases.json (E2 v1, 45 brand).
const expectedBrandSha256 = '6d434533e479f0f2e1d2602af72f54a1d15677961540684834536ae5d94fbee6';

class LoadedExtractor {
  final E2Extractor extractor;
  final int pslRules;
  final int nBrands;
  final String brandSha256;
  const LoadedExtractor(this.extractor, this.pslRules, this.nBrands, this.brandSha256);
}

/// Nạp extractor từ assets. Ném lỗi nếu brand reference không đúng bản E2 v1 đã freeze.
Future<LoadedExtractor> loadE2Extractor([AssetBundle? bundle]) async {
  final b = bundle ?? rootBundle;
  final psl = PublicSuffixList.fromText(await b.loadString(pslAsset));
  final data = await b.load(brandAsset);
  final bytes = data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes);
  final ref = BrandReference.fromBytes(bytes);
  if (ref.sha256Hex != expectedBrandSha256) {
    throw StateError('brand_reference_v1.csv không khớp bản đã freeze.\n'
        'cần  : $expectedBrandSha256\nthực tế: ${ref.sha256Hex}\n'
        'Chạy lại mobile/tool/sync_assets.sh từ checkout đúng phiên bản.');
  }
  return LoadedExtractor(E2Extractor(psl, ref), psl.size, ref.nBrands, ref.sha256Hex);
}
