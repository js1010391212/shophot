"""浏览器主动观测的输入契约；仅校验，不请求网络、不保存观测。"""
import json
import re
from datetime import timedelta
from urllib.parse import urlsplit
from uuid import UUID

from django.core import signing
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .browser_capture_targets import identify_capture_target, target_configuration
from .quote_identity import QuoteTarget
from .validation import clean_currency, clean_price


FIELDS = frozenset({
    'schema_version', 'capture_id', 'adapter_version', 'platform', 'url',
    'product_id', 'sku_id', 'title', 'price', 'currency', 'quote_type',
    'market_country', 'conditions', 'observed_at', 'evidence',
})
MAX_CAPTURE_BYTES = 16 * 1024
PREVIEW_SALT = 'browser-capture-preview-v1'
PREVIEW_MAX_AGE = 20 * 60


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError('浏览器观测JSON包含重复字段，无法确认内容。')
        result[key] = value
    return result


def _reject_constant(value):
    raise ValidationError('浏览器观测JSON不接受NaN或Infinity。')


def parse_capture(raw, target_url, *, now=None):
    """接收有界UTF-8 JSON字节；目标仍由服务器提供，不创建记录。"""
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_CAPTURE_BYTES:
        raise ValidationError('浏览器观测须为JSON字节正文，最大16KiB。')
    try:
        payload = json.loads(
            raw.decode('utf-8'), object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise ValidationError('浏览器观测JSON编码、格式或嵌套层级无效。')
    return validate_capture(payload, target_url, now=now)


def _preview_context(target_url, owner_id, product_pk):
    if any(type(value) is not int or value <= 0 for value in (owner_id, product_pk)):
        raise ValidationError('预览须绑定已登录账号及已存在商品。')
    _, target = identify_capture_target(target_url)
    return {'owner': owner_id, 'product': product_pk, 'url': target}


def sign_preview(raw, target_url, *, owner_id, product_pk, now=None):
    """控制器提供账号与商品；签名不代替登录、CSRF或确认事务。"""
    context = _preview_context(target_url, owner_id, product_pk)
    capture = parse_capture(raw, context['url'], now=now)
    return signing.dumps({**context, 'capture': capture}, salt=PREVIEW_SALT, compress=True)


def load_preview(token, target_url, *, owner_id, product_pk):
    """仅读取本模块生成的20分钟预览；商品当前URL变更会使确认无效。"""
    context = _preview_context(target_url, owner_id, product_pk)
    token = _text(token, '签名预览', 32000)
    try:
        data = signing.loads(token, salt=PREVIEW_SALT, max_age=PREVIEW_MAX_AGE)
    except (signing.BadSignature, ValueError, TypeError):
        raise ValidationError('浏览器观测预览无效或已过期，请重新采集。')
    if (not isinstance(data, dict) or set(data) != {'owner', 'product', 'url', 'capture'}
            or any(data[key] != value for key, value in context.items())
            or not isinstance(data['capture'], dict) or set(data['capture']) != FIELDS):
        raise ValidationError('预览的账号、商品或规格已变更，请重新采集。')
    return data['capture']


def _text(value, label, limit):
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ud800-\udfff]', value)):
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

    platform, target, normalizer, variant_key = target_configuration(target_url)
    if payload['platform'] != platform:
        raise ValidationError('观测平台与目标商品不一致。')
    captured_url = _text(payload['url'], '来源商品链接', 500)
    identity = QuoteTarget(target, normalizer, variant_key)
    if not identity.matches(captured_url, strict=True):
        raise ValidationError('观测链接的商品或规格与目标不一致。')
    path = urlsplit(target).path
    product_id = (
        path.rsplit('-', 1)[-1].rstrip('/') if platform == 'OTTO'
        else path.rsplit('/', 1)[-1] if platform == 'eBay'
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
