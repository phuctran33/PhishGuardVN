const Map<String, String> featureDescriptions = {
  'url_len': 'Độ dài URL (đã bỏ scheme)',
  'dom_len': 'Độ dài tên miền đăng ký',
  'is_ip': 'URL dùng địa chỉ IP (1/0)',
  'subdom_cnt': 'Số nhãn trong subdomain',
  'letter_cnt': 'Số ký tự chữ',
  'digit_cnt': 'Số chữ số',
  'dot_cnt': "Số dấu '.'",
  'dash_cnt': "Số dấu '-'",
  'under_cnt': "Số dấu '_'",
  'slash_cnt': "Số dấu '/'",
  'entropy': 'Entropy Shannon (log2) của URL',
  'path_len': 'Độ dài path',
  'brand_in_domain': 'Tên brand xuất hiện trong tên miền (SLD)',
  'brand_in_subdomain': 'Tên brand xuất hiện trong subdomain',
  'brand_in_path': 'Tên brand xuất hiện trong path/query',
  'brand_domain_mismatch': 'Có brand nhưng tên miền không thuộc domain chính thức',
  'brand_typo_score': 'Điểm gõ sai tên brand (0 đến 1)',
  'susp_token_cnt': 'Số từ khóa đáng ngờ khác nhau',
  'idna_flag': 'Host có nhãn Punycode (xn--)',
  'homoglyph_brand_hit': 'Brand bị che bằng ký tự dễ nhầm',
};

const Set<String> continuousFeatureNames = {'entropy', 'brand_typo_score'};

String formatFeature(String name, double v) =>
    continuousFeatureNames.contains(name) ? v.toStringAsFixed(4) : v.toInt().toString();

String describeError(String? code) {
  switch (code) {
    case 'missing_url':
      return 'Chưa có URL.';
    case 'empty_url':
      return 'URL rỗng.';
    case 'invalid_port':
      return 'Cổng (port) không hợp lệ.';
    case 'invalid_hostname':
      return 'Tên máy chủ (host) không hợp lệ.';
    case 'unresolved_domain':
      return 'Không xác định được tên miền đăng ký (theo Public Suffix List).';
    default:
      return 'Không phân tích được URL (${code ?? 'lỗi không rõ'}).';
  }
}
