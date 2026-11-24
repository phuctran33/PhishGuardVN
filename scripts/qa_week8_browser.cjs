/* Real Teacher smoke from a release build. See reports/week8_9_hung_verification.md. */
const assert = require('node:assert/strict');
const { execFileSync, spawn } = require('node:child_process');
const { once } = require('node:events');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const root = path.resolve(__dirname, '..');
const out = process.env.PGVN_EVIDENCE_DIR || path.join(root, 'reports/figures/week8_9');
const python = process.env.PGVN_PYTHON || 'python3.11';
const api = 'http://127.0.0.1:18380';
const web = 'http://127.0.0.1:3308';
const good = 'https://www.vietcombank.com.vn/';
const demoBrand = 'https://napas.com.vn/';
const flagged = 'https://vietcombank-verify.example.net/login/secure?mode=demo';
const release = JSON.parse(fs.readFileSync(path.join(root, 'configs/teacher_lock.json')));
const temp = fs.mkdtempSync('/tmp/pgvn-w89-browser-');
const results = [];
const unexpectedNetwork = new Set();
const children = new Set();

function server(args, env = {}) {
  const child = spawn(python, args, {
    cwd: root,
    stdio: ['ignore', 'ignore', 'inherit'],
    env: { ...process.env, ...env },
  });
  children.add(child);
  child.once('exit', () => children.delete(child));
  return child;
}

async function stop(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const exited = once(child, 'exit');
  child.kill('SIGTERM');
  await exited;
}

async function poll(url, accepted) {
  for (let i = 0; i < 80; i++) {
    try {
      const response = await fetch(url);
      if (response.ok && await accepted(response)) return;
    } catch {
      // Startup may be waiting to bind the port.
    }
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  throw new Error('Service did not reach expected state: ' + url);
}

async function startBackend(ready = true) {
  const child = server(['-m', 'uvicorn', 'phishguard_vn.api:app', '--host', '127.0.0.1',
    '--port', '18380', '--no-access-log'], {
    PHISHGUARD_BUNDLE_FORMAT: 'teacher',
    PHISHGUARD_TEACHER_ROOT: ready ? root : temp,
    PHISHGUARD_CORS_ORIGINS: web,
    PHISHGUARD_MODEL_BUNDLE: '',
    PHISHGUARD_MODEL_NAME: '',
    PHISHGUARD_MODEL_SHA256: '',
    OMP_NUM_THREADS: '1',
  });
  await poll(api + '/health', async r => {
    const h = await r.json();
    if (h.model_ready !== ready) return false;
    if (ready) {
      assert.equal(h.model, release.model_version);
      assert.equal(h.artifact_sha256, release.bundle.sha256);
    }
    return true;
  });
  return child;
}

function record(name, detail = {}) {
  results.push({ check: name, result: 'pass', ...detail });
  console.log('PASS', name);
}

async function snapshot(page, basename) {
  const location = path.join(out, basename + '.png');
  await page.screenshot({ path: location });
}

async function restrict(context) {
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (!['http:', 'https:'].includes(url.protocol) || [api, web].includes(url.origin)) {
      return route.continue();
    }
    unexpectedNetwork.add(url.origin);
    return route.abort();
  });
}

function button(page, name) {
  return page.getByRole('button', { name, exact: true }).first();
}

async function enterUrl(page, value) {
  const field = page.getByRole('textbox', { name: /URL cần kiểm tra/ }).first();
  await field.click();
  await page.waitForTimeout(180);
  const editor = page.locator('input:focus, textarea:focus').first();
  if (!(await editor.inputValue()) && value) {
    await page.keyboard.insertText(value);
  } else {
    await editor.fill(value);
  }
  if (value) await visible(page, value);
}

async function post(endpoint, url) {
  const response = await fetch(api + endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  });
  return { status: response.status, body: await response.json() };
}

async function visible(page, text, present = true) {
  // CanvasKit can combine adjacent Text widgets in a single accessible name.
  // Inspect the live accessibility tree rather than assume DOM text nodes.
  const deadline = Date.now() + 13000;
  let snapshot;
  do {
    snapshot = await page.locator('body').ariaSnapshot();
    const found = text instanceof RegExp ? text.test(snapshot) : snapshot.includes(text);
    if (found === present) return;
    await page.waitForTimeout(100);
  } while (Date.now() < deadline);
  throw new Error('Unexpected accessibility state for ' + text + '\n' + snapshot);
}

async function webSmoke(backend) {
  const browser = await chromium.launch({ channel: 'chromium' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1120 } });
  const errors = [];
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.name));
  await restrict(context);
  try {
    await page.goto(web);
    await visible(page, 'API sẵn sàng');
    await snapshot(page, 'web-input');
    await enterUrl(page, demoBrand);
    await button(page, 'Kiểm tra URL').click();
    const prediction = await post('/predict', demoBrand);
    await visible(page, 'Nhãn mô hình: benign');
    assert.equal(prediction.body.threshold, release.threshold);
    await visible(page, 'Quy tắc backend: score ≥ ' + release.threshold);
    await button(page, 'Brand Detector & URL X-Ray').click();
    const inspection = await post('/inspect', demoBrand);
    assert.equal(inspection.body.catalog_status, 'expanded');
    assert.deepEqual(inspection.body.official_brand_ids, ['napas']);
    await visible(page, inspection.body.catalog_version + ' · ' + inspection.body.reference_brands + ' thương hiệu');
    await visible(page, /Khớp domain chính thức · NAPAS/);
    await visible(page, /Domain đăng ký thực tế: napas\.com\.vn/);
    await page.mouse.move(1020, 780);
    await page.mouse.wheel(0, 560);
    await page.waitForTimeout(280);
    await snapshot(page, 'web-brand-xray');
    record('Web real released Teacher + expanded Brand Detector and X-Ray');

    await button(page, 'Tìm ca phishing tương tự').click();
    await visible(page, 'Tra cứu lịch sử chưa sẵn sàng. Vui lòng thử lại.');
    await button(page, 'Thử lại tra cứu').click();
    await visible(page, 'Tra cứu lịch sử chưa sẵn sàng. Vui lòng thử lại.');
    await visible(page, 'Nhãn mô hình: benign');
    await visible(page, 'BRAND DETECTOR · QUY TẮC');
    record('Web #36 missing endpoint, retry preserves Teacher and inspection', { upstream: 'HTTP 404' });

    await enterUrl(page, flagged);
    await visible(page, 'BRAND DETECTOR · QUY TẮC', false);
    await button(page, 'Kiểm tra URL').click();
    await visible(page, 'Nhãn mô hình: phishing');
    await snapshot(page, 'web-phishing');
    record('Web valid phishing response with changed input');

    for (const [file, text] of [
      ['broken.png', 'Không đọc được ảnh.'],
      ['no_qr.png', 'Không tìm thấy QR đọc được.'],
      ['qr_text.png', 'QR không chứa URL web hợp lệ.'],
      ['qr_bad_scheme.png', 'QR không chứa URL web hợp lệ.'],
    ]) {
      const choose = page.waitForEvent('filechooser');
      await button(page, 'Chọn ảnh QR').click();
      await (await choose).setFiles(path.join(root, 'apps/web/test/fixtures', file));
      await visible(page, text);
      await button(page, 'Chọn ảnh khác').waitFor();
      record('Web QR error · ' + file);
    }
    const requests = [];
    page.on('request', req => { if (req.method() === 'POST' && req.url() === api + '/predict') requests.push(req); });
    const choose = page.waitForEvent('filechooser');
    await button(page, 'Chọn ảnh QR').click();
    await (await choose).setFiles(path.join(root, 'apps/web/test/fixtures/qr_url.png'));
    await visible(page, 'URL đọc từ QR — chưa gửi phân tích');
    assert.equal(requests.length, 0);
    await snapshot(page, 'web-qr-preview');
    await Promise.all([
      page.waitForResponse(r => r.url() === api + '/predict' && r.status() === 200),
      button(page, 'Xác nhận và phân tích').click(),
    ]);
    assert.equal(requests.length, 1);
    record('Web QR file decodes locally and submits only after confirmation');

    for (const width of [768, 375, 320]) {
      await page.setViewportSize({ width, height: 880 });
      await enterUrl(page, demoBrand);
      await button(page, 'Brand Detector & URL X-Ray').click();
      await visible(page, 'BRAND DETECTOR · QUY TẮC');
      await button(page, 'Kiểm tra URL').click();
      await visible(page, 'Nhãn mô hình: benign');
      const overflow = await page.evaluate(() =>
        document.documentElement.scrollWidth > window.innerWidth);
      assert.equal(overflow, false);
      if (width === 375) await snapshot(page, 'web-mobile');
      record('Web viewport ' + width + 'px responds without horizontal overflow');
    }

    await page.setViewportSize({ width: 960, height: 960 });
    await page.reload();
    await visible(page, 'API sẵn sàng');
    await button(page, 'Kiểm tra URL').click();
    await visible(page, 'Vui lòng nhập một URL.');
    await page.reload();
    await visible(page, 'API sẵn sàng');
    await enterUrl(page, 'https://example.com:bad/path');
    await button(page, 'Kiểm tra URL').click();
    await visible(page, /URL không hợp lệ/);
    record('Web empty and invalid-port errors');

    await page.route(api + '/predict', async route => {
      if (route.request().method() !== 'POST') return route.continue();
      return route.fulfill({ response: await route.fetch(), body: 'test-only invalid JSON' });
    });
    await enterUrl(page, good);
    await button(page, 'Kiểm tra URL').click();
    await visible(page, 'Phản hồi máy chủ chưa đúng API contract.');
    await page.unroute(api + '/predict');
    record('Web malformed response (HTTP fault injection)');

    await stop(backend);
    await button(page, 'Thử lại').click();
    await visible(page, 'Không kết nối được máy chủ. Kiểm tra kết nối rồi thử lại.');
    await snapshot(page, 'web-offline');
    backend = await startBackend(false);
    await button(page, 'Thử lại').click();
    await visible(page, 'Máy chủ chưa sẵn sàng để phân tích. Vui lòng thử lại sau.');
    await button(page, 'Brand Detector & URL X-Ray').click();
    await visible(page, 'BRAND DETECTOR · QUY TẮC');
    record('Web degraded Teacher 503 with inspection available');
    await stop(backend);
    backend = await startBackend();
    await button(page, 'Thử lại').click();
    await visible(page, 'Nhãn mô hình: benign');
    record('Web real shutdown, restart and retry in the same tab');
    assert.deepEqual(errors, []);
    record('Web release without JavaScript errors');
    return backend;
  } finally {
    await browser.close();
  }
}

// Use native events to open Chromium's actual macOS link context menu. No
// calls to the worker listener or /predict are substituted for a menu click.
const nativeCode = String.raw`
import ctypes as c
import sys
import time
cg=c.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
cf=c.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
cg.CGPreflightPostEventAccess.restype=c.c_bool
assert cg.CGPreflightPostEventAccess(), "macOS accessibility permission is required"
class Point(c.Structure):
    _fields_=[("x",c.c_double),("y",c.c_double)]
cg.CGEventCreateMouseEvent.argtypes=[c.c_void_p,c.c_uint32,Point,c.c_uint32]
cg.CGEventCreateMouseEvent.restype=c.c_void_p
cg.CGEventCreateKeyboardEvent.argtypes=[c.c_void_p,c.c_uint16,c.c_bool]
cg.CGEventCreateKeyboardEvent.restype=c.c_void_p
cg.CGEventPost.argtypes=[c.c_uint32,c.c_void_p]
cf.CFRelease.argtypes=[c.c_void_p]
def emit(ev):
    cg.CGEventPost(0,ev)
    cf.CFRelease(ev)
    time.sleep(.09)
x,y=map(float,sys.argv[1:])
for event in (3,4):
    emit(cg.CGEventCreateMouseEvent(None,event,Point(x,y),1))
time.sleep(.32)
for key in (40,36):
    for down in (True,False):
        emit(cg.CGEventCreateKeyboardEvent(None,key,down))
`;

async function extensionSmoke(backend) {
  assert.equal(process.platform, 'darwin', 'macOS native interaction is required for this script');
  const extension = path.join(root, 'apps/extension');
  const profile = path.join(temp, 'profile');
  const context = await chromium.launchPersistentContext(profile, {
    channel: 'chromium', headless: false, viewport: null,
    args: ['--disable-extensions-except=' + extension, '--load-extension=' + extension,
      '--window-position=42,55', '--window-size=900,700', '--no-first-run'],
  });
  try {
    await restrict(context);
    const worker = context.serviceWorkers()[0] || await context.waitForEvent('serviceworker');
    const origin = worker.url().split('/').slice(0, 3).join('/');
    const { manifest, origins } = await worker.evaluate(async () => ({
      manifest: chrome.runtime.getManifest(), origins: (await chrome.permissions.getAll()).origins,
    }));
    assert.equal(manifest.manifest_version, 3);
    assert.deepEqual(origins, ['http://127.0.0.1/*']);
    const page = context.pages()[0];
    const processes = execFileSync('/bin/ps', ['-axo', 'pid,command'], { encoding: 'utf8' });
    const processLine = processes.split('\n').find(line =>
      line.includes('--user-data-dir=' + profile) &&
      line.includes(chromium.executablePath()) && !line.includes('--type='));
    assert.ok(processLine, 'Could not identify the isolated Chrome process');
    const browserPid = Number(processLine.trim().split(/\s+/)[0]);
    await page.goto(origin + '/options.html');
    await page.locator('#backend').fill(api);
    await page.locator('#save').click();
    await visible(page, 'Đã lưu địa chỉ backend.');
    await snapshot(page, 'extension-settings');
    record('Chrome installed unpacked MV3 and configured backend through the options UI');

    async function selectLink(url) {
      await context.route(web + '/extension-link', route => route.fulfill({
        contentType: 'text/html',
        body: '<title>PhishGuardVN local link fixture</title><body style="margin:60px">' +
          '<a id="fixture" style="display:block;width:380px;font:24px system-ui">Liên kết kiểm thử</a>',
      }));
      await page.goto(web + '/extension-link');
      await page.locator('#fixture').evaluate((a, href) => { a.href = href; }, url);
      const selected = await page.locator('#fixture').evaluate(a => a.href);
      await page.bringToFront();
      const bounds = await page.locator('#fixture').boundingBox();
      let result;
      for (let attempt = 0; attempt < 3 && !result; attempt++) {
        const raiseWindow = [
          'tell application "System Events"',
          'tell (first application process whose unix id is ' + browserPid + ')',
          'set frontmost to true',
          'perform action "AXRaise" of (first window whose name contains "PhishGuardVN local link fixture")',
          'end tell',
          'end tell',
        ].join('\n');
        execFileSync('/usr/bin/osascript', ['-e', raiseWindow]);
        await page.waitForTimeout(360);
        const coords = await page.evaluate(() => ({
          x: screenX, y: screenY, chromeHeight: outerHeight - innerHeight,
        }));
        const popup = context.waitForEvent('page', { timeout: 4000 });
        execFileSync(python, ['-c', nativeCode, String(coords.x + bounds.x + 55),
          String(coords.y + coords.chromeHeight + bounds.y + 12)]);
        try {
          result = await popup;
        } catch (error) {
          if (attempt === 2) throw error;
          await page.keyboard.press('Escape');
        }
      }
      await result.waitForURL(origin + '/result.html', { timeout: 6000 });
      assert.equal(page.url(), web + '/extension-link');
      await context.unroute(web + '/extension-link');
      return { result, selected };
    }

    const requests = [];
    context.on('request', req => {
      if (req.method() === 'POST' && req.url() === api + '/predict') requests.push(req.postDataJSON());
    });
    for (const [url, label] of [[good, 'benign'], [flagged, 'phishing']]) {
      const before = requests.length;
      const { result, selected } = await selectLink(url);
      await result.locator('#label').waitFor({ state: 'visible' });
      const expected = await post('/predict', selected);
      assert.equal(expected.body.label, label);
      assert.equal(expected.body.threshold, release.threshold);
      assert.equal(await result.locator('#label').textContent(), expected.body.label);
      assert.equal(await result.locator('#model').textContent(), expected.body.model);
      assert.equal(Number(await result.locator('#score').textContent()), expected.body.score);
      assert.equal(Number(await result.locator('#threshold').textContent()), expected.body.threshold);
      assert.equal(await result.locator('#hostname').textContent(), 'Hostname: ' + new URL(selected).hostname);
      assert.deepEqual(requests.slice(before), [{ url: selected }]);
      assert.equal((await result.locator('body').textContent()).includes('?mode=demo'), false);
      const stored = await worker.evaluate(() => chrome.storage.local.get(null));
      assert.deepEqual(stored, { backend: api });
      await snapshot(result, 'extension-' + label);
      record('Chrome native right-click · ' + label + ' · direct API label/score/threshold and exact selected URL',
        { label, score: expected.body.score, threshold: expected.body.threshold });
      await result.close();
    }

    const rejects = [
      ['ftp://example.com/archive', 'Chỉ kiểm tra liên kết HTTP hoặc HTTPS.', false],
      ['https://no-domain.invalid/', 'Máy chủ từ chối URL. Kiểm tra tên miền và cổng.', true],
    ];
    for (const [url, message, sends] of rejects) {
      const before = requests.length;
      const { result, selected } = await selectLink(url);
      await visible(result, message);
      assert.deepEqual(requests.slice(before), sends ? [{ url: selected }] : []);
      await result.close();
      record(sends ? 'Chrome real API 422' : 'Chrome unsupported scheme does not call backend');
    }

    await stop(backend);
    const { result } = await selectLink(good);
    await visible(result, 'Không kết nối được backend. Kiểm tra cấu hình hoặc thử lại.');
    await snapshot(result, 'extension-offline');
    backend = await startBackend(false);
    await result.locator('#retry').click();
    await visible(result, 'Teacher chưa sẵn sàng. Hãy thử lại sau.');
    await stop(backend);
    backend = await startBackend();
    for (const [status, message] of [
      [500, 'Máy chủ gặp lỗi khi phân tích. Hãy thử lại.'],
      [200, 'Phản hồi không đúng API contract.'],
    ]) {
      await context.route(api + '/predict', route => route.fulfill({
        status, body: 'test-only invalid prediction response',
      }));
      await result.locator('#retry').click();
      await visible(result, message);
      assert.equal(await result.locator('#label').isVisible(), false);
      await context.unroute(api + '/predict');
      record('Chrome HTTP fault injection · ' + status);
    }

    await context.route(api + '/predict', async route => {
      await new Promise(resolve => setTimeout(resolve, 8500));
      await route.abort().catch(() => {});
    });
    await result.locator('#retry').click();
    await visible(result, 'Máy chủ phản hồi quá chậm. Hãy thử lại.');
    assert.equal(await result.locator('#label').isVisible(), false);
    await context.unroute(api + '/predict');
    record('Chrome timeout (delayed transport)');
    await result.locator('#retry').click();
    await result.locator('#label').waitFor({ state: 'visible' });
    assert.equal(await result.locator('#label').textContent(), 'benign');
    record('Chrome real backend offline, degraded Teacher 503, restart and retry');
    return backend;
  } finally {
    await context.close();
  }
}

async function main() {
  fs.mkdirSync(out, { recursive: true });
  const backend = await startBackend();
  server(['-m', 'http.server', '3308', '--bind', '127.0.0.1', '--directory', 'apps/web/build/web']);
  await poll(web, r => r.ok);
  let live = await webSmoke(backend);
  live = await extensionSmoke(live);
  assert.equal(unexpectedNetwork.size, 0, [...unexpectedNetwork].join(', '));
  record('No browser requests to inspected links or external origins');
  const version = execFileSync(chromium.executablePath(), ['--version'], { encoding: 'utf8' }).trim();
  const report = {
    revision: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(),
    browser: version,
    platform: process.platform + ' ' + process.arch,
    model: release.model_version,
    artifact_sha256: release.bundle.sha256,
    threshold: release.threshold,
    checks: results,
    live_similar_results: false,
  };
  fs.writeFileSync(path.join(out, 'browser_smoke.json'), JSON.stringify(report, null, 2) + '\n');
  await stop(live);
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
}).finally(async () => {
  await Promise.all([...children].map(stop));
  fs.rmSync(temp, { recursive: true, force: true });
});
