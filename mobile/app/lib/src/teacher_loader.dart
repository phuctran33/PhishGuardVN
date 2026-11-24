import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart';
import 'package:phishguard_features/phishguard_features.dart';

import 'teacher_contract.dart';

/// Loại lỗi khi nạp Teacher v2. Không có đường rơi về E2-only: lỗi nào cũng chặn suy luận.
enum TeacherLoadFailure {
  missingAsset,
  invalidJson,
  schemaMismatch,
  hashMismatch,
  contractMismatch,
  modelInit,
}

String describeLoadFailure(TeacherLoadFailure kind) {
  switch (kind) {
    case TeacherLoadFailure.missingAsset:
      return 'Thiếu file mô hình trong ứng dụng.';
    case TeacherLoadFailure.invalidJson:
      return 'File mô hình không phải JSON hợp lệ.';
    case TeacherLoadFailure.schemaMismatch:
      return 'Manifest của mô hình sai cấu trúc.';
    case TeacherLoadFailure.hashMismatch:
      return 'File mô hình bị hỏng hoặc khác phiên bản (kích thước hoặc SHA-256 lệch manifest).';
    case TeacherLoadFailure.contractMismatch:
      return 'Mô hình không khớp hợp đồng Teacher v2 đã đóng băng.';
    case TeacherLoadFailure.modelInit:
      return 'Không khởi tạo được mô hình từ JSON.';
  }
}

class TeacherLoadException implements Exception {
  const TeacherLoadException(this.kind, this.message, {this.cause});

  final TeacherLoadFailure kind;
  final String message;
  final Object? cause;

  @override
  String toString() => 'TeacherLoadException(${kind.name}): $message';
}

/// Thời gian từng giai đoạn nạp (dữ liệu cho H7.4; đo thật trên thiết bị mới có giá trị).
class TeacherLoadTimings {
  const TeacherLoadTimings({
    required this.read,
    required this.hash,
    required this.parse,
    required this.build,
  });

  final Duration read;
  final Duration hash;
  final Duration parse;
  final Duration build;

  Duration get total => read + hash + parse + build;
}

class TeacherRuntimeInfo {
  const TeacherRuntimeInfo({
    required this.modelVersion,
    required this.threshold,
    required this.decisionRule,
    required this.sourceBundleSha256,
    required this.svmBytes,
    required this.modelBytes,
    required this.timings,
  });

  final String modelVersion;
  final double threshold;
  final String decisionRule;
  final String sourceBundleSha256;
  final int svmBytes;
  final int modelBytes;
  final TeacherLoadTimings timings;
}

class LoadedTeacher {
  const LoadedTeacher({required this.model, required this.info});

  final TeacherV2OfflineModel model;
  final TeacherRuntimeInfo info;
}

Future<Uint8List> _readBytes(AssetBundle bundle, String path) async {
  try {
    final data = await bundle.load(path);
    return data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes);
  } on Object catch (error) {
    throw TeacherLoadException(
      TeacherLoadFailure.missingAsset,
      'Không đọc được asset $path',
      cause: error,
    );
  }
}

Object? _decodeJson(Uint8List bytes, String name) {
  try {
    return jsonDecode(utf8.decode(bytes));
  } on FormatException catch (error) {
    throw TeacherLoadException(
      TeacherLoadFailure.invalidJson,
      '$name không phải JSON hợp lệ',
      cause: error,
    );
  }
}

Map<String, dynamic> _asObject(Object? value, String name, TeacherLoadFailure kind) {
  if (value is Map<String, dynamic>) return value;
  throw TeacherLoadException(kind, '$name phải là JSON object');
}

bool _sameList(Object? actual, Iterable<Object?> expected) {
  if (actual is! List) return false;
  final want = expected.toList();
  if (actual.length != want.length) return false;
  for (var i = 0; i < want.length; i++) {
    if (actual[i] != want[i]) return false;
  }
  return true;
}

({int size, String sha}) _fileEntry(Map<String, dynamic> files, String name) {
  final entry = files[name];
  if (entry is Map<String, dynamic>) {
    final size = entry['size_bytes'];
    final sha = entry['sha256'];
    if (size is int && sha is String && sha.length == 64) {
      return (size: size, sha: sha);
    }
  }
  throw TeacherLoadException(
    TeacherLoadFailure.schemaMismatch,
    'manifest.files thiếu hoặc sai định dạng mục $name',
  );
}

Never _mismatch(String field, Object? got) => throw TeacherLoadException(
      TeacherLoadFailure.contractMismatch,
      'manifest.$field = $got không khớp hợp đồng đóng băng',
    );

void _checkContract(Map<String, dynamic> m, String extractorBrandSha256) {
  if (m['model_version'] != teacherModelVersion) {
    _mismatch('model_version', m['model_version']);
  }
  final threshold = m['threshold'];
  if (threshold is! num || threshold.toDouble() != teacherThreshold) {
    _mismatch('threshold', threshold);
  }
  if (m['decision_rule'] != teacherDecisionRule) {
    _mismatch('decision_rule', m['decision_rule']);
  }
  if (!_sameList(m['members_order'], teacherMembersOrder)) {
    _mismatch('members_order', m['members_order']);
  }
  final classes = m['class_mapping'];
  if (classes is! Map ||
      classes.length != 2 ||
      classes['benign'] != 0 ||
      classes['phishing'] != 1) {
    _mismatch('class_mapping', classes);
  }
  final order = m['feature_order'];
  if (!_sameList(order, teacherV2FeatureOrder) ||
      !_sameList(order, e2FeatureOrder) ||
      m['feature_count'] != e2FeatureOrder.length) {
    _mismatch('feature_order', order);
  }
  if (m['source_bundle_sha256'] != teacherSourceBundleSha256) {
    _mismatch('source_bundle_sha256', m['source_bundle_sha256']);
  }
  final referenceSha = m['brand_reference_sha256'];
  if (referenceSha != teacherBrandReferenceSha256 || referenceSha != extractorBrandSha256) {
    _mismatch('brand_reference_sha256', referenceSha);
  }
}

void _verifyBytes(Uint8List bytes, ({int size, String sha}) entry, String name) {
  if (bytes.length != entry.size) {
    throw TeacherLoadException(
      TeacherLoadFailure.hashMismatch,
      '$name: kích thước ${bytes.length} khác manifest ${entry.size}',
    );
  }
  final digest = sha256.convert(bytes).toString();
  if (digest != entry.sha) {
    throw TeacherLoadException(
      TeacherLoadFailure.hashMismatch,
      '$name: SHA-256 $digest khác manifest ${entry.sha}',
    );
  }
}

/// Nạp Teacher v2 từ assets đã đóng gói. Thứ tự: manifest -> hợp đồng -> bytes thô -> kích thước/SHA-256
/// trên bytes gốc -> giải mã JSON -> TeacherV2OfflineModel.fromJson.
/// [extractorBrandSha256] là sha256 của brand reference mà extractor E2 đã nạp; phải bằng giá trị trong manifest.
Future<LoadedTeacher> loadTeacherV2({
  required String extractorBrandSha256,
  AssetBundle? bundle,
}) async {
  final assets = bundle ?? rootBundle;
  final read = Stopwatch();
  final hash = Stopwatch();
  final parse = Stopwatch();
  final build = Stopwatch();

  read.start();
  final manifestBytes = await _readBytes(assets, teacherManifestAsset);
  read.stop();

  parse.start();
  final manifest = _asObject(
    _decodeJson(manifestBytes, 'manifest'),
    'manifest',
    TeacherLoadFailure.schemaMismatch,
  );
  parse.stop();

  _checkContract(manifest, extractorBrandSha256);
  final files = _asObject(manifest['files'], 'manifest.files', TeacherLoadFailure.schemaMismatch);
  final svmEntry = _fileEntry(files, teacherSvmFileName);
  final modelEntry = _fileEntry(files, teacherModelFileName);

  read.start();
  final svmBytes = await _readBytes(assets, teacherSvmAsset);
  final modelBytes = await _readBytes(assets, teacherModelAsset);
  read.stop();

  hash.start();
  _verifyBytes(svmBytes, svmEntry, teacherSvmFileName);
  _verifyBytes(modelBytes, modelEntry, teacherModelFileName);
  hash.stop();

  parse.start();
  final svmJson = _asObject(
    _decodeJson(svmBytes, teacherSvmFileName),
    teacherSvmFileName,
    TeacherLoadFailure.invalidJson,
  );
  final teacherJson = _asObject(
    _decodeJson(modelBytes, teacherModelFileName),
    teacherModelFileName,
    TeacherLoadFailure.invalidJson,
  );
  parse.stop();

  build.start();
  final TeacherV2OfflineModel model;
  try {
    model = TeacherV2OfflineModel.fromJson(svmJson: svmJson, teacherJson: teacherJson);
  } on Object catch (error) {
    throw TeacherLoadException(
      TeacherLoadFailure.modelInit,
      'Không khởi tạo được mô hình (${error.runtimeType})',
      cause: error,
    );
  }
  build.stop();

  return LoadedTeacher(
    model: model,
    info: TeacherRuntimeInfo(
      modelVersion: teacherModelVersion,
      threshold: teacherThreshold,
      decisionRule: teacherDecisionRule,
      sourceBundleSha256: teacherSourceBundleSha256,
      svmBytes: svmBytes.length,
      modelBytes: modelBytes.length,
      timings: TeacherLoadTimings(
        read: read.elapsed,
        hash: hash.elapsed,
        parse: parse.elapsed,
        build: build.elapsed,
      ),
    ),
  );
}
