import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';
import {targetIdentity,decimalPrice,buildCapture,isLocalSender,isPopupSender,TTL,LOCAL_URL,FIELDS} from '../capture.mjs';
import {createController} from '../controller.mjs';

const now=Date.parse('2026-10-08T12:00:00Z'), uuid='f45b9333-1ac0-4d40-8363-bf699ab2a780';
const reading={url:'https://www.otto.de/p/laterne-S0R0I0F0/?variationId=S0R0I0F04SO6&tracking=foo',
  productId:'S0R0I0F0',sku:'S0R0I0F04SO6',title:'灯笼',priceText:'10,90 €',currency:'EUR',referencePrice:'10.90',conditions:['规格：gelb'],evidence:'灯笼 10,90 € gelb'};
const fails=(fn,code)=>assert.throws(fn,e=>e.code===code);

test('15 exact backend fields, decimal strings, unknown country',()=>{
  const capture=buildCapture(reading,new Date(now),uuid);
  assert.deepEqual(Object.keys(capture).sort(),[...FIELDS].sort());
  assert.equal(capture.price,'10.90');assert.equal(capture.market_country,null);
  assert.equal(capture.url,'https://www.otto.de/p/laterne-S0R0I0F0/?variationId=S0R0I0F04SO6');
});
test('AliExpress tracking cleaned, numeric SKU retained',()=>{
  assert.deepEqual(targetIdentity('https://www.aliexpress.com/item/1005001234567.html?spm=abc&sku_id=456'),
    {platform:'AliExpress',productId:'1005001234567',sku:'456',key:'sku_id',url:'https://www.aliexpress.com/item/1005001234567.html?sku_id=456'});
});
test('eBay item/title canonicalization preserves regional site and var',()=>{
  const t=targetIdentity('https://www.ebay.de/itm/Lamp/123456789012?var=987654&mkcid=1');
  assert.equal(t.url,'https://www.ebay.de/itm/123456789012?var=987654');assert.equal(t.sku,'987654');assert.equal(t.platform,'eBay');
});
for(const url of ['http://www.otto.de/p/x-S1/','https://www.otto.de.evil.com/p/x-S1/','https://user:pass@www.otto.de/p/x-S1/',
  'https://www.ebay.com:8443/itm/123456789012','https://www.ebay.com.evil.com/itm/123456789012','https://www.ebay.jp/itm/123456789012'])
  test('reject untrusted target '+url,()=>fails(()=>targetIdentity(url),'unsupported'));
for(const query of ['variationId=','variationId=a&variationId=b','variationId=a%2Fb'])
  test('reject invalid/duplicate SKU '+query,()=>fails(()=>targetIdentity('https://www.otto.de/p/x-S1/?'+query),'variant'));
for(const [text,currency,expected] of [['10,90 €','EUR','10.90'],['1.234,56 €','EUR','1234.56'],['US $1,234.56','USD','1234.56'],['£0.5','GBP','0.50']])
  test('normalize exact visible amount '+text,()=>assert.equal(decimalPrice(text,currency),expected));
for(const text of ['10–20 €','ab 10,90 €','10,90 € 13,90 €','1,00 € monatlich','-1 €','10,999 €'])
  test('reject ambiguous amount '+text,()=>assert.throws(()=>decimalPrice(text,'EUR')));
test('ambiguous dollar symbol is not USD',()=>fails(()=>decimalPrice('$10.90','USD'),'currency'));
test('visible amount cannot disagree with DOM cents / structured Offer',()=>fails(()=>buildCapture({...reading,referencePrice:'0.01'},new Date(now),uuid),'price'));
test('product and SKU contradictions fail',()=>{
  fails(()=>buildCapture({...reading,productId:'S_OTHER'},new Date(now),uuid),'identity');
  fails(()=>buildCapture({...reading,sku:null},new Date(now),uuid),'variant');
});
test('invalid evidence and excessive conditions fail',()=>{
  fails(()=>buildCapture({...reading,evidence:'\u0000'},new Date(now),uuid),'evidence');
  fails(()=>buildCapture({...reading,conditions:Array(6).fill('a')},new Date(now),uuid),'evidence');
});
test('public page errors preserved before payload creation',()=>fails(()=>buildCapture({error:'challenge'},new Date(now),uuid),'challenge'));

function harness() {
  let time=now, data={}, tabId=20, injections=0;
  const events=[];
  const chrome={runtime:{id:'extension-id',getURL:p=>'chrome-extension://extension-id/'+p},
    storage:{session:{get:async keys=>Object.fromEntries(keys.filter(k=>k in data).map(k=>[k,structuredClone(data[k])])),
      set:async state=>{data={...data,...structuredClone(state)};events.push('store');}}},
    tabs:{query:async()=>[{id:7,url:reading.url}],create:async options=>{events.push('create:'+options.url);return{id:tabId++}},
      update:async(id,options)=>{assert.ok(data.pending[id]?.payload);assert.equal(options.url,LOCAL_URL);events.push('navigate');return{id}}},
    scripting:{executeScript:async options=>{assert.deepEqual(options.target,{tabId:7,frameIds:[0]});injections++;return[{frameId:0,result:reading}]}},
  };
  const controller=createController(chrome,()=>{},()=>time);
  const popup={id:'extension-id',url:chrome.runtime.getURL('popup.html')};
  const local=(id=20,url=LOCAL_URL)=>({id:'extension-id',frameId:0,url,tab:{id,url}});
  return {chrome,controller,popup,local,events,data:()=>data,time:v=>time=v,injections:()=>injections};
}
test('popup authorization rejects page messages and unknown extension',()=>{
  const h=harness();assert.equal(isPopupSender({...h.popup,tab:{id:7}},h.chrome.runtime),false);
  assert.equal(isPopupSender({...h.popup,id:'evil'},h.chrome.runtime),false);
});
test('local sender must be top frame, exact origin/port/path and extension',()=>{
  const h=harness();assert.ok(isLocalSender(h.local(),'extension-id'));
  for(const sender of [{...h.local(),frameId:1},{...h.local(),id:'evil'},h.local(20,'https://127.0.0.1:8000/browser/capture/'),
    h.local(20,'http://127.0.0.1:8001/browser/capture/'),h.local(20,'http://localhost:8000/browser/capture/'),
    h.local(20,'http://127.0.0.1:8000/browser/capture/other')]) assert.equal(isLocalSender(sender,'extension-id'),false);
});
test('capture creates blank tab, binds payload, then opens fixed local URL',async()=>{
  const h=harness();assert.equal((await h.controller.handle({type:'capture'},h.popup)).code,'waiting');
  assert.equal(h.injections(),1);assert.ok(h.data().pending[20].payload);
  assert.ok(h.events.indexOf('create:about:blank') < h.events.lastIndexOf('store'));
  assert.ok(h.events.lastIndexOf('store') < h.events.indexOf('navigate'));
});
test('other local tabs, foreign pages, iframe and mismatched tab URL receive no payload',async()=>{
  const h=harness();await h.controller.handle({type:'capture'},h.popup);
  for(const sender of [h.local(99),{...h.local(),frameId:1},{...h.local(),url:'https://evil.com/'},
    {...h.local(),tab:{id:20,url:'https://evil.com/'}}]) {
    const r=await h.controller.handle({type:'ready'},sender);assert.equal(r.ok,false);assert.equal(r.payload,undefined);
  }
  assert.ok(h.data().pending[20].payload);
});
test('consume once, erase raw payload, preview is distinct from saved',async()=>{
  const h=harness();await h.controller.handle({type:'capture'},h.popup);
  const first=await h.controller.handle({type:'ready'},h.local());assert.equal(first.payload.price,'10.90');
  assert.equal(h.data().pending[20].payload,undefined);
  assert.equal((await h.controller.handle({type:'ready'},h.local())).code,'duplicate');
  assert.equal((await h.controller.handle({type:'preview'},h.local())).code,'preview');
  assert.deepEqual(h.data().pending,{});assert.equal(h.data().last.code,'preview');
});
test('TTL expires raw payload at ten minutes including clock reversal',async()=>{
  for(const time of [now+TTL,now-1]) {
    const h=harness();await h.controller.handle({type:'capture'},h.popup);h.time(time);
    assert.equal((await h.controller.handle({type:'ready'},h.local())).code,'no_capture');
    assert.deepEqual(h.data().pending,{});assert.equal(h.data().last.code,'expired');
  }
});
test('local login never gets payload and instructs recapture',async()=>{
  const h=harness();await h.controller.handle({type:'capture'},h.popup);
  const r=await h.controller.handle({type:'login'},h.local(20,'http://127.0.0.1:8000/accounts/login/'));
  assert.equal(r.code,'login_local');assert.equal(r.payload,undefined);assert.deepEqual(h.data().pending,{});
});
test('closed tab and unexpected redirect remove pending data',async()=>{
  const h=harness();await h.controller.handle({type:'capture'},h.popup);await h.controller.removed(20);assert.deepEqual(h.data().pending,{});
  await h.controller.handle({type:'capture'},h.popup);await h.controller.navigated(21,'https://evil.com/');assert.deepEqual(h.data().pending,{});
});
test('service offline and no response have visible status codes',async()=>{
  const h=harness();h.chrome.tabs.update=async()=>{throw Error('offline')};
  assert.equal((await h.controller.handle({type:'capture'},h.popup)).code,'offline');assert.deepEqual(h.data().pending,{});
  const h2=harness();await h2.controller.handle({type:'capture'},h2.popup);h2.time(now+16000);
  assert.equal((await h2.controller.handle({type:'status'},h2.popup)).code,'no_response');
});
test('cap pending observations and never open local tab for extraction failure',async()=>{
  const h=harness();for(let i=0;i<3;i++) assert.ok((await h.controller.handle({type:'capture'},h.popup)).ok);
  assert.equal((await h.controller.handle({type:'capture'},h.popup)).code,'pending_limit');
  const h2=harness();h2.chrome.scripting.executeScript=async()=>[{frameId:0,result:{error:'challenge'}}];
  assert.equal((await h2.controller.handle({type:'capture'},h2.popup)).code,'challenge');assert.equal(h2.events.some(e=>e.startsWith('create:')),false);
});
test('extension suspension/restart retains binding in session storage',async()=>{
  const h=harness();await h.controller.handle({type:'capture'},h.popup);
  const next=createController(h.chrome,()=>{},()=>now);
  assert.ok((await next.handle({type:'ready'},h.local())).payload);
});
test('page navigation during extraction cannot change product identity',async()=>{
  const h=harness();h.chrome.scripting.executeScript=async()=>[{frameId:0,result:{...reading,url:'https://www.otto.de/p/x-S999/?variationId=v',productId:'S999',sku:'v'}}];
  assert.equal((await h.controller.handle({type:'capture'},h.popup)).code,'identity');assert.equal(h.events.some(e=>e.startsWith('create:')),false);
});

const bridgeSource=await fs.readFile(new URL('../bridge.js',import.meta.url),'utf8');
async function bridgeHarness({marker=true,action=LOCAL_URL,csrf='existing-csrf',response,preview=false,pathname='/browser/capture/',throws=false}={}) {
  const fields={target_url:{value:''},capture:{value:''},csrfmiddlewaretoken:{value:csrf}};
  const calls=[], notices=[];let submits=0;
  const form={method:'post',action,elements:{namedItem:name=>fields[name]},requestSubmit:()=>{submits++},checkValidity:()=>true,
    querySelectorAll:selector=>fields[selector.match(/name="(.*?)"/)[1]] ? [{}] : []};
  const confirm={action:'http://127.0.0.1:8000/products/5/browser/confirm/',querySelector:()=>({})};
  const document={querySelector:selector=>selector.startsWith('#browser-capture-form') ? marker ? form : null : null,
    querySelectorAll:()=>preview ? [confirm] : [],createElement:()=>({setAttribute(){},style:{}}),body:{prepend:p=>notices.push(p.textContent)}};
  const window={};window.top=window;
  const context={window,document,location:{origin:'http://127.0.0.1:8000',pathname,href:LOCAL_URL},URL,TextEncoder,
    chrome:{runtime:{sendMessage:async message=>{calls.push(message.type);if(throws)throw Error('invalid');return response || {ok:true,payload:buildCapture(reading,new Date(now),uuid)}}}}};
  vm.runInNewContext(bridgeSource,context);await new Promise(resolve=>setImmediate(resolve));
  return {fields,calls,notices,submits:()=>submits,rerun:()=>vm.runInNewContext(bridgeSource,context)};
}
test('bridge fills target/JSON, retains CSRF and requestSubmit exactly once',async()=>{
  const b=await bridgeHarness();assert.equal(b.fields.csrfmiddlewaretoken.value,'existing-csrf');
  assert.equal(JSON.parse(b.fields.capture.value).price,'10.90');assert.equal(b.submits(),1);
  b.rerun();assert.equal(b.submits(),1);assert.deepEqual(b.calls,['ready']);
});
test('preview document never fills/resubmits any form or reads token',async()=>{
  const b=await bridgeHarness({marker:false,preview:true});assert.deepEqual(b.calls,['preview']);assert.equal(b.submits(),0);assert.equal(b.fields.capture.value,'');
});
test('missing ready marker, forged action and missing CSRF fail before receiving data',async()=>{
  for(const opts of [{marker:false},{action:'https://evil.com/'},{csrf:''}]) {
    const b=await bridgeHarness(opts);assert.deepEqual(b.calls,['bridge_error']);assert.equal(b.submits(),0);assert.equal(b.fields.capture.value,'');
  }
});
test('local login requests no raw capture',async()=>{
  const b=await bridgeHarness({pathname:'/accounts/login/',response:{ok:false,code:'login_local'}});
  assert.deepEqual(b.calls,['login']);assert.equal(b.submits(),0);assert.match(b.notices[0],/登录/);
});
test('extension disconnection and duplicate capture visibly fail',async()=>{
  const b=await bridgeHarness({throws:true});assert.equal(b.submits(),0);assert.match(b.notices[0],/扩展连接已失效/);
  const dup=await bridgeHarness({response:{ok:false,code:'duplicate'}});assert.equal(dup.submits(),0);assert.match(dup.notices[0],/已发送/);
});
test('oversized payload cannot be submitted',async()=>{
  const b=await bridgeHarness({response:{ok:true,payload:{url:reading.url,evidence:'x'.repeat(17000)}}});assert.equal(b.submits(),0);assert.deepEqual(b.calls,['ready','bridge_error']);
});
test('manifest has no external messages, broad host permissions or credential permissions',async()=>{
  const manifest=JSON.parse(await fs.readFile(new URL('../manifest.json',import.meta.url),'utf8'));
  assert.equal(manifest.manifest_version,3);assert.equal(manifest.externally_connectable,undefined);assert.equal(manifest.host_permissions,undefined);
  assert.deepEqual(manifest.permissions,['activeTab','scripting','storage','alarms']);
  assert.ok(manifest.content_scripts[0].matches.every(u=>u.startsWith('http://127.0.0.1:8000/')));
  assert.equal(manifest.content_scripts[0].all_frames,false);
  assert.doesNotMatch(bridgeSource,/postMessage|localStorage|sessionStorage|fetch\(|XMLHttpRequest/);
});
