"""联盟单商品响应归一化；无网络、数据库、保存或浏览器观测副作用。"""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, DecimalException, localcontext
import json
import re
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError

from .validation import clean_count, clean_currency, clean_price


METHOD = 'aliexpress.affiliate.productdetail.get'
DOCUMENTATION = 'https://jaq-doc.alibaba.com/docs/api.htm?apiId=48595'
MAX_RESPONSE_BYTES = 256 * 1024
TARGET_CURRENCIES = frozenset('USD GBP CAD EUR UAH MXN TRY RUB BRL AUD INR JPY IDR SEK KRW'.split())
PRICE_FIELDS = ('sale_price', 'original_price', 'app_sale_price',
                'target_sale_price', 'target_original_price', 'target_app_sale_price')
PROMO_FIELDS = ('promo_code', 'code_campaigntype', 'code_value', 'code_mini_spend',
               'code_availabletime_start', 'code_availabletime_end', 'code_quantity')
_ENVELOPE = 'aliexpress_affiliate_productdetail_get_response'
_CONTROL = re.compile(r'[\x00-\x1f\x7f\ud800-\udfff]')
_MESSAGES = {
    'invalid_context': '请求上下文无效；须指定单商品、明确请求条件与带时区的开始/接收时间。',
    'response_too_large': '接口响应超过只读预览大小上限。',
    'invalid_json': '接口响应须为有界 UTF-8 JSON，不能是网页或非标准数值。',
    'duplicate_key': '接口响应包含重复 JSON 字段，无法确定报价。',
    'invalid_structure': '接口响应结构与已核对的联盟详情 JSON 契约不符。',
    'vendor_error': '接口返回错误；尚未验证该错误码含义，请核实获批接口文档。',
    'service_error': '联盟详情返回非成功状态；不按未核实的错误码猜测原因。',
    'ambiguous_product': '单商品请求返回多条商品，无法确定唯一报价。',
    'identity_mismatch': '返回的商品身份与请求不一致。',
    'invalid_field': '返回字段类型、长度或取值不符合只读预览要求。',
    'incomplete_price': '价格与币种未成对提供，无法确定该报价。',
    'unsupported_price': '价格须为非负、可精确表示到分且在项目金额范围内的十进制字符串。',
    'currency_mismatch': '目标价格币种与请求目标币种不一致。',
}
_SAFE_FIELDS = set(PRICE_FIELDS) | {f'{f}_currency' for f in PRICE_FIELDS} | set(PROMO_FIELDS) | {
    'product_id', 'product_title', 'product_detail_url', 'evaluate_rate', 'lastest_volume',
    'discount', 'promo_code_info', 'current_record_count',
}


class AffiliateResponseError(ValueError):
    """仅固定提示/字段名/有界数字码；不回显原始响应或供应方 message。"""

    def __init__(self, code, *, field=None, vendor_code=None):
        self.code = code if code in _MESSAGES else 'invalid_structure'
        self.field = field if field in _SAFE_FIELDS else None
        self.vendor_code = vendor_code if type(vendor_code) is int and 0 <= vendor_code <= 2147483647 else None
        super().__init__(_MESSAGES[self.code])

    @property
    def messages(self):
        return [str(self)]

    def as_dict(self):
        return {'code': self.code, 'message': str(self), 'field': self.field,
                'vendor_code': self.vendor_code}


def _product_id(value):
    if type(value) is int:
        value = str(value)
    if not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]{0,79}', value):
        raise AffiliateResponseError('invalid_field', field='product_id')
    return value


@dataclass(frozen=True, slots=True)
class AffiliateRequestContext:
    product_id: str
    country: str | None
    target_currency: str | None
    requested_at: datetime
    received_at: datetime

    def __post_init__(self):
        try:
            if type(self.product_id) is not str or _product_id(self.product_id) != self.product_id:
                raise ValueError
            if self.country is not None and (not isinstance(self.country, str) or
                                              not re.fullmatch(r'[A-Z]{2}', self.country)):
                raise ValueError
            if self.target_currency is not None and (not isinstance(self.target_currency, str) or
                                                      self.target_currency not in TARGET_CURRENCIES):
                raise ValueError
            for moment in (self.requested_at, self.received_at):
                if not isinstance(moment, datetime) or moment.utcoffset() is None:
                    raise ValueError
            if self.received_at.astimezone(timezone.utc) < self.requested_at.astimezone(timezone.utc):
                raise ValueError
        except (ValueError, TypeError, OverflowError):
            raise AffiliateResponseError('invalid_context') from None

    def as_dict(self):
        return {'product_id': self.product_id, 'country': self.country, 'target_currency': self.target_currency,
                'requested_at': self.requested_at.isoformat(),
                'received_at': self.received_at.isoformat()}


@dataclass(frozen=True, slots=True)
class AffiliatePrice:
    field: str
    amount: Decimal
    currency: str

    def as_dict(self):
        return {'amount': format(self.amount, '.2f'), 'currency': self.currency}


@dataclass(frozen=True, slots=True)
class AffiliateProduct:
    product_id: str
    title: str
    product_url: str
    prices: tuple[AffiliatePrice, ...]
    evaluate_rate: str | None
    lastest_volume: int | None
    discount: str | None
    promo_code_info: tuple[tuple[str, str], ...]

    def as_dict(self):
        prices = {field: None for field in PRICE_FIELDS}
        prices.update({quote.field: quote.as_dict() for quote in self.prices})
        return {'product_id': self.product_id, 'title': self.title, 'product_url': self.product_url,
                'prices': prices, 'sku_id': None, 'specification_status': 'unknown',
                'may_use_as_selected_sku_cost': False, 'evaluate_rate': self.evaluate_rate,
                'lastest_volume': self.lastest_volume, 'recent_volume_window': None,
                'discount': self.discount, 'promo_code_info': dict(self.promo_code_info)}


@dataclass(frozen=True, slots=True)
class AffiliatePreview:
    context: AffiliateRequestContext
    product: AffiliateProduct | None
    reported_record_count: int | None

    @property
    def status(self):
        return 'ok' if self.product is not None else 'empty'

    def as_dict(self):
        return {'status': self.status, 'source': {'method': METHOD, 'documentation': DOCUMENTATION},
                'request': self.context.as_dict(), 'reported_record_count': self.reported_record_count,
                'product': self.product.as_dict() if self.product is not None else None}


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AffiliateResponseError('duplicate_key')
        result[key] = value
    return result


def _nonstandard_number(_value):
    raise AffiliateResponseError('invalid_json')


def _integer(value):
    if len(value) > 80:
        raise AffiliateResponseError('invalid_json')
    return int(value)


def _decimal_number(value):
    if len(value) > 80:
        raise AffiliateResponseError('invalid_json')
    try:
        return Decimal(value)
    except DecimalException:
        raise AffiliateResponseError('invalid_json') from None


def _parse(body):
    if type(body) is not bytes:
        raise AffiliateResponseError('invalid_json')
    if len(body) > MAX_RESPONSE_BYTES:
        raise AffiliateResponseError('response_too_large')
    try:
        data = json.loads(body.decode('utf-8'), object_pairs_hook=_pairs,
                          parse_int=_integer, parse_float=_decimal_number, parse_constant=_nonstandard_number)
    except AffiliateResponseError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        # Do not expose JSONDecodeError snippets containing credentials.
        raise AffiliateResponseError('invalid_json') from None
    # Iterative bounds also reject deeply nested *unknown* fields; never echo them.
    pending = [(data, 0)]
    nodes = 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if depth > 24 or nodes > 10000:
            raise AffiliateResponseError('invalid_structure')
        if isinstance(value, dict):
            if any(len(key) > 128 for key in value):
                raise AffiliateResponseError('invalid_structure')
            pending.extend((v, depth + 1) for v in value.values())
        elif isinstance(value, list):
            pending.extend((v, depth + 1) for v in value)
        elif isinstance(value, str) and len(value) > 8192:
            raise AffiliateResponseError('invalid_structure')
    return data


def _object(value):
    if not isinstance(value, dict):
        raise AffiliateResponseError('invalid_structure')
    return value


def _text(value, field, limit=240):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or _CONTROL.search(value):
        raise AffiliateResponseError('invalid_field', field=field)
    return value.strip()


def _missing(value):
    return value is None or value == ''


def _count(value, field):
    if type(value) is not int:
        raise AffiliateResponseError('invalid_field', field=field)
    try:
        return clean_count(value)
    except ValidationError:
        raise AffiliateResponseError('invalid_field', field=field) from None


def _prices(product, context):
    quotes = []
    for field in PRICE_FIELDS:
        price, currency = product.get(field), product.get(f'{field}_currency')
        if _missing(price) and _missing(currency):
            continue
        if _missing(price) or _missing(currency):
            raise AffiliateResponseError('incomplete_price', field=field)
        if not isinstance(price, str) or not re.fullmatch(r'[0-9]{1,10}(?:\.[0-9]{1,20})?', price):
            raise AffiliateResponseError('unsupported_price', field=field)
        try:
            with localcontext() as decimal_context:
                decimal_context.prec = 40
                amount = clean_price(price)
        except ValidationError:
            raise AffiliateResponseError('unsupported_price', field=field) from None
        try:
            currency = clean_currency(currency)
        except ValidationError:
            raise AffiliateResponseError('invalid_field', field=f'{field}_currency') from None
        if field.startswith('target_') and context.target_currency is not None and currency != context.target_currency:
            raise AffiliateResponseError('currency_mismatch', field=f'{field}_currency')
        quotes.append(AffiliatePrice(field, amount, currency))
    return tuple(quotes)


def _url(value, identity):
    # Retain only a canonical identity link, never response tracking/auth query strings.
    if not _missing(value):
        value = _text(value, 'product_detail_url', 1000)
        try:
            u = urlsplit(value)
            if u.scheme != 'https' or u.hostname not in ('aliexpress.com', 'www.aliexpress.com') or u.port not in (None, 443) or u.username or u.password:
                raise ValueError
            if u.path != f'/item/{identity}.html':
                raise AffiliateResponseError('identity_mismatch')
        except AffiliateResponseError:
            raise
        except ValueError:
            raise AffiliateResponseError('invalid_field', field='product_detail_url') from None
    return f'https://www.aliexpress.com/item/{identity}.html'


def normalize_affiliate_response(raw: bytes, context: AffiliateRequestContext) -> AffiliatePreview:
    """仅支持官方 non-simplify JSON 包裹；单商品、无自动选价与副作用。"""
    if type(context) is not AffiliateRequestContext:
        raise AffiliateResponseError('invalid_context')
    data = _object(_parse(raw))
    if set(data) == {'error_response'}:
        error = _object(data['error_response'])
        raise AffiliateResponseError('vendor_error', vendor_code=error.get('code'))
    if set(data) != {_ENVELOPE}:
        raise AffiliateResponseError('invalid_structure')
    response = _object(_object(data[_ENVELOPE]).get('resp_result'))
    code = response.get('resp_code')
    if type(code) is not int:
        raise AffiliateResponseError('invalid_structure')
    if code != 200:
        raise AffiliateResponseError('service_error', vendor_code=code)
    result = _object(response.get('result'))
    count = result.get('current_record_count')
    count = _count(count, 'current_record_count') if count is not None else None
    products = _object(result.get('products')).get('product')
    if not isinstance(products, list):
        raise AffiliateResponseError('invalid_structure')
    if not products:
        return AffiliatePreview(context, None, count)
    if len(products) != 1:
        raise AffiliateResponseError('ambiguous_product')
    product = _object(products[0])
    identity = _product_id(product.get('product_id'))
    if identity != context.product_id:
        raise AffiliateResponseError('identity_mismatch')
    title = _text(product.get('product_title'), 'product_title')
    url = _url(product.get('product_detail_url'), identity)
    prices = _prices(product, context)
    rate = product.get('evaluate_rate')
    if not _missing(rate):
        if not isinstance(rate, str) or not re.fullmatch(r'[0-9]{1,3}(?:\.[0-9]{1,2})?%', rate) or Decimal(rate[:-1]) > 100:
            raise AffiliateResponseError('invalid_field', field='evaluate_rate')
    else:
        rate = None
    volume = product.get('lastest_volume')
    volume = _count(volume, 'lastest_volume') if volume is not None else None
    discount = product.get('discount')
    discount = _text(discount, 'discount', 40) if not _missing(discount) else None
    promo = product.get('promo_code_info')
    if promo is None:
        promo = {}
    elif not isinstance(promo, dict):
        raise AffiliateResponseError('invalid_field', field='promo_code_info')
    conditions = tuple((field, _text(promo[field], field)) for field in PROMO_FIELDS
                       if field in promo and not _missing(promo[field]))
    return AffiliatePreview(context, AffiliateProduct(identity, title, url, prices, rate, volume, discount, conditions), count)
