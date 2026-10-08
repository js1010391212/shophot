"""按 robots 与 sitemap 发现公开 Shopify 商品；不推算销量。"""
import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser
import httpx
from django.core.exceptions import ValidationError
from .collectors import CollectionError, MAX_BYTES
from .network import PublicProductTransport
from .validation import clean_url
from .shopify import normalize_shopify_url

AGENT = 'ShopHot'
LIMIT = 100


def store_url(value):
    parts = urlsplit(clean_url(value))
    if parts.scheme != 'https' or parts.port not in (None, 443) or parts.path not in ('', '/') or parts.query:
        raise ValidationError('请填写 HTTPS 店铺首页域名，不含路径或参数。')
    # 复用商品链接的域名验证，连接时另行检查 DNS 公网地址。
    normalize_shopify_url(urlunsplit(('https', parts.hostname, '/products/check', '', '')))
    return urlunsplit(('https', parts.hostname, '', '', ''))


def xml_document(data):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise CollectionError('站点地图含不支持的 XML 声明。')
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise CollectionError('站点地图 XML 无效。') from exc


def discover(url, client=None, pause=time.sleep):
    root_url = store_url(url)
    own_client = client is None
    client = client or httpx.Client(transport=PublicProductTransport(), timeout=20, trust_env=False, follow_redirects=False,
                                   headers={'User-Agent': 'ShopHot/0.3 (public catalog research)'})
    try:
        def read(target):
            parts = urlsplit(target)
            if parts.scheme != 'https' or parts.port not in (None, 443) or parts.username or parts.password or parts.hostname != urlsplit(root_url).hostname:
                raise CollectionError('站点地图指向其他域名，已停止。')
            with client.stream('GET', target) as response:
                if response.status_code == 429:
                    raise CollectionError('店铺目录限流，停止发现；请稍后重试。')
                if response.status_code != 200:
                    raise CollectionError(f'公开目录返回 HTTP {response.status_code}，未保存目录。')
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise CollectionError('目录响应超过 2 MB，已停止。')
                return bytes(data)
        robots_url = root_url + '/robots.txt'
        rules = RobotFileParser(robots_url)
        rules.parse(read(robots_url).decode('utf-8', errors='replace').splitlines())
        delay = max(1, rules.crawl_delay(AGENT) or 1)
        if delay > 30:
            raise CollectionError('店铺要求较长采集间隔，本次停止。')
        def sitemap(target):
            if not rules.can_fetch(AGENT, target):
                raise CollectionError('robots.txt 不允许读取该站点地图。')
            pause(delay)
            return xml_document(read(target))
        index = sitemap(root_url + '/sitemap.xml')
        tag = index.tag.rsplit('}', 1)[-1]
        limited = False
        if tag == 'sitemapindex':
            children = [node.text for node in index.findall('.//{*}loc') if node.text and
                        re.fullmatch(r'/sitemap_products[^/]*\.xml', urlsplit(node.text).path)]
            if not children:
                raise CollectionError('未找到公开商品站点地图。')
            limited = len(children) > 3
            docs = [sitemap(target) for target in children[:3]]
        elif tag == 'urlset':
            docs = [index]
        else:
            raise CollectionError('不支持的站点地图格式。')
        products = {}
        for doc in docs:
            for node in doc.findall('{*}url'):
                location = node.findtext('{*}loc') or ''
                if urlsplit(location).hostname != urlsplit(root_url).hostname or not rules.can_fetch(AGENT, location):
                    continue
                try:
                    normalized = normalize_shopify_url(location)
                except ValidationError:
                    continue
                if normalized in products:
                    continue
                if len(products) >= LIMIT:
                    limited = True
                    continue
                image = node.find('.//{*}image')
                products[normalized] = {'url': normalized, 'title': (image.findtext('{*}title') if image is not None else '') or urlsplit(normalized).path.rsplit('/', 1)[-1],
                                       'lastmod': (node.findtext('{*}lastmod') or '')[:50]}
        if not products:
            raise CollectionError('公开站点地图没有可识别商品。')
        for item in products.values():
            item['title'] = item['title'][:300]
        return {'products': list(products.values()), 'limited': limited}
    except httpx.HTTPError as exc:
        raise CollectionError(f'目录网络请求失败（{type(exc).__name__}）。') from exc
    finally:
        if own_client:
            client.close()
