"""OTTO 商品链接规范化与兼容解析入口。"""
import re
from urllib.parse import urlsplit, urlunsplit, parse_qs, urlencode
from django.core.exceptions import ValidationError
from .validation import clean_url


def normalize_otto_url(value):
    try:
        parts=urlsplit(clean_url(value))
        port=parts.port
    except ValueError:
        raise ValidationError('商品链接端口无效。')
    if parts.scheme!='https' or parts.hostname not in ('otto.de','www.otto.de') or port not in (None,443):
        raise ValidationError('请使用 https://www.otto.de 的公开商品链接。')
    if not re.fullmatch(r'/p/[a-zA-Z0-9%_-]+-(?:S|C)[a-zA-Z0-9]+/?',parts.path):
        raise ValidationError('OTTO 本模块只支持 /p/ 商品链接，店铺目录尚未接入。')
    params=parse_qs(parts.query,keep_blank_values=True)
    variation=params.get('variationId',[])
    if variation and (len(variation)!=1 or not re.fullmatch(r'[A-Za-z0-9]{1,80}',variation[0])):
        raise ValidationError('OTTO variationId 规格编号无效或重复。')
    return urlunsplit(('https','www.otto.de',parts.path.rstrip('/')+'/',urlencode({'variationId':variation[0]}) if variation else '', ''))


def parse_page(raw, target):
    from .structured_page import parse_structured_page
    return parse_structured_page(raw, target, normalize_otto_url, 'variationId', 'OTTO')
