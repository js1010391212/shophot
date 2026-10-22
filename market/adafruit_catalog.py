"""Offline adapter for the verified Adafruit USD product-page layout.

The non-www schema Offer URL is evidence only, never a request destination.
No HTTP, discovery imports, model access, or generic identity relaxation.
"""
import json
import re
from decimal import Decimal

from bs4 import BeautifulSoup
from django.core.exceptions import ValidationError
from django.utils import timezone

from .collectors import CollectionError, MAX_BYTES, json_nodes
from .validation import clean_currency, clean_price

ROOT = 'https://www.adafruit.com'
_PID = r'[1-9][0-9]*'


def is_adafruit_store(root):
    return isinstance(root, str) and root == ROOT


def normalize_adafruit_product_url(value):
    if (not isinstance(value, str) or len(value) > 500
            or not re.fullmatch(r'https://www\.adafruit\.com/product/' + _PID, value)):
        raise ValidationError('Adafruit 商品须使用规范 HTTPS 主机及 /product/正整数链接，不含其他参数。')
    return value


def _require(condition, message):
    if not condition:
        raise CollectionError(message)


def _one(parent, selector):
    nodes = parent.select(selector)
    _require(len(nodes) == 1, '页面缺少唯一的商品、身份或主价格字段。')
    return nodes[0]


def _text(node):
    return ' '.join(node.get_text(' ', strip=True).split())


def _sku(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    value = str(value)
    return value if re.fullmatch(_PID, value) else None


def _reference(value, pid):
    # Fixed merchant schema alias only; do not expose this as a URL normalizer.
    return value in (ROOT + '/product/' + pid, 'https://adafruit.com/product/' + pid)


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError('non-finite JSON number')


def _product(soup):
    products = []
    try:
        for script in soup.find_all('script', type='application/ld+json'):
            data = json.loads(script.get_text(), parse_float=Decimal,
                              object_pairs_hook=_json_object, parse_constant=_invalid_constant)
            for node in json_nodes(data):
                types = node.get('@type', [])
                types = [types] if isinstance(types, str) else types
                if not isinstance(types, list):
                    continue
                if 'ProductGroup' in types:
                    raise ValueError('unsupported ProductGroup')
                if 'Product' in types:
                    products.append(node)
    except (ValueError, TypeError, RecursionError) as exc:
        raise CollectionError('商品结构化数据不完整或存在歧义。') from exc
    _require(len(products) == 1, '缺少唯一的主商品结构化数据。')
    return products[0]


def _amount(value):
    try:
        return clean_price(value)
    except ValidationError as exc:
        raise CollectionError('主价格无效或精度不明确。') from exc


def _visible_amount(node):
    value = _text(node)
    _require(bool(re.fullmatch(r'\$[0-9]+(?:,[0-9]{3})*(?:\.[0-9]{2})?', value)),
             '主价格展示格式尚未验证。')
    return _amount(value[1:].replace(',', ''))


def _selected_version(soup, main, pid, title, availability, amount):
    widgets = soup.select('.meta_pid_boxes')
    _require(not main.select('select, .variant-picker, input[type="radio"]'),
             '存在尚未支持的版本选择控件。')
    if not widgets:
        _require(not main.select('[data-part-id], [aria-current="page"]')
                 and 'multiple versions' not in _text(main).lower(),
                 '缺少可核对的明确选中版本。')
        # Other mandatory checks still require explicit schema SKU, visible PID,
        # Offer identity and three independent price/currency representations.
        return title
    names = set()
    for widget in widgets:
        selected = widget.select('li.ui-selected')
        _require(len(selected) == 1, '商品版本没有唯一明确选择。')
        item = selected[0]
        link = _one(item, 'a[aria-current="page"]')
        _require(item.get('data-part-id') == pid and link.get('href') == '/product/' + pid,
                 '选中版本与目标商品或 SKU 不一致。')
        _require(len(widget.select('a[aria-current="page"]')) == 1,
                 '商品版本选择存在冲突。')
        name = _text(_one(item, '.option_name'))
        _require(bool(name) and len(name) <= 300, '选中版本名称不完整。')
        state = _text(_one(item, '.option_meta')).lower()
        if availability == 'OutOfStock':
            _require(state == 'out of stock', '选中版本库存状态与主报价冲突。')
        else:
            _require(state == 'in stock' or _visible_amount(_one(item, '.option_meta')) == amount,
                     '选中版本价格或库存状态与主报价冲突。')
        names.add(name)
    _require(len(names) == 1, '响应式版本选择控件相互冲突。')
    return names.pop()


def parse_adafruit_price(html, target):
    try:
        target = normalize_adafruit_product_url(target)
    except ValidationError as exc:
        raise CollectionError('Adafruit 目标商品链接无效。') from exc
    pid = target.rsplit('/', 1)[-1]
    try:
        if isinstance(html, bytes):
            _require(len(html) <= MAX_BYTES, '商品页面超过 2 MB。')
            html = html.decode('utf-8')
        _require(isinstance(html, str), '商品页面正文无效。')
        _require(len(html.encode('utf-8')) <= MAX_BYTES, '商品页面超过 2 MB。')
    except UnicodeError as exc:
        raise CollectionError('商品页面字符编码无效。') from exc
    soup = BeautifulSoup(html, 'html.parser')
    node = _product(soup)
    _require(_sku(node.get('sku')) == pid, '显式商品 SKU 与目标 PID 不一致。')
    for key in ('url', '@id'):
        if key in node:
            _require(_reference(node[key], pid), '商品结构化身份指向其他商品。')
    for canonical in soup.select('link[rel="canonical"]'):
        _require(canonical.get('href') == target, '规范页链接与目标商品不一致。')
    title = node.get('name')
    _require(isinstance(title, str) and bool(title.strip()) and len(title) <= 300,
             '商品名称不完整。')
    title = ' '.join(title.split())
    main = _one(soup, '#prod-right-side')
    _require(_text(_one(main, 'h1.products_name')) == title, '主商品名称与结构化数据冲突。')
    ids = soup.select('.product_id span')
    _require(bool(ids) and all(_text(span) == pid for span in ids)
             and bool(main.select('.product_id span')), '可见商品 PID 与显式 SKU 不一致。')
    for header in soup.select('.mobile-product-header h1'):
        _require(_text(header) == title, '移动端商品名称冲突。')
    offer = node.get('offers')
    _require(isinstance(offer, dict) and offer.get('@type') == 'Offer',
             '需要单个明确 Offer，不支持商品组或范围报价。')
    _require(_reference(offer.get('url'), pid), '报价身份不是该商家的目标商品。')
    _require('sku' not in offer or _sku(offer['sku']) == pid, '报价 SKU 与目标商品冲突。')
    _require(not any(key in offer for key in ('lowPrice', 'highPrice', 'priceSpecification',
                                             'eligibleQuantity', 'eligibleCustomerType', 'eligibleRegion')),
             '存在尚未支持的数量、市场或条件报价。')
    amount = _amount(offer.get('price'))
    try:
        currency = clean_currency(offer.get('priceCurrency'))
    except ValidationError as exc:
        raise CollectionError('报价缺少明确币种。') from exc
    _require(currency == 'USD', '当前仅验证明确 USD 的 Adafruit 展示布局。')
    _one(soup, '#prod-price')
    price = _one(main, '#prod-price [itemprop="price"]')
    _require(price.has_attr('content'), '主价格缺少明确金额。')
    currency_node = _one(price, '[itemprop="priceCurrency"][content]')
    _require(currency_node['content'] == currency, '可见主价格币种与结构化数据冲突。')
    _require(_amount(price['content']) == amount == _visible_amount(price),
             '可见主价格与结构化数据冲突。')
    og_amount = _one(soup, 'meta[property="product:price:amount"][content]')
    og_currency = _one(soup, 'meta[property="product:price:currency"][content]')
    _require(_amount(og_amount['content']) == amount and og_currency['content'] == currency,
             '页面 OG 价格或币种与主报价冲突。')
    for mobile in soup.select('.mobile-product-header .product-price'):
        _require(_visible_amount(mobile) == amount, '移动端主价格与报价冲突。')
    state = offer.get('availability')
    states = {scheme + '://schema.org/' + value: value
              for scheme in ('http', 'https') for value in ('InStock', 'OutOfStock')}
    _require(isinstance(state, str) and state in states, '缺少已验证的明确库存状态。')
    availability = states[state]
    visible_state = _text(_one(main, '#prod-stock [itemprop="availability"]')).lower()
    _require(visible_state == {'InStock': 'in stock', 'OutOfStock': 'out of stock'}[availability],
             '可见库存状态与结构化报价冲突。')
    version = _selected_version(soup, main, pid, title, availability, amount)
    value = str(amount)
    variant = {'name': version, 'sku': pid, 'size': '', 'color': '',
               'price_low': value, 'price_high': value, 'currency': currency,
               'availability': availability, 'url': target, 'is_range': False}
    return {'price_title': title, 'price_low': value, 'price_high': value,
            'currency': currency, 'availability': availability, 'price_source': target,
            'price_observed_at': timezone.now().strftime('%Y-%m-%d %H:%M UTC'),
            'sku': pid, 'variants': [variant], 'variants_limited': False,
            'content_policy': 'facts_only',
            'images': [], 'description': '', 'description_limited': True,
            'content_source': target}
