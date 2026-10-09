"""物流计费服务：Decimal 进位、有效期、币种和报价条件由服务端验证。"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
import hashlib
import json
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import ShippingRate
from .sf_rates import SF_ECONOMY_PARCEL_ZONES

D = Decimal
SF_SOURCE = 'https://www.sf-international.com/cn/sc/support/querySupport/fee_rate'
SF_PDF = 'https://www.sf-international.com/cms/cms-service/admin/file/get/d47b68236d174adea90e2ba383d072001488926341242949632.pdf'
COUNTRIES = [('CN', '中国内地'), ('US', '美国'), ('GB', '英国'), ('DE', '德国'), ('FR', '法国'),
             ('CA', '加拿大'), ('AU', '澳大利亚'), ('JP', '日本'), ('SG', '新加坡'), ('HK', '中国香港'),
             ('KR', '韩国'), ('IT', '意大利'), ('ES', '西班牙'), ('NL', '荷兰'), ('RU', '俄罗斯'),
             ('PL', '波兰'), ('BR', '巴西'), ('MX', '墨西哥'), ('AE', '阿联酋'), ('VN', '越南')]
COUNTRY_NAMES = dict(COUNTRIES)
RATE_FIELDS = ('name', 'carrier', 'origin', 'destination', 'currency', 'method', 'min_weight', 'max_weight',
               'step_weight', 'per_kg', 'first_weight', 'first_price', 'step_price', 'fixed_fee',
               'fuel_basis', 'volume_divisor', 'effective_from', 'effective_until', 'source_url', 'notes')


@dataclass
class Quote:
    key: str
    name: str
    carrier: str
    origin: str
    destination: str
    currency: str
    method: str
    min_weight: Decimal
    max_weight: Decimal
    step_weight: Decimal
    fixed_fee: Decimal
    volume_divisor: int | None
    effective_from: date
    fuel_basis: str = 'freight'
    effective_until: date | None = None
    per_kg: Decimal | None = None
    first_weight: Decimal | None = None
    first_price: Decimal | None = None
    step_price: Decimal | None = None
    source_url: str = ''
    notes: str = ''
    source: str = 'public'
    checked_at: str = ''
    table: dict = field(default_factory=dict)

    @property
    def route(self):
        return f'{COUNTRY_NAMES.get(self.origin, self.origin)} → {COUNTRY_NAMES.get(self.destination, self.destination)}'

    @property
    def label(self):
        prefix = '公开参考' if self.source == 'public' else '我的报价'
        return f'{prefix} · {self.name} · {self.route} · {self.currency}'

    def metadata(self):
        return {'name': self.name, 'route': self.route, 'currency': self.currency,
                'min_weight': str(self.min_weight), 'max_weight': str(self.max_weight),
                'step_weight': str(self.step_weight), 'volume_divisor': self.volume_divisor,
                'effective_from': self.effective_from.isoformat(), 'source_url': self.source_url,
                'notes': self.notes, 'checked_at': self.checked_at,
                'source': '官方公布参考价' if self.source == 'public' else '自己的报价', 'fuel_basis': self.fuel_basis}


def public_quotes():
    # Page 4 explicit parcel bands; >=20kg changes tariff and is not extrapolated.
    zones = SF_ECONOMY_PARCEL_ZONES
    routes = [('US', 6), ('GB', 7), ('DE', 7), ('FR', 7), ('CA', 6), ('AU', 4), ('JP', 3), ('SG', 2)]
    return [Quote(
        key=f'public:sf-economy-{country}', name='顺丰国际特惠 · 包裹', carrier='顺丰国际',
        origin='CN', destination=country, currency='CNY', method='table', min_weight=D('.5'),
        max_weight=D('19.5'), step_weight=D('.5'), fixed_fee=D('0'), volume_divisor=5000,
        effective_from=date(2026, 1, 20), source_url=SF_SOURCE, checked_at='2026-10-09',
        notes='中国内地出口寄付包裹公布价，非货代协议价。基础运费未含燃油、偏远地区、特殊处理、税项及报关等费用；实际收寄条件与结算以承运商为准。当前录入 0.5–19.5 kg 的逐档包裹价；20 kg 及以上改用每公斤运价及不同进位规则，尚未录入，不能外推。',
        table={D(i + 1) / 2: D(price) for i, price in enumerate(zones[zone])}) for country, zone in routes]


def quotes_for(user, today=None):
    today = today or timezone.localdate()
    quotes = public_quotes()
    if user.is_authenticated:
        for rate in ShippingRate.objects.filter(owner=user, active=True):
            quotes.append(Quote(key=f'user:{rate.pk}', source=rate.source,
                                **{key: getattr(rate, key) for key in RATE_FIELDS}))
    return [q for q in quotes if q.effective_from <= today and (not q.effective_until or q.effective_until >= today)]


def rate_payload(data):
    return {key: (value.isoformat() if isinstance(value, date) else format(value.normalize(), 'f') if isinstance(value, Decimal) else value)
            for key in RATE_FIELDS for value in [data.get(key)]}


def rate_fingerprint(data):
    return hashlib.sha256(json.dumps(rate_payload(data), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def money(value):
    return value.quantize(D('.01'), rounding=ROUND_HALF_UP)


def estimate(quote, *, weight, length=None, width=None, height=None, fuel_rate, extra, exchange_rate, currency, units=1):
    today = timezone.localdate()
    if quote.effective_from > today or (quote.effective_until and quote.effective_until < today):
        raise ValidationError('该报价不在生效期内，请重新选择。')
    if weight <= 0 or fuel_rate < 0 or extra < 0 or exchange_rate <= 0 or units < 1:
        raise ValidationError('重量、费用或汇率无效。')
    volume_weight = None
    if quote.volume_divisor:
        if not all(v is not None and v > 0 for v in (length, width, height)):
            raise ValidationError('该线路计体积重，请填写包装后的长、宽、高。')
        volume_weight = length * width * height / quote.volume_divisor
    raw_weight = max(weight, volume_weight or D('0'), quote.min_weight)
    if quote.method == 'first_step':
        billed = quote.first_weight + max(D('0'), ((raw_weight - quote.first_weight) / quote.step_weight).to_integral_value(rounding=ROUND_CEILING)) * quote.step_weight
    else:
        billed = (raw_weight / quote.step_weight).to_integral_value(rounding=ROUND_CEILING) * quote.step_weight
    if billed > quote.max_weight:
        volume_text = f'{format(volume_weight, "f")} kg' if volume_weight is not None else '不适用（该报价不计体积重）'
        raise ValidationError(
            f'实重 {format(weight, "f")} kg，体积重 {volume_text}，进位后计费重 {format(billed, "f")} kg；'
            f'超过当前录入报价上限 {format(quote.max_weight, "f")} kg，无法估价，不能外推价格。'
            '请改选覆盖该计费重量的适用报价，或核实后手填实际单件运费。'
        )
    if quote.method == 'table':
        if billed not in quote.table:
            raise ValidationError('报价表没有该计费重量，不能估价。')
        freight = quote.table[billed]
    elif quote.method == 'per_kg':
        freight = money(billed * quote.per_kg)
    else:
        freight = money(quote.first_price + ((billed - quote.first_weight) / quote.step_weight) * quote.step_price)
    base = freight + quote.fixed_fee
    fuel_base = base if quote.fuel_basis == 'subtotal' else freight
    fuel = money(fuel_base * fuel_rate / 100)
    total = money(base + fuel + extra)
    fx = D('1') if currency == quote.currency else exchange_rate
    converted_package = money(total * fx)
    converted = money(converted_package / units)
    if converted > D('9999999999.99'):
        raise ValidationError('换算后的运费超出利润工具金额范围。')
    if quote.method == 'table':
        pricing_rule = f'官方包裹价表 {format(billed, "f")} kg 档位'
    elif quote.method == 'per_kg':
        pricing_rule = f'{format(billed, "f")} kg × {quote.per_kg} {quote.currency}/kg'
    else:
        steps = (billed - quote.first_weight) / quote.step_weight
        pricing_rule = f'首重 {quote.first_weight} kg / {quote.first_price} + {steps} 个续重单位 × {quote.step_price}（每单位 {quote.step_weight} kg）'
    return {'quote': quote, 'weight': weight, 'volume_weight': volume_weight,
            'volume_display': format(volume_weight, 'f') if volume_weight is not None else None,
            'length': length, 'width': width, 'height': height, 'pricing_rule': pricing_rule,
            'billed_weight': billed, 'freight': freight, 'fixed_fee': quote.fixed_fee, 'base': base,
            'fuel_rate': fuel_rate, 'fuel_base': fuel_base, 'fuel': fuel,
            'extra': extra, 'total': total, 'exchange_rate': fx, 'currency': currency, 'converted': converted,
            'units': units, 'converted_package': converted_package, 'allocation_delta': converted * units - converted_package}
