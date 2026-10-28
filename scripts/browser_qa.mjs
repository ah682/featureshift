import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const serviceUrl = (process.env.FEATURESHIFT_URL ?? 'http://127.0.0.1:8765').replace(/\/$/, '');
const debugUrl = (process.env.CHROME_DEBUG_URL ?? 'http://127.0.0.1:9227').replace(/\/$/, '');
const artifacts = path.join(root, '.featureshift/verification');
await fs.mkdir(artifacts, {recursive:true});
// Use a fresh tab in the isolated debugger instance supplied by the caller.
const target = await (await fetch(`${debugUrl}/json/new?about:blank`, {method:'PUT'})).json();
if (!target.webSocketDebuggerUrl) throw new Error('Could not create an isolated Chrome page target');
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject) => { ws.addEventListener('open', resolve, {once:true}); ws.addEventListener('error', reject, {once:true}); });
let seq = 0;
const pending = new Map();
const errors = [];
const consoleErrors = [];
const result = {checked_at: new Date().toISOString(), url:serviceUrl, checks:[], widths:[], screenshots:[], downloads:[], errors, consoleErrors};
ws.addEventListener('message', event => {
  const message = JSON.parse(event.data);
  if (message.id && pending.has(message.id)) {
    const {resolve,reject} = pending.get(message.id); pending.delete(message.id);
    message.error ? reject(new Error(JSON.stringify(message.error))) : resolve(message.result);
  }
  if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails);
  if (message.method === 'Runtime.consoleAPICalled' && message.params.type === 'error') consoleErrors.push(message.params.args.map(arg=>arg.value ?? arg.description));
});
const cdp = (method,params={}) => new Promise((resolve,reject) => { const id=++seq; pending.set(id,{resolve,reject}); ws.send(JSON.stringify({id,method,params})); });
const evaluate = async (expression) => {
  const response=await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  if(response.exceptionDetails) throw new Error(JSON.stringify(response.exceptionDetails));
  return response.result.value;
};
const pause = ms => new Promise(r=>setTimeout(r,ms));
const waitFor = async (expression,label,timeout=35000) => {
  const deadline=Date.now()+timeout;
  do { if(await evaluate(expression)) return; await pause(150); } while(Date.now()<deadline);
  throw new Error(`Timed out waiting for ${label}`);
};
const assert = (truth,label,detail) => { result.checks.push({label,passed:Boolean(truth),detail}); if(!truth) throw new Error(`${label}: ${JSON.stringify(detail)}`); };
const screenshot = async (name,full=false) => {
  if(full) await evaluate(`window.scrollTo({top:0,left:0,behavior:'instant'});document.activeElement?.blur()`);
  // Wait for requested smooth scrolling to settle before capturing fixed elements.
  await evaluate(`new Promise(resolve=>{let previous=scrollY,stable=0;const deadline=performance.now()+1500;function frame(){stable=scrollY===previous?stable+1:0;previous=scrollY;if(stable>=4||performance.now()>deadline)resolve();else requestAnimationFrame(frame)}requestAnimationFrame(frame)})`);
  const metrics=await cdp('Page.getLayoutMetrics');
  const image=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:full, ...(full ? {clip:{x:0,y:0,width:metrics.cssContentSize.width,height:metrics.cssContentSize.height,scale:1}} : {})});
  const destination=path.join(artifacts,name); await fs.writeFile(destination,Buffer.from(image.data,'base64')); result.screenshots.push(destination);
};
const resize = async (width,height) => { await cdp('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false}); await pause(75); };
const measure = async (width) => {
  const data=await evaluate(`({width:innerWidth,documentWidth:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth,viewportContentWidth:document.documentElement.clientWidth,overflow:document.documentElement.scrollWidth>document.documentElement.clientWidth,heading:document.querySelector('h1').textContent,report:document.querySelector('#report-heading').textContent})`);
  result.widths.push(data); assert(!data.overflow,`No horizontal page overflow at ${width}px`,data);
};
try {
  await cdp('Page.enable'); await cdp('Runtime.enable');
  await cdp('Network.enable'); await cdp('Network.setCacheDisabled', {cacheDisabled: true});
  await resize(1440,1000);
  await cdp('Page.navigate',{url:result.url});
  await waitFor(`document.querySelector('#report-heading')?.textContent && !document.querySelector('#case-select')?.disabled`,'seeded preflight');
  await waitFor(`document.querySelector('#report-heading')?.textContent === 'Object dtype selector'`,'selector report');
  assert(await evaluate(`document.querySelector('.input-mode[disabled]')?.disabled`),'Arbitrary upload is visibly disabled');
  const baseline = await evaluate(`({title:document.querySelector('#report-heading').textContent,metrics:[...document.querySelectorAll('.summary-number')].map(e=>e.textContent),findings:document.querySelectorAll('.finding').length})`);
  assert(baseline.metrics[0] === '2' && baseline.metrics[1] === '2','Seeded report shows actual executed differences and contract violations',baseline);
  await measure(1440); await screenshot('ui-desktop.png');
  const selectorId = await evaluate(`new URL(document.querySelector('#download-options a').href).pathname.split('/')[3]`);
  await evaluate(`document.querySelector('#tab-execution').click()`);
  assert(await evaluate(`!document.querySelector('#panel-execution').hidden && document.querySelectorAll('.dataframe').length > 0`),'Execution tab displays structured DataFrame output');
  await screenshot('ui-execution.png');
  await evaluate(`document.querySelector('#tab-source').click()`);
  assert(await evaluate(`document.querySelector('#panel-source').textContent.includes('Declared output contract') && document.querySelectorAll('#panel-source .probe-card').length > 0`),'Source tab includes contract, probes and reviewable patch');
  await evaluate(`document.querySelector('#tab-evidence').click();document.querySelector('#tab-evidence').focus()`);
  assert(await evaluate(`document.querySelectorAll('#panel-evidence .evidence-card').length > 0 && document.querySelector('#panel-evidence').textContent.includes('Source provenance')`),'Evidence tab retains source provenance and passage offsets');
  await cdp('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39});
  await cdp('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39});
  assert(await evaluate(`document.querySelector('#tab-source').getAttribute('aria-selected')==='true' && document.activeElement.id==='tab-source'`),'Keyboard arrow navigation switches report tabs and focus');
  await evaluate(`document.querySelector('#tab-findings').click();document.activeElement?.blur();window.scrollTo(0,0)`);
  for(const [width,height] of [[1024,900],[768,1000],[390,844],[320,780]]) {
    await resize(width,height); await measure(width);
    if(width===390) { await screenshot('ui-mobile.png'); await screenshot('ui-mobile-full.png',true); }
  }
  await resize(1440,1000);
  await evaluate(`document.querySelector('#case-select').value='numeric';document.querySelector('#case-select').dispatchEvent(new Event('change',{bubbles:true}));document.querySelector('#run-button').click()`);
  await waitFor(`!document.querySelector('#run-progress').hidden`,'visible running state');
  assert(await evaluate(`document.querySelector('#run-button').disabled && document.querySelector('#case-select').disabled`),'Running state prevents duplicate execution');
  await waitFor(`document.querySelector('#report-heading').textContent==='Spend per visit' && document.querySelector('#run-progress').hidden`,'unaffected numeric run',300000);
  assert(await evaluate(`document.querySelector('.equivalent-state')?.textContent.includes('No observed differences') && [...document.querySelectorAll('.summary-number')].every(e=>e.textContent==='0')`),'New unaffected run reports equivalent normalized output and no findings');
  await screenshot('ui-equivalent.png');
  const intentionalRun = await evaluate(`fetch('/api/runs').then(r=>r.json()).then(runs=>runs.find(r=>r.case_id==='intentional').id)`);
  await evaluate(`document.querySelector('[data-run="${intentionalRun}"]').click()`);
  await waitFor(`document.querySelector('#report-heading').textContent==='Adopt the string dtype'`,'intentional audit report');
  assert(await evaluate(`document.querySelectorAll('.accepted-note').length > 0 && document.querySelector('#panel-findings').textContent.includes('audit record')`),'Intentional change preserves accepted findings and audit text');
  await screenshot('ui-intentional.png');
  await evaluate(`document.querySelector('#case-select').value='selector';document.querySelector('#case-select').dispatchEvent(new Event('change',{bubbles:true}));document.querySelector('#run-button').click()`);
  await waitFor(`!document.querySelector('#run-progress').hidden`,'new selector running');
  await waitFor(`document.querySelector('#report-heading').textContent==='Object dtype selector' && document.querySelector('#run-progress').hidden`,'new selector result',300000);
  await evaluate(`document.querySelector('.accept-toggle').click()`);
  await evaluate(`document.querySelector('.accept-box:not([hidden]) textarea').value='UI verification: accepting this constructed fixture change to verify the local audit trail. Not a production approval.';document.querySelector('.accept-box:not([hidden])').requestSubmit()`);
  await waitFor(`document.querySelectorAll('.accepted-note').length > 0`,'saved acceptance audit');
  assert(await evaluate(`document.querySelector('#panel-findings').textContent.includes('UI verification: accepting this constructed fixture') && document.querySelectorAll('.finding-compare').length > 0`),'Local review acceptance persists its reason and retains before/after evidence');
  const reportId=await evaluate(`new URL(document.querySelector('#download-options a').href).pathname.split('/')[3]`);
  result.acceptance_run=reportId;
  const acceptanceAudit=await evaluate(`fetch('/api/runs/${reportId}').then(r=>r.json()).then(r=>({accepted:r.findings.filter(f=>f.accepted).length,events:r.events.filter(e=>e.kind==='finding_accepted').length}))`);
  assert(acceptanceAudit.accepted > 0 && acceptanceAudit.events > 0,'Acceptance is persisted as an audit event',acceptanceAudit);
  await fs.mkdir(path.join(artifacts,'downloads'),{recursive:true});
  const filesBeforeDownloads = new Set(await fs.readdir(path.join(artifacts,'downloads')));
  await cdp('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:path.join(artifacts,'downloads'),eventsEnabled:true});
  for(const suffix of ['report.json','report.html','regression_test.py']) {
    const response=await evaluate(`fetch('/api/runs/${reportId}/${suffix}').then(async r=>({status:r.status,type:r.headers.get('content-type'),bytes:(await r.text()).length}))`);
    assert(response.status===200 && response.bytes>0,`Download endpoint ${suffix} returns an artifact`,response);
    await evaluate(`document.querySelector('.download-menu').open=true;document.querySelector('#download-options a[href$="${suffix}"]').click()`);
    result.downloads.push({suffix,...response});
  }
  let downloaded=[];
  for(let attempt=0;attempt<30;attempt++){
    downloaded=(await fs.readdir(path.join(artifacts,'downloads'))).filter(name=>!filesBeforeDownloads.has(name) && !name.endsWith('.crdownload'));
    if(downloaded.length>=3) break;
    await pause(100);
  }
  assert(downloaded.length >= 3,'Export controls trigger all three file downloads',downloaded);

  // Hold successful responses after the server has completed its work, then navigate.
  await evaluate(`
    window.qaNativeFetch = window.fetch;
    window.fetch = async (url, options) => {
      const response = await window.qaNativeFetch(url, options);
      if (String(url).endsWith('/accept')) {
        const body = await response.json();
        window.qaWaiting = true;
        await new Promise(resolve => { window.qaRelease = resolve; });
        window.qaReturned = true;
        return {ok: true, json: async () => body};
      }
      return response;
    };
    document.querySelector('.accept-toggle').click();
    document.querySelector('.accept-box:not([hidden]) textarea').value = 'Delayed browser regression review';
    document.querySelector('.accept-box:not([hidden])').requestSubmit();
  `);
  await waitFor(`window.qaWaiting`, 'acceptance response held');
  await evaluate(`document.querySelector('[data-run="${intentionalRun}"]').click()`);
  await waitFor(`document.querySelector('#download-options a').href.includes('${intentionalRun}')`, 'different report selected');
  await evaluate(`window.qaRelease()`);
  await waitFor(`window.qaReturned`, 'acceptance response returned');
  const acceptanceKeptSelection = await evaluate(`document.querySelector('#download-options a').href.includes('${intentionalRun}')`);
  await evaluate(`window.fetch = window.qaNativeFetch`);

  await evaluate(`
    window.qaWaiting = false; window.qaReturned = false;
    window.fetch = async (url, options) => {
      if (url === '/api/runs' && options?.method === 'POST') {
        return {ok: true, json: async () => ({id: 'delayed-browser-run', status: 'queued'})};
      }
      if (url === '/api/runs/delayed-browser-run') {
        const report = await window.qaNativeFetch('/api/runs/${reportId}').then(r => r.json());
        window.qaWaiting = true;
        await new Promise(resolve => { window.qaRelease = resolve; });
        window.qaReturned = true;
        return {ok: true, json: async () => report};
      }
      return window.qaNativeFetch(url, options);
    };
    document.querySelector('#run-button').click();
  `);
  await waitFor(`window.qaWaiting`, 'completion response held');
  await evaluate(`document.querySelector('[data-run="${intentionalRun}"]').click()`);
  await waitFor(`document.querySelector('#download-options a').href.includes('${intentionalRun}')`, 'report selected during execution');
  await evaluate(`window.qaRelease()`);
  await waitFor(`window.qaReturned && document.querySelector('#run-progress').hidden`, 'background execution completed');
  const completionKeptSelection = await evaluate(`document.querySelector('#download-options a').href.includes('${intentionalRun}')`);
  await evaluate(`window.fetch = window.qaNativeFetch`);
  assert(acceptanceKeptSelection && completionKeptSelection, 'Delayed acceptance and completion preserve the selected report', {acceptanceKeptSelection, completionKeptSelection});

  await evaluate(`document.querySelector('[data-run="${selectorId}"]').click()`);
  await waitFor(`document.querySelector('#download-options a')?.href.includes('${selectorId}')`,'restored seeded selector');
  await evaluate(`window.scrollTo(0,0)`); await screenshot('ui-desktop-final.png');
  assert(errors.length===0,'No page JavaScript exceptions',errors);
  assert(consoleErrors.length===0,'No browser console errors',consoleErrors);
  result.passed=true;
} catch(error) {
  result.passed=false; result.failure=error.stack;
  try { await screenshot('ui-failure.png'); } catch {}
} finally {
  await fs.writeFile(path.join(artifacts,'ui-checks.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify(result,null,2)); ws.close();
  if(!result.passed) process.exitCode=1;
}
