import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:phishguard_features/phishguard_features.dart';

import 'extractor_loader.dart';
import 'feature_info.dart';
import 'input_validation.dart';
import 'parity_page.dart';
import 'teacher_loader.dart';
import 'url_classifier.dart';
import 'student_loader.dart';

const sampleUrls = <String>[
  'https://www.vietcombank.com.vn/vi-VN/',
  'https://vietcombank.com.vn.xacminh-id.xyz/',
  'https://vietcombnak.com/',
  'https://vietc0mbank.top/',
  'http://bücher.de/Path',
  'http://[2001:db8::1]/login',
  'https://example.com:99999/',
];

class HomePage extends StatefulWidget {
  const HomePage({
    super.key,
    required this.extractor,
    required this.classifier,
    this.info,
    this.teacherInfo,
    this.studentInfo,
    this.studentClassifier,
    this.studentLoadError,
  });

  final E2Extractor extractor;
  final UrlClassifier classifier;
  final LoadedExtractor? info;
  final TeacherRuntimeInfo? teacherInfo;
  final UrlClassifier? studentClassifier;
  final StudentRuntimeInfo? studentInfo;
  final Object? studentLoadError;

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  final _controller = TextEditingController();
  ClassificationOutcome? _outcome;
  ClassificationOutcome? _studentOutcome;
  String? _studentError;
  FeatureResult? _features;
  String _submitted = '';

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _analyze() {
    FocusScope.of(context).unfocus();
    final text = _controller.text;
    final outcome = widget.classifier.classify(text);
    setState(() {
      _submitted = text;
      _outcome = outcome;
      _features =
          outcome is InvalidInput ? null : widget.extractor.extract(text);
    });
  }

  void _useSample(String url) {
    _controller.text = url;
    _analyze();
  }

  Future<void> _copyJson(FeatureResult r) async {
    final text = const JsonEncoder.withIndent('  ')
        .convert({'url': _submitted, 'features': r.toMap()});
    await Clipboard.setData(ClipboardData(text: text));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Đã sao chép JSON đặc trưng E2')));
  }

  void _analyzeStudent() {
    FocusScope.of(context).unfocus();

    final classifier = widget.studentClassifier;
    if (classifier == null) return;

    try {
      final outcome = classifier.classify(_controller.text);

      setState(() {
        _studentOutcome = outcome;
        _studentError = null;
      });
    } on FormatException {
      setState(() {
        _studentOutcome = null;
        _studentError = 'URL không hợp lệ. Vui lòng kiểm tra lại địa chỉ.';
      });
    } catch (e) {
      setState(() {
        _studentOutcome = null;
        _studentError = 'Student không thể phân tích URL này.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final outcome = _outcome;
    return Scaffold(
      appBar: AppBar(
        title: const Text('PhishGuard VN · Teacher v2'),
        actions: [
          IconButton(
            key: const Key('parity_button'),
            icon: const Icon(Icons.fact_check_outlined),
            tooltip: 'Kiểm tra parity E2 trên thiết bị',
            onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
              builder: (_) => ParityPage(extractor: widget.extractor),
            )),
          ),
        ],
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextField(
                key: const Key('url_field'),
                controller: _controller,
                keyboardType: TextInputType.url,
                autocorrect: false,
                enableSuggestions: false,
                minLines: 1,
                maxLines: 4,
                textInputAction: TextInputAction.done,
                onSubmitted: (_) => _analyze(),
                decoration: const InputDecoration(
                  labelText: 'URL cần phân tích',
                  hintText: 'https://example.com/path',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 4,
                children: [
                  for (final u in sampleUrls)
                    ActionChip(
                      label: Text(u, overflow: TextOverflow.ellipsis),
                      onPressed: () => _useSample(u),
                    ),
                ],
              ),
              const SizedBox(height: 12),
              FilledButton.icon(
                key: const Key('analyze_button'),
                onPressed: _analyze,
                icon: const Icon(Icons.search),
                label: const Text('Phân tích URL'),
              ),
              const SizedBox(height: 12),
              if (outcome != null) ..._buildResult(context, outcome),
              const SizedBox(height: 16),
              const Divider(),
              Text(
                'Student MLP · Chế độ thử nghiệm',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 8),
              FilledButton.tonalIcon(
                key: const Key('student_analyze_button'),
                onPressed:
                    widget.studentClassifier == null ? null : _analyzeStudent,
                icon: const Icon(Icons.science_outlined),
                label: const Text('Phân tích bằng Student'),
              ),
              const SizedBox(height: 8),
              if (widget.studentClassifier == null)
                Text(
                  widget.studentLoadError == null
                      ? 'Student chưa được nạp.'
                      : 'Student load lỗi: ${widget.studentLoadError.runtimeType}',
                ),
              if (_studentError != null)
                Card(
                  key: const Key('student_error'),
                  color: Theme.of(context).colorScheme.errorContainer,
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(
                          Icons.error_outline,
                          color: Theme.of(context).colorScheme.error,
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            _studentError!,
                            style: TextStyle(
                              color: Theme.of(context)
                                  .colorScheme
                                  .onErrorContainer,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              if (_studentError != null)
                _messageCard(
                  context,
                  cardKey: const Key('student_error'),
                  title: 'Lỗi khi chạy Student',
                  lines: [_studentError!],
                ),
              if (_studentOutcome case final outcome?)
                _buildStudentResult(context, outcome),
              const SizedBox(height: 16),
              _Footer(info: widget.info, teacher: widget.teacherInfo),
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _buildResult(
      BuildContext context, ClassificationOutcome outcome) {
    switch (outcome) {
      case Classified c:
        return [_classifiedCard(context, c), ..._e2Details(context)];
      case Unclassifiable u:
        return [
          _messageCard(
            context,
            cardKey: const Key('result_invalid'),
            title: 'Không phân loại được',
            lines: [
              describeError(u.reasonCode),
              'mã lỗi: ${u.reasonCode}',
              'Không có nhãn và không có điểm số; ứng dụng không trả số giả.',
            ],
          ),
        ];
      case InvalidInput i:
        return [
          _messageCard(
            context,
            cardKey: const Key('result_invalid'),
            title: 'Đầu vào không hợp lệ',
            lines: [describeInputIssue(i.issue)],
          ),
        ];
      case InferenceFailure f:
        return [
          _messageCard(
            context,
            cardKey: const Key('result_error'),
            title: 'Lỗi khi chạy mô hình',
            lines: [
              'Mô hình gặp lỗi bất thường (${f.errorType}) nên không có kết quả phân loại.',
              'Đây không phải nhãn benign hoặc phishing.',
            ],
          ),
        ];
    }
  }

  Widget _buildStudentResult(
      BuildContext context, ClassificationOutcome outcome) {
    switch (outcome) {
      case Classified c:
        return Card(
          key: const Key('result_student'),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Kết quả Student MLP'),
                Text(c.phishing ? 'Phishing' : 'Benign'),
                Text('Score: ${c.score.toStringAsFixed(6)}'),
                Text('Threshold: ${c.threshold}'),
                Text('Model: ${c.modelVersion}'),
                const Text('Score sigmoid chưa hiệu chuẩn.'),
              ],
            ),
          ),
        );

      case Unclassifiable u:
        return _messageCard(
          context,
          cardKey: const Key('result_student_invalid'),
          title: 'Student không phân loại được',
          lines: [
            describeError(u.reasonCode),
            'Mã lỗi: ${u.reasonCode}',
          ],
        );

      case InvalidInput i:
        return _messageCard(
          context,
          cardKey: const Key('result_student_invalid'),
          title: 'Đầu vào Student không hợp lệ',
          lines: [describeInputIssue(i.issue)],
        );

      case InferenceFailure f:
        return _messageCard(
          context,
          cardKey: const Key('result_student_error'),
          title: 'Lỗi khi chạy Student',
          lines: [
            'Mô hình gặp lỗi bất thường (${f.errorType}).',
            'Không có kết quả phân loại.',
          ],
        );
    }
  }

  Widget _classifiedCard(BuildContext context, Classified c) {
    final scheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    return Card(
      key: const Key('result_teacher'),
      color: c.phishing ? scheme.errorContainer : scheme.primaryContainer,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              c.phishing
                  ? 'Có dấu hiệu lừa đảo'
                  : 'Chưa phát hiện dấu hiệu lừa đảo',
              style:
                  textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            SelectableText('Điểm của mô hình: ${c.score.toStringAsFixed(6)}'),
            SelectableText(
                'Ngưỡng: ${c.threshold} · quy tắc: ${c.decisionRule}'),
            Text('Mô hình: ${c.modelVersion}'),
            const SizedBox(height: 8),
            Text(
              'Điểm này chưa được hiệu chuẩn; không được hiểu là phần trăm an toàn hay phần trăm lừa đảo.',
              style: textTheme.bodySmall,
            ),
            Text(
              'Chưa phát hiện dấu hiệu không có nghĩa là website chắc chắn an toàn.',
              style: textTheme.bodySmall,
            ),
            Text(
              'Phân tích chỉ dùng mô hình có sẵn trong ứng dụng; URL không bị gửi đi và website không được truy cập.',
              style: textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }

  Widget _messageCard(
    BuildContext context, {
    required Key cardKey,
    required String title,
    required List<String> lines,
  }) {
    final textTheme = Theme.of(context).textTheme;
    return Card(
      key: cardKey,
      color: Theme.of(context).colorScheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title,
                style: textTheme.titleMedium
                    ?.copyWith(fontWeight: FontWeight.bold)),
            for (final line in lines) ...[
              const SizedBox(height: 4),
              Text(line),
            ],
          ],
        ),
      ),
    );
  }

  List<Widget> _e2Details(BuildContext context) {
    final r = _features;
    if (r == null || !r.isClassifiable) return const [];
    final map = r.toMap()!;
    final p = r.parsed;
    return [
      const SizedBox(height: 8),
      Card(
        child: ExpansionTile(
          key: const Key('e2_details_tile'),
          title: const Text('Chi tiết đặc trưng E2 (20)'),
          childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
          expandedCrossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Column(
              key: const Key('result_ok'),
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SelectableText('Host: ${p.hostname}'),
                SelectableText(p.registrableDomain != null
                    ? 'Tên miền đăng ký: ${p.registrableDomain}'
                    : 'Tên miền đăng ký: (không có, URL là địa chỉ IP)'),
                SelectableText(
                    'Subdomain: ${p.subdomain.isEmpty ? '(rỗng)' : p.subdomain}'),
                if (p.schemeWasAdded)
                  const Text('Đã tự thêm http:// để phân tích.'),
              ],
            ),
            ..._featureRows(context, 'Lexical (12 đặc trưng E1)',
                lexicalFeatureOrder, map, false),
            ..._featureRows(context, 'Brand (8 đặc trưng E2)',
                brandFeatureOrder, map, true),
            OutlinedButton.icon(
              key: const Key('copy_json_button'),
              onPressed: () => _copyJson(r),
              icon: const Icon(Icons.copy),
              label: const Text('Sao chép JSON'),
            ),
          ],
        ),
      ),
    ];
  }

  List<Widget> _featureRows(
    BuildContext context,
    String title,
    List<String> names,
    Map<String, double> map,
    bool highlightNonZero,
  ) {
    return [
      Padding(
        padding: const EdgeInsets.only(top: 12, bottom: 4),
        child: Text(title, style: Theme.of(context).textTheme.titleSmall),
      ),
      for (final name in names)
        ListTile(
          key: Key('feature_row_$name'),
          dense: true,
          contentPadding: EdgeInsets.zero,
          title: Text(name, style: const TextStyle(fontFamily: 'monospace')),
          subtitle: Text(featureDescriptions[name] ?? ''),
          trailing: Text(
            formatFeature(name, map[name]!),
            style: TextStyle(
              fontFamily: 'monospace',
              fontWeight: highlightNonZero && map[name] != 0
                  ? FontWeight.bold
                  : FontWeight.normal,
            ),
          ),
        ),
    ];
  }
}

class _Footer extends StatelessWidget {
  const _Footer({this.info, this.teacher});

  final LoadedExtractor? info;
  final TeacherRuntimeInfo? teacher;

  @override
  Widget build(BuildContext context) {
    final i = info;
    final t = teacher;
    final extractorLine = 'Schema $featureSchemaVersion'
        '${i == null ? '' : ' · ${i.nBrands} brand · ref ${i.brandSha256.substring(0, 12)}… · ${i.pslRules} quy tắc PSL'}';
    final teacherLine = t == null
        ? ''
        : '\nTeacher ${t.modelVersion} · nạp ${t.timings.total.inMilliseconds} ms '
            '(đọc ${t.timings.read.inMilliseconds}, băm ${t.timings.hash.inMilliseconds}, '
            'parse ${t.timings.parse.inMilliseconds}, dựng ${t.timings.build.inMilliseconds}) · '
            '${t.svmBytes + t.modelBytes} byte JSON';
    return Text(
      '$extractorLine$teacherLine\nChỉ phân tích chuỗi URL, không truy cập website.',
      style: Theme.of(context).textTheme.bodySmall,
    );
  }
}
