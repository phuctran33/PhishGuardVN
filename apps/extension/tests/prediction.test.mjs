import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { backendOrigin, DEFAULT_BACKEND, hostPermission, parsePrediction, predict, selectedHostname } from '../prediction.mjs';

const testResponse = {
  label: 'phishing',
  model: 'teacher-stacking-v2',
  score: 0.73,
  score_kind: 'probability',
  decision_rule: 'score >= threshold',
  score_definition: 'fixture',
  protocol: 'test fixture',
  threshold: 0.7,
};

test('Manifest V3 grants only the chosen checks and configuration', () => {
  const m = JSON.parse(readFileSync(new URL('../manifest.json', import.meta.url), 'utf-8'));
  assert.equal(m.manifest_version, 3);
  assert.deepEqual(m.permissions, ['contextMenus', 'storage']);
  assert.deepEqual(m.host_permissions, ['http://127.0.0.1/*']);
  assert.equal(m.content_scripts, undefined);
  assert.equal(m.web_accessible_resources, undefined);
});

test('backend URL is an HTTPS origin or HTTP loopback', () => {
  assert.equal(backendOrigin(DEFAULT_BACKEND), DEFAULT_BACKEND);
  assert.equal(backendOrigin('https://EXAMPLE.com/'), 'https://example.com');
  assert.equal(hostPermission('http://localhost:18380'), 'http://localhost/*');
  for (const origin of ['http://example.com', 'https://user@example.com', 'https://example.com/api',
    'https://example.com/?key=private', 'https://example.com/#x', 'https:example.com', 'file:///file']) {
    assert.throws(() => backendOrigin(origin), { code: 'BACKEND_ORIGIN' });
  }
});

test('source URL is never visited and is passed unmodified only in POST JSON', async () => {
  const raw = 'https://user:pass@EXAMPLE.com:443/A%2Fa?temp=private';
  const send = async (url, options) => {
    assert.equal(url, DEFAULT_BACKEND + '/predict');
    assert.deepEqual(JSON.parse(options.body), { url: raw });
    assert.equal(options.credentials, 'omit');
    assert.equal(options.cache, 'no-store');
    assert.equal(options.method, 'POST');
    assert.equal(options.redirect, 'error');
    assert.equal(options.referrerPolicy, 'no-referrer');
    return Response.json(testResponse);
  };
  assert.equal(selectedHostname(raw), 'example.com');
  assert.equal((await predict(raw, DEFAULT_BACKEND, { send })).label, 'phishing');
});

test('prediction display follows API label and uses the API threshold', () => {
  const p = parsePrediction({ ...testResponse, threshold: 0.9, label: 'benign' });
  assert.equal(p.label, 'benign');
  assert.equal(p.threshold, 0.9);
  for (const patch of [
    { label: 'safe' }, { score: NaN }, { score: 1.2 }, { model: '' },
    { threshold: undefined }, { threshold: -1 }, { decision_rule: 'invalid' },
    { score_kind: 'decision_function' },
  ]) {
    assert.throws(() => parsePrediction({ ...testResponse, ...patch }), { code: 'INVALID_RESPONSE' });
  }
});

for (const [status, code] of [[422, 'INVALID_URL'], [503, 'MODEL_UNAVAILABLE'], [500, 'INFERENCE_FAILED']]) {
  test('HTTP ' + status + ' has its own sanitized status', async () => {
    const send = async () => new Response('test-only private diagnostics', { status });
    await assert.rejects(predict('https://example.com', DEFAULT_BACKEND, { send }), { code });
  });
}

test('invalid URL and unsupported schemes never make a request', async () => {
  const send = async () => assert.fail('unexpected request');
  await assert.rejects(predict('ftp://example.com', DEFAULT_BACKEND, { send }), { code: 'UNSUPPORTED_SCHEME' });
  await assert.rejects(predict('https://example.com:bad', DEFAULT_BACKEND, { send }), { code: 'INVALID_URL' });
});

test('malformed response and offline are distinguishable', async () => {
  const url = 'https://example.com';
  const malformed = async () => new Response('<html>test-only</html>');
  await assert.rejects(predict(url, DEFAULT_BACKEND, { send: malformed }), { code: 'INVALID_RESPONSE' });
  const offline = async () => { throw new TypeError('test-only network error'); };
  await assert.rejects(predict(url, DEFAULT_BACKEND, { send: offline }), { code: 'NETWORK_ERROR' });
});

test('timeout aborts the configured backend request and supports retry', async () => {
  const send = async (_, { signal }) => {
    // Keep the test event loop alive while AbortSignal.timeout() is pending.
    const timer = setTimeout(() => {}, 100);
    try {
      await new Promise((_, reject) =>
        signal.addEventListener('abort', () => reject(signal.reason), { once: true }),
      );
    } finally {
      clearTimeout(timer);
    }
  };
  await assert.rejects(
    predict('https://example.com', DEFAULT_BACKEND, { timeoutMs: 5, send }),
    { code: 'TIMEOUT', retryable: true },
  );
});
