import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:phishguard_android/src/student_contract.dart';
import 'package:phishguard_android/src/student_loader.dart';

class _MapAssetBundle extends CachingAssetBundle {
  _MapAssetBundle(this.files);

  final Map<String, Uint8List> files;

  @override
  Future<ByteData> load(String key) async {
    final bytes = files[key];
    if (bytes == null) {
      throw StateError('Asset not found: $key');
    }
    return ByteData.sublistView(bytes);
  }
}

Uint8List _readFixture(String path) => File(path).readAsBytesSync();

Map<String, Uint8List> _validAssets() => {
      studentManifestAsset:
          _readFixture('test/fixtures/student_mlp_manifest.json'),
      studentModelAsset: _readFixture('test/fixtures/student_mlp.json.gz'),
      studentPslAsset: _readFixture(
        '../packages/phishguard_features/assets/'
        'psl_icann_tldextract_5.4.0.txt',
      ),
    };

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('loadStudentMlpV1', () {
    test('loads verified Student model and PSL', () async {
      final loaded = await loadStudentMlpV1(
        bundle: _MapAssetBundle(_validAssets()),
      );

      expect(loaded.info.modelVersion, studentModelVersion);
      expect(loaded.info.threshold, studentThreshold);
      expect(loaded.info.decisionRule, studentDecisionRule);
      expect(loaded.info.modelBytes, studentModelBytes);
      expect(loaded.info.pslBytes, studentPslBytes);
      expect(loaded.info.modelSha256, studentModelSha256);
      expect(loaded.info.pslSha256, studentPslSha256);
      expect(loaded.info.timings.total, greaterThanOrEqualTo(Duration.zero));

      final text = loaded.canonicalizer.studentText(
        'https://example.com/',
      );
      final prediction = loaded.model.predictCanonicalText(text);

      expect(prediction['model_version'], studentModelVersion);
      expect(prediction['threshold'], studentThreshold);
      expect(prediction['class_id'], anyOf(0, 1));
      expect(prediction['score'], isA<double>());
    });

    test('rejects missing manifest asset', () async {
      final assets = _validAssets()..remove(studentManifestAsset);

      await expectLater(
        loadStudentMlpV1(bundle: _MapAssetBundle(assets)),
        throwsA(
          isA<StudentLoadException>().having(
            (e) => e.kind,
            'kind',
            StudentLoadFailure.missingAsset,
          ),
        ),
      );
    });

    test('rejects invalid manifest JSON', () async {
      final assets = _validAssets()
        ..[studentManifestAsset] =
            Uint8List.fromList(utf8.encode('{invalid json'));

      await expectLater(
        loadStudentMlpV1(bundle: _MapAssetBundle(assets)),
        throwsA(
          isA<StudentLoadException>().having(
            (e) => e.kind,
            'kind',
            StudentLoadFailure.invalidJson,
          ),
        ),
      );
    });

    test('rejects manifest with mismatched threshold', () async {
      final assets = _validAssets();
      final manifest = jsonDecode(
        utf8.decode(assets[studentManifestAsset]!),
      ) as Map<String, dynamic>;

      manifest['threshold'] = 0.5;
      assets[studentManifestAsset] =
          Uint8List.fromList(utf8.encode(jsonEncode(manifest)));

      await expectLater(
        loadStudentMlpV1(bundle: _MapAssetBundle(assets)),
        throwsA(
          isA<StudentLoadException>().having(
            (e) => e.kind,
            'kind',
            StudentLoadFailure.contractMismatch,
          ),
        ),
      );
    });

    test('rejects corrupted model bytes before decompression', () async {
      final assets = _validAssets();
      final corrupted = Uint8List.fromList(
        assets[studentModelAsset]!,
      );

      corrupted[100] ^= 0x01;
      assets[studentModelAsset] = corrupted;

      await expectLater(
        loadStudentMlpV1(bundle: _MapAssetBundle(assets)),
        throwsA(
          isA<StudentLoadException>().having(
            (e) => e.kind,
            'kind',
            StudentLoadFailure.hashMismatch,
          ),
        ),
      );
    });

    test('rejects corrupted PSL bytes', () async {
      final assets = _validAssets();
      final corrupted = Uint8List.fromList(
        assets[studentPslAsset]!,
      );

      corrupted[100] ^= 0x01;
      assets[studentPslAsset] = corrupted;

      await expectLater(
        loadStudentMlpV1(bundle: _MapAssetBundle(assets)),
        throwsA(
          isA<StudentLoadException>().having(
            (e) => e.kind,
            'kind',
            StudentLoadFailure.hashMismatch,
          ),
        ),
      );
    });

    test('rejects missing model asset', () async {
      final assets = _validAssets()..remove(studentModelAsset);

      await expectLater(
        loadStudentMlpV1(bundle: _MapAssetBundle(assets)),
        throwsA(
          isA<StudentLoadException>().having(
            (e) => e.kind,
            'kind',
            StudentLoadFailure.missingAsset,
          ),
        ),
      );
    });

    test('rejects missing PSL asset', () async {
      final assets = _validAssets()..remove(studentPslAsset);

      await expectLater(
        loadStudentMlpV1(bundle: _MapAssetBundle(assets)),
        throwsA(
          isA<StudentLoadException>().having(
            (e) => e.kind,
            'kind',
            StudentLoadFailure.missingAsset,
          ),
        ),
      );
    });
  });
}
