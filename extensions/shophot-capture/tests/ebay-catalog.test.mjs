import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';
import {targetIdentity,decimalPrice,buildCapture,FIELDS} from '../capture.mjs';
import {createController} from '../controller.mjs';

// Public observations were supplied and real-source execution was verified by
// the project lead. All DOM objects below are controlled selector doubles;
// evidence/ebay-readings.json separately preserves the real Chrome readings.
const catalog='https://www.ebay.com/p/813169729?iid=318716291619';
const listing='https://www.ebay.com/itm/318716291619';
const reject=(url,code)=>assert.throws(()=>targetIdentity(url),e=>e.code===code);

test('catalog ePID is not the candidate listing product_id',()=>{
  assert.deepEqual(targetIdentity(catalog),{platform:'eBay',productId:'318716291619',sku:null,key:'var',url:listing});
  assert.notEqual(targetIdentity(catalog).productId,'813169729');
});
test('catalog alias and direct listing share the URL-declared candidate only',()=>{
  assert.deepEqual(targetIdentity(catalog),targetIdentity(listing));
  assert.deepEqual(targetIdentity(catalog.replace('/813169729','/999999999')),targetIdentity(listing));
});
test('different iid on same catalog never merges listings',()=>{
  const other=targetIdentity(catalog.replace('318716291619','318716291620'));
  assert.notEqual(other.url,targetIdentity(catalog).url);assert.notEqual(other.productId,targetIdentity(catalog).productId);
});
test('tracking removed and var retained without guessing a selected option',()=>{
  const result=targetIdentity(catalog+'&var=456&mkcid=1#tracking');
  assert.equal(result.url,listing+'?var=456');assert.equal(result.sku,'456');
});
test('regional origin preserved for same catalog and listing numbers',()=>{
  const de=targetIdentity(catalog.replace('ebay.com','ebay.de'));
  assert.equal(de.url,'https://www.ebay.de/itm/318716291619');
  assert.notEqual(de.url,targetIdentity(catalog).url);
});
test('bare regional host is canonicalized without merging regions',()=>{
  assert.equal(targetIdentity('https://ebay.co.uk/p/813169729/?iid=318716291619').url,'https://www.ebay.co.uk/itm/318716291619');
});
for(const query of ['', '?iid=', '?IID=318716291619', '?iid=abc', '?iid=318716291619&iid=318716291620',
  '?iid=318716291619&iid=318716291619', '?iid=318716291619&%69id=318716291619', '?iid='+ '1'.repeat(81),
  '?iid=12345678', '?iid=1234567890123456', '?iid=%EF%BC%91', '?iid=318716291619%2Fother'])
  test('catalog needs exactly one valid explicit iid '+query,()=>reject('https://www.ebay.com/p/813169729'+query,'catalog'));
for(const url of ['http://www.ebay.com/p/813169729?iid=318716291619',
  'https://www.ebay.com.evil.example/p/813169729?iid=318716291619',
  'https://user:password@www.ebay.com/p/813169729?iid=318716291619',
  'https://www.ebay.com:8443/p/813169729?iid=318716291619',
  'https://signin.ebay.com/p/813169729?iid=318716291619',
  'https://www.ebay.com/p/name/813169729?iid=318716291619',
  'https://www.ebay.com/p/not-an-id?iid=318716291619'])
  test('catalog candidate cannot bypass target trust rules '+url,()=>reject(url,'unsupported'));
test('conflicting iid on direct listing is not dropped as tracking',()=>{
  reject(listing+'?iid=813169729','identity');reject(listing+'?iid=','identity');
  reject(listing+'?iid=318716291619&iid=318716291619','identity');
  assert.equal(targetIdentity(listing+'?iid=318716291619').url,listing);
});
test('var identity boundaries are unchanged for catalog candidates',()=>{
  reject(catalog+'&var=','variant');reject(catalog+'&var=1&var=2','variant');reject(catalog+'&var=invalid','variant');
});
test('numeric item bounds agree with backend 1..80 character rule',()=>{
  for(const id of ['1','1'.repeat(80)]) assert.equal(targetIdentity('https://www.ebay.com/itm/'+id).productId,id);
  reject('https://www.ebay.com/itm/'+'1'.repeat(81),'unsupported');
});
test('catalog iid accepts exactly the backend 9..15 ASCII digit boundaries',()=>{
  for(const id of ['123456789','123456789012345'])
    assert.equal(targetIdentity('https://www.ebay.com/p/1?iid='+id).productId,id);
});
test('ePID in a controlled reading cannot masquerade as listing identity',()=>{
  const reading={url:catalog,productId:'813169729',sku:null,title:'Controlled title',priceText:'US $54.99',currency:'USD',referencePrice:'54.99',conditions:[],evidence:'Controlled quote'};
  assert.throws(()=>buildCapture(reading,new Date('2026-10-08T12:00:00Z'),'f45b9333-1ac0-4d40-8363-bf699ab2a780'),e=>e.code==='identity');
  const payload=buildCapture({...reading,productId:'318716291619'},new Date('2026-10-08T12:00:00Z'),'f45b9333-1ac0-4d40-8363-bf699ab2a780');
  assert.deepEqual(Object.keys(payload).sort(),[...FIELDS].sort());assert.equal(payload.url,listing);
  assert.equal(payload.price,'54.99');assert.equal(payload.market_country,null);
});
test('US quote does not become its approximate yen conversion',()=>{
  assert.equal(decimalPrice('US $54.99','USD'),'54.99');
  for(const text of ['US $54.99 約JPY 8,000','約JPY 8,000','JPY 8,000']) assert.throws(()=>decimalPrice(text,'USD'));
  assert.throws(()=>decimalPrice('$54.99','USD'));
});

const readerSource=(await fs.readFile(new URL('../dom-reader.mjs',import.meta.url),'utf8')).replace('export function','function');
const readings=JSON.parse(await fs.readFile(new URL('../evidence/ebay-readings.json',import.meta.url),'utf8'));
const controls='select,[role="listbox"],input[type="radio"],[role="radio"],[aria-haspopup="listbox"]';
function node(text='',attrs={},selectors={}) {
  return {innerText:text,textContent:text,attrs,selectors,
    getAttribute(k){return this.attrs[k]??null},getClientRects(){return this.attrs.hidden ? [] : [{}]},
    closest(s){return s==='del,s' && this.attrs.struck ? {} : null},
    querySelectorAll(s){return this.selectors[s]||[]}};
}
function fixture(kind='catalog') {
  const isCatalog=kind==='catalog', expected=readings[kind].reading, calls=[];
  const bold=node(expected.title),h1=node(expected.title+(isCatalog?'':' -'),{}, {'.ux-textspans--BOLD':[bold]});
  const quote=node('US $54.99'),primary=node('',{}, {
    [isCatalog?':scope > .ux-textspans':'.x-price-primary__price > .ux-textspans']:[quote],
    '.x-price-primary__orBestOffer':isCatalog?[]:[node('またはベストオファー')]});
  const detail=node('',{href:listing});
  const buy=node('今すぐ買う',{href:'https://pay.ebay.com/rxo?action=create&rypsvc=true&pagename=ryp&item=318716291619&quantity=1&TransactionId=-1'});
  const scope=node('',{}, {'.x-item-title h1':[h1],'.x-see-details-action a[href]':[detail],'.x-price-primary':[primary],'a#binBtn_btn_1':[buy]});
  const canonical=node('',{href:listing}),og=node('',{content:listing});
  // The observed detail Product has no Product.url and quotes a JPY conversion.
  const page={'@type':'ItemPage',url:listing};
  const product={'@type':'Product',name:readings.listing.reading.title,offers:{'@type':'Offer',url:listing,
    price:'8693.0',priceCurrency:'JPY',availability:'https://schema.org/InStock'}};
  const document=node('',{}, {'h1,h2':[h1],
    [isCatalog?'.x-prp-main-container_col-right':'#mainContent.x-evo-atf-right-river']:[scope],
    'link[rel="canonical"]':[canonical],'meta[property="og:url"]':[og]});
  const query=document.querySelectorAll;document.querySelectorAll=function(s){calls.push(s);return query.call(this,s)};
  const location=new URL(isCatalog?catalog:listing);
  const f={document,location,calls,h1,bold,quote,primary,scope,detail,buy,canonical,og,page,product,scripts:null};
  f.read=()=>{
    document.selectors['script[type="application/ld+json"]']=f.scripts||[node(JSON.stringify([page,product]))];
    return JSON.parse(JSON.stringify(vm.runInNewContext(readerSource+'\nreadPublicPage();',{
      document,location,URL,getComputedStyle:e=>({display:'block',visibility:'visible',textDecorationLine:e.attrs.struck?'line-through':'none'}),
    })));
  };
  return f;
}
for(const kind of ['catalog','listing']) test('controlled '+kind+' selector reading matches separately recorded real Chrome output',()=>{
  const f=fixture(kind),result=f.read();assert.deepEqual(result,readings[kind].reading);
  const payload=buildCapture(result,new Date(readings[kind].observedAt),'f45b9333-1ac0-4d40-8363-bf699ab2a780');
  assert.equal(payload.url,listing);assert.equal(payload.product_id,'318716291619');assert.equal(payload.price,'54.99');
  assert.equal(payload.currency,'USD');assert.equal(payload.sku_id,null);assert.equal(payload.market_country,null);
  assert.equal(payload.adapter_version,'ebay-dom/2');assert.equal(payload.observed_at,readings[kind].observedAt);
  assert.deepEqual(Object.keys(payload).sort(),[...FIELDS].sort());
});
test('catalog never reads nineteen controlled unrelated JPY structured Offers',()=>{
  const f=fixture();f.scripts=[node(JSON.stringify({'@type':'Product',offers:Array.from({length:19},(_,i)=>({
    '@type':'Offer',url:'https://www.ebay.com/itm/'+(900000000000+i),price:'100',priceCurrency:'JPY'}))}))];
  assert.equal(f.read().priceText,'US $54.99');assert.ok(!f.calls.some(s=>s.includes('ld+json')));
});
for(const href of [listing.replace('318716291619','318716291620'),listing.replace('ebay.com','ebay.de'),
  'https://user:password@www.ebay.com/itm/318716291619',listing+'?var=1',listing+'?iid=1',
  listing+'?iid=318716291619&iid=318716291619','http://www.ebay.com/itm/318716291619',
  'https://www.ebay.com:8443/itm/318716291619'])
  test('catalog current detail link must independently own iid '+href,()=>{
    const f=fixture();f.detail.attrs.href=href;assert.equal(f.read().error,'identity');
  });
test('catalog detail link accepts same listing tracking and relative href',()=>{
  const f=fixture();f.detail.attrs.href='/itm/318716291619?mkcid=1';assert.equal(f.read().url,listing);
});
for(const kind of ['catalog','listing']) {
  test(kind+' requires one visible enabled fixed-price buy control for this listing',()=>{
    for(const mutate of [f=>f.scope.selectors['a#binBtn_btn_1']=[],f=>f.buy.attrs.hidden=true,
      f=>f.scope.selectors['a#binBtn_btn_1'].push(f.buy),f=>f.buy.attrs['aria-disabled']='true',
      f=>f.buy.attrs.disabled='',f=>f.buy.attrs.href=f.buy.attrs.href.replace('318716291619','318716291620'),
      f=>f.buy.attrs.href=f.buy.attrs.href.replace('pay.ebay.com','pay.ebay.com.evil.example'),
      f=>f.buy.attrs.href=f.buy.attrs.href.replace('action=create','action=bid'),
      f=>f.buy.attrs.href+='&item=318716291619',f=>f.buy.attrs.href+='&action=create']) {
      const f=fixture(kind);mutate(f);assert.equal(f.read().error,'unavailable');
    }
  });
  test(kind+' missing or ambiguous current title/scope fails',()=>{
    for(const mutate of [f=>f.scope.attrs.hidden=true,f=>f.scope.selectors['.x-item-title h1']=[],
      f=>f.scope.selectors['.x-item-title h1'].push(node('Other title'))]) {
      const f=fixture(kind);mutate(f);assert.equal(f.read().error,'identity');
    }
  });
  test(kind+' rejects var and visible unverified specification controls',()=>{
    for(const mutate of [f=>f.location.search+='&var=123',f=>f.scope.selectors[controls]=[node('Size')]]) {
      const f=fixture(kind);mutate(f);assert.equal(f.read().error,'variant');
    }
    const f=fixture(kind);f.scope.selectors[controls]=[node('Size',{hidden:true})];assert.equal(f.read().currency,'USD');
  });
  test(kind+' hidden/struck/duplicate primary quotes cannot be current price',()=>{
    for(const mutate of [f=>f.quote.attrs.hidden=true,f=>f.quote.attrs.struck=true,
      f=>f.scope.selectors['.x-price-primary'].push(node('US $1.00')),
      f=>f.primary.selectors[kind==='catalog'?':scope > .ux-textspans':'.x-price-primary__price > .ux-textspans'].push(node('US $68.99'))]) {
      const f=fixture(kind);mutate(f);assert.equal(f.read().error,'price');
    }
  });
  test(kind+' scoped quote ignores original price, conversion and recommendation nodes',()=>{
    const f=fixture(kind);f.scope.selectors['.x-price-transparency']=[node('US $68.99')];
    f.scope.selectors['.x-price-approx']=[node('約8,693 円')];f.document.selectors['.x-price-primary']=[node('US $1.00')];
    assert.equal(buildCapture(f.read()).price,'54.99');
  });
}
for(const [part,mutate] of [
  ['canonical',f=>f.canonical.attrs.href=listing.replace('318716291619','318716291620')],
  ['og',f=>f.og.attrs.content=listing.replace('ebay.com','ebay.de')],
  ['ItemPage',f=>f.page.url=listing.replace('318716291619','318716291620')],
  ['Offer',f=>f.product.offers.url=listing.replace('318716291619','318716291620')],
  ['duplicate canonical',f=>f.document.selectors['link[rel="canonical"]'].push(f.canonical)],
  ['duplicate og',f=>f.document.selectors['meta[property="og:url"]'].push(f.og)],
  ['Offer array',f=>f.product.offers=[f.product.offers]],
  ['AggregateOffer',f=>f.product.offers['@type']='AggregateOffer'],
  ['title mismatch',f=>f.product.name+=' extra'],
  ['non-string name',f=>f.product.name={value:f.product.name}],
  ['missing bold title',f=>f.h1.selectors['.ux-textspans--BOLD']=[]],
  ['ambiguous bold title',f=>f.h1.selectors['.ux-textspans--BOLD'].push(node('Other title'))],
]) test('listing rejects inconsistent '+part,()=>{
  const f=fixture('listing');mutate(f);assert.equal(f.read().error,'identity');
});
test('listing real title punctuation retained; only display suffix is excluded',()=>{
  const f=fixture('listing');f.bold.innerText=f.product.name='Actual title -';f.h1.innerText='Actual title - -';
  assert.equal(f.read().title,'Actual title -');
});
test('listing duplicate current ItemPage or owning Product is ambiguous',()=>{
  for(const key of ['page','product']) {
    const f=fixture('listing');f.scripts=[node(JSON.stringify([f.page,f.product,f[key]]))];assert.equal(f.read().error,'identity');
  }
});
test('listing explicit stock state required',()=>{
  for(const value of [undefined,'https://schema.org/OutOfStock']) {
    const f=fixture('listing');f.product.offers.availability=value;assert.equal(f.read().error,'unavailable');
  }
});
test('same-currency structured price cross-checks USD, converted JPY does not',()=>{
  const f=fixture('listing');assert.equal(f.read().referencePrice,null);assert.equal(buildCapture(f.read()).price,'54.99');
  f.product.offers.priceCurrency='USD';f.product.offers.price='54.99';assert.equal(f.read().referencePrice,'54.99');
  assert.equal(buildCapture(f.read()).price,'54.99');f.product.offers.price='68.99';
  assert.throws(()=>buildCapture(f.read()),e=>e.code==='price');f.product.offers.price=54.99;assert.equal(f.read().error,'price');
});
test('ambiguous currency and combined conversion/range text fails payload creation',()=>{
  const f=fixture();f.quote.innerText='$54.99';assert.equal(f.read().error,'currency');
  for(const value of ['US $54.99 約8,693 円','US $54.99 - US $68.99']) {
    f.quote.innerText=value;assert.throws(()=>buildCapture(f.read()),e=>e.code==='price');
  }
});
test('visible challenge takes priority and no verification is attempted',()=>{
  const f=fixture();f.document.selectors['h1,h2']=[node('Verify you are human')];assert.equal(f.read().error,'challenge');
  const f2=fixture('listing');f2.location.pathname='/splashui/challenge';assert.equal(f2.read().error,'challenge');
});
test('catalog identity failure creates no local tab and persists no raw capture',async()=>{
  let stored={},opened=0,injected=0;
  const chrome={runtime:{id:'extension-id',getURL:p=>'chrome-extension://extension-id/'+p},
    storage:{session:{get:async()=>structuredClone(stored),set:async data=>{stored={...stored,...structuredClone(data)}}}},
    tabs:{query:async()=>[{id:7,url:catalog}],create:async()=>{opened++;return{id:8}}},
    scripting:{executeScript:async()=>{injected++;const f=fixture();f.detail.attrs.href=listing.replace('318716291619','318716291620');return[{frameId:0,result:f.read()}]}},
  };
  const controller=createController(chrome,()=>{},()=>Date.parse('2026-10-08T12:00:00Z'));
  const result=await controller.handle({type:'capture'},{id:'extension-id',url:chrome.runtime.getURL('popup.html')});
  assert.equal(result.ok,false);assert.equal(result.code,'identity');assert.equal(opened,0);assert.equal(injected,1);
  assert.deepEqual(stored.pending,{});assert.equal(stored.last.code,'identity');
});
test('controller binds verified catalog reading to one new local preview tab',async()=>{
  let stored={},opened=0,updated=null;
  const chrome={runtime:{id:'extension-id',getURL:p=>'chrome-extension://extension-id/'+p},
    storage:{session:{get:async()=>structuredClone(stored),set:async data=>{stored={...stored,...structuredClone(data)}}}},
    tabs:{query:async()=>[{id:7,url:catalog}],create:async()=>{opened++;return{id:8}},update:async(id,data)=>{updated={id,...data}}},
    scripting:{executeScript:async()=>[{frameId:0,result:fixture().read()}]},
  };
  const controller=createController(chrome,()=>{},()=>Date.parse('2026-10-08T14:20:46Z'));
  const result=await controller.handle({type:'capture'},{id:'extension-id',url:chrome.runtime.getURL('popup.html')});
  assert.deepEqual(result,{ok:true,code:'waiting'});assert.equal(opened,1);
  assert.deepEqual(updated,{id:8,url:'http://127.0.0.1:8000/browser/capture/'});
  assert.equal(stored.pending[8].payload.url,listing);assert.equal(stored.pending[8].payload.price,'54.99');
  assert.equal(stored.pending[8].payload.adapter_version,'ebay-dom/2');
});
test('popup reports missing unique catalog iid without claiming success',async()=>{
  const status={textContent:''},button={addEventListener(){}};
  const source=await fs.readFile(new URL('../popup.mjs',import.meta.url),'utf8');
  await vm.runInNewContext('(async()=>{'+source+'})()',{
    document:{querySelector:selector=>selector==='#status' ? status : button},
    chrome:{runtime:{sendMessage:async()=>({ok:false,code:'catalog'})}},
  });
  assert.match(status.textContent,/商品目录链接/);assert.match(status.textContent,/唯一有效/);assert.match(status.textContent,/未发送/);
});
