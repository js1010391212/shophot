// Pure contract helpers. No network, page state, credentials, or storage access.
export const TTL = 10 * 60 * 1000;
export const LOCAL_URL = 'http://127.0.0.1:8000/browser/capture/';
export const FIELDS = ['schema_version', 'capture_id', 'adapter_version', 'platform', 'url',
  'product_id', 'sku_id', 'title', 'price', 'currency', 'quote_type', 'market_country',
  'conditions', 'observed_at', 'evidence'];
export const EBAY_DOMAINS = ['ebay.com', 'ebay.co.uk', 'ebay.de', 'ebay.fr', 'ebay.it',
  'ebay.es', 'ebay.ca', 'ebay.com.au', 'ebay.ie', 'ebay.nl'];

export class CaptureError extends Error {
  constructor(code) { super(code); this.code = code; }
}
export function targetIdentity(value) {
  let u;
  try { u = new URL(value); } catch { throw new CaptureError('unsupported'); }
  if (u.protocol !== 'https:' || u.username || u.password || (u.port && u.port !== '443'))
    throw new CaptureError('unsupported');
  let platform, productId, key, domain;
  if ((u.hostname === 'aliexpress.com' || u.hostname.endsWith('.aliexpress.com')) &&
      /^\/item\/\d+\.html$/.test(u.pathname)) {
    platform = 'AliExpress'; productId = u.pathname.match(/\d+/)[0]; key = 'sku_id'; domain = 'www.aliexpress.com';
  } else if (['otto.de', 'www.otto.de'].includes(u.hostname) &&
      /^\/p\/[a-zA-Z0-9%_-]+-(?:S|C)[a-zA-Z0-9]+\/?$/.test(u.pathname)) {
    platform = 'OTTO'; productId = u.pathname.replace(/\/$/, '').split('-').at(-1); key = 'variationId'; domain = 'www.otto.de';
    u.pathname = u.pathname.replace(/\/$/, '') + '/';
  } else if (EBAY_DOMAINS.some(h => u.hostname === h || u.hostname === 'www.' + h) &&
      /^\/itm\/(?:[^/]+\/)?\d{9,15}\/?$/.test(u.pathname)) {
    platform = 'eBay'; productId = u.pathname.replace(/\/$/, '').split('/').at(-1); key = 'var';
    domain = 'www.' + u.hostname.replace(/^www\./, ''); u.pathname = '/itm/' + productId;
  } else throw new CaptureError('unsupported');
  const values = u.searchParams.getAll(key);
  if (values.length > 1 || (values.length && !new RegExp(platform === 'OTTO' ? '^[A-Za-z0-9]{1,80}$' : '^\\d{1,80}$').test(values[0])))
    throw new CaptureError('variant');
  u.hostname = domain; u.hash = ''; u.search = ''; u.port = '';
  if (values.length) u.searchParams.set(key, values[0]);
  return { platform, productId, sku: values[0] || null, key, url: u.href };
}
export function decimalPrice(text, currency) {
  const compact = text.trim().replace(/[\s\u00a0\u202f]/g, '');
  const symbols = {EUR: '€', USD: 'US\\$|USD', GBP: '£', CAD: 'C\\$|CAD', AUD: 'AU\\$|AUD'};
  const unit = symbols[currency] || currency;
  // A bare "$" is intentionally ambiguous; ISO currency must be visibly explicit.
  let value = compact.replace(new RegExp('^(?:' + unit + ')|(?:' + unit + ')$', 'g'), '');
  if (value === compact) throw new CaptureError('currency');
  if (/^\d{1,10},\d{2}$/.test(value)) value = value.replace(',', '.');
  else if (/^\d{1,3}(?:\.\d{3})+,\d{2}$/.test(value)) value = value.replaceAll('.', '').replace(',', '.');
  else if (/^\d{1,3}(?:,\d{3})+\.\d{2}$/.test(value)) value = value.replaceAll(',', '');
  if (!/^\d{1,10}(?:\.\d{1,2})?$/.test(value)) throw new CaptureError('price');
  const [whole, cents = ''] = value.split('.');
  return whole.replace(/^0+(?=\d)/, '') + '.' + cents.padEnd(2, '0');
}
function cleanText(value, limit) {
  if (typeof value !== 'string' || !value.trim() || value.trim().length > limit ||
      /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ud800-\udfff]/u.test(value))
    throw new CaptureError('evidence');
  return value.trim().replace(/\s+/g, ' ');
}
export function buildCapture(reading, now = new Date(), uuid = crypto.randomUUID()) {
  if (!reading || reading.error) throw new CaptureError(reading?.error || 'page');
  const target = targetIdentity(reading.url);
  if (reading.productId !== target.productId) throw new CaptureError('identity');
  if (reading.sku !== target.sku) throw new CaptureError('variant');
  if (!/^[A-Z]{3}$/.test(reading.currency)) throw new CaptureError('currency');
  const price = decimalPrice(reading.priceText, reading.currency);
  if (reading.referencePrice != null && price !== reading.referencePrice) throw new CaptureError('price');
  if (!Array.isArray(reading.conditions) || reading.conditions.length > 5) throw new CaptureError('evidence');
  return {
    schema_version: 1, capture_id: uuid,
    adapter_version: ({OTTO:'otto-dom/1', AliExpress:'aliexpress-dom/1', eBay:'ebay-dom/1'})[target.platform],
    platform: target.platform, url: target.url, product_id: target.productId, sku_id: target.sku,
    title: cleanText(reading.title, 240), price, currency: reading.currency, quote_type: 'current',
    market_country: null, conditions: reading.conditions.map(v=>cleanText(v,160)),
    observed_at: now.toISOString(), evidence: cleanText(reading.evidence,500),
  };
}
export function isLocalSender(sender, id, path = '/browser/capture/') {
  if (sender?.id !== id || sender.frameId !== 0 || !Number.isInteger(sender.tab?.id)) return false;
  try {
    const u = new URL(sender.url);
    return u.origin === new URL(LOCAL_URL).origin && u.pathname === path && !u.username && !u.password;
  } catch { return false; }
}
export function isPopupSender(sender, runtime) {
  return sender?.id === runtime.id && !sender.tab && sender.url === runtime.getURL('popup.html');
}
