import 'dart:io';
import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart';
import 'package:phishguard_features/phishguard_features.dart'
    show PublicSuffixList, UrlParser;

import 'student_contract.dart';
import 'student_mlp_v1.dart';
import 'student_url_canonicalizer.dart';

enum StudentLoadFailure {
  missingAsset,
  invalidJson,
  schemaMismatch,
  hashMismatch,
  contractMismatch,
  modelInit,
}

class StudentLoadException implements Exception {
  const StudentLoadException(this.kind, this.message, {this.cause});

  final StudentLoadFailure kind;
  final String message;
  final Object? cause;

  @override
  String toString() => 'StudentLoadException(${kind.name}): $message';
}

class StudentRuntimeInfo {
  const StudentRuntimeInfo({
    required this.modelVersion,
    required this.threshold,
    required this.decisionRule,
    required this.modelBytes,
    required this.pslBytes,
    required this.modelSha256,
    required this.pslSha256,
    required this.timings,
  });

  final String modelVersion;
  final double threshold;
  final String decisionRule;
  final int modelBytes;
  final int pslBytes;
  final String modelSha256;
  final String pslSha256;
  final StudentLoadTimings timings;
}

class StudentLoadTimings {
  const StudentLoadTimings({
    required this.read,
    required this.hash,
    required this.decompress,
    required this.parse,
    required this.build,
  });

  final Duration read;
  final Duration hash;
  final Duration decompress;
  final Duration parse;
  final Duration build;

  Duration get total => read + hash + decompress + parse + build;
}

class LoadedStudent {
  const LoadedStudent({
    required this.model,
    required this.canonicalizer,
    required this.info,
  });

  final StudentMlpV1 model;
  final StudentUrlCanonicalizer canonicalizer;
  final StudentRuntimeInfo info;
}

Future<Uint8List> _readBytes(AssetBundle bundle, String path) async {
  try {
    final data = await bundle.load(path);
    return data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes);
  } on Object catch (error) {
    throw StudentLoadException(
      StudentLoadFailure.missingAsset,
      'Không đọc được asset $path',
      cause: error,
    );
  }
}

Never _contractError(String field, Object? actual) =>
    throw StudentLoadException(
      StudentLoadFailure.contractMismatch,
      'manifest.$field không khớp contract Student: $actual',
    );

Map<String, dynamic> _decodeObject(Uint8List bytes, String name) {
  try {
    final decoded = jsonDecode(utf8.decode(bytes));
    if (decoded is Map<String, dynamic>) return decoded;
    throw StudentLoadException(
      StudentLoadFailure.schemaMismatch,
      '$name phải là JSON object',
    );
  } on StudentLoadException {
    rethrow;
  } on Object catch (error) {
    throw StudentLoadException(
      StudentLoadFailure.invalidJson,
      '$name không phải JSON/UTF-8 hợp lệ',
      cause: error,
    );
  }
}

void _checkManifest(Map<String, dynamic> m) {
  if (m['schema'] != studentModelSchema) {
    _contractError('schema', m['schema']);
  }
  if (m['model_version'] != studentModelVersion) {
    _contractError('model_version', m['model_version']);
  }
  if (m['decision_rule'] != studentDecisionRule) {
    _contractError('decision_rule', m['decision_rule']);
  }
  if (m['score_kind'] != studentScoreKind) {
    _contractError('score_kind', m['score_kind']);
  }

  final threshold = m['threshold'];
  if (threshold is! num || threshold.toDouble() != studentThreshold) {
    _contractError('threshold', threshold);
  }

  final classes = m['classes'];
  if (classes is! Map ||
      classes.length != 2 ||
      classes['benign'] != 0 ||
      classes['phishing'] != 1) {
    _contractError('classes', classes);
  }

  final model = m['model'];
  if (model is! Map ||
      model['bytes'] != studentModelBytes ||
      model['sha256'] != studentModelSha256) {
    _contractError('model', model);
  }

  final psl = m['psl'];
  if (psl is! Map ||
      psl['bytes'] != studentPslBytes ||
      psl['sha256'] != studentPslSha256) {
    _contractError('psl', psl);
  }

  final teacher = m['teacher'];
  if (teacher is! Map ||
      teacher['model_version'] != studentTeacherModelVersion ||
      teacher['bundle_sha256'] != studentTeacherBundleSha256 ||
      teacher['lock_sha256'] != studentTeacherLockSha256) {
    _contractError('teacher', teacher);
  }

  if (m['research_revision'] != studentResearchRevision) {
    _contractError('research_revision', m['research_revision']);
  }
  if (m['research_fingerprint'] != studentResearchFingerprint) {
    _contractError('research_fingerprint', m['research_fingerprint']);
  }
}

void _verifyBytes(
  Uint8List bytes, {
  required int expectedSize,
  required String expectedSha,
  required String name,
}) {
  if (bytes.length != expectedSize) {
    throw StudentLoadException(
      StudentLoadFailure.hashMismatch,
      '$name có ${bytes.length} bytes; manifest yêu cầu $expectedSize',
    );
  }

  final actualSha = sha256.convert(bytes).toString();
  if (actualSha != expectedSha) {
    throw StudentLoadException(
      StudentLoadFailure.hashMismatch,
      '$name SHA-256 không khớp manifest',
    );
  }
}

/// Loads Student from verified raw gzip + PSL assets.
/// Hash verification always happens before decompression or parsing.
Future<LoadedStudent> loadStudentMlpV1({
  AssetBundle? bundle,
}) async {
  final assets = bundle ?? rootBundle;

  final read = Stopwatch()..start();
  final manifestBytes = await _readBytes(assets, studentManifestAsset);
  final modelBytes = await _readBytes(assets, studentModelAsset);
  final pslBytes = await _readBytes(assets, studentPslAsset);
  read.stop();

  final parse = Stopwatch()..start();
  final manifest = _decodeObject(manifestBytes, 'manifest');
  _checkManifest(manifest);
  parse.stop();

  final hash = Stopwatch()..start();
  _verifyBytes(
    modelBytes,
    expectedSize: studentModelBytes,
    expectedSha: studentModelSha256,
    name: 'student_mlp.json.gz',
  );
  _verifyBytes(
    pslBytes,
    expectedSize: studentPslBytes,
    expectedSha: studentPslSha256,
    name: 'PSL',
  );
  hash.stop();

  final decompress = Stopwatch()..start();
  final Uint8List modelJsonBytes;
  try {
    modelJsonBytes = Uint8List.fromList(gzip.decode(modelBytes));
  } on Object catch (error) {
    throw StudentLoadException(
      StudentLoadFailure.modelInit,
      'Không giải nén được Student gzip',
      cause: error,
    );
  }
  decompress.stop();

  parse.start();
  final modelJson = _decodeObject(modelJsonBytes, 'student_mlp.json');
  final pslText = utf8.decode(pslBytes);
  parse.stop();

  final build = Stopwatch()..start();
  final StudentMlpV1 model;
  final PublicSuffixList psl;
  try {
    model = StudentMlpV1.fromJson(modelJson);

    if (model.modelVersion != studentModelVersion ||
        model.threshold != studentThreshold) {
      throw const StudentLoadException(
        StudentLoadFailure.contractMismatch,
        'Student model metadata không khớp frozen contract',
      );
    }

    psl = PublicSuffixList.fromText(pslText);
  } on StudentLoadException {
    rethrow;
  } on Object catch (error) {
    throw StudentLoadException(
      StudentLoadFailure.modelInit,
      'Không khởi tạo được Student model hoặc PSL',
      cause: error,
    );
  }
  build.stop();

  return LoadedStudent(
    model: model,
    canonicalizer: StudentUrlCanonicalizer(UrlParser(psl)),
    info: StudentRuntimeInfo(
      modelVersion: studentModelVersion,
      threshold: studentThreshold,
      decisionRule: studentDecisionRule,
      modelBytes: modelBytes.length,
      pslBytes: pslBytes.length,
      modelSha256: studentModelSha256,
      pslSha256: studentPslSha256,
      timings: StudentLoadTimings(
        read: read.elapsed,
        hash: hash.elapsed,
        decompress: decompress.elapsed,
        parse: parse.elapsed,
        build: build.elapsed,
      ),
    ),
  );
}
