"""浏览器主动观测的输入契约；仅校验，不请求网络、不保存观测。"""
import re
from datetime import timedelta
from urllib.parse import urlsplit
from uuid import UUID

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .otto import normalize_otto_url
from .page_import import identify_target, normalize_aliexpress_url
from .quote_identity import QuoteTarget
from .validation import clean_currency, clean_price


FIELDS = frozenset({
    'schema_version', 'capture_id', 'adapter_version', 'platform', 'url',
    'product_id', 'sku_id', 'title', 'price', 'currency', 'quote_type',
    'market_country', 'conditions', 'observed_at', 'evidence',
})


def _text(value, label, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValidationError(f'{label}须为非空文本，最多{limit}个字符。')
    return value.strip()


def validate_capture(payload, target_url, *, now=None):
    """校验受控字段与服务器指定目标；结果不代表实站真实性或保存授权。"""
    if not isinstance(payload, dict) or set(payload) != FIELDS:
        raise ValidationError('浏览器观测字段缺失或包含未允许的字段。')
    if type(payload['schema_version']) is not int or payload['schema_version'] != 1:
        raise ValidationError('浏览器观测协议版本不支持。')
    capture_id = _text(payload['capture_id'], '观测编号', 36)
    try:
        if str(UUID(capture_id)) != capture_id:
            raise ValueError
    except ValueError:
        raise ValidationError('观测编号须为规范的UUID。')
    adapter = _text(payload['adapter_version'], '适配器版本', 48)
    if not re.fullmatch(r'[a-z][a-z0-9_-]{0,30}/[1-9][0-9]{0,5}', adapter):
        raise ValidationError('适配器版本须为名称/版本编号。')

    platform, target = identify_target(target_url)
    if payload['platform'] != platform:
        raise ValidationError('观测平台与目标商品不一致。')
    captured_url = _text(payload['url'], '来源商品链接', 500)
    normalizer, variant_key = (
        (normalize_otto_url, 'variationId') if platform == 'OTTO'
        else (normalize_aliexpress_url, 'sku_id')
    )
    identity = QuoteTarget(target, normalizer, variant_key)
    if not identity.matches(captured_url, strict=True):
        raise ValidationError('观测链接的商品或规格与目标不一致。')
    path = urlsplit(target).path
    product_id = (
        path.rsplit('-', 1)[-1].rstrip('/') if platform == 'OTTO'
        else path.rsplit('/', 1)[-1].removesuffix('.html')
    )
    if payload['product_id'] != product_id:
        raise ValidationError('商品编号与链接不一致。')
    if payload['sku_id'] != (identity.variant or None):
        raise ValidationError('规格编号与目标链接不一致；未知规格须为空。')
    if payload['quote_type'] != 'current':
        raise ValidationError('首版只接受明确的当前报价，不接受区间或划线价格。')
    # JSON 数值经过浮点转换可能丢精度；发送端必须保留十进制文本。
    price = _text(payload['price'], '价格', 13)
    if not re.fullmatch(r'[0-9]{1,10}(?:\.[0-9]{1,2})?', price):
        raise ValidationError('价格须为最多两位小数的十进制文本。')
    price = str(clean_price(price))
    currency = clean_currency(payload['currency'])
    country = payload['market_country']
    if country is not None and (
        not isinstance(country, str) or not re.fullmatch(r'[A-Z]{2}', country)
    ):
        raise ValidationError('收货国家须为两位大写代码或空值，不从语言猜测。')
    conditions = payload['conditions']
    if not isinstance(conditions, list) or len(conditions) > 5:
        raise ValidationError('报价条件最多5条。')
    conditions = [_text(item, '报价条件', 160) for item in conditions]
    title = _text(payload['title'], '商品标题', 240)
    evidence = _text(payload['evidence'], '可见报价证据', 500)

    observed_text = _text(payload['observed_at'], '观测时间', 40)
    try:
        observed = parse_datetime(observed_text)
    except ValueError:
        observed = None
    if observed is None or timezone.is_naive(observed):
        raise ValidationError('观测时间须包含明确时区。')
    current = now if now is not None else timezone.now()
    if not current - timedelta(minutes=10) <= observed <= current + timedelta(minutes=2):
        raise ValidationError('观测已过期或时间超前，请重新点击采集。')
    return {
        **payload, 'url': target, 'capture_id': capture_id,
        'adapter_version': adapter, 'title': title, 'price': price,
        'currency': currency, 'conditions': conditions,
        'observed_at': observed.isoformat(), 'evidence': evidence,
    }
