// Independent Windows/Web smoke. Only loopback HTTP is allowed; no prediction mocks.
const { chromium } = require('playwright');
const { spawn, spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const options = Object.fromEntries(process.argv.slice(2).map(x => {const i=x.indexOf('='); return [x.slice(0,i),x.slice(i+1)];}));
const root = path.resolve(options['--handoff-root'] || process.cwd());
const python = options['--python'] || path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const output = path.resolve(options['--output'] || 'week7-browser-qa.json');
fs.mkdirSync(path.dirname(output),{recursive:true});
const apiPort = Number(options['--api-port'] || 18767);
const webPort = Number(options['--web-port'] || 13007);
const apiUrl = `http://127.0.0.1:${apiPort}`;
const webUrl = `http://127.0.0.1:${webPort}`;
const web = path.join(root, 'apps/web');
const delay = ms => new Promise(resolve => setTimeout(resolve,ms));
const report = {schema_version:1, status:'running', handoff_revision:spawnSync('git',['-c',`safe.directory=${root.replaceAll('\\','/')}`,'rev-parse','HEAD'],{cwd:root,encoding:'utf8',windowsHide:true}).stdout.trim(), platform:process.platform, node:process.version, real_teacher:true, prediction_mocking:false, checks:[], page_errors:[], external_requests:[]};
let backend, server, browser, page;
let serverLog = '';
function startBackend(mode='teacher') {
  const env={...process.env, OMP_NUM_THREADS:'1', PYTHONIOENCODING:'utf-8', PHISHGUARD_BUNDLE_FORMAT:mode, PHISHGUARD_TEACHER_ROOT:root, PHISHGUARD_CORS_ORIGINS:webUrl};
  for(const k of ['PHISHGUARD_MODEL_BUNDLE','PHISHGUARD_MODEL_NAME','PHISHGUARD_MODEL_SHA256']) delete env[k];
  backend=spawn(python,['-m','uvicorn','phishguard_vn.api:app','--host','127.0.0.1','--port',String(apiPort),'--no-access-log'],{cwd:root,env,windowsHide:true,stdio:['ignore','pipe','pipe']});
  backend.on('error',e=>serverLog+=e.message);
  for(const s of [backend.stdout,backend.stderr]) s.on('data',b=>serverLog+=b.toString());
}
async function stop(child) {
  if(!child || child.exitCode!==null)return;
  const exited=new Promise(resolve=>child.once('exit',resolve));
  child.kill(); await Promise.race([exited,delay(5000)]);
  if(child.exitCode===null){child.kill('SIGKILL');await exited;}
}
async function health(ready) {
  for(let i=0;i<160;i++){
    if(backend.exitCode!==null)throw Error('Backend exited: '+serverLog.slice(-1500));
    try { const r=await fetch(apiUrl+'/health',{signal:AbortSignal.timeout(600)}); const b=await r.json(); if(r.status===200 && b.model_ready===ready)return b; }catch{}
    await delay(250);
  }
  throw Error('Backend readiness timeout: '+serverLog.slice(-1500));
}
async function text(value) {
  await page.waitForFunction(value=>{const h=document.querySelector('flt-semantics-host');return h && [h.textContent,...Array.from(h.querySelectorAll('[aria-label]'),e=>e.getAttribute('aria-label'))].join(' ').includes(value);},value);
}
async function enter(value) {
  const input=page.getByRole('textbox').first();
  const trace=[];
  const snapshot=async stage=>trace.push({stage,...await page.evaluate(()=>({active_tag:document.activeElement?.tagName,active_label:document.activeElement?.getAttribute('aria-label'),inputs:[...document.querySelectorAll('input')].map(x=>({value:x.value,label:x.getAttribute('aria-label')}))}))});
  await input.click(); await delay(150);
  await snapshot('focused');
  await page.keyboard.press(process.platform==='darwin'?'Meta+A':'Control+A'); await delay(100);
  await page.keyboard.press('Backspace'); await delay(150);
  await snapshot('cleared');
  await page.keyboard.insertText(value); await delay(150);
  await snapshot('inserted');
  await page.keyboard.press('Tab'); await delay(150);
  report.last_input_edit={value,trace};
  assert.equal(await input.inputValue(),value,'Flutter input must settle before submitting');
}
async function click(name) {await page.getByRole('button',{name,exact:true}).click();}
async function requestFromUi(endpoint,button,value) {
  if(value!==undefined)await enter(value);
  const waiting=page.waitForResponse(r=>r.url()===apiUrl+endpoint && r.request().method()==='POST');
  await click(button);const r=await waiting;return {status:r.status(),body:await r.json(),input:r.request().postDataJSON().url};
}
async function upload(name) {
  const chooser=page.waitForEvent('filechooser'); await click('Chọn ảnh QR'); await (await chooser).setFiles(path.join(web,'test/fixtures',name));
}
async function check(name,fn) {
  try{const details=await fn();report.checks.push({name,status:'passed',...details});console.log('PASS '+name);}
  catch(e){report.checks.push({name,status:'failed',error:e.message,input_trace:report.last_input_edit});process.exitCode=1;console.error('FAIL '+name+': '+e.message);}
}
(async()=>{
 try {
  startBackend();report.health=await health(true);
  assert.equal(report.health.model,'teacher-stacking-v2');
  server=spawn(python,['-m','http.server',String(webPort),'--bind','127.0.0.1','--directory',path.join(web,'build/web')],{cwd:root,windowsHide:true,stdio:'ignore'});
  for(let i=0;i<100;i++){try{if((await fetch(webUrl,{signal:AbortSignal.timeout(500)})).ok)break;}catch{}await delay(200);}
  const chrome=options['--chrome'] || (process.platform==='win32'?'C:/Program Files/Google/Chrome/Application/chrome.exe':undefined);
  browser=await chromium.launch({...(chrome?{executablePath:chrome}:{}),headless:true});report.browser=browser.version();
  const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
  await context.route('**/*',route=>{const u=new URL(route.request().url());if(['data:','blob:','about:'].includes(u.protocol)||u.hostname==='127.0.0.1')return route.continue();report.external_requests.push(u.origin);return route.abort();});
  page=await context.newPage();page.setDefaultTimeout(20000);page.on('pageerror',e=>report.page_errors.push(e.message));
  const posts=[];page.on('request',r=>{if(r.method()==='POST')posts.push({path:new URL(r.url()).pathname,data:r.postDataJSON()});});
  await page.goto(webUrl);await page.getByRole('textbox').first().waitFor();
  if(options['--scenario']==='qr-focus') {
    await enter('example.com');await upload('broken.png');await text('Không đọc được ảnh');
    await check('typing after QR error retains focus and replacement text',async()=>{await enter('https://example.com/replacement');});
    report.status=report.checks.some(x=>x.status==='failed')?'failed':'passed';return;
  }
  await check('URL → real Teacher; score above .5 uses locked threshold',async()=>{const r=await requestFromUi('/predict','Kiểm tra URL','https://example.com/Login?Q=A');assert.equal(r.status,200);assert.equal(r.body.label,'benign');assert.ok(r.body.score>.5 && r.body.score<r.body.threshold);assert.equal(r.body.threshold,.6945740700635259);await text('teacher-stacking-v2');return {response:r.body};});
  await check('selection and focus preserve rendered prediction',async()=>{const input=page.getByRole('textbox').first();await input.click();await page.keyboard.press('ArrowLeft');await page.keyboard.press('Tab');await text('teacher-stacking-v2');});
  await check('X-Ray identifies true domain and keeps ML result separate',async()=>{const r=await requestFromUi('/inspect','Brand Detector & URL X-Ray','https://vietcombank.com.vn.example.com/login');assert.equal(r.status,200);assert.equal(r.body.registrable_domain,'example.com');assert.deepEqual(r.body.official_brand_ids,[]);assert.ok(!('score' in r.body));await text('Domain đăng ký thực tế: example.com');await text('Quy tắc chuỗi URL, không phải dự đoán');return {reference_sha256:r.body.reference_sha256};});
  await check('real Teacher phishing response alongside rule evidence',async()=>{const r=await requestFromUi('/predict','Kiểm tra URL');assert.equal(r.status,200);assert.equal(r.body.label,'phishing');assert.ok(r.body.score>=r.body.threshold);await text('Domain đăng ký thực tế: example.com');return {response:r.body};});
  await check('official reference domain',async()=>{const r=await requestFromUi('/inspect','Brand Detector & URL X-Ray','https://www.vietcombank.com.vn/');assert.deepEqual(r.body.official_brand_ids,['vietcombank']);await text('Khớp domain tham chiếu');});
  await check('QR PNG preview, cancel without POST, retry and confirm real Teacher',async()=>{let n=posts.length;await upload('qr_url.png');await text('URL đọc từ QR — chưa gửi phân tích');assert.equal(posts.length,n);await click('Hủy');assert.equal(posts.length,n);await upload('qr_url.png');await text('URL đọc từ QR — chưa gửi phân tích');assert.equal(posts.length,n);const r=await requestFromUi('/predict','Xác nhận và phân tích');assert.equal(r.status,200);assert.equal(r.input,'https://example.com/Login?Q=A');await text('teacher-stacking-v2');});
  for(const ext of ['jpg','webp']) await check('actual QR '+ext+' decode before confirmation',async()=>{const n=posts.length;await upload('qr_url.'+ext);await text('URL đọc từ QR — chưa gửi phân tích');assert.equal(posts.length,n);await click('Hủy');});
  for(const [name,message] of [['broken.png','Không đọc được ảnh'],['no_qr.png','Không tìm thấy QR'],['qr_text.png','QR không chứa URL web hợp lệ'],['qr_bad_scheme.png','QR không chứa URL web hợp lệ'],['oversized_dimensions.png','Ảnh tối đa 4 megapixel']]) await check('reject QR fixture '+name+' without POST',async()=>{const n=posts.length;await upload(name);await text(message);assert.equal(posts.length,n);});
  await check('typing after QR error retains focus and replacement text',async()=>{await enter('https://example.com/replacement');});
  await check('backend rejects invalid port through UI',async()=>{const r=await requestFromUi('/predict','Kiểm tra URL','http://example.com:99999/');assert.equal(r.status,422);assert.equal(r.body.error.reason,'invalid_port');await text('URL không hợp lệ. Hãy kiểm tra');});
  for(const width of [768,375,320]) await check('X-Ray responsive '+width+'px',async()=>{await page.setViewportSize({width,height:950});const r=await requestFromUi('/inspect','Brand Detector & URL X-Ray','https://vietcombank.com.vn.example.com/login');assert.equal(r.status,200);await text('Domain đăng ký thực tế: example.com');const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);assert.equal(overflow,false);});
  await page.setViewportSize({width:1440,height:1000});
  await check('backend process stopped; error; restart; retry same page',async()=>{await enter('example.com');await stop(backend);await click('Kiểm tra URL');await text('Không kết nối được máy chủ');startBackend();await health(true);const r=await requestFromUi('/predict','Thử lại');assert.equal(r.status,200);await text('teacher-stacking-v2');});
  await check('degraded backend keeps inspection usable; Teacher returns503',async()=>{await stop(backend);startBackend('v2');await health(false);const r=await requestFromUi('/inspect','Brand Detector & URL X-Ray','example.com');assert.equal(r.status,200);const p=await requestFromUi('/predict','Kiểm tra URL');assert.equal(p.status,503);assert.equal(p.body.error.code,'MODEL_UNAVAILABLE');await text('Máy chủ chưa sẵn sàng để phân tích.');});
  assert.deepEqual(report.page_errors,[]);assert.deepEqual(report.external_requests,[]);
  report.post_endpoints=[...new Set(posts.map(p=>p.path))];report.status=report.checks.some(x=>x.status==='failed')?'failed':'passed';
 }catch(e){report.status='failed';report.error=e.stack;process.exitCode=1;console.error(e.message);}
 finally {if(page)await page.screenshot({path:output.replace(/\.json$/,'.png'),fullPage:true}).catch(()=>{});if(browser)await browser.close();await stop(backend);await stop(server);fs.mkdirSync(path.dirname(output),{recursive:true});fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({status:report.status,passed:report.checks.filter(x=>x.status==='passed').length,failed:report.checks.filter(x=>x.status==='failed').length,output}));}
})();
