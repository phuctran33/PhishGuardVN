import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:phishguard_features/io.dart';
import 'package:test/test.dart';

/// sha256 do scripts/export_psl_for_dart.py in ra (tldextract 5.4.0, include_psl_private_domains=False).
const expectedPslSha256 = 'fb8419c17a533dfdd57199da1cef1481974119fe23ce7c478af3d12eb8466c8f';
const expectedPslRules = 6871;

void main() {
  test('asset PSL đúng snapshot tldextract 5.4.0', () {
    final f = File(pslAssetPath(findRepoRoot()));
    expect(f.existsSync(), isTrue,
        reason: 'Thiếu ${f.path}: chạy scripts/export_psl_for_dart.py rồi chép file vào assets/.');
    // Chuẩn hóa CRLF -> LF (Windows autocrlf) trước khi băm, vì script Python băm với "\n".
    final text = f.readAsStringSync().replaceAll('\r\n', '\n');
    expect(sha256.convert(utf8.encode(text)).toString(), expectedPslSha256);
    expect(text.split('\n').where((l) => l.isNotEmpty).length, expectedPslRules);
  });
}
