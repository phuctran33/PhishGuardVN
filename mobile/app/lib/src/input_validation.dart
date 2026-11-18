/// Kiểm đầu vào theo hợp đồng của Teacher Python (validate_urls trong stacking.py):
/// từ chối chuỗi rỗng, ký tự điều khiển (< 32, gồm NUL) và khoảng trắng hai đầu. Không trim ngầm.
enum InputIssue { blank, controlCharacter, surroundingWhitespace }

/// Ký tự mà str.isspace() của Python coi là khoảng trắng.
bool _isPySpace(int c) =>
    (c >= 0x09 && c <= 0x0D) ||
    (c >= 0x1C && c <= 0x20) ||
    c == 0x85 ||
    c == 0xA0 ||
    c == 0x1680 ||
    (c >= 0x2000 && c <= 0x200A) ||
    c == 0x2028 ||
    c == 0x2029 ||
    c == 0x202F ||
    c == 0x205F ||
    c == 0x3000;

/// Trả null nếu hợp lệ. Thứ tự kiểm giống Python: rỗng, ký tự điều khiển, khoảng trắng hai đầu.
InputIssue? validateUrlInput(String? value) {
  if (value == null) return InputIssue.blank;
  final runes = value.runes.toList();
  var start = 0;
  var end = runes.length;
  while (start < end && _isPySpace(runes[start])) {
    start++;
  }
  while (end > start && _isPySpace(runes[end - 1])) {
    end--;
  }
  if (start == end) return InputIssue.blank;
  if (runes.any((c) => c < 32)) return InputIssue.controlCharacter;
  if (start != 0 || end != runes.length) return InputIssue.surroundingWhitespace;
  return null;
}

String describeInputIssue(InputIssue issue) {
  switch (issue) {
    case InputIssue.blank:
      return 'Chưa nhập URL.';
    case InputIssue.controlCharacter:
      return 'URL chứa ký tự điều khiển (gồm tab, xuống dòng hoặc NUL). Hãy dán lại URL thuần.';
    case InputIssue.surroundingWhitespace:
      return 'URL có khoảng trắng ở đầu hoặc cuối. Ứng dụng không tự cắt bỏ; hãy xóa khoảng trắng rồi thử lại.';
  }
}
