import 'package:phishguard_features/phishguard_features.dart';

import 'extractor_loader.dart';
import 'student_loader.dart';
import 'student_url_classifier.dart';
import 'teacher_loader.dart';
import 'teacher_url_classifier.dart';
import 'url_classifier.dart';

/// Mọi thứ app cần sau khi khởi tạo thành công. Chỉ tồn tại khi CẢ extractor E2 và Teacher đã nạp.
class AppRuntime {
  const AppRuntime({
    required this.extractorInfo,
    required this.teacherInfo,
    required this.classifier,
    this.studentInfo,
    this.studentClassifier,
    this.studentLoadError,
  });

  final LoadedExtractor extractorInfo;
  final TeacherRuntimeInfo teacherInfo;
  final UrlClassifier classifier;
  final StudentRuntimeInfo? studentInfo;
  final UrlClassifier? studentClassifier;
  final Object? studentLoadError;

  E2Extractor get extractor => extractorInfo.extractor;
}

/// Khởi tạo thất bại. [extractorInfo] khác null nếu riêng extractor E2 đã nạp được
/// (cho phép mở trang parity E2, không phải dự đoán).
class BootstrapFailure implements Exception {
  const BootstrapFailure(this.error, {this.extractorInfo});

  final Object error;
  final LoadedExtractor? extractorInfo;
}

Future<AppRuntime> bootstrapApp() async {
  LoadedExtractor? extractorInfo;
  try {
    extractorInfo = await loadE2Extractor();
    final teacher =
        await loadTeacherV2(extractorBrandSha256: extractorInfo.brandSha256);

    LoadedStudent? student;
    Object? studentLoadError;

    try {
      student = await loadStudentMlpV1();
    } on Object catch (error) {
      studentLoadError = error;
    }

    return AppRuntime(
      extractorInfo: extractorInfo,
      teacherInfo: teacher.info,
      classifier: TeacherUrlClassifier(
        extractor: extractorInfo.extractor,
        model: teacher.model,
      ),
      studentInfo: student?.info,
      studentClassifier:
          student == null ? null : StudentUrlClassifier(student: student),
      studentLoadError: studentLoadError,
    );
  } on Object catch (error) {
    throw BootstrapFailure(error, extractorInfo: extractorInfo);
  }
}

String describeBootError(Object error) {
  final cause = error is BootstrapFailure ? error.error : error;
  if (cause is TeacherLoadException) {
    final hint = cause.kind == TeacherLoadFailure.missingAsset
        ? '\nChạy `bash mobile/tool/sync_assets.sh` rồi build lại ứng dụng.'
        : '';
    return '${describeLoadFailure(cause.kind)}\n(${cause.kind.name}) ${cause.message}$hint';
  }
  return 'Lỗi khởi tạo: ${cause.runtimeType}';
}
