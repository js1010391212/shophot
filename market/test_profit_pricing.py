"""以独立整数账本和有界枚举验收舍入边界的最小建议价。"""
from decimal import Decimal
from random import Random
from unittest.mock import patch
from django.test import SimpleTestCase
from .profit import calculate_profit
from . import profit_pricing


class RoundedPricingBoundaryTests(SimpleTestCase):
    def data(self, **changes):
        values = dict(selling_price='1', discount_rate='0', exchange_rate='1', cost='0', shipping='0',
                      ad_cost='0', other_cost='0', fee_rate='0', payment_fee_rate='0', payment_fixed='0', target_margin='0')
        values.update(changes)
        return {**{key: Decimal(value) for key, value in values.items()}, 'sale_currency': 'USD', 'cost_currency': 'CNY'}

    @staticmethod
    def eligible(price_cents, rate, fee, payment, target):
        # 不调用被测ledger或定价器，用整数商余数独立核算两次费用四舍五入。
        fx = int(rate * 1000000)
        income, remainder = divmod(price_cents * fx, 1000000)
        income += remainder >= 500000
        total_fee = 0
        for value in (fee, payment):
            units, remainder = divmod(income * int(value * 100), 10000)
            total_fee += units + (remainder >= 5000)
        return income > 0 and (income - total_fee) * 10000 >= income * int(target * 100)

    def test_previously_rejected_targets_are_reachable_after_rounding(self):
        cases = [({'fee_rate': '100'}, '.01'),
                 ({'target_margin': '100'}, '.01'),
                 ({'fee_rate': '50', 'target_margin': '50'}, '.02'),
                 ({'fee_rate': '30', 'payment_fee_rate': '30', 'target_margin': '50'}, '.01'),
                 ({'fee_rate': '50', 'target_margin': '50', 'exchange_rate': '.000001'}, '15000.00'),
                 ({'fee_rate': '50', 'target_margin': '50', 'exchange_rate': '10000.5'}, '.03'),
                 ({'fee_rate': '50', 'target_margin': '50', 'exchange_rate': '.333333'}, '.05'),
                 ({'fee_rate': '50', 'target_margin': '50', 'exchange_rate': '999999.999999'}, '.01')]
        for values, expected in cases:
            with self.subTest(values=values):
                data = self.data(**values)
                result = calculate_profit(data)
                self.assertEqual(result['target_price'], Decimal(expected))
                self.assertEqual(result['breakeven'], Decimal('0'))
                price = int(result['target_price'] * 100)
                self.assertTrue(self.eligible(price, data['exchange_rate'], data['fee_rate'], data['payment_fee_rate'], data['target_margin']))
                if price > 1:
                    self.assertFalse(self.eligible(price - 1, data['exchange_rate'], data['fee_rate'], data['payment_fee_rate'], data['target_margin']))

    def test_positive_fixed_cost_and_unreachable_rounded_targets_remain_unavailable(self):
        for values in [dict(cost='.01', fee_rate='50', target_margin='50'),
                       dict(payment_fixed='.01', fee_rate='30', payment_fee_rate='30', target_margin='50'),
                       dict(fee_rate='100', target_margin='1'),
                       dict(fee_rate='50', target_margin='100', exchange_rate='999999.999999')]:
            with self.subTest(values=values):
                self.assertIsNone(calculate_profit(self.data(**values))['target_price'])

    def test_price_minima_match_independent_bounded_enumeration(self):
        cases = [('50', '0', '50'), ('33.33', '16.67', '50'), ('10', '20', '70'),
                 ('49.99', '50', '.01'), ('30', '30', '50'), ('100', '0', '0')]
        for fee, payment, target in cases:
            for fx in ['.125', '.333333', '1', '7', '10000.5']:
                data = self.data(fee_rate=fee, payment_fee_rate=payment, target_margin=target, exchange_rate=fx)
                expected = next((c for c in range(1, 401) if self.eligible(c, data['exchange_rate'], data['fee_rate'], data['payment_fee_rate'], data['target_margin'])), None)
                with self.subTest(fee=fee, payment=payment, target=target, fx=fx):
                    result = calculate_profit(data)['target_price']
                    if expected is None:
                        self.assertTrue(result is None or result > Decimal('4'))
                    else:
                        self.assertEqual(result, Decimal(expected) / 100)

    def test_euclidean_counts_match_naive_lattice_sum(self):
        rng = Random(19)
        for _ in range(200):
            count, modulus, slope, offset = rng.randrange(40), rng.randrange(1, 41), rng.randrange(300), rng.randrange(300)
            self.assertEqual(profit_pricing._floor_sum(count, modulus, slope, offset),
                             sum((slope * index + offset) // modulus for index in range(count)))

    def test_extreme_fx_uses_bounded_prefix_search(self):
        # 50%费用的奇数收入档均不达50%目标；微小汇率对应150万分的最小售价。
        # 不允许靠逐价遍历，精确周期最多10^10分，二分最多34步/5000区间。
        with patch.object(profit_pricing, '_floor_sum', wraps=profit_pricing._floor_sum) as counted:
            result = calculate_profit(self.data(fee_rate='50', target_margin='50', exchange_rate='.000001'))
        self.assertEqual(result['target_price'], Decimal('15000.00'))
        self.assertLessEqual(counted.call_count, 34 * 5000 * 2)
