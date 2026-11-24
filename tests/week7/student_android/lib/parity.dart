import 'dart:math' as math;
import 'student_adapter.dart';

/// Dùng cùng phép đối chiếu cho host và APK; không lấy thời gian host làm Android.
Map<String, dynamic> verifyStudentParity(
    LoadedStudent loaded, Map<String, dynamic> reference) {
  final model = loaded.model;
  var classified = 0, rejected = 0, frozenClassified = 0, frozenRejected = 0;
  var maxTextDelta = 0.0, maxE2Delta = 0.0, maxScoreDelta = 0.0;
  var closestMargin = double.infinity;
  final results = <Map<String, dynamic>>[];
  void check(bool valid, String field, String name) {
    if (!valid) throw StateError('Student parity mismatch: $name / $field');
  }

  for (final item
      in (reference['cases'] as List).cast<Map<String, dynamic>>()) {
    final name = item['name'] as String;
    if (item['status'] == 'rejected') {
      try {
        model.predict(item['url'], loaded.extractor);
        throw StateError('Rejected input produced prediction: $name');
      } on StudentInputException catch (error) {
        rejected++;
        if (item['origin'] == 'frozen') frozenRejected++;
        results
            .add({'name': name, 'status': 'rejected', 'reason': error.reason});
      }
      continue;
    }
    final vector = model.vector(item['url'], loaded.extractor);
    check(vector.text == item['canonical_text'], 'canonical_text', name);
    final indices = vector.row.keys.where((i) => i < 8192).toList()..sort();
    final expectedIndices = (item['text_indices'] as List).cast<int>();
    check(indices.length == expectedIndices.length, 'TF-IDF length', name);
    for (var i = 0; i < indices.length; i++) {
      check(indices[i] == expectedIndices[i], 'TF-IDF index', name);
      final delta =
          (vector.row[indices[i]]! - (item['text_values'][i] as num).toDouble())
              .abs();
      maxTextDelta = math.max(maxTextDelta, delta);
      check(delta <= 1e-12, 'TF-IDF value', name);
    }
    for (var i = 0; i < 20; i++) {
      final delta = (vector.e2[i] - (item['e2'][i] as num).toDouble()).abs();
      maxE2Delta = math.max(maxE2Delta, delta);
      check(delta <= 1e-6, 'E2 $i', name);
      check(vector.row[8192 + i] == vector.e2[i], 'combined E2 offset', name);
    }
    final actual = model.predict(item['url'], loaded.extractor);
    final expected = item['expected'][model.mode] as Map;
    final delta =
        ((actual['score'] as double) - (expected['score'] as num).toDouble())
            .abs();
    maxScoreDelta = math.max(maxScoreDelta, delta);
    check(delta <= 1e-6, 'score', name);
    for (final key in [
      'label',
      'class_id',
      'threshold',
      'model_version',
      'score_kind',
      'calibrated',
      'release_status'
    ]) {
      check(actual[key] == expected[key], key, name);
    }
    check(
        actual['decision_rule'] == 'score >= threshold', 'decision_rule', name);
    closestMargin = math.min(
        closestMargin, ((actual['score'] as double) - model.threshold).abs());
    classified++;
    if (item['origin'] == 'frozen') frozenClassified++;
    results.add({
      'name': name,
      'status': 'classified',
      ...actual,
      'score_delta': delta
    });
  }
  check(frozenClassified == 52 && frozenRejected == 6, 'frozen fixture counts',
      'suite');
  return {
    'status': 'passed',
    'mode': model.mode,
    'model_version': model.version,
    'threshold': model.threshold,
    'decision_rule': 'score >= threshold',
    'classified': classified,
    'rejected': rejected,
    'frozen_classified': frozenClassified,
    'frozen_rejected': frozenRejected,
    'max_tfidf_delta': maxTextDelta,
    'max_e2_delta': maxE2Delta,
    'max_score_delta': maxScoreDelta,
    'score_atol': 1e-6,
    'nearest_observed_threshold_distance': closestMargin,
    'results': results
  };
}
