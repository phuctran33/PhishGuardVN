import { backendOrigin, CheckError, DEFAULT_BACKEND, predict, selectedHostname } from './prediction.mjs';

const get = (id) => document.getElementById(id);
const card = get('card');
let selected;

function show(status, tone = '', note = '', retryable = false) {
  get('status').textContent = status;
  card.dataset.tone = tone;
  card.setAttribute('aria-busy', String(tone === 'loading'));
  get('note').textContent = note;
  get('note').hidden = !note;
  get('retry').hidden = !retryable;
}

async function check() {
  get('details').hidden = true;
  get('hostname').hidden = true;
  show('Đang kiểm tra…', 'loading');
  try {
    const hostname = selectedHostname(selected);
    get('hostname').textContent = 'Hostname: ' + hostname;
    get('hostname').hidden = false;
    const { backend } = await chrome.storage.local.get({ backend: DEFAULT_BACKEND });
    get('endpoint').textContent = 'Backend: ' + backendOrigin(backend);
    get('endpoint').hidden = false;
    const prediction = await predict(selected, backend);
    const flagged = prediction.label === 'phishing';
    show(
      flagged ? 'Có dấu hiệu phishing' : 'Chưa phát hiện dấu hiệu phishing',
      prediction.label,
      flagged
        ? 'Hãy xác minh nguồn gửi trước khi mở. Điểm mô hình chưa hiệu chuẩn.'
        : 'Nhãn benign không bảo đảm đường dẫn an toàn. Điểm mô hình chưa hiệu chuẩn.',
    );
    get('label').textContent = prediction.label;
    get('model').textContent = prediction.model;
    get('score-label').textContent = prediction.score_kind === 'probability' ? 'Điểm mô hình' : 'Biên quyết định';
    get('score').textContent = String(prediction.score);
    const hasThreshold = prediction.threshold !== null;
    get('threshold-label').hidden = get('threshold').hidden = !hasThreshold;
    get('threshold').textContent = hasThreshold ? String(prediction.threshold) : '';
    get('details').hidden = false;
  } catch (error) {
    show('Chưa kiểm tra được đường dẫn', 'error',
      error instanceof CheckError ? error.message : 'Không đọc được cấu hình backend.',
      error instanceof CheckError && error.retryable);
  }
}

get('retry').addEventListener('click', check);
get('options').addEventListener('click', () => chrome.runtime.openOptionsPage());
try {
  selected = await chrome.runtime.sendMessage({ type: 'take-link', id: location.hash.slice(1) });
  history.replaceState(null, '', location.pathname);
} catch {
  selected = null;
}
if (selected === null || selected === undefined) {
  show('Chưa chọn đường dẫn', 'error', 'Nhấn chuột phải vào link và chọn Kiểm tra bằng PhishGuardVN.');
} else {
  await check();
}
