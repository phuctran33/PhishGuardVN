import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

class ApiFailure implements Exception {
  const ApiFailure(this.code, this.message);
  final String code;
  final String message;
}

class Prediction {
  const Prediction({
    required this.label,
    required this.model,
    required this.score,
    required this.scoreKind,
    required this.scoreDefinition,
    required this.protocol,
  });
  final String label;
  final String model;
  final double score;
  final String scoreKind;
  final String scoreDefinition;
  final String protocol;

  factory Prediction.fromJson(Map<String, dynamic> json) {
    final label = json['label'];
    final kind = json['score_kind'];
    final value = json['score'];
    if (!{'benign', 'phishing'}.contains(label) ||
        !{'probability', 'decision_function'}.contains(kind) ||
        value is! num ||
        !value.isFinite ||
        (kind == 'probability' && (value < 0 || value > 1)) ||
        json['model'] is! String ||
        json['score_definition'] is! String ||
        json['protocol'] is! String ||
        json['decision_rule'] != 'estimator.predict') {
      throw const FormatException('Unexpected prediction schema');
    }
    return Prediction(
      label: label as String,
      model: json['model'] as String,
      score: value.toDouble(),
      scoreKind: kind as String,
      scoreDefinition: json['score_definition'] as String,
      protocol: json['protocol'] as String,
    );
  }
}

class PredictionApi {
  PredictionApi({
    required this.baseUrl,
    http.Client? client,
    this.timeout = const Duration(seconds: 10),
  }) : _client = client ?? http.Client();
  final String baseUrl;
  final Duration timeout;
  final http.Client _client;
  Uri _endpoint(String path) =>
      Uri.parse('${baseUrl.replaceAll(RegExp(r'/+$'), '')}$path');

  Future<bool> health() async {
    final response = await _request(() => _client.get(_endpoint('/health')));
    final body = _decode(response);
    if (response.statusCode != 200 || body['model_ready'] is! bool) {
      throw const ApiFailure(
        'INVALID_RESPONSE',
        'Phản hồi máy chủ chưa đúng API contract.',
      );
    }
    return body['model_ready'] as bool;
  }

  Future<Prediction> predict(String url) async {
    final response = await _request(
      () => _client.post(
        _endpoint('/predict'),
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: jsonEncode({'url': url}),
      ),
    );
    final body = _decode(response);
    if (response.statusCode != 200) {
      final error = body['error'];
      if (error is! Map ||
          error['code'] is! String ||
          error['message'] is! String) {
        throw const ApiFailure(
          'INVALID_RESPONSE',
          'Phản hồi máy chủ chưa đúng API contract.',
        );
      }
      final code = error['code'] as String;
      final message = switch (code) {
        'MODEL_UNAVAILABLE' =>
          'Máy chủ chưa sẵn sàng để phân tích. Vui lòng thử lại sau.',
        'INVALID_URL' =>
          'URL không hợp lệ. Hãy kiểm tra tên miền, ký tự và cổng kết nối.',
        'INVALID_REQUEST' => 'Vui lòng nhập URL từ 1 đến 4096 ký tự.',
        _ => 'Chưa thể phân tích đường dẫn lúc này. Vui lòng thử lại.',
      };
      throw ApiFailure(code, message);
    }
    try {
      return Prediction.fromJson(body);
    } on FormatException {
      throw const ApiFailure(
        'INVALID_RESPONSE',
        'Phản hồi máy chủ chưa đúng API contract.',
      );
    }
  }

  Map<String, dynamic> _decode(http.Response response) {
    try {
      final value = jsonDecode(utf8.decode(response.bodyBytes));
      if (value is Map<String, dynamic>) return value;
    } on FormatException {
      /* Never render upstream HTML or exception text. */
    }
    throw const ApiFailure(
      'INVALID_RESPONSE',
      'Phản hồi máy chủ chưa đúng API contract.',
    );
  }

  Future<http.Response> _request(Future<http.Response> Function() send) async {
    try {
      return await send().timeout(timeout);
    } on TimeoutException {
      throw const ApiFailure(
        'TIMEOUT',
        'Máy chủ phản hồi chậm. Vui lòng thử lại.',
      );
    } on http.ClientException {
      throw const ApiFailure(
        'NETWORK_ERROR',
        'Không kết nối được máy chủ. Kiểm tra kết nối rồi thử lại.',
      );
    }
  }

  void close() => _client.close();
}
