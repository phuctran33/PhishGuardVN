import 'package:phishguard_features/phishguard_features.dart';

import 'teacher_contract.dart';
import 'url_classifier.dart';

/// Gọi TeacherV2OfflineModel.predict(url, extractor). Chạy hoàn toàn trong tiến trình, không dùng mạng.
class TeacherUrlClassifier extends GuardedClassifier {
  TeacherUrlClassifier({required E2Extractor extractor, required this.model})
      : super(extractor);

  final TeacherV2OfflineModel model;

  @override
  ClassificationOutcome infer(String url) {
    final prediction = model.predict(url, extractor);

    if (!prediction.classifiable) {
      return Unclassifiable(prediction.errorReason ?? 'unknown');
    }

    final score = prediction.finalScore;
    final classId = prediction.classId;
    final threshold = prediction.threshold;

    if (score == null || !score.isFinite) {
      throw StateError('Teacher returned an invalid finalScore');
    }

    if (classId != 0 && classId != 1) {
      throw StateError('Teacher returned an invalid classId');
    }

    if (threshold == null ||
        !threshold.isFinite ||
        threshold != teacherThreshold) {
      throw StateError('Teacher threshold does not match the frozen contract');
    }

    final expectedClassId = score >= teacherThreshold ? 1 : 0;
    if (classId != expectedClassId) {
      throw StateError(
          'Teacher classId does not match the frozen decision rule');
    }

    return Classified(
      phishing: classId == 1,
      score: score,
      threshold: threshold,
      decisionRule: teacherDecisionRule,
      modelVersion: teacherModelVersion,
    );
  }
}
