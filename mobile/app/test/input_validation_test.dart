import 'package:flutter_test/flutter_test.dart';
import 'package:phishguard_android/src/input_validation.dart';

void main() {
  test('URL hợp lệ (kể cả có dấu cách bên trong, như Teacher Python)', () {
    expect(validateUrlInput('https://example.com/path'), isNull);
    expect(validateUrlInput('example.com/a b'), isNull);
  });

  test('rỗng, chỉ khoảng trắng hoặc null -> blank', () {
    expect(validateUrlInput(null), InputIssue.blank);
    expect(validateUrlInput(''), InputIssue.blank);
    expect(validateUrlInput('   '), InputIssue.blank);
    expect(validateUrlInput('\u00A0'), InputIssue.blank);
    expect(validateUrlInput('\u3000'), InputIssue.blank);
    expect(validateUrlInput('\x1C'), InputIssue.blank); // str.strip() của Python coi \x1c là khoảng trắng
  });

  test('ký tự điều khiển (< 32, gồm NUL) -> controlCharacter', () {
    expect(validateUrlInput('http://x/\t'), InputIssue.controlCharacter);
    expect(validateUrlInput('a\nb'), InputIssue.controlCharacter);
    expect(validateUrlInput('a\u0000b'), InputIssue.controlCharacter);
  });

  test('khoảng trắng hai đầu -> surroundingWhitespace (không trim ngầm)', () {
    expect(validateUrlInput(' http://x'), InputIssue.surroundingWhitespace);
    expect(validateUrlInput('http://x '), InputIssue.surroundingWhitespace);
    expect(validateUrlInput('\u00A0http://x'), InputIssue.surroundingWhitespace);
  });

  test('mọi lý do đều có thông báo tiếng Việt', () {
    for (final issue in InputIssue.values) {
      expect(describeInputIssue(issue), isNotEmpty);
    }
  });
}
