import 'package:phishguard_features/phishguard_features.dart';

import 'input_validation.dart';

/// Kết quả phân loại một URL. Bốn trường hợp tách biệt để UI không nhầm lỗi với nhãn.
sealed class ClassificationOutcome {
  const ClassificationOutcome();
}

/// Teacher đã cho điểm. [phishing] = score >= threshold (quy tắc đóng băng).
final class Classified extends ClassificationOutcome {
  const Classified({
    required this.phishing,
    required this.score,
    required this.threshold,
    required this.decisionRule,
    required this.modelVersion,
  });

  final bool phishing;
  final double score;
  final double threshold;
  final String decisionRule;
  final String modelVersion;
}

/// URL qua kiểm đầu vào nhưng parser không phân loại được (invalid_port, unresolved_domain...).
final class Unclassifiable extends ClassificationOutcome {
  const Unclassifiable(this.reasonCode);

  final String reasonCode;
}

/// Đầu vào bị từ chối theo hợp đồng Teacher (rỗng, ký tự điều khiển, khoảng trắng hai đầu).
final class InvalidInput extends ClassificationOutcome {
  const InvalidInput(this.issue);

  final InputIssue issue;
}

/// Lỗi bất thường khi chạy mô hình. Không bao giờ được hiển thị như một nhãn.
final class InferenceFailure extends ClassificationOutcome {
  const InferenceFailure(this.errorType);

  final String errorType;
}

abstract interface class UrlClassifier {
  ClassificationOutcome classify(String url);
}

/// Khung chung: kiểm đầu vào -> extractor E2 phân loại được? -> suy luận.
/// Lớp thật (Teacher) và lớp giả trong test chỉ khác nhau ở [infer], nên cùng đi qua đúng đoạn bảo vệ này.
abstract class GuardedClassifier implements UrlClassifier {
  GuardedClassifier(this.extractor);

  final E2Extractor extractor;

  /// Chạy mô hình. Được phép ném lỗi; [classify] sẽ chuyển thành [InferenceFailure].
  ClassificationOutcome infer(String url);

  @override
  ClassificationOutcome classify(String url) {
    final issue = validateUrlInput(url);
    if (issue != null) return InvalidInput(issue);
    final features = extractor.extract(url);
    if (!features.isClassifiable) {
      return Unclassifiable(features.errorReason ?? 'unknown');
    }
    try {
      return infer(url);
    } on Object catch (error) {
      return InferenceFailure(error.runtimeType.toString());
    }
  }
}
