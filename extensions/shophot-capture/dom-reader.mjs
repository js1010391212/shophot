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
  const ebayHosts = ['ebay.com','ebay.co.uk','ebay.de','ebay.fr','ebay.it','ebay.es','ebay.ca','ebay.com.au','ebay.ie','ebay.nl'];
  const ebay = ebayHosts.includes(url.hostname.replace(/^www\./,''));
  const match = ali ? url.pathname.match(/^\/item\/(\d+)\.html$/) : ebay ? url.pathname.match(/^\/itm\/(?:[^/]+\/)?(\d{9,15})\/?$/) : null;
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
