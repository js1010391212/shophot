"""单件利润场景计算：Decimal 精确计算，汇率由用户提供。"""
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING

HUNDRED = Decimal('100')
CENT = Decimal('0.01')
MAX_PRICE = Decimal('9999999999.99')


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def ledger(transaction_price, data):
    """先舍入折后成交价和换算收入，各项费用再分别舍入；合计只加展示分项。"""
    revenue = money(money(transaction_price) * data['exchange_rate'])
    platform_fee = money(revenue * data['fee_rate'] / HUNDRED)
    payment_fee = money(revenue * data['payment_fee_rate'] / HUNDRED) + money(data['payment_fixed'])
    fixed = sum((money(data[key]) for key in ('cost', 'shipping', 'other_cost', 'ad_cost')), Decimal('0'))
    expenses = fixed + platform_fee + payment_fee
    return revenue, platform_fee, payment_fee, expenses, revenue - expenses


def recommended_price(data, margin=None):
    """寻找在分项舍入后真正达标的最小两位成交价，不假设净利在每分钱都单调。

    两项比例费各最多产生半分舍入误差。由误差界限定收入搜索窗口，
    按成本币种的分遍历；直接跳到可产生该收入的最小售价，跳过汇率造成的空档。
    表单费率/目标精度为 0.01%，窗口最多约 20000 个收入档，不逐分钱遍历极小汇率的售价。
    """
    target = Decimal('0') if margin is None else margin / HUNDRED
    fee_rate = (data['fee_rate'] + data['payment_fee_rate']) / HUNDRED
    fixed = sum((money(data[key]) for key in ('cost', 'shipping', 'other_cost', 'ad_cost', 'payment_fixed')), Decimal('0'))
    denominator = 1 - fee_rate - target
    if denominator <= 0:
        if margin is None and fixed == 0:
            return Decimal('0.00')
        return None
    error_bound = sum((Decimal('.005') for key in ('fee_rate', 'payment_fee_rate') if data[key]), Decimal('0'))
    lower = max(Decimal('0'), (fixed - error_bound) / denominator)
    revenue_floor = lower.quantize(CENT, rounding=ROUND_CEILING)
    rate = data['exchange_rate']
    while True:
        # 非负金额 ROUND_HALF_UP 的边界：P × 汇率 >= 目标收入 - 0.005。
        price = max(Decimal('0'), (revenue_floor - Decimal('.005')) / rate).quantize(CENT, rounding=ROUND_CEILING)
        if price > MAX_PRICE:
            return None
        revenue, _, _, _, net = ledger(price, data)
        if net >= revenue * target and (margin is None or revenue > 0):
            return price
        revenue_floor = revenue + CENT


def calculate_profit(data):
    rate = data['exchange_rate']
    discounted_price = money(data['selling_price'] * (1 - data['discount_rate'] / HUNDRED))
    revenue, platform_fee, payment_fee, expenses, net = ledger(discounted_price, data)
    # 建议价是折后成交价；目标利润率 = 利润 / 收入，不能当作加价率。
    breakeven = recommended_price(data)
    target_price = recommended_price(data, data['target_margin'])
    return {'revenue': money(revenue), 'fee': money(platform_fee), 'payment_fee': money(payment_fee),
            'expenses': money(expenses), 'net': money(net), 'sale_net': money(net / rate),
            'margin': money(net / revenue * HUNDRED) if revenue else None,
            'roi': money(net / expenses * HUNDRED) if expenses else None,
            'discounted_price': discounted_price, 'breakeven': breakeven,
            'target_price': target_price,
            'target_margin': data['target_margin'], 'sale_currency': data['sale_currency'], 'cost_currency': data['cost_currency'],
            'rate': rate, 'negative': net < 0,
            'costs': [(label, money(data[key])) for label, key in [('采购成本', 'cost'), ('履约运费', 'shipping'),
                      ('广告成本', 'ad_cost'), ('其他成本', 'other_cost')]]}
