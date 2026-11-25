export const DEFAULT_BACKEND = 'http://127.0.0.1:8000';

export class CheckError extends Error {
  constructor(code, message, retryable = false) {
    super(message);
    this.code = code;
    this.retryable = retryable;
  }
}

export function backendOrigin(value) {
  try {
    const url = new URL(value.trim());
    if (url.username || url.password || url.pathname !== '/' ||
        url.search || url.hash || !/^https?:\/\//i.test(value.trim()) ||
        (url.protocol !== 'https:' &&
         !(url.protocol === 'http:' && ['127.0.0.1', 'localhost'].includes(url.hostname)))) {
      throw new Error();
    }
    return url.origin;
  } catch {
    throw new CheckError('BACKEND_ORIGIN', 'Nhập địa chỉ gốc HTTPS hoặc HTTP trên localhost/127.0.0.1.');
  }
}

export function hostPermission(origin) {
  const url = new URL(origin);
  // Chrome match patterns cover the host on all ports.
  return url.protocol + '//' + url.hostname + '/*';
}

export function selectedHostname(raw) {
  if (typeof raw !== 'string' || !raw || raw.length > 4096 || /[\s\u0000-\u001f\u007f\\]/u.test(raw)) {
    throw new CheckError('INVALID_URL', 'Đường dẫn không hợp lệ hoặc vượt quá 4096 ký tự.');
  }
  if (!/^https?:\/\//i.test(raw)) {
    throw new CheckError('UNSUPPORTED_SCHEME', 'Chỉ kiểm tra liên kết HTTP hoặc HTTPS.');
  }
  try {
    return new URL(raw).hostname;
  } catch {
    throw new CheckError('INVALID_URL', 'Đường dẫn không hợp lệ. Kiểm tra hostname và cổng.');
  }
}

function invalidResponse() {
  return new CheckError('INVALID_RESPONSE', 'Phản hồi không đúng API contract.', true);
}

export function parsePrediction(body) {
  if (!body || !['benign', 'phishing'].includes(body.label) ||
      !['probability', 'decision_function'].includes(body.score_kind) ||
      !Number.isFinite(body.score) ||
      (body.score_kind === 'probability' && (body.score < 0 || body.score > 1)) ||
      !['model', 'protocol', 'score_definition'].every(
        key => typeof body[key] === 'string' && body[key].trim().length > 0
      ) || !['estimator.predict', 'score >= threshold'].includes(body.decision_rule) ||
      (body.decision_rule === 'score >= threshold' &&
       (body.score_kind !== 'probability' || !Number.isFinite(body.threshold) ||
        body.threshold < 0 || body.threshold > 1 + Number.EPSILON)) ||
      (body.decision_rule === 'estimator.predict' && body.threshold != null)) {
    throw invalidResponse();
  }
  return {
    label: body.label,
    model: body.model,
    score: body.score,
    score_kind: body.score_kind,
    threshold: body.threshold ?? null,
  };
}

export async function predict(raw, backend, { timeoutMs = 8000, send = fetch } = {}) {
  selectedHostname(raw);
  const endpoint = backendOrigin(backend) + '/predict';
  const signal = AbortSignal.timeout(timeoutMs);
  let response;
  let json;
  try {
    response = await send(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ url: raw }),
      signal,
      credentials: 'omit',
      cache: 'no-store',
      redirect: 'error',
      referrerPolicy: 'no-referrer',
    });
    // Only a successful response is expected to contain predictions. Error
    // bodies may be proxy pages, which should never be rendered as text.
    if (response.status === 200) json = await response.json();
  } catch (error) {
    if (signal.aborted) {
      throw new CheckError('TIMEOUT', 'Máy chủ phản hồi quá chậm. Hãy thử lại.', true);
    }
    if (response) throw invalidResponse();
    throw new CheckError('NETWORK_ERROR', 'Không kết nối được backend. Kiểm tra cấu hình hoặc thử lại.', true);
  }
  switch (response.status) {
    case 200:
      return parsePrediction(json);
    case 422:
      throw new CheckError('INVALID_URL', 'Máy chủ từ chối URL. Kiểm tra tên miền và cổng.');
    case 503:
      throw new CheckError('MODEL_UNAVAILABLE', 'Teacher chưa sẵn sàng. Hãy thử lại sau.', true);
    case 500:
      throw new CheckError('INFERENCE_FAILED', 'Máy chủ gặp lỗi khi phân tích. Hãy thử lại.', true);
    default:
      throw invalidResponse();
  }
}
