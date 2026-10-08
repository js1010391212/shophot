from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .models import Product, Snapshot


class ProfitScenarioTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user('profit-user', password='test-password'))
        self.data = {'sale_currency': 'USD', 'cost_currency': 'CNY', 'selling_price': '100', 'exchange_rate': '7',
                     'cost': '200', 'shipping': '30', 'fee_rate': '5', 'other_cost': '10', 'ad_cost': '20',
                     'payment_fee_rate': '3', 'payment_fixed': '2', 'discount_rate': '10', 'target_margin': '20'}

    def result(self, **changes):
        return self.client.post(reverse('profit'), dict(self.data, **changes)).context['result']

    def test_multi_currency_discount_and_cost_breakdown(self):
        result = self.result()
        self.assertEqual(result['revenue'], Decimal('630.00'))
        self.assertEqual(result['fee'], Decimal('31.50'))
        self.assertEqual(result['payment_fee'], Decimal('20.90'))
        self.assertEqual(result['expenses'], Decimal('312.40'))
        self.assertEqual(result['net'], Decimal('317.60'))
        self.assertEqual(result['sale_net'], Decimal('45.37'))
        self.assertEqual(result['sale_currency'], 'USD')
        self.assertEqual(result['cost_currency'], 'CNY')

    def test_same_currency_no_exchange_rate_needed_or_tampered_conversion(self):
        for value in ['', '999']:
            result = self.result(sale_currency='EUR', cost_currency='EUR', exchange_rate=value)
            self.assertEqual(result['rate'], Decimal('1'))
            self.assertEqual(result['revenue'], Decimal('90.00'))

    def test_cross_currency_requires_rate_and_explicit_currencies(self):
        for changes in [{'exchange_rate': ''}, {'sale_currency': 'ZZZ'}, {'cost_currency': ''}, {'exchange_rate': '0'}, {'exchange_rate': 'NaN'}]:
            with self.subTest(changes=changes):
                self.assertIsNone(self.result(**changes))

    def test_loss_and_zero_denominators(self):
        self.assertTrue(self.result(selling_price='1')['negative'])
        result = self.result(selling_price='0', cost='0', shipping='0', other_cost='0', ad_cost='0', payment_fixed='0')
        self.assertIsNone(result['margin'])
        self.assertIsNone(result['roi'])
        self.assertEqual(result['net'], Decimal('0.00'))

    def test_unreachable_target_and_fee_validation(self):
        result = self.result(fee_rate='70', payment_fee_rate='30')
        self.assertIsNone(result['breakeven'])
        self.assertIsNone(result['target_price'])
        self.assertIsNone(self.result(fee_rate='70', payment_fee_rate='31'))
        self.assertIsNone(self.result(discount_rate='101'))

    def test_target_price_uses_margin_not_markup(self):
        result = self.result(sale_currency='USD', cost_currency='USD', cost='50', shipping='0', other_cost='0', ad_cost='0',
                             payment_fixed='0', fee_rate='10', payment_fee_rate='0', target_margin='40')
        self.assertEqual(result['target_price'], Decimal('100.00'))
        self.assertEqual(result['breakeven'], Decimal('55.56'))

    def test_snapshot_prefill_and_htmx_form_errors(self):
        product = Product.objects.create(title='真实价格参考', url='https://store.example.com/products/coat', platform='Shopify')
        Snapshot.objects.create(product=product, price=50, currency='EUR', source='manual', observed_at=timezone.now())
        response = self.client.get(reverse('profit'), {'product': product.pk})
        self.assertEqual(response.context['form']['sale_currency'].value(), 'EUR')
        self.assertEqual(response.context['form']['selling_price'].value(), Decimal('50'))
        response = self.client.post(reverse('profit'), dict(self.data, exchange_rate=''), HTTP_HX_REQUEST='true')
        self.assertContains(response, '不同币种需要填写汇率')
        self.assertContains(response, 'id="profit-workspace"')
        self.assertIsNone(response.context['result'])

    def assert_reconciled(self, result):
        self.assertEqual(sum(value for _, value in result['costs']) + result['fee'] + result['payment_fee'], result['expenses'])
        self.assertEqual(result['revenue'] - result['expenses'], result['net'])

    def test_tiny_separately_rounded_fees_reconcile_to_net(self):
        result = self.result(sale_currency='USD', cost_currency='USD', selling_price='.05', cost='0', shipping='0',
            other_cost='0', ad_cost='0', payment_fixed='0', discount_rate='0', fee_rate='10', payment_fee_rate='10')
        self.assertEqual(result['revenue'], Decimal('.05'))
        self.assertEqual(result['fee'], Decimal('.01'))
        self.assertEqual(result['payment_fee'], Decimal('.01'))
        self.assertEqual(result['expenses'], Decimal('.02'))
        self.assertEqual(result['net'], Decimal('.03'))
        self.assert_reconciled(result)

    def test_discounted_transaction_price_rounded_before_currency_conversion(self):
        result = self.result(selling_price='.11', exchange_rate='7', discount_rate='50', cost='0', shipping='0',
            other_cost='0', ad_cost='0', payment_fixed='.01', fee_rate='10', payment_fee_rate='10')
        self.assertEqual(result['discounted_price'], Decimal('.06'))
        self.assertEqual(result['revenue'], Decimal('.42'))
        self.assertEqual(result['expenses'], Decimal('.09'))
        self.assertEqual(result['net'], Decimal('.33'))
        self.assert_reconciled(result)

    def test_recommended_prices_meet_actual_rounded_ledger_and_are_minimal(self):
        from .profit import calculate_profit, ledger
        # 旧连续理论价 .05，在两项10%舍入后亏 .01；.04 反而可保本，净利并非逐分单调。
        cases = [dict(cost='.04', fee_rate='10', payment_fee_rate='10', exchange_rate='1', target_margin='20'),
                 dict(cost='.17', fee_rate='33.33', payment_fee_rate='22.22', exchange_rate='7', target_margin='10'),
                 dict(cost='0', fee_rate='10', payment_fee_rate='10', exchange_rate='.000001', target_margin='20'),
                 dict(cost='1', fee_rate='99.99', payment_fee_rate='0', exchange_rate='1', target_margin='0')]
        for case in cases:
            values = dict(selling_price='1', cost='0', shipping='0', other_cost='0', ad_cost='0', payment_fixed='0',
                          discount_rate='0', exchange_rate='1', fee_rate='0', payment_fee_rate='0', target_margin='20')
            values.update(case)
            data = {key: Decimal(value) for key, value in values.items()}
            data.update(sale_currency='USD', cost_currency='CNY')
            with self.subTest(case=case):
                result = calculate_profit(data)
                for key, margin in [('breakeven', None), ('target_price', data['target_margin'])]:
                    price = result[key]
                    self.assertIsNotNone(price)
                    revenue, _, _, _, net = ledger(price, data)
                    self.assertGreaterEqual(net, revenue * (margin or 0) / 100)
                    if margin is not None:
                        self.assertGreater(revenue, 0)
                    # 验算前一分钱不达标；低金额样例还逐分穷举更低价格，覆盖非单调净利。
                    if price > 0:
                        previous_revenue, _, _, _, previous_net = ledger(price - Decimal('.01'), data)
                        self.assertTrue(previous_net < previous_revenue * (margin or 0) / 100 or (margin is not None and previous_revenue == 0))
                    if price <= Decimal('1'):
                        for cents in range(int(price * 100)):
                            r, _, _, _, n = ledger(Decimal(cents) / 100, data)
                            self.assertTrue(n < r * (margin or 0) / 100 or (margin is not None and r == 0))
        first = {key: Decimal(value) for key, value in dict(selling_price='1', cost='.04', shipping='0', other_cost='0',
            ad_cost='0', payment_fixed='0', discount_rate='0', exchange_rate='1', fee_rate='10', payment_fee_rate='10', target_margin='20').items()}
        first.update(sale_currency='USD', cost_currency='USD')
        self.assertEqual(calculate_profit(first)['breakeven'], Decimal('.04'))

    def test_price_recommendation_outside_input_range_is_unavailable(self):
        result = self.result(cost='9999999999.99', shipping='0', other_cost='0', ad_cost='0', payment_fixed='0',
            sale_currency='USD', cost_currency='USD', fee_rate='99.99', payment_fee_rate='0', target_margin='0')
        self.assertIsNone(result['breakeven'])
        self.assertIsNone(result['target_price'])
