"""Offline facts-only parser for the verified Pololu one-unit USD layout.

Only the first quantity break (exactly one unit) is quoted. Other tiers are
never variants or a price range. No network, models or shared identity changes.
"""
import json
import re
from decimal import Decimal

from bs4 import BeautifulSoup
from django.core.exceptions import ValidationError
from django.utils import timezone

from .collectors import CollectionError, MAX_BYTES, json_nodes
from .validation import clean_price

ROOT = 'https://www.pololu.com'


def is_pololu_store(root):
    return isinstance(root, str) and root == ROOT


def normalize_pololu_product_url(value):
    if (not isinstance(value, str) or len(value) > 500
            or not re.fullmatch(r'https://www\.pololu\.com/product/[1-9][0-9]*', value)):
        raise ValidationError('Pololu 商品须为规范 HTTPS www 主机及 /product/正整数，不含端口或参数。')
    return value


def _require(condition, message):
    if not condition:
        raise CollectionError(message)


def _one(parent, selector):
    nodes = parent.select(selector)
    _require(len(nodes) == 1, 'Pololu 页面缺少唯一的身份或报价字段。')
    return nodes[0]


def _text(node):
    return ' '.join(node.get_text(' ', strip=True).split())


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def _constant(value):
    raise ValueError('non-finite JSON number')


def _amount(value):
    try:
        return clean_price(value)
    except ValidationError as exc:
        raise CollectionError('Pololu 价格缺失或金额精度无效。') from exc


def parse_pololu_price(html, target):
    try:
        target = normalize_pololu_product_url(target)
    except ValidationError as exc:
        raise CollectionError('Pololu 目标商品链接无效。') from exc
    pid = target.rsplit('/', 1)[-1]
    try:
        if isinstance(html, bytes):
            _require(len(html) <= MAX_BYTES, 'Pololu 页面超过 2 MB。')
            html = html.decode('utf-8')
        _require(isinstance(html, str) and len(html.encode('utf-8')) <= MAX_BYTES,
                 'Pololu 页面正文无效或超过 2 MB。')
    except UnicodeError as exc:
        raise CollectionError('Pololu 页面不是有效 UTF-8。') from exc
    soup = BeautifulSoup(html, 'html.parser')
    products = []
    try:
        for script in soup.find_all('script', type='application/ld+json'):
            data = json.loads(script.get_text(), parse_float=Decimal,
                              object_pairs_hook=_pairs, parse_constant=_constant)
            for node in json_nodes(data):
                types = node.get('@type', [])
                types = [types] if isinstance(types, str) else types
                if isinstance(types, list):
                    if 'ProductGroup' in types:
                        raise ValueError('unsupported group')
                    if 'Product' in types:
                        products.append(node)
    except (ValueError, TypeError, RecursionError) as exc:
        raise CollectionError('Pololu 商品结构化数据不完整或有歧义。') from exc
    _require(len(products) == 1, 'Pololu 页面没有唯一的主商品。')
    product = products[0]
    sku = product.get('sku')
    _require(type(sku) in (int, str) and str(sku) == pid, 'Pololu 显式 SKU 与目标 PID 冲突。')
    for key in ('url', 'URL', '@id'):
        if key in product:
            _require(product[key] == target, 'Pololu 主商品身份冲突。')
    canonical = soup.select('link[rel="canonical"]')
    _require(len(canonical) <= 1 and all(n.get('href') == target for n in canonical),
             'Pololu 规范页面身份冲突。')
    title = product.get('name')
    _require(isinstance(title, str) and bool(title.strip()) and len(title) <= 300,
             'Pololu 商品名称不完整。')
    title = ' '.join(title.split())
    _require(_text(_one(soup, 'h1#page_title')) == title
             and _text(_one(soup, 'title')) in (title, 'Pololu - ' + title),
             'Pololu 商品名称证据不一致。')
    area = _one(soup, '.order_form_with_price_notification')
    identity = _one(area, '.part_number_and_stock')
    _require(_text(_one(identity, '.part_number')) == 'Pololu item #: ' + pid,
             'Pololu 可见商品编号与 SKU 不一致。')
    product_input = _one(area, 'input[name="product[id]"]')
    _require(product_input.get('value') == pid, 'Pololu 订单控件指向其他商品。')
    form = product_input.find_parent('form')
    _require(form is not None and form.get('action') == '/cart/add', 'Pololu 主商品控件身份不完整。')
    _require(not form.select('select, input[type="radio"]'), 'Pololu 存在尚未支持的规格选择。')
    _require(_one(form, 'input[name="product[quantity]"]').get('value') == '1',
             'Pololu 页面当前数量不是明确单件。')
    offer = product.get('offers')
    _require(isinstance(offer, dict) and offer.get('@type') == 'Offer'
             and offer.get('URL') == target and offer.get('url', target) == target,
             'Pololu 报价不是该目标商品的明确单个 Offer。')
    _require('sku' not in offer or type(offer['sku']) in (int, str) and str(offer['sku']) == pid,
             'Pololu Offer SKU 冲突。')
    _require(not any(k in offer for k in ('lowPrice', 'highPrice', 'priceSpecification',
                                         'eligibleQuantity', 'eligibleRegion', 'eligibleCustomerType')),
             'Pololu 存在未支持的范围或附加条件报价。')
    _require(offer.get('priceCurrency') == 'USD', 'Pololu 报价币种不是明确 USD。')
    pricing = _one(area, 'table.pricing')
    rows = pricing.find_all('tr')
    _require(bool(rows) and [_text(x) for x in rows[0].find_all('th', recursive=False)]
             == ['Price break', 'Unit price (US$)'], 'Pololu 数量阶梯或单价币种表头未知。')
    tiers = []
    for row in rows[1:]:
        cells = row.find_all('td', recursive=False)
        _require(len(cells) == 2 and bool(re.fullmatch(r'[1-9][0-9]*', _text(cells[0])))
                 and bool(re.fullmatch(r'[0-9]+\.[0-9]{2}', _text(cells[1]))),
                 'Pololu 数量阶梯报价无法明确识别。')
        quantity, amount = int(_text(cells[0])), _amount(_text(cells[1]))
        _require(not tiers or quantity > tiers[-1][0], 'Pololu 数量阶梯重复或顺序冲突。')
        tiers.append((quantity, amount))
    _require(bool(tiers) and tiers[0][0] == 1 and tiers[0][1] == _amount(offer.get('price')),
             'Pololu 单件价与结构化报价冲突，不使用批量最低价。')
    labels = [n for n in identity.select('span.label') if _text(n) == 'Status:']
    _require(len(labels) == 1 and _text(_one(labels[0].parent, 'span.value')) == 'Active and Preferred'
             and offer.get('availability') == 'InStock',
             'Pololu 状态尚未验证或与结构化库存声明冲突。')
    # This is the source's InStock declaration, not a counted or guaranteed
    # available quantity. The observed page also permits backorders.
    value = str(tiers[0][1])
    variant = {'name': title, 'sku': pid, 'size': '', 'color': '',
               'price_low': value, 'price_high': value, 'currency': 'USD',
               'availability': 'InStock', 'url': target, 'is_range': False}
    return {'price_title': title, 'price_low': value, 'price_high': value,
            'currency': 'USD', 'availability': 'InStock', 'sku': pid,
            'variants': [variant], 'variants_limited': False, 'price_source': target,
            'price_observed_at': timezone.now().strftime('%Y-%m-%d %H:%M UTC'),
            'content_policy': 'facts_only', 'images': [], 'description': '',
            'description_limited': True, 'content_source': target}


def parse_pololu_home(html, root=ROOT):
    """Return at most 100 homepage candidates in first-link DOM order.

    This is always a limited homepage list, never a full-store directory.
    A later text link may supply the title for an earlier image-only link;
    this does not reorder candidates. Image alt/title metadata is not copied.
    """
    _require(is_pololu_store(root), 'Pololu 首页目录仅支持精确的规范 HTTPS www 根域名。')
    try:
        if isinstance(html, bytes):
            _require(len(html) <= MAX_BYTES, 'Pololu 首页超过 2 MB。')
            html = html.decode('utf-8')
        _require(isinstance(html, str) and len(html.encode('utf-8')) <= MAX_BYTES,
                 'Pololu 首页正文无效或超过 2 MB。')
    except UnicodeError as exc:
        raise CollectionError('Pololu 首页不是有效 UTF-8。') from exc
    soup = BeautifulSoup(html, 'html.parser')
    _require(all(node.get('href') in (None, '/', root, root + '/')
                 for node in soup.find_all('base')),
             'Pololu 首页含无法确认的链接基准地址。')
    products, titled = {}, set()
    for link in soup.find_all('a', href=True):
        href = link.get('href')
        if not isinstance(href, str):
            continue
        target = root + href if href.startswith('/product/') else href
        try:
            target = normalize_pololu_product_url(target)
        except ValidationError:
            continue
        title = _text(link)[:300]
        if target in products:
            if title and target not in titled:
                products[target]['title'] = title
                titled.add(target)
            continue
        if len(products) >= 100:
            continue
        products[target] = {'url': target, 'title': title or target.rsplit('/', 1)[-1]}
        if title:
            titled.add(target)
    _require(bool(products), 'Pololu 首页没有可识别的规范商品候选链接。')
    return {'products': list(products.values()), 'limited': True}
