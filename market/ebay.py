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
    query = parse_qs(parts.query, keep_blank_values=True)
    item = re.fullmatch(r'/itm/(?:[^/]+/)?([0-9]{1,80})/?', parts.path)
    catalog = re.fullmatch(r'/p/[0-9]{1,80}/?', parts.path)
    listing_ids = query.get('iid', [])
    if catalog:
        # /p/ 后的编号是产品目录(ePID)，只有明确 iid 才指向一条卖家刊登。
        if len(listing_ids) != 1 or not re.fullmatch(r'[0-9]{9,15}', listing_ids[0]):
            raise ValidationError('eBay目录页须含唯一有效iid刊登编号，请打开具体商品详情。')
        item_id = listing_ids[0]
    elif item:
        item_id = item[1]
        if listing_ids and (len(listing_ids) != 1 or listing_ids[0] != item_id):
            raise ValidationError('eBay链接中的iid与商品刊登编号冲突或重复。')
    else:
        raise ValidationError('请使用eBay完整/itm/商品链接或含iid的/p/目录链接，店铺和搜索页未接入。')
    variants = query.get('var', [])
    if variants and (len(variants) != 1 or not re.fullmatch(r'[0-9]{1,80}', variants[0])):
        raise ValidationError('eBay var规格编号无效或重复。')
    # 保留地区站，不把同编号的跨地区报价归为同一目标。
    return urlunsplit(('https', 'www.' + domain, '/itm/' + item_id,
                      urlencode({'var': variants[0]}) if variants else '', ''))
