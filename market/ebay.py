"""eBay单商品浏览器目标规范化；不请求页面或调用API。"""
import re
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from django.core.exceptions import ValidationError

from .validation import clean_url


EBAY_DOMAINS = ('ebay.com', 'ebay.co.uk', 'ebay.de', 'ebay.fr', 'ebay.it',
                'ebay.es', 'ebay.ca', 'ebay.com.au', 'ebay.ie', 'ebay.nl')


def normalize_ebay_url(value):
    if not isinstance(value, str):
        raise ValidationError('eBay商品链接须为文本。')
    try:
        parts = urlsplit(clean_url(value))
        port = parts.port
    except ValueError:
        raise ValidationError('eBay商品链接端口无效。')
    host = parts.hostname or ''
    domain = host.removeprefix('www.')
    if parts.scheme != 'https' or domain not in EBAY_DOMAINS or port not in (None, 443):
        raise ValidationError('请使用已支持eBay站点的HTTPS商品链接；短链接、跟踪跳转和未知地区站未接入。')
    item = re.fullmatch(r'/itm/(?:[^/]+/)?([0-9]{1,80})/?', parts.path)
    if not item:
        raise ValidationError('请使用eBay完整/itm/商品编号链接，店铺和搜索页未接入。')
    variants = parse_qs(parts.query, keep_blank_values=True).get('var', [])
    if variants and (len(variants) != 1 or not re.fullmatch(r'[0-9]{1,80}', variants[0])):
        raise ValidationError('eBay var规格编号无效或重复。')
    # 保留地区站，不把同编号的跨地区报价归为同一目标。
    return urlunsplit(('https', 'www.' + domain, '/itm/' + item[1],
                      urlencode({'var': variants[0]}) if variants else '', ''))
