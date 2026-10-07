"""共享输入校验，网页、CSV 和采集器使用一致的数据规则。"""
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit, urlunsplit
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator


def clean_url(value):
    value = value.strip()
    URLValidator(schemes=["http", "https"])(value)
    parts = urlsplit(value)
    if parts.username or parts.password:
        raise ValidationError("链接不能包含账号或密码。")
    if len(value) > 500:
        raise ValidationError("链接不能超过 500 个字符。")
    # 去除片段，但保留可能影响商品身份的查询参数。
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ""))


def clean_price(value):
    try:
        price = Decimal(str(value))
        if not price.is_finite() or price < 0 or price > Decimal("9999999999.99"):
            raise ValueError
        if price != price.quantize(Decimal("0.01")):
            raise ValueError
        return price.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ValidationError("价格须为非负数，最多两位小数且不超过 9999999999.99。")


def clean_currency(value):
    currency = value.strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValidationError("币种须为三个英文字母，例如 USD、CNY。")
    return currency
