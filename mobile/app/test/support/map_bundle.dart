import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// AssetBundle giả cho test: trả đúng bytes đã cho, ném lỗi nếu asset không tồn tại.
class MapBundle extends CachingAssetBundle {
  MapBundle(this.files);

  final Map<String, Uint8List> files;

  @override
  Future<ByteData> load(String key) async {
    final bytes = files[key];
    if (bytes == null) {
      throw FlutterError('Unable to load asset: $key');
    }
    return ByteData.sublistView(bytes);
  }
}
