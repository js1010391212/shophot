// Injected only into frame 0 after a user click. Keep this function self-contained.
export function readPublicPage() {
  const fail = error => ({error});
  const text = e => (e?.innerText || '').trim().replace(/\s+/g, ' ');
  const visible = e => !!e && e.getClientRects().length > 0 &&
    getComputedStyle(e).visibility !== 'hidden' && getComputedStyle(e).display !== 'none' &&
    !e.closest('[hidden],[aria-hidden="true"]');
  const one = (root, selector) => {
    const items = [...root.querySelectorAll(selector)].filter(visible);
    return items.length === 1 ? items[0] : null;
  };
  const heading = [...document.querySelectorAll('h1,h2')].filter(visible).slice(0,8).map(text).join(' ');
  if (/_____tmd_____|\/splashui\/challenge|\/captcha|\/challenge/.test(location.pathname) ||
      /verify.{0,20}(human|browser)|security check|robot|captcha|ブラウザを確認|验证|驗證/i.test(heading) ||
      [...document.querySelectorAll('iframe[src*="captcha"],input[name*="captcha"],[id="captcha"]')].some(visible))
    return fail('challenge');
  if (/\/login|\/signin|\/sign-in|\/accounts\//.test(location.pathname)) return fail('login_external');
  const url = new URL(location.href);
  if (url.protocol !== 'https:' || url.username || url.password) return fail('unsupported');
  const ebayHosts = ['ebay.com','ebay.co.uk','ebay.de','ebay.fr','ebay.it','ebay.es','ebay.ca','ebay.com.au','ebay.ie','ebay.nl'];
  const ebay = ebayHosts.includes(url.hostname.replace(/^www\./,''));
  if (ebay) {
    const catalog=/^\/p\/[0-9]{1,80}\/?$/.test(url.pathname);
    const item=url.pathname.match(/^\/itm\/(?:[^/]+\/)?([0-9]{1,80})\/?$/);
    if (!catalog && !item) return fail('unsupported');
    if (url.searchParams.has('var')) return fail('variant');
    const declared=url.searchParams.getAll('iid');
    if (catalog && (declared.length!==1 || !/^[0-9]{9,15}$/.test(declared[0]))) return fail('catalog');
    const id=catalog ? declared[0] : item[1];
    if (!catalog && (declared.length>1 || (declared.length && declared[0]!==id))) return fail('identity');
    // Read only DOM regions observed on the normal catalog/listing sample. No
    // recommendation fallback; a catalog ePID cannot identify a seller listing.
    const scope=one(document,catalog ? '.x-prp-main-container_col-right' : '#mainContent.x-evo-atf-right-river');
    if (!scope) return fail('identity');
    const headingNode=one(scope,'.x-item-title h1');
    // The observed listing h1 appends a separate display-only "-" span. Match
    // only its unique bold title span; catalog h1 uses the observed plain title.
    const title=catalog ? headingNode : headingNode && one(headingNode,'.ux-textspans--BOLD');
    if (!title) return fail('identity');
    if ([...scope.querySelectorAll('select,[role="listbox"],input[type="radio"],[role="radio"],[aria-haspopup="listbox"]')].some(visible)) return fail('variant');
    const matchesListing=value=>{
      if (typeof value!=='string') return false;
      try {
        const u=new URL(value,url.href), match=u.pathname.match(/^\/itm\/(?:[^/]+\/)?([0-9]{1,80})\/?$/);
        const iid=u.searchParams.getAll('iid');
        return u.protocol==='https:' && !u.username && !u.password && !u.port &&
          u.hostname.replace(/^www\./,'')===url.hostname.replace(/^www\./,'') &&
          match?.[1]===id && !u.searchParams.has('var') && iid.length<=1 && (!iid.length || iid[0]===id);
      } catch {return false;}
    };
    // Observed public Buy It Now control proves an active fixed-price listing.
    // Inspect only its DOM href; never navigate to or request the payment URL.
    const buy=one(scope,'a#binBtn_btn_1');
    if (!buy || buy.getAttribute('aria-disabled')==='true' || buy.getAttribute('disabled')!==null)
      return fail('unavailable');
    try {
      const link=new URL(buy.getAttribute('href'),url.href);
      const items=link.searchParams.getAll('item'),actions=link.searchParams.getAll('action');
      if (link.protocol!=='https:' || link.hostname!=='pay.ebay.com' || link.port || link.username || link.password ||
          link.pathname!=='/rxo' || items.length!==1 || items[0]!==id || actions.length!==1 || actions[0]!=='create')
        return fail('unavailable');
    } catch {return fail('unavailable');}
    let referencePrice=null;
    if (catalog) {
      const detail=one(scope,'.x-see-details-action a[href]');
      if (!detail || !matchesListing(detail.getAttribute('href'))) return fail('identity');
    } else {
      const canonical=[...document.querySelectorAll('link[rel="canonical"]')];
      const og=[...document.querySelectorAll('meta[property="og:url"]')];
      if (canonical.length!==1 || og.length!==1 || !matchesListing(canonical[0].getAttribute('href')) ||
          !matchesListing(og[0].getAttribute('content'))) return fail('identity');
      const pages=[],products=[];
      const walk=(v,depth=0)=>{
        if (!v || depth>12) return;
        if (Array.isArray(v)) {v.slice(0,100).forEach(x=>walk(x,depth+1));return;}
        if (typeof v!=='object') return;
        const types=Array.isArray(v['@type']) ? v['@type'] : [v['@type']];
        if (types.includes('ItemPage')) pages.push(v);
        if (types.includes('Product')) products.push(v);
        if (v['@graph']) walk(v['@graph'],depth+1);
      };
      for (const script of [...document.querySelectorAll('script[type="application/ld+json"]')].slice(0,15)) {
        if (script.textContent.length>200000) continue;
        try {walk(JSON.parse(script.textContent));} catch {/* malformed public metadata */}
      }
      if (pages.length!==1 || !matchesListing(pages[0].url)) return fail('identity');
      const owners=products.filter(p=>p.offers && !Array.isArray(p.offers) && p.offers['@type']==='Offer' && matchesListing(p.offers.url));
      if (owners.length!==1) return fail('identity');
      const product=owners[0],offer=product.offers;
      if (product.name!==undefined && (typeof product.name!=='string' ||
          product.name.trim().replace(/\s+/g,' ')!==text(title))) return fail('identity');
      if (typeof offer.availability!=='string' || !/\/InStock$/.test(offer.availability)) return fail('unavailable');
      // The real listing metadata quotes an approximate JPY conversion. It is
      // identity evidence only, never the reference amount for visible USD.
      if (offer.priceCurrency==='USD') {
        if (typeof offer.price!=='string' || !/^[0-9]{1,10}(?:\.[0-9]{1,2})?$/.test(offer.price)) return fail('price');
        const [whole,fraction='']=offer.price.split('.');
        referencePrice=whole.replace(/^0+(?=\d)/,'')+'.'+fraction.padEnd(2,'0');
      }
    }
    const primary=one(scope,'.x-price-primary');
    const quote=primary && one(primary,catalog ? ':scope > .ux-textspans' : '.x-price-primary__price > .ux-textspans');
    if (!quote || quote.closest('del,s') || getComputedStyle(quote).textDecorationLine.includes('line-through')) return fail('price');
    const priceText=text(quote);
    // USD is the only eBay currency DOM verified for this bounded adapter.
    if (!/^(?:US\s*\$|USD)\s*[0-9]/.test(priceText)) return fail('currency');
    const conditions=[];
    const bestOffer=primary && one(primary,'.x-price-primary__orBestOffer');
    if (bestOffer && text(bestOffer)) conditions.push(text(bestOffer));
    const target=new URL('/itm/'+id,url.origin);
    target.hostname='www.'+url.hostname.replace(/^www\./,'');
    return {url:target.href,productId:id,sku:null,title:text(title),priceText,currency:'USD',referencePrice,
      conditions,evidence:[text(title),priceText,'listing='+id,...conditions].join(' | ')};
  }
  const h1 = one(document, 'h1');
  if (!h1) return fail('identity');
  if (['otto.de','www.otto.de'].includes(url.hostname)) {
    const id = url.pathname.replace(/\/$/,'').split('-').at(-1);
    const frame = one(document, '.pdp-frame[data-product-id]');
    const price = frame && one(frame, '.pdp_price[data-product-id]');
    if (!frame || !price || frame.getAttribute('data-product-id') !== id || price.getAttribute('data-product-id') !== id)
      return fail('identity');
    const sku = price.getAttribute('data-variation-id');
    const ordering=one(frame,'.pdp_ordering[data-variation-id]');
    // Outer frame and JSON-LD can retain the initial SKU after a normal SPA switch.
    if (!sku || !ordering || ordering.getAttribute('data-variation-id') !== sku || !/^[A-Za-z0-9]{1,80}$/.test(sku) ||
        url.searchParams.getAll('variationId').length > 1 ||
        (url.searchParams.has('variationId') && url.searchParams.get('variationId') !== sku)) return fail('variant');
    if (price.getAttribute('data-is-sold-out') !== 'false') return fail('unavailable');
    const tag = one(price, '.js_pdp_price__tag[data-price-cents]');
    if (!tag || tag.getAttribute('data-benefit-id') !== 'original') return fail('price');
    const quote = tag && one(tag, '.pdp_price__retail-price span');
    if (!quote || quote.closest('del,s') || getComputedStyle(quote).textDecorationLine.includes('line-through')) return fail('price');
    const cents = tag.getAttribute('data-price-cents');
    if (!/^\d{1,12}$/.test(cents)) return fail('price');
    const dimensions = [...frame.querySelectorAll('.pdp_dimension-selection[data-product-id]')].filter(visible);
    const conditions = [];
    for (const d of dimensions) {
      if (d.getAttribute('data-product-id') !== id) return fail('variant');
      const radios = [...d.querySelectorAll('input[type="radio"]')];
      if (radios.length && d.getAttribute('data-variation-id') !== sku) return fail('variant');
      const groups = [...new Set(radios.map(e=>e.name))];
      for (const name of groups) {
        const checked = radios.filter(e=>e.name === name && e.checked);
        if (checked.length !== 1 || !checked[0].closest('[data-qa-dimension-item="selected"]')) return fail('variant');
        conditions.push('规格：' + checked[0].value);
      }
      // Unhandled select/button variation widgets fail rather than guessing their selection.
      if (!radios.length && d.querySelector('select,[role="listbox"],[role="radio"]')) return fail('variant');
    }
    const tax = one(price, '.pdp_price__vat-and-shipping-link');
    if (tax && text(tax)) conditions.push(text(tax));
    url.searchParams.set('variationId',sku);
    const padded=cents.padStart(3,'0');
    const referencePrice = padded.slice(0,-2).replace(/^0+(?=\d)/,'') + '.' + padded.slice(-2);
    return {url:url.href,productId:id,sku,title:text(h1),priceText:text(quote),currency:'EUR',referencePrice,
      conditions,evidence:[text(h1),text(quote),...conditions,'variationId='+sku].join(' | ')};
  }
  // Candidate semantic adapters: no platform-specific success claim without live samples.
  // A single explicit Product + Offer URL must own both identity and visible current price.
  const products = [];
  const walk = (v, depth=0) => {
    if (!v || depth > 12) return;
    if (Array.isArray(v)) { v.slice(0,100).forEach(x=>walk(x,depth+1)); return; }
    if (typeof v !== 'object') return;
    if (v['@type'] === 'Product' || (Array.isArray(v['@type']) && v['@type'].includes('Product'))) products.push(v);
    if (v['@graph']) walk(v['@graph'],depth+1);
  };
  for (const script of [...document.querySelectorAll('script[type="application/ld+json"]')].slice(0,15)) {
    if (script.textContent.length > 200000) continue;
    try { walk(JSON.parse(script.textContent)); } catch { /* malformed public structured data */ }
  }
  const ali = url.hostname === 'aliexpress.com' || url.hostname.endsWith('.aliexpress.com');
  const match = ali ? url.pathname.match(/^\/item\/(\d+)\.html$/) : ebay ? url.pathname.match(/^\/itm\/(?:[^/]+\/)?([0-9]{1,80})\/?$/) : null;
  if (!match) return fail('unsupported');
  const key = ali ? 'sku_id' : 'var';
  const sku = url.searchParams.get(key) || null;
  if (url.searchParams.getAll(key).length > 1 || (sku && !/^\d{1,80}$/.test(sku))) return fail('variant');
  const owns = value => {
    if (typeof value !== 'string') return false;
    try {
      const u = new URL(value,url.href);
      return u.protocol === 'https:' && u.hostname.replace(/^www\./,'') === url.hostname.replace(/^www\./,'') &&
        u.pathname === url.pathname && u.searchParams.getAll(key).length <= 1 && (u.searchParams.get(key)||null) === sku;
    } catch { return false; }
  };
  const matching = products.filter(p=>owns(p.url || p['@id']));
  if (matching.length !== 1) return fail('identity');
  const p = matching[0], offer = p.offers;
  if (!offer || Array.isArray(offer) || offer['@type'] !== 'Offer' || !owns(offer.url)) return fail('identity');
  if (offer.availability && !/\/InStock$/.test(offer.availability)) return fail('unavailable');
  if (p.sku && sku && String(p.sku) !== sku) return fail('variant');
  const scope = h1.closest('[itemtype="https://schema.org/Product"],[itemtype="http://schema.org/Product"]');
  if (!scope) return fail('identity');
  const quote = one(scope,'[itemprop="price"]');
  if (!quote || quote.closest('del,s') || getComputedStyle(quote).textDecorationLine.includes('line-through')) return fail('price');
  const controls = [...scope.querySelectorAll('select,[role="listbox"],input[type="radio"],[role="radio"]')].filter(visible);
  // No proven URL-to-selected-control mapping yet: any variation widget is rejected.
  if (controls.length || sku) return fail('variant');
  const currency = offer.priceCurrency;
  if (typeof offer.price !== 'string' || !/^\d{1,10}(\.\d{1,2})?$/.test(offer.price)) return fail('price');
  const [whole, fraction=''] = offer.price.split('.');
  const referencePrice = whole.replace(/^0+(?=\d)/,'')+'.'+fraction.padEnd(2,'0');
  return {url:url.href,productId:match[1],sku,title:text(h1),priceText:text(quote),currency,referencePrice,
    conditions:[],evidence:[text(h1),text(quote),'item='+match[1]].join(' | ')};
}
