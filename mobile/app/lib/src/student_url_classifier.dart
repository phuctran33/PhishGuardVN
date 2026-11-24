import 'student_contract.dart';
import 'student_loader.dart';
import 'input_validation.dart';
import 'url_classifier.dart';

/// Student MLP inference độc lập với E2 và Teacher.
class StudentUrlClassifier implements UrlClassifier {
  StudentUrlClassifier({
    required this.student,
  });

  final LoadedStudent student;

  @override
  ClassificationOutcome classify(String url) {
    final issue = validateUrlInput(url);
    if (issue != null) return InvalidInput(issue);

    try {
      final text = student.canonicalizer.studentText(url);
      final prediction = student.model.predictCanonicalText(text);

      final score = prediction['score'] as double;
      final threshold = prediction['threshold'] as double;
      final classId = prediction['class_id'] as int;

      if (!score.isFinite ||
          threshold != studentThreshold ||
          (classId != 0 && classId != 1) ||
          classId != (score >= threshold ? 1 : 0)) {
        throw StateError('Student prediction violates frozen contract');
      }

      return Classified(
        phishing: classId == 1,
        score: score,
        threshold: threshold,
        decisionRule: studentDecisionRule,
        modelVersion: studentModelVersion,
      );
    } on FormatException {
      return const Unclassifiable('invalid_url');
    } on Object catch (error) {
      return InferenceFailure(error.runtimeType.toString());
    }
  }
}
