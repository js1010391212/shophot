"""离线商品文件适配：不发网络请求，不执行页面脚本。"""
import hashlib
import re
from urllib.parse import urlsplit, urlunsplit, parse_qs, urlencode
from django.core.exceptions import ValidationError
from .validation import clean_url

SUPPORTED_PLATFORMS = ('OTTO', 'AliExpress')


def normalize_aliexpress_url(value):
    try:
        parts = urlsplit(clean_url(value))
        port = parts.port
    except ValueError:
        raise ValidationError('商品链接端口无效。')
    host = parts.hostname or ''
    if parts.scheme != 'https' or not (host == 'aliexpress.com' or host.endswith('.aliexpress.com')) or port not in (None, 443):
        raise ValidationError('文件导入目前支持速卖通 aliexpress.com 的 HTTPS 商品链接；地区站、短链接和店铺目录尚未接入。')
    if not re.fullmatch(r'/item/\d+\.html', parts.path):
        raise ValidationError('请使用完整速卖通商品链接 /item/商品编号.html。')
    values = parse_qs(parts.query, keep_blank_values=True).get('sku_id', [])
    if values and (len(values) != 1 or not re.fullmatch(r'\d{1,80}', values[0])):
        raise ValidationError('sku_id 规格编号无效或重复。')
    return urlunsplit(('https', 'www.aliexpress.com', parts.path, urlencode({'sku_id': values[0]}) if values else '', ''))


def identify_target(value):
    from .platforms import known_platform
    from .otto import normalize_otto_url
    platform = known_platform(value)
    if platform == 'OTTO':
        return platform, normalize_otto_url(value)
    if platform == 'AliExpress':
        return platform, normalize_aliexpress_url(value)
    raise ValidationError('页面文件导入目前只接入 OTTO 和速卖通商品；Shopify、SHEIN、Ozon 文件适配尚未接入。')


def parse_page(raw, target, platform):
    from .otto import normalize_otto_url
    from .structured_page import parse_structured_page
    detected, target = identify_target(target)
    if detected != platform:
        raise ValidationError('商品链接与保存的平台不一致，请先核对商品资料。')
    normalizer, key = (normalize_otto_url, 'variationId') if platform == 'OTTO' else (normalize_aliexpress_url, 'sku_id')
    result = parse_structured_page(raw, target, normalizer, key, platform)
    result['file_fingerprint'] = hashlib.sha256(raw).hexdigest()[:16]
    return result
