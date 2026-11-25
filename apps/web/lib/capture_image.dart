import 'dart:typed_data';

import 'package:image/image.dart' as img;

import 'qr_image.dart';

typedef ImageRegion = ({double left, double top, double width, double height});

class CaptureImage {
  const CaptureImage(
    this.bytes,
    this.width,
    this.height,
    this.qr,
    this.qrRegion,
  );

  final Uint8List bytes;
  final int width;
  final int height;
  final String? qr;
  final ImageRegion? qrRegion;
}

/// Normalizes EXIF orientation once so the raster, OCR and overlay agree.
CaptureImage readCaptureImage(Uint8List bytes) {
  final original = decodeQrRaster(bytes);
  final orientation = original.exif.imageIfd.orientation;
  var raster = original;
  var displayBytes = bytes;
  if (orientation != null && orientation != 1) {
    raster = img.bakeOrientation(original);
    displayBytes = img.encodeJpg(raster, quality: 96);
  }
  final qr = detectQr(raster);
  ImageRegion? region;
  if (qr != null && qr.resultPoints.length >= 3) {
    final points = qr.resultPoints;
    final xs = points.map((point) => point.x).toList()..sort();
    final ys = points.map((point) => point.y).toList()..sort();
    final padding = ((xs.last - xs.first) + (ys.last - ys.first)) * .08;
    region = (
      left: xs.first - padding,
      top: ys.first - padding,
      width: xs.last - xs.first + 2 * padding,
      height: ys.last - ys.first + 2 * padding,
    );
  }
  return CaptureImage(
    displayBytes,
    raster.width,
    raster.height,
    qr?.text.trim(),
    region,
  );
}
