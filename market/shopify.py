"""Shopify 公开商品 Ajax 接口；不访问商家后台，不推算销量。"""
import ipaddress
import json
import re
import time
from decimal import Decimal
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import httpx
from django.core.exceptions import ValidationError
from .collectors import CollectionError, MAX_BYTES
from .validation import clean_currency, clean_price, clean_url


def normalize_shopify_url(value):
    parts = urlsplit(clean_url(value))
    if parts.scheme != 'https' or parts.port not in (None, 443):
        raise ValidationError('Shopify 商品必须使用 HTTPS 默认端口。')
    # 保留语言/市场路径；集合路径统一到商品路径。
    match = re.fullmatch(r'(?P<locale>/[a-z]{2}(?:-[a-zA-Z]{2})?)?(?:/collections/[\w-]+)?/products/(?P<handle>[\w-]+)/?', parts.path)
    if not match:
        raise ValidationError('请填写 Shopify 商品链接（/products/商品名称），支持自定义店铺域名。')
    try:
        address = ipaddress.ip_address(parts.hostname)
    except ValueError:
        address = None
    if address is not None or parts.hostname == 'localhost' or parts.hostname.endswith('.local'):
        raise ValidationError('请使用公开店铺域名，不能使用 IP 或本地地址。')
    params = parse_qs(parts.query, keep_blank_values=True)
    query = {}
    for key in ('variant', 'currency', 'country'):
        if key in params:
            if len(params[key]) != 1:
                raise ValidationError('规格或市场参数不能重复。')
            value = params[key][0]
            pattern = r'[0-9]+' if key == 'variant' else (r'[A-Za-z]{3}' if key == 'currency' else r'[A-Za-z]{2}')
            if not re.fullmatch(pattern, value):
                raise ValidationError('规格编号、币种或国家参数无效。')
            query[key] = value if key == 'variant' else value.upper()
    path = (match.group('locale') or '') + '/products/' + match.group('handle')
    return urlunsplit(('https', parts.hostname, path, urlencode(query), ''))


from .network import public_address, PublicProductTransport as PublicShopifyTransport


def _read_json_once(client, url):
    with client.stream('GET', url) as response:
        # 不自动跟随跨域/登录/地区重定向，防止市场条件悄悄改变。
        if response.status_code == 429:
            retry = response.headers.get('retry-after', '60')
            try:
                delay = max(1, int(retry))
            except ValueError:
                delay = 60
            raise ShopifyRateLimited(delay)
        if response.status_code != 200:
            raise CollectionError(f'Shopify 返回 HTTP {response.status_code}；请使用最终商品链接，确认店铺公开可访问。')
        if response.headers.get('content-type', '').split(';')[0].lower() not in ('application/json', 'text/javascript', 'application/javascript'):
            raise CollectionError('店铺未返回公开 Shopify JSON，可能不是 Shopify 店铺或需要访问验证。')
        chunks, size = [], 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > MAX_BYTES:
                raise CollectionError('Shopify 响应超过 2 MB，已停止采集。')
            chunks.append(chunk)
        try:
            data = json.loads(b''.join(chunks))
        except (ValueError, UnicodeError) as exc:
            raise CollectionError('Shopify 返回的数据格式无效。') from exc
        if not isinstance(data, dict):
            raise CollectionError('Shopify 返回的数据格式无效。')
        return data


class ShopifyRateLimited(CollectionError):
    def __init__(self, delay):
        self.delay = delay
        super().__init__(f'Shopify 接口限流，请至少 {delay} 秒后重试；未保存价格。')


def read_json(client, url):
    try:
        return _read_json_once(client, url)
    except ShopifyRateLimited as exc:
        # 尊重 Retry-After；只进行一次延迟重试，不切换身份或规避限流。
        if exc.delay > 60:
            raise
        time.sleep(exc.delay)
        return _read_json_once(client, url)


def parse_shopify(product, cart, url):
    parts = urlsplit(url)
    params = parse_qs(parts.query)
    handle = parts.path.rsplit('/', 1)[-1]
    if product.get('handle') != handle:
        raise CollectionError('接口商品与目标链接不一致，未保存价格。')
    variants = product.get('variants')
    if not isinstance(variants, list) or not variants or any(not isinstance(v, dict) for v in variants):
        raise CollectionError('商品缺少可识别规格。')
    variant_id = params.get('variant', [None])[0]
    if variant_id:
        selected = [v for v in variants if str(v.get('id')) == variant_id]
        if len(selected) != 1:
            raise CollectionError('指定规格不存在或未在公开接口返回，请重新选择商品规格。')
        variant = selected[0]
    elif len(variants) == 1:
        variant = variants[0]
    else:
        raise CollectionError('商品有多个规格，请在店铺选择规格后粘贴带 ?variant=编号 的链接。')
    try:
        currency = clean_currency(cart.get('currency'))
        if params.get('currency') and params['currency'][0] != currency:
            raise CollectionError('店铺返回币种与链接指定币种不一致，未保存价格。')
        minor = variant.get('price')
        if type(minor) is not int or minor < 0:
            raise ValueError
        price = clean_price(Decimal(minor) / 100)
    except (ValidationError, ValueError) as exc:
        raise CollectionError('商品价格或实际展示币种无效，未保存价格。') from exc
    title = product.get('title')
    if not isinstance(title, str) or not title.strip():
        raise CollectionError('商品缺少名称，无法确认公开商品数据。')
    condition = f"Shopify 公开接口 / variant={variant.get('id')} / {variant.get('title', '')} / {currency} / 运费税费未确认"
    if params.get('country'):
        condition += ' / 请求国家=' + params['country'][0] + '（未确认地区生效）'
    return {'price': price, 'currency': currency, 'sales': None, 'rating': None, 'review_count': None,
            'title': title.strip()[:300], 'context': condition[:300]}


def collect_shopify(url):
    try:
        url = normalize_shopify_url(url)
        parts = urlsplit(url)
        locale = parts.path.split('/products/')[0]
        market_query = urlencode({k: v[0] for k, v in parse_qs(parts.query).items() if k in ('currency', 'country')})
        # 同一客户端共享地区 Cookie；币种取实际 cart 响应，不根据价格猜测。
        with httpx.Client(timeout=httpx.Timeout(20, connect=10), follow_redirects=False, trust_env=False,
                          transport=PublicShopifyTransport(),
                          headers={'User-Agent': 'ShopHot/0.2 (public product monitoring)'}) as client:
            cart_url = urlunsplit(('https', parts.netloc, locale + '/cart.js', market_query, ''))
            cart = read_json(client, cart_url)
            product_url = urlunsplit(('https', parts.netloc, parts.path + '.js', market_query, ''))
            product = read_json(client, product_url)
            return parse_shopify(product, cart, url)
    except ValidationError as exc:
        raise CollectionError('Shopify 商品链接无效。') from exc
    except httpx.HTTPError as exc:
        raise CollectionError(f'Shopify 网络请求失败（{type(exc).__name__}）。') from exc
