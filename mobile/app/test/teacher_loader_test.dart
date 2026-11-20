import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:phishguard_android/src/extractor_loader.dart';
import 'package:phishguard_android/src/teacher_contract.dart';
import 'package:phishguard_android/src/teacher_loader.dart';

import 'support/map_bundle.dart';

/// Test chạy từ mobile/app; đọc artifact thật trực tiếp (không cần chạy sync_assets.sh).
const _artifactDir = '../../artifacts/teacher_v2_android';

Uint8List _readArtifact(String name) {
  final file = File('$_artifactDir/$name');
  if (!file.existsSync()) {
    fail('Thiếu ${file.path}. Chạy `flutter test` từ mobile/app trong repo đầy đủ.');
  }
  return file.readAsBytesSync();
}

late final Uint8List _svm;
late final Uint8List _model;
late final Map<String, dynamic> _manifest;

Map<String, dynamic> _copyManifest() => jsonDecode(jsonEncode(_manifest)) as Map<String, dynamic>;

Uint8List _bytesOf(String text) => Uint8List.fromList(utf8.encode(text));

Map<String, Uint8List> _files({Map<String, dynamic>? manifest, Uint8List? svm, Uint8List? model}) => {
      teacherManifestAsset: _bytesOf(jsonEncode(manifest ?? _manifest)),
      teacherSvmAsset: svm ?? _svm,
      teacherModelAsset: model ?? _model,
    };

/// Manifest khai báo đúng kích thước và SHA-256 của [bytes] cho mục [name].
Map<String, dynamic> _manifestDeclaring(String name, Uint8List bytes) {
  final manifest = _copyManifest();
  final files = manifest['files'] as Map<String, dynamic>;
  files[name] = {'size_bytes': bytes.length, 'sha256': sha256.convert(bytes).toString()};
  return manifest;
}

Future<LoadedTeacher> _load(Map<String, Uint8List> files, {String brandSha = expectedBrandSha256}) =>
    loadTeacherV2(extractorBrandSha256: brandSha, bundle: MapBundle(files));

Future<void> _expectKind(Future<Object?> future, TeacherLoadFailure kind) => expectLater(
      future,
      throwsA(isA<TeacherLoadException>().having((e) => e.kind, 'kind', kind)),
    );

void main() {
  setUpAll(() {
    _svm = _readArtifact('dart_svm_model.json');
    _model = _readArtifact('dart_teacher_v2_model.json');
    _manifest = jsonDecode(utf8.decode(_readArtifact('manifest.json'))) as Map<String, dynamic>;
  });

  test('nạp thành công từ bytes thật, chỉ với manifest + hai JSON (không cần vocabulary, npz)', () async {
    final files = _files();
    expect(files.keys, unorderedEquals([teacherManifestAsset, teacherSvmAsset, teacherModelAsset]));
    final loaded = await _load(files);
    expect(loaded.info.modelVersion, teacherModelVersion);
    expect(loaded.info.threshold, teacherThreshold);
    expect(loaded.info.decisionRule, teacherDecisionRule);
    expect(loaded.info.svmBytes, _svm.length);
    expect(loaded.info.modelBytes, _model.length);
    expect(loaded.info.timings.total, greaterThanOrEqualTo(Duration.zero));
  });

  group('thiếu asset', () {
    for (final missing in [teacherManifestAsset, teacherSvmAsset, teacherModelAsset]) {
      test('thiếu $missing -> missingAsset', () async {
        final files = _files()..remove(missing);
        await _expectKind(_load(files), TeacherLoadFailure.missingAsset);
      });
    }
  });

  group('manifest', () {
    test('không phải JSON -> invalidJson', () async {
      final files = _files()..[teacherManifestAsset] = _bytesOf('{không phải json');
      await _expectKind(_load(files), TeacherLoadFailure.invalidJson);
    });

    test('gốc không phải object -> schemaMismatch', () async {
      final files = _files()..[teacherManifestAsset] = _bytesOf('[]');
      await _expectKind(_load(files), TeacherLoadFailure.schemaMismatch);
    });

    test('thiếu mục files -> schemaMismatch', () async {
      final manifest = _copyManifest()..remove('files');
      await _expectKind(_load(_files(manifest: manifest)), TeacherLoadFailure.schemaMismatch);
    });

    test('mục file sai định dạng -> schemaMismatch', () async {
      final manifest = _copyManifest();
      (manifest['files'] as Map<String, dynamic>)[teacherSvmFileName] = 'sai';
      await _expectKind(_load(_files(manifest: manifest)), TeacherLoadFailure.schemaMismatch);
    });

    test('sha256 sai độ dài -> schemaMismatch', () async {
      final manifest = _copyManifest();
      (manifest['files'] as Map<String, dynamic>)[teacherModelFileName] = {
        'size_bytes': _model.length,
        'sha256': 'abc',
      };
      await _expectKind(_load(_files(manifest: manifest)), TeacherLoadFailure.schemaMismatch);
    });
  });

  group('hợp đồng đóng băng', () {
    final mutations = <String, void Function(Map<String, dynamic>)>{
      'model_version': (m) => m['model_version'] = 'teacher-stacking-v1',
      'threshold': (m) => m['threshold'] = 0.5,
      'decision_rule': (m) => m['decision_rule'] = 'score > threshold',
      'members_order': (m) => m['members_order'] = ['hist', 'svm'],
      'class_mapping': (m) => m['class_mapping'] = {'benign': 1, 'phishing': 0},
      'feature_order (hoán vị hai cột đầu)': (m) {
        final order = List<Object?>.from(m['feature_order'] as List);
        final first = order[0];
        order[0] = order[1];
        order[1] = first;
        m['feature_order'] = order;
      },
      'feature_count': (m) => m['feature_count'] = 19,
      'source_bundle_sha256': (m) => m['source_bundle_sha256'] = '0' * 64,
      'brand_reference_sha256': (m) => m['brand_reference_sha256'] = '0' * 64,
    };
    mutations.forEach((name, mutate) {
      test('$name sai -> contractMismatch', () async {
        final manifest = _copyManifest();
        mutate(manifest);
        await _expectKind(_load(_files(manifest: manifest)), TeacherLoadFailure.contractMismatch);
      });
    });

    test('brand reference của extractor khác manifest -> contractMismatch', () async {
      await _expectKind(_load(_files(), brandSha: '1' * 64), TeacherLoadFailure.contractMismatch);
    });
  });

  group('toàn vẹn trên bytes thô', () {
    test('lật một byte của dart_svm_model.json -> hashMismatch', () async {
      final bad = Uint8List.fromList(_svm);
      bad[0] = bad[0] ^ 0xFF;
      await _expectKind(_load(_files(svm: bad)), TeacherLoadFailure.hashMismatch);
    });

    test('thêm một ký tự xuống dòng vào dart_teacher_v2_model.json -> hashMismatch', () async {
      final bad = Uint8List.fromList([..._model, 0x0A]);
      await _expectKind(_load(_files(model: bad)), TeacherLoadFailure.hashMismatch);
    });

    test('manifest khai sai SHA-256 -> hashMismatch', () async {
      final manifest = _copyManifest();
      (manifest['files'] as Map<String, dynamic>)[teacherSvmFileName] = {
        'size_bytes': _svm.length,
        'sha256': 'f' * 64,
      };
      await _expectKind(_load(_files(manifest: manifest)), TeacherLoadFailure.hashMismatch);
    });

    test('manifest khai sai kích thước -> hashMismatch', () async {
      final manifest = _copyManifest();
      (manifest['files'] as Map<String, dynamic>)[teacherModelFileName] = {
        'size_bytes': _model.length + 1,
        'sha256': sha256.convert(_model).toString(),
      };
      await _expectKind(_load(_files(manifest: manifest)), TeacherLoadFailure.hashMismatch);
    });
  });

  group('nội dung JSON (hash đúng nhưng nội dung không dùng được)', () {
    test('không phải JSON -> invalidJson', () async {
      final bad = _bytesOf('{không phải json');
      final manifest = _manifestDeclaring(teacherSvmFileName, bad);
      await _expectKind(_load(_files(manifest: manifest, svm: bad)), TeacherLoadFailure.invalidJson);
    });

    test('gốc là mảng -> invalidJson', () async {
      final bad = _bytesOf('[]');
      final manifest = _manifestDeclaring(teacherModelFileName, bad);
      await _expectKind(_load(_files(manifest: manifest, model: bad)), TeacherLoadFailure.invalidJson);
    });

    test('dart_teacher_v2_model.json rỗng {} -> modelInit', () async {
      final bad = _bytesOf('{}');
      final manifest = _manifestDeclaring(teacherModelFileName, bad);
      await _expectKind(_load(_files(manifest: manifest, model: bad)), TeacherLoadFailure.modelInit);
    });

    test('dart_svm_model.json rỗng {} -> modelInit', () async {
      final bad = _bytesOf('{}');
      final manifest = _manifestDeclaring(teacherSvmFileName, bad);
      await _expectKind(_load(_files(manifest: manifest, svm: bad)), TeacherLoadFailure.modelInit);
    });
  });
}
