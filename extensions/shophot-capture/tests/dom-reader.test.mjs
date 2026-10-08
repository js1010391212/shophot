import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';
const source=(await fs.readFile(new URL('../dom-reader.mjs',import.meta.url),'utf8')).replace('export function','function');

// Minimal DOM doubles test public selector boundaries and contradictory page states.
// They are not real site HTML fixtures; real readings are separately documented.
function node(text='',attrs={},selectors={}) {
  return {innerText:text,textContent:text,attrs,selectors,name:'color-preview-input',value:'gelb',checked:true,
    getAttribute:k=>attrs[k] ?? null,getClientRects:()=>attrs.hidden ? [] : [{}],
    closest:s=>s.includes('data-qa-dimension-item') ? attrs.selected ? {} : null : s==='del,s' ? attrs.struck ? {} : null : null,
    querySelectorAll(s){return this.selectors[s] || []},querySelector(s){return (this.selectors[s] || [])[0] || null}};
}
function fixture() {
  const quote=node('10,90 €'), tag=node('',{'data-price-cents':'1090','data-benefit-id':'original'},{'.pdp_price__retail-price span':[quote]});
  const radio=node('',{selected:true}), dimension=node('',{'data-product-id':'S1','data-variation-id':'v1'},{'input[type="radio"]':[radio]});
  const price=node('',{'data-product-id':'S1','data-variation-id':'v1','data-is-sold-out':'false'},
    {'.js_pdp_price__tag[data-price-cents]':[tag],'.pdp_price__vat-and-shipping-link':[node('inkl. MwSt. zzgl. Versandkosten')]});
  const ordering=node('',{'data-variation-id':'v1'}), h1=node('Lamp');
  const frame=node('',{'data-product-id':'S1','data-variation-id':'old-stale'},
    {'.pdp_price[data-product-id]':[price],'.pdp_ordering[data-variation-id]':[ordering],'.pdp_dimension-selection[data-product-id]':[dimension]});
  const document=node('',{},{'h1':[h1],'h1,h2':[h1],'.pdp-frame[data-product-id]':[frame]});
  const location=new URL('https://www.otto.de/p/lamp-S1/?variationId=v1');
  const read=()=>vm.runInNewContext(source+'\nreadPublicPage();',{document,location,URL,getComputedStyle:e=>({display:'block',visibility:'visible',textDecorationLine:e.attrs.struck ? 'line-through' : 'none'})});
  return {document,location,read,frame,price,quote,tag,radio,dimension,ordering};
}
test('OTTO reads current product price; stale frame/JSON-LD not used',()=>{
  const f=fixture();const r=f.read();assert.equal(r.referencePrice,'10.90');assert.equal(r.sku,'v1');assert.equal(r.conditions[0],'规格：gelb');
});
test('recommendation price and installment text never queried',()=>{
  const f=fixture();f.document.selectors['[itemprop="price"]']=[node('1,00 €'),node('99,00 €')];
  assert.equal(f.read().priceText,'10,90 €');
});
test('SKU transition: price, ordering, dimension and URL must agree',()=>{
  for(const change of [f=>f.price.attrs['data-variation-id']='v2',f=>f.ordering.attrs['data-variation-id']='v2',
    f=>f.dimension.attrs['data-variation-id']='v2',f=>f.location.search='?variationId=v2',f=>f.radio.attrs.selected=false]) {
    const f=fixture();change(f);assert.equal(f.read().error,'variant');
  }
});
test('wrong product scoped price rejected',()=>{
  const f=fixture();f.price.attrs['data-product-id']='OTHER';assert.equal(f.read().error,'identity');
});
test('coupon/benefit-specific quote cannot replace ordinary current price',()=>{
  const f=fixture();f.tag.attrs['data-benefit-id']='coupon';assert.equal(f.read().error,'price');
});
test('hidden price, multiple visible quotes, struck price and sold out fail',()=>{
  for(const [change,code] of [[f=>f.quote.attrs.hidden=true,'price'],[f=>f.tag.selectors['.pdp_price__retail-price span'].push(node('11,00 €')),'price'],
    [f=>f.quote.attrs.struck=true,'price'],[f=>f.price.attrs['data-is-sold-out']='true','unavailable']]) {
    const f=fixture();change(f);assert.equal(f.read().error,code);
  }
});
test('empty dimensions allowed only with explicit current ordering SKU',()=>{
  const f=fixture();f.dimension.selectors={};delete f.dimension.attrs['data-variation-id'];assert.equal(f.read().sku,'v1');
  f.dimension.selectors['select,[role="listbox"],[role="radio"]']=[node('Unknown variant')];assert.equal(f.read().error,'variant');
});
test('verification URL/visible heading blocks extraction',()=>{
  const f=fixture();f.location.pathname='/splashui/challenge';assert.equal(f.read().error,'challenge');
  const f2=fixture();f2.document.selectors['h1,h2']=[node('Verify you are human')];assert.equal(f2.read().error,'challenge');
});
test('eBay/AliExpress anonymous Product and missing public Offer identity fail',()=>{
  for(const url of ['https://www.ebay.com/itm/123456789012','https://www.aliexpress.com/item/1234.html']) {
    const f=fixture();
    f.location.href=url;f.document.selectors['script[type="application/ld+json"]']=[node(JSON.stringify({'@type':'Product',offers:{'@type':'Offer',price:'10.90',priceCurrency:'EUR'}}))];
    assert.equal(f.read().error,'identity');
  }
});
test('eBay generic microdata cannot replace the verified main listing region',()=>{
  const f=fixture(), url='https://www.ebay.com/itm/123456789012';f.location.href=url;
  const product={'@type':'Product',url,offers:{'@type':'Offer',url,price:'10.90',priceCurrency:'USD',availability:'https://schema.org/InStock'}};
  const script=node(JSON.stringify(product));f.document.selectors['script[type="application/ld+json"]']=[script];
  const scope=node('',{}, {'[itemprop="price"]':[node('US $10.90')]});
  f.document.selectors.h1[0].closest=s=>s.startsWith('[itemtype=') ? scope : null;
  assert.equal(f.read().error,'identity');
  product.offers['@type']='AggregateOffer';script.textContent=JSON.stringify(product);assert.equal(f.read().error,'identity');
});
test('candidate adapters reject every unverified variant mapping',()=>{
  const f=fixture(),url='https://www.ebay.com/itm/123456789012?var=123';f.location.href=url;
  const product={'@type':'Product',url,sku:'123',offers:{'@type':'Offer',url,price:'10.90',priceCurrency:'USD'}};
  f.document.selectors['script[type="application/ld+json"]']=[node(JSON.stringify(product))];
  f.document.selectors.h1[0].closest=s=>s.startsWith('[itemtype=') ? node('',{},{'[itemprop="price"]':[node('US $10.90')]}) : null;
  assert.equal(f.read().error,'variant');
});
