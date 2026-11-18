import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:phishguard_features/phishguard_features.dart';

import 'extractor_loader.dart';
import 'feature_info.dart';
import 'parity_page.dart';

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
  const HomePage({super.key, required this.extractor, this.info});
  final E2Extractor extractor;
  final LoadedExtractor? info;

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  final _controller = TextEditingController();
  FeatureResult? _result;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _analyze() {
    FocusScope.of(context).unfocus();
    setState(() => _result = widget.extractor.extract(_controller.text));
  }

  void _useSample(String url) {
    _controller.text = url;
    _analyze();
  }

  Future<void> _copyJson(FeatureResult r) async {
    final text = const JsonEncoder.withIndent('  ')
        .convert({'url': _controller.text, 'features': r.toMap()});
    await Clipboard.setData(ClipboardData(text: text));
    if (!mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(const SnackBar(content: Text('Đã sao chép JSON đặc trưng')));
  }

  @override
  Widget build(BuildContext context) {
    final result = _result;
    return Scaffold(
      appBar: AppBar(
        title: const Text('PhishGuard VN · E2 v1'),
        actions: [
          IconButton(
            key: const Key('parity_button'),
            icon: const Icon(Icons.fact_check_outlined),
            tooltip: 'Kiểm tra parity trên thiết bị',
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
                    ActionChip(label: Text(u, overflow: TextOverflow.ellipsis), onPressed: () => _useSample(u)),
                ],
              ),
              const SizedBox(height: 12),
              FilledButton.icon(
                key: const Key('analyze_button'),
                onPressed: _analyze,
                icon: const Icon(Icons.search),
                label: const Text('Trích xuất đặc trưng'),
              ),
              const SizedBox(height: 12),
              if (result != null) ..._buildResult(context, result),
              const SizedBox(height: 16),
              _Footer(info: widget.info),
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _buildResult(BuildContext context, FeatureResult r) {
    final scheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    final p = r.parsed;
    if (!r.isClassifiable) {
      return [
        Card(
          key: const Key('result_invalid'),
          color: scheme.errorContainer,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Không phân loại được',
                    style: textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
                const SizedBox(height: 6),
                Text(describeError(r.errorReason)),
                const SizedBox(height: 4),
                Text('mã lỗi: ${r.errorReason}', style: textTheme.bodySmall),
                const SizedBox(height: 4),
                Text('Không có vector đặc trưng; app không trả số giả.', style: textTheme.bodySmall),
              ],
            ),
          ),
        ),
      ];
    }
    final map = r.toMap()!;
    return [
      Card(
        key: const Key('result_ok'),
        color: scheme.primaryContainer,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Đã trích xuất đủ 20 đặc trưng',
                  style: textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
              const SizedBox(height: 6),
              SelectableText('Host: ${p.hostname}'),
              SelectableText(p.registrableDomain != null
                  ? 'Tên miền đăng ký: ${p.registrableDomain}'
                  : 'Tên miền đăng ký: (không có, URL là địa chỉ IP)'),
              SelectableText('Subdomain: ${p.subdomain.isEmpty ? '(rỗng)' : p.subdomain}'),
              if (p.schemeWasAdded) const Text('Đã tự thêm http:// để phân tích.'),
              const SizedBox(height: 4),
              Text('Đây mới là bước trích xuất đặc trưng; chưa có mô hình nên chưa có kết luận lừa đảo.',
                  style: textTheme.bodySmall),
            ],
          ),
        ),
      ),
      const SizedBox(height: 8),
      _section(context, 'Lexical (12 đặc trưng E1)', lexicalFeatureOrder, map, false),
      const SizedBox(height: 8),
      _section(context, 'Brand (8 đặc trưng E2)', brandFeatureOrder, map, true),
      const SizedBox(height: 8),
      OutlinedButton.icon(
        key: const Key('copy_json_button'),
        onPressed: () => _copyJson(r),
        icon: const Icon(Icons.copy),
        label: const Text('Sao chép JSON'),
      ),
    ];
  }

  Widget _section(BuildContext context, String title, List<String> names, Map<String, double> map,
      bool highlightNonZero) {
    return Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: Text(title, style: Theme.of(context).textTheme.titleSmall),
          ),
          for (final name in names)
            ListTile(
              key: Key('feature_row_$name'),
              dense: true,
              title: Text(name, style: const TextStyle(fontFamily: 'monospace')),
              subtitle: Text(featureDescriptions[name] ?? ''),
              trailing: Text(
                formatFeature(name, map[name]!),
                style: TextStyle(
                  fontFamily: 'monospace',
                  fontWeight: highlightNonZero && map[name] != 0 ? FontWeight.bold : FontWeight.normal,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _Footer extends StatelessWidget {
  const _Footer({this.info});
  final LoadedExtractor? info;

  @override
  Widget build(BuildContext context) {
    final i = info;
    final style = Theme.of(context).textTheme.bodySmall;
    return Text(
      'Schema $featureSchemaVersion'
      '${i == null ? '' : ' · ${i.nBrands} brand · ref ${i.brandSha256.substring(0, 12)}… · ${i.pslRules} quy tắc PSL'}'
      '\nChỉ phân tích chuỗi URL, không truy cập website. Không gửi dữ liệu ra ngoài.',
      style: style,
    );
  }
}
