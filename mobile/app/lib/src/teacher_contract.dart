/// Hợp đồng Teacher v2 đã đóng băng (docs/teacher_v2_release.md, configs/teacher_lock.json).
/// Mọi giá trị phải khớp artifacts/teacher_v2_android/manifest.json; lệch thì không cho suy luận.
const String teacherModelVersion = 'teacher-stacking-v2';
const double teacherThreshold = 0.6945740700635259;
const String teacherDecisionRule = 'score >= threshold';
const List<String> teacherMembersOrder = ['svm', 'hist'];
const String teacherSourceBundleSha256 =
    '63199c925b28492765019de84c178bd3f8b935a0031f6c960b5db6c31a57c4f1';
const String teacherBrandReferenceSha256 =
    '6d434533e479f0f2e1d2602af72f54a1d15677961540684834536ae5d94fbee6';

/// Đường dẫn asset trong ứng dụng (do mobile/tool/sync_assets.sh chép vào mobile/app/assets/).
const String teacherManifestAsset = 'assets/teacher_v2_manifest.json';
const String teacherSvmAsset = 'assets/dart_svm_model.json';
const String teacherModelAsset = 'assets/dart_teacher_v2_model.json';

/// Tên khóa trong manifest.files.
const String teacherSvmFileName = 'dart_svm_model.json';
const String teacherModelFileName = 'dart_teacher_v2_model.json';
