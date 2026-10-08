"""速卖通公开页面采集：只接受明确的商品价格，不猜测销量或绕过访问验证。"""
import ipaddress
import json
import re
import socket
from urllib.parse import urljoin, urlsplit
import httpx
from bs4 import BeautifulSoup
from django.core.exceptions import ValidationError
from .validation import clean_count, clean_currency, clean_price, clean_rating
from .quote_identity import QuoteTarget

MAX_BYTES = 2 * 1024 * 1024


class CollectionError(Exception):
    """可显示给用户的采集失败原因。"""


def validate_target(url):
    """限制域名、协议、端口和地址；重定向的每一跳也必须校验。"""
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        valid_host = host == "aliexpress.com" or host.endswith(".aliexpress.com")
        if parts.scheme != "https" or not valid_host or parts.port not in (None, 443) or parts.username or parts.password:
            raise CollectionError("当前网页采集仅支持 https://*.aliexpress.com 的商品链接。")
        from .network import public_address
        public_address(host)
    except (ValueError, socket.gaierror) as exc:
        raise CollectionError("商品地址无效或域名无法解析。") from exc


def json_nodes(value):
    """兼容 JSON-LD 数组、@graph，以及嵌套 Product 节点。"""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from json_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from json_nodes(child)


def product_id(url):
    if not isinstance(url, str):
        return None
    match = re.fullmatch(r"/item/(\d+)\.html", urlsplit(url).path)
    return match.group(1) if match else None


def parse_product(html, target_url=None):
    soup = BeautifulSoup(html, "html.parser")
    products = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or script.get_text())
        except (ValueError, TypeError, RecursionError):
            continue
        for node in json_nodes(data):
            types = node.get("@type", [])
            if types != "Product" and not (isinstance(types, list) and "Product" in types):
                continue
            products.append(node)
    selected_offer = None
    if target_url is not None:
        from .page_import import normalize_aliexpress_url
        try:
            target = QuoteTarget(target_url, normalize_aliexpress_url, 'sku_id')
            node, selected_offer = target.select(products)
            # 字段类型校验失败也返回采集错误，不落入 worker 的内部异常分支。
            clean_price(selected_offer['price'])
            clean_currency(selected_offer['priceCurrency'])
        except (ValidationError, ValueError) as exc:
            message = ' '.join(exc.messages) if isinstance(exc, ValidationError) else '商品链接无效。'
            raise CollectionError(message) from exc
        products = [node]
    if len(products) > 1:
        raise CollectionError("页面包含多个商品，无法确定目标竞品；未保存价格。请记录明确商品的公开数据。")
    for node in products:
        # 无 target 的旧调用仍可解析匿名夹具；collect 始终传入明确目标。
        offers = selected_offer if selected_offer is not None else node.get("offers", {})
        offers = offers if isinstance(offers, list) else [offers]
        # 不把区间最低价当作明确成交价，也不从文本猜测销量。
        candidates = []
        for offer in offers:
            if not isinstance(offer, dict) or "price" not in offer or "priceCurrency" not in offer:
                continue
            if offer.get('@type') not in (None, 'Offer'):
                continue
            try:
                candidates.append((clean_price(offer["price"]), clean_currency(offer["priceCurrency"])))
            except ValidationError:
                continue
        if len(candidates) == 1:
            price, currency = candidates[0]
            rating = review_count = None
            aggregate = node.get("aggregateRating", {})
            if isinstance(aggregate, dict):
                # 不把其他评分尺度折算成五分制；无效的可选字段不影响明确价格。
                try:
                    if str(aggregate.get("bestRating", 5)) in ("5", "5.0", "5.00"):
                        rating = clean_rating(aggregate.get("ratingValue"))
                except ValidationError:
                    pass
                try:
                    review_count = clean_count(aggregate.get("reviewCount"))
                except ValidationError:
                    pass
            return {"price": price, "currency": currency, "sales": None,
                    "rating": rating, "review_count": review_count,
                    "title": node["name"].strip()[:300] if isinstance(node.get("name"), str) else None}
        if candidates:
            raise CollectionError("页面存在多个规格价格，请使用 CSV 导入明确规格的价格。")
    raise CollectionError("页面未提供可读取的明确商品价格；可能需要登录、动态加载或访问验证。可改用 CSV 导入。")


def collect(url):
    target_url = url
    try:
        from .network import PublicProductTransport
        with httpx.Client(timeout=httpx.Timeout(20, connect=10), follow_redirects=False, trust_env=False,
                          transport=PublicProductTransport(),
                          headers={"User-Agent": "ShopHot/0.1 (+personal seller analytics)"}) as client:
            for _ in range(5):
                validate_target(url)
                with client.stream("GET", url) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location:
                            raise CollectionError("网页重定向缺少目标地址。")
                        url = urljoin(url, location)
                        continue
                    if response.status_code != 200:
                        raise CollectionError(f"目标网站返回 HTTP {response.status_code}，未保存任何价格。")
                    if "text/html" not in response.headers.get("content-type", "").lower():
                        raise CollectionError("目标没有返回 HTML 商品页面。")
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise CollectionError("页面超过 2 MB，已停止下载。")
                        chunks.append(chunk)
                    html = b"".join(chunks)
                    if b'_____tmd_____' in html or b'x5secdata' in html:
                        raise CollectionError("速卖通要求访问验证，未取得商品数据。请接入已授权的官方商品 API，或记录实际页面公开数据。")
                    return parse_product(html, target_url=target_url)
            raise CollectionError("页面重定向次数过多。")
    except httpx.HTTPError as exc:
        # 不把代理信息、带认证参数的请求地址写入日志或用户消息。
        raise CollectionError(f"网络请求失败（{type(exc).__name__}），请检查网络访问设置。") from exc
