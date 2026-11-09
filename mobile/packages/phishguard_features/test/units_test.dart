// Test đơn vị KHÔNG cần file PSL thật: chạy được ngay sau `dart pub get`.
import 'package:phishguard_features/phishguard_features.dart';
import 'package:phishguard_features/src/brand.dart' show osaDistance, confusableFold, foldText, tokensOf, parseCsv;
import 'package:phishguard_features/src/idna.dart';
import 'package:phishguard_features/src/ip.dart';
import 'package:phishguard_features/src/punycode.dart';
import 'package:phishguard_features/src/py_compat.dart';
import 'package:test/test.dart';

void main() {
  group('punycode / idna', () {
    test('bücher <-> bcher-kva', () {
      expect(punycodeEncode('bücher'), 'bcher-kva');
      expect(punycodeDecode('bcher-kva'), 'bücher');
    });
    test('hostToAscii', () {
      expect(hostToAscii('bücher.de'), 'xn--bcher-kva.de');
      expect(hostToAscii('BÜCHER.de'), 'xn--bcher-kva.de');
    });
    test('hostToAscii từ chối ký tự bị cấm', () {
      expect(hostToAscii('😀.com'), isNull);
      expect(hostToAscii('bücher_x.de'), isNull);
      expect(hostToAscii('-bücher.de'), isNull);
      expect(hostToAscii('bü..de'), isNull);
      expect(hostToAscii('vietcombank-đăngnhập.top'), isNotNull);
    });
    test('decodeHost giữ nguyên nhãn lỗi', () {
      expect(decodeHost('xn--bcher-kva.de'), 'bücher.de');
      expect(decodeHost('xn--!!!.de'), 'xn--!!!.de');
    });
  });

  group('ip', () {
    test('ipv4', () {
      expect(parseIp('192.168.1.1'), '192.168.1.1');
      expect(parseIp('192.168.01.1'), isNull);
      expect(parseIp('256.1.1.1'), isNull);
      expect(parseIp('1.2.3'), isNull);
    });
    test('ipv6 rút gọn', () {
      expect(parseIp('2001:0db8:0:0:0:0:0:1'), '2001:db8::1');
      expect(parseIp('2001:db8::1'), '2001:db8::1');
      expect(parseIp('::'), '::');
      expect(parseIp('::1'), '::1');
      expect(parseIp('1:0:0:2:0:0:0:3'), '1:0:0:2::3');
      expect(parseIp('1::2::3'), isNull);
      expect(parseIp('example.com'), isNull);
    });
  });

  group('psl (bộ luật nhỏ tự dựng)', () {
    final psl = PublicSuffixList.fromRules(['com', 'vn', 'com.vn', 'co.uk', 'uk', '*.ck', '!www.ck', 'ck']);
    test('khớp suffix dài nhất', () {
      expect(psl.suffixIndex(['www', 'vietcombank', 'com', 'vn']), 2);
      expect(psl.suffixIndex(['a', 'b', 'c', 'example', 'co', 'uk']), 4);
      expect(psl.suffixIndex(['x', 'vn']), 1);
    });
    test('wildcard và ngoại lệ', () {
      expect(psl.suffixIndex(['a', 'b', 'ck']), 1); // *.ck: suffix = b.ck
      expect(psl.suffixIndex(['a', 'www', 'ck']), 2); // !www.ck: suffix = ck
    });
    test('không khớp -> labels.length', () {
      expect(psl.suffixIndex(['invalid_url']), 1);
      expect(psl.suffixIndex(['foo', 'unknowntld']), 2);
    });
  });

  group('chuỗi kiểu Python', () {
    test('unquote', () {
      expect(unquote('%76ietcombank'), 'vietcombank');
      expect(unquote('Đăng%20Nhập'), 'Đăng Nhập');
      expect(unquote('%E1%BA%A1'), 'ạ');
    });
    test('pyStrip / pyLen', () {
      expect(pyStrip('  \u00A0x\u3000 '), 'x');
      expect(pyLen('😀a'), 2);
    });
    test('foldText / tokens', () {
      expect(foldText('Đăng Nhập'), 'dang nhap');
      expect(tokensOf('Đăng-Nhập_2'), ['dang', 'nhap', '2']);
      expect(confusableFold('vietc0mbank'), 'vletcombank'); // 0->o và i->l (contract mục 7)
      expect(confusableFold('momornomo'), 'momomomo');
    });
    test('OSA', () {
      expect(osaDistance('vietcombnak', 'vietcombank'), 1);
      expect(osaDistance('vietcombanks', 'vietcombank'), 1);
      expect(osaDistance('abc', 'abc'), 0);
      expect(osaDistance('kitten', 'sitting'), 3);
    });
  });

  test('parseCsv xử lý ô có dấu phẩy và nháy kép', () {
    final rows = parseCsv('a,b\n1,"x, y"\n2,"he said ""hi"""\n');
    expect(rows[0]['b'], 'x, y');
    expect(rows[1]['b'], 'he said "hi"');
  });
}
