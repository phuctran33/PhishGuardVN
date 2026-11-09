import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:phishguard_features/phishguard_features.dart';

/// Chạy bộ ca parity (frozen + extra) NGAY TRÊN THIẾT BỊ và so từng cột với kỳ vọng của Python.
class ParityPage extends StatefulWidget {
  const ParityPage({super.key, required this.extractor, this.bundle});
  final E2Extractor extractor;
  final AssetBundle? bundle;

  @override
  State<ParityPage> createState() => _ParityPageState();
}

class _ParityPageState extends State<ParityPage> {
  bool _running = false;
  String? _report;
  int _total = 0, _passed = 0;
  Object? _error;

  Future<void> _run() async {
    setState(() {
      _running = true;
      _error = null;
    });
    try {
      final bundle = widget.bundle ?? rootBundle;
      final suites = <String, Map<String, dynamic>>{
        'frozen': jsonDecode(await bundle.loadString('assets/mobile_parity_cases.json'))
            as Map<String, dynamic>,
      };
      try {
        suites['extra'] = jsonDecode(await bundle.loadString('assets/mobile_parity_cases_extra.json'))
            as Map<String, dynamic>;
      } catch (_) {
        // file extra là tùy chọn
      }
      final sw = Stopwatch()..start();
      final tol = (suites['frozen']!['tolerance'] as num).toDouble();
      var total = 0, passed = 0;
      final failures = <String>[];
      final perSuite = <String>[];
      for (final entry in suites.entries) {
        final cases = (entry.value['cases'] as List).cast<Map<String, dynamic>>();
        var ok = 0;
        for (final c in cases) {
          final r = widget.extractor.extract(c['url'] as String?);
          final diffs = [
            ...compareParsed(c['parsed'] as Map<String, dynamic>, r.parsed),
            ...compareFeatures(c['expected'] as Map<String, dynamic>, r, tol),
          ];
          total++;
          if (diffs.isEmpty) {
            passed++;
            ok++;
          } else {
            failures.add('${entry.key}/${c['name']}: ${diffs.join('; ')}');
          }
        }
        perSuite.add('${entry.key}: $ok/${cases.length}');
      }
      sw.stop();
      final report = StringBuffer()
        ..writeln('Parity trên thiết bị: $passed/$total ca khớp (${perSuite.join(', ')})')
        ..writeln('Thiết bị: ${Platform.operatingSystem} ${Platform.operatingSystemVersion}')
        ..writeln('Dart: ${Platform.version}')
        ..writeln('Schema: $featureSchemaVersion · tolerance: $tol · thời gian: ${sw.elapsedMilliseconds} ms');
      if (failures.isNotEmpty) {
        report
          ..writeln()
          ..writeln('Ca lệch:');
        failures.forEach(report.writeln);
      }
      setState(() {
        _total = total;
        _passed = passed;
        _report = report.toString();
      });
    } catch (e) {
      setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _running = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Parity Python – Android')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('So từng cột của 20 đặc trưng (và các giá trị trung gian của parser) '
                  'với kỳ vọng sinh bởi Python.'),
              const SizedBox(height: 12),
              FilledButton.icon(
                key: const Key('run_parity_button'),
                onPressed: _running ? null : _run,
                icon: const Icon(Icons.play_arrow),
                label: Text(_running ? 'Đang chạy…' : 'Chạy parity'),
              ),
              const SizedBox(height: 12),
              if (_error != null)
                Card(
                  color: scheme.errorContainer,
                  child: Padding(padding: const EdgeInsets.all(16), child: SelectableText('$_error')),
                ),
              if (_report != null) ...[
                Card(
                  key: const Key('parity_result'),
                  color: _passed == _total ? scheme.primaryContainer : scheme.errorContainer,
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: SelectableText(_report!, style: const TextStyle(fontFamily: 'monospace')),
                  ),
                ),
                OutlinedButton.icon(
                  onPressed: () => Clipboard.setData(ClipboardData(text: _report!)),
                  icon: const Icon(Icons.copy),
                  label: const Text('Sao chép báo cáo'),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
