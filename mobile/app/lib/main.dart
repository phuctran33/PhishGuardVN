import 'package:flutter/material.dart';

import 'src/extractor_loader.dart';
import 'src/home_page.dart';

void main() => runApp(const PhishGuardApp());

class PhishGuardApp extends StatelessWidget {
  const PhishGuardApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'PhishGuard VN',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(colorSchemeSeed: Colors.indigo, useMaterial3: true),
        home: const _Boot(),
      );
}

/// Nạp PSL + brand reference từ assets rồi mới vào màn hình chính.
class _Boot extends StatefulWidget {
  const _Boot();
  @override
  State<_Boot> createState() => _BootState();
}

class _BootState extends State<_Boot> {
  late final Future<LoadedExtractor> _future = loadE2Extractor();

  @override
  Widget build(BuildContext context) => FutureBuilder<LoadedExtractor>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Scaffold(body: Center(child: CircularProgressIndicator()));
          }
          if (snap.hasError) {
            return Scaffold(
              appBar: AppBar(title: const Text('Không nạp được extractor')),
              body: Padding(
                padding: const EdgeInsets.all(16),
                child: SelectableText(
                  '${snap.error}\n\nNếu báo thiếu asset: chạy `bash mobile/tool/sync_assets.sh` '
                  'rồi build lại.',
                ),
              ),
            );
          }
          final loaded = snap.data!;
          return HomePage(extractor: loaded.extractor, info: loaded);
        },
      );
}
