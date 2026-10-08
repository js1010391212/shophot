"""店铺目录的小批量公开报价；只使用目标商品结构化数据。"""
import json
import time
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser
import httpx
from bs4 import BeautifulSoup
from django.core.exceptions import ValidationError
from django.utils import timezone
from .collectors import CollectionError, MAX_BYTES, json_nodes
from .discovery import AGENT, store_url
from .network import PublicProductTransport
from .shopify import normalize_shopify_url
from .validation import clean_price, clean_currency
from .reviews import product_reviews, widget_review_samples
from .catalog_content import product_content, plain_text, same_product

BATCH_SIZE = 10


def parse_catalog_price(html, target):
    nodes = []
    groups = []
    soup = BeautifulSoup(html, 'html.parser')
    def matches(value):
        return same_product(value, target)
    canonical = soup.select('link[rel="canonical"]')
    canonical_matches = len(canonical) == 1 and matches(canonical[0].get('href'))
    def identifies_product(node, types):
        if any(matches(value) for value in [node.get('url'), node.get('@id')]):
            return True
        # 有些主题仅在 Offer 提供商品 URL；须同时有唯一匹配的规范页链接。
        # 显式但不匹配的商品身份不能被此回退覆盖。
        if not canonical_matches or 'ProductGroup' in types or node.get('url') or node.get('@id'):
            return False
        offers = node.get('offers', [])
        offers = offers if isinstance(offers, list) else [offers]
        return bool(offers) and all(isinstance(offer, dict) and matches(offer.get('url')) for offer in offers)
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.get_text())
        except (ValueError, TypeError):
            continue
        for node in json_nodes(data):
            types = node.get('@type', [])
            types = [types] if isinstance(types, str) else types
            if not isinstance(types, list) or not set(types).intersection({'Product', 'ProductGroup'}):
                continue
            if identifies_product(node, types):
                (groups if 'ProductGroup' in types else nodes).append(node)
    nodes = groups or nodes
    if len(nodes) != 1:
        raise CollectionError('缺少唯一匹配的商品结构化报价。')
    node = nodes[0]
    if groups:
        variants = node.get('hasVariant')
        if not isinstance(variants, list) or not variants:
            raise CollectionError('商品组缺少公开规格报价。')
        offers, owners = [], []
        for variant in variants:
            if not isinstance(variant, dict) or not any(matches(value) for value in [variant.get('url'), variant.get('@id')]):
                raise CollectionError('商品组包含无法匹配的规格，未保存报价。')
            variant_offers = variant.get('offers', [])
            variant_offers = variant_offers if isinstance(variant_offers, list) else [variant_offers]
            if not variant_offers:
                raise CollectionError('商品组规格缺少报价。')
            offers.extend(variant_offers)
            owners.extend([variant] * len(variant_offers))
    else:
        offers = node.get('offers', [])
        offers = offers if isinstance(offers, list) else [offers]
        owners = [node] * len(offers)
    prices, currencies, availability = [], set(), set()
    variants = []
    for offer, owner in zip(offers, owners):
        if not isinstance(offer, dict):
            raise CollectionError('商品报价格式无效。')
        if offer.get('url') and not matches(offer['url']):
            raise CollectionError('商品报价指向其他商品，未保存报价。')
        try:
            currency = clean_currency(offer.get('priceCurrency'))
            if 'price' in offer:
                low = high = clean_price(offer['price'])
            elif offer.get('@type') == 'AggregateOffer':
                low, high = clean_price(offer.get('lowPrice')), clean_price(offer.get('highPrice'))
            else:
                raise ValidationError('缺少价格')
            if low > high:
                raise ValidationError('价格范围无效')
        except ValidationError as exc:
            raise CollectionError('页面价格或币种不完整，未保存报价。') from exc
        prices.extend([low, high])
        currencies.add(currency)
        state = offer.get('availability', '')
        state = state.rsplit('/', 1)[-1] if isinstance(state, str) else ''
        availability.add(state)
        variant_url = offer.get('url') or owner.get('url') or owner.get('@id')
        variant_url = urljoin(target, variant_url) if matches(variant_url) else target
        variants.append({'name': plain_text(offer.get('name') or owner.get('name')) or '页面公开规格',
                         'sku': plain_text(offer.get('sku') or owner.get('sku')),
                         'size': plain_text(owner.get('size')), 'color': plain_text(owner.get('color')),
                         'price_low': str(low), 'price_high': str(high), 'currency': currency,
                         'availability': state, 'url': variant_url,
                         'is_range': low != high})
    if not prices or len(currencies) != 1:
        raise CollectionError('页面没有明确的单一币种报价。')
    title = node.get('name')
    reviews = product_reviews(node, target)
    if not reviews['review_samples']:
        samples = widget_review_samples(soup, node, target)
        if samples:
            reviews.update(review_samples=samples, review_sample_source='公开商品页 Judge.me 组件',
                           review_samples_limited=True, review_source=target)
    return {**product_content(node, target, variants), **reviews,
            'price_low': str(min(prices)), 'price_high': str(max(prices)), 'currency': currencies.pop(),
            'availability': next(iter(availability)) if len(availability) == 1 else 'Mixed',
            'price_title': title.strip()[:300] if isinstance(title, str) else '',
            'price_source': target, 'price_observed_at': timezone.now().strftime('%Y-%m-%d %H:%M UTC')}


def collect_catalog_prices(root, items, save, client=None, pause=time.sleep):
    root = store_url(root)
    own = client is None
    client = client or httpx.Client(transport=PublicProductTransport(), timeout=20, trust_env=False,
                                   follow_redirects=False, headers={'User-Agent': 'ShopHot/0.3 (public catalog research)'})
    try:
        def read(target, html=False):
            with client.stream('GET', target) as response:
                if response.status_code != 200:
                    raise CollectionError(f'公开页面返回 HTTP {response.status_code}，本批次已停止。')
                if html and 'text/html' not in response.headers.get('content-type', '').lower():
                    raise CollectionError('目标没有返回 HTML 商品页面，本批次已停止。')
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise CollectionError('公开页面超过 2 MB，本批次已停止。')
                return bytes(data)
        rules = RobotFileParser(root + '/robots.txt')
        rules.parse(read(root + '/robots.txt').decode('utf-8', errors='replace').splitlines())
        delay = max(1, rules.crawl_delay(AGENT) or 1)
        if delay > 30:
            raise CollectionError('店铺要求较长采集间隔，本次停止。')
        for index, item in enumerate(items[:BATCH_SIZE]):
            target = normalize_shopify_url(item['url'])
            if urlsplit(target).hostname != urlsplit(root).hostname:
                raise CollectionError('商品目录指向其他域名，本次停止。')
            if not rules.can_fetch(AGENT, target):
                save(index, {'price_error': 'robots.txt 不允许采集此商品。'})
                continue
            pause(delay)
            html = read(target, html=True)
            try:
                result = parse_catalog_price(html, target)
                result['price_error'] = ''
            except CollectionError as exc:
                result = {'price_error': str(exc)}
            save(index, result)
    except httpx.HTTPError as exc:
        raise CollectionError(f'公开页面网络请求失败（{type(exc).__name__}），本批次已停止。') from exc
    finally:
        if own:
            client.close()
