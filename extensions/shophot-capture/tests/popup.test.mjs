import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';

const source=await fs.readFile(new URL('../popup.mjs',import.meta.url),'utf8');
const html=await fs.readFile(new URL('../popup.html',import.meta.url),'utf8');
const manifest=JSON.parse(await fs.readFile(new URL('../manifest.json',import.meta.url),'utf8'));
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return{promise,resolve,reject};};

// Execute the actual popup source with controlled DOM/runtime; no external page,
// browser extension installation, HTTP probing or backend save is simulated.
function harness({version='0.1.2',status={code:'idle'},capture={code:'waiting'},manifestError=false}={}) {
  const calls=[],listeners=new Map();
  const nodes=Object.fromEntries(['status','version','capture','open-shophot','open-guide'].map(id=>[id,{
    textContent:'',disabled:false,addEventListener(type,listener){listeners.set(id+':'+type,listener);},
    async click(){return listeners.get(id+':click')?.();},
  }]));
  const chrome={runtime:{getManifest(){if(manifestError)throw Error('disconnected');return{version};},
    async sendMessage(message){calls.push(message);const result=message.type==='status'?status:capture;
      if(result instanceof Error)throw result;return await result;}}};
  const ready=new AsyncFunction('document','chrome',source)({querySelector:selector=>nodes[selector.slice(1)]},chrome);
  return{nodes,calls,ready};
}

test('actual installed version is displayed rather than source package version',async()=>{
  const h=harness({version:'0.1.1'});await h.ready;
  assert.equal(h.nodes.version.textContent,'已安装版本 0.1.1');
  assert.deepEqual(h.calls,[{type:'status'}]);
  assert.equal(manifest.version,'0.1.2');
});
for(const options of [{manifestError:true},{version:''}])test('version failure leaves status and capture usable '+JSON.stringify(options),async()=>{
  const h=harness(options);await h.ready;
  assert.match(h.nodes.version.textContent,/无法读取安装版本/);
  await h.nodes.capture.click();assert.match(h.nodes.status.textContent,/等待校验/);
  assert.equal(h.nodes.capture.disabled,false);
});
for(const [code,action] of [['idle',/先打开 ShopHot/],['login_local',/打开 ShopHot \/ 登录/],
  ['offline',/启动 127\.0\.0\.1:8000/],['waiting',/接收页.*进度/],['submitted',/前往接收页核对/],
  ['preview',/预览页核对并点击确认/],['no_response',/检查服务和登录/],['extension',/重新加载扩展和商品页/]])
  test('stored '+code+' gives a next action without claiming saved or live service',async()=>{
    const h=harness({status:{code}});await h.ready;
    assert.match(h.nodes.status.textContent,action);
    assert.doesNotMatch(h.nodes.status.textContent,/保存成功|已保存|服务在线|服务正常/);
    assert.deepEqual(h.calls,[{type:'status'}]);
  });
test('unsupported URL explains unique eBay iid and limited verification',async()=>{
  const h=harness({status:{code:'unsupported'}});await h.ready;
  assert.match(h.nodes.status.textContent,/\/p\/目录ID\?iid=唯一刊登编号/);
  assert.match(h.nodes.status.textContent,/AliExpress 未实站验收/);
  assert.match(h.nodes.status.textContent,/eBay 仅单刊登/);
});
test('unknown or absent worker response falls back to actionable reconnect',async()=>{
  for(const status of [undefined,{code:'new-code'},null]){
    const h=harness({status:status===undefined?{code:undefined}:status});await h.ready;
    assert.match(h.nodes.status.textContent,/重新加载扩展和商品页/);
  }
});
test('status exception and capture rejection re-enable button for retry',async()=>{
  const h=harness({status:Error('worker'),capture:Error('worker')});await h.ready;
  await h.nodes.capture.click();
  assert.match(h.nodes.status.textContent,/重新加载扩展和商品页/);
  assert.equal(h.nodes.capture.disabled,false);
  assert.deepEqual(h.calls,[{type:'status'},{type:'capture'}]);
});
test('pending capture disables duplicate clicks and reports preview without saving',async()=>{
  const result=deferred(),h=harness({capture:result.promise});await h.ready;
  const first=h.nodes.capture.click();
  assert.equal(h.nodes.capture.disabled,true);assert.match(h.nodes.status.textContent,/正在读取/);
  await h.nodes.capture.click();assert.equal(h.calls.length,2);
  result.resolve({code:'preview'});await first;
  assert.equal(h.nodes.capture.disabled,false);assert.match(h.nodes.status.textContent,/不是保存结果/);
  assert.deepEqual(h.calls,[{type:'status'},{type:'capture'}]);
});
for(const fails of [false,true])test('late initial status '+(fails?'rejection':'response')+' cannot overwrite newer click',async()=>{
  const initial=deferred(),h=harness({status:initial.promise,capture:{code:'preview'}});
  await h.nodes.capture.click();assert.match(h.nodes.status.textContent,/预览页核对/);
  if(fails)initial.reject(Error('old status'));else initial.resolve({code:'offline'});
  await h.ready;assert.match(h.nodes.status.textContent,/预览页核对/);
});
test('help links use only fixed local GET pages and never send capture/save messages',async()=>{
  assert.match(html,/<a id="open-shophot" href="http:\/\/127\.0\.0\.1:8000\/" target="_blank" rel="noopener noreferrer">/);
  assert.match(html,/<a id="open-guide" href="http:\/\/127\.0\.0\.1:8000\/browser\/capture\/" target="_blank" rel="noopener noreferrer">/);
  assert.match(html,/不代表本地服务正在运行/);
  assert.doesNotMatch(html,/onclick=|onsubmit=|<form/);
  const h=harness();await h.ready;
  await h.nodes['open-shophot'].click();await h.nodes['open-guide'].click();
  assert.deepEqual(h.calls,[{type:'status'}]);
});
test('permissions, matches, Chrome floor and running resource references remain frozen',()=>{
  assert.deepEqual(manifest.permissions,['activeTab','scripting','storage','alarms']);
  assert.equal(manifest.minimum_chrome_version,'102');
  assert.equal(manifest.background.service_worker,'worker.mjs');
  assert.equal(manifest.action.default_popup,'popup.html');
  assert.deepEqual(manifest.content_scripts,[{matches:['http://127.0.0.1:8000/browser/capture/*','http://127.0.0.1:8000/accounts/login/*'],js:['bridge.js'],run_at:'document_idle',all_frames:false}]);
  assert.equal(manifest.host_permissions,undefined);
  assert.equal(manifest.externally_connectable,undefined);
});
