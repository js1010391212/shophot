"""Bounded trial economics from the existing, cent-rounded per-unit ledger."""
from decimal import Decimal, ROUND_CEILING


def calculate_trial_budget(result, data):
    quantity = data['trial_quantity']
    operating = [(label, amount * quantity) for label, amount in result['costs']]
    once = [(label, data[key]) for label, key in (
        ('样品及寄送', 'trial_sample_cost'), ('素材 / 开店准备', 'trial_setup_cost'),
        ('合规 / 检测', 'trial_compliance_cost'))]
    fixed = sum((value for _, value in once), Decimal('0.00'))
    reserve = data['trial_reserve_cost']
    prepared = sum((value for _, value in operating), Decimal('0.00')) + fixed + reserve
    settlement = (result['fee'] + result['payment_fee']) * quantity
    revenue = result['revenue'] * quantity
    expenses = result['expenses'] * quantity + fixed
    net = result['net'] * quantity - fixed
    recovery = int((fixed / result['net']).to_integral_value(rounding=ROUND_CEILING)) if result['net'] > 0 else None
    if result['net'] < 0:
        status = '单件亏损'
    elif result['net'] == 0:
        status = '单件无利润缓冲'
    elif net < 0:
        status = '本批未覆盖一次性费用'
    else:
        status = '本批可覆盖一次性费用'
    return dict(quantity=quantity, currency=result['cost_currency'], operating=operating,
                once=once, fixed=fixed, reserve=reserve, prepared=prepared, settlement=settlement,
                revenue=revenue, expenses=expenses, net=net, recovery=recovery, status=status,
                negative=net < 0)
