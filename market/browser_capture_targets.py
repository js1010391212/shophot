"""浏览器采集目标注册；不扩大旧文件导入或自动HTTP采集的支持范围。"""
from django.core.exceptions import ValidationError

from .ebay import normalize_ebay_url
from .otto import normalize_otto_url
from .page_import import identify_target, normalize_aliexpress_url
from .platforms import known_platform


CAPTURE_PLATFORMS = ('AliExpress', 'OTTO', 'eBay')


def identify_capture_target(value):
    if known_platform(value) == 'eBay':
        return 'eBay', normalize_ebay_url(value)
    if known_platform(value) not in ('AliExpress', 'OTTO'):
        raise ValidationError('浏览器采集首版只接入速卖通、OTTO和eBay的明确单商品。')
    return identify_target(value)


def target_configuration(value):
    platform, target = identify_capture_target(value)
    if platform == 'eBay':
        return platform, target, normalize_ebay_url, 'var'
    if platform == 'OTTO':
        return platform, target, normalize_otto_url, 'variationId'
    return platform, target, normalize_aliexpress_url, 'sku_id'
