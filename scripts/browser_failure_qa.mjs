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
  await cdp('Page.navigate',{url:serviceUrl});
  await waitFor(`document.querySelector('#report-heading')?.textContent && !document.querySelector('#case-select')?.disabled`,'seeded preflight');
  const runCase=async(id,title)=>{
    await evaluate(`document.querySelector('#case-select').value='${id}';document.querySelector('#case-select').dispatchEvent(new Event('change',{bubbles:true}));document.querySelector('#run-button').click()`);
    await waitFor(`!document.querySelector('#run-progress').hidden`,'running '+id);
    await waitFor(`document.querySelector('#report-heading').textContent===${JSON.stringify(title)} && document.querySelector('#run-progress').hidden`,'completed '+id,300000);
  };
  await runCase('install-failure','Dependency setup failure stays an environment error');
  assert(await evaluate(`document.querySelector('#report-notice').textContent.includes('Execution is incomplete') && !document.querySelector('#report-notice').textContent.includes('Repeatability check failed') && document.querySelectorAll('.accept-toggle').length===0`),'Failed installation is an execution error with no false stochastic claim or acceptance action');
  assert(await evaluate(`[...document.querySelectorAll('.summary-number')].map(e=>e.textContent).join(',')==='0,0,0,1'`),'Environment failure is not counted as a semantic difference');
  await screenshot('ui-environment-error.png');
  await runCase('wrong-version','Wrong-version evidence is withheld');
  assert(await evaluate(`document.querySelector('#report-notice').textContent.includes('insufficient-evidence') && document.querySelectorAll('.summary-number')[2].textContent==='0'`),'Wrong-version evidence produces visible uncertainty and no documented-change claim');
  await evaluate(`document.querySelector('#tab-evidence').click()`);
  assert(await evaluate(`document.querySelector('#panel-evidence').textContent.includes('No supporting documentation recorded')`),'Missing evidence displays unavailable-source state');
  await evaluate(`document.querySelector('#tab-findings').click()`);
  await runCase('probe-timeout','Generated probe is terminated at its deadline');
  assert(await evaluate(`document.querySelector('#report-notice').textContent.includes('Execution is incomplete') && document.querySelector('#panel-findings').textContent.includes('Probe could not validate')`),'Timed-out probe has a partial-failure report');
  await screenshot('ui-probe-timeout.png');
  await runCase('selector','Object dtype selector');
  await evaluate(`document.activeElement?.blur();window.scrollTo(0,0)`);
  await screenshot('ui-desktop-final.png');
  await resize(390,844); await screenshot('ui-mobile-final.png'); await resize(1440,1000);
  assert(errors.length===0,'Failure states introduce no JavaScript exceptions',errors);
  assert(consoleErrors.length===0,'Failure states introduce no console errors',consoleErrors);
  result.passed=true;
} catch(error) { result.passed=false;result.failure=error.stack; try{await screenshot('ui-negative-failure.png')}catch{} }
finally{await fs.writeFile(path.join(artifacts,'ui-failure-checks.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));ws.close();if(!result.passed)process.exitCode=1;}
