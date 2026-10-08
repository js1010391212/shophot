"""真实POST/HTMX流程回归，受控输入可手算，不使用业务库。"""
import json
from decimal import Decimal
from html.parser import HTMLParser
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .models import ShippingRate
from .shipping import rate_fingerprint


class WorkspaceMetadata(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.depth = 0
        self.inside = None
        self.in_script = False
        self.content = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'div':
            self.depth += 1
            if attrs.get('id') == 'profit-workspace':
                self.inside = self.depth
        if tag == 'script' and attrs.get('id') == 'shipping-quote-metadata' and self.inside is not None:
            self.in_script = True

    def handle_endtag(self, tag):
        if tag == 'script':
            self.in_script = False
        if tag == 'div':
            if self.depth == self.inside:
                self.inside = None
            self.depth -= 1

    def handle_data(self, text):
        if self.in_script:
            self.content.append(text)

    def metadata(self):
        return json.loads(''.join(self.content)) if self.content else None


class ProfitFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='profit-flow-qa')
        self.client.force_login(self.user)
        self.url = reverse('profit')
        self.data = {'sale_currency': 'USD', 'cost_currency': 'USD', 'selling_price': '60',
                     'discount_rate': '10', 'exchange_rate': '', 'cost': '40', 'shipping_mode': 'manual',
                     'shipping': '10', 'ad_cost': '2', 'other_cost': '0', 'fee_rate': '0',
                     'payment_fee_rate': '0', 'payment_fixed': '0', 'target_margin': '20'}

    def post(self, **changes):
        return self.client.post(self.url, {**self.data, **changes}, HTTP_HX_REQUEST='true')

    def quote(self):
        values = dict(name='Controlled USD quote', carrier='QA', origin='CN', destination='US', currency='USD',
                      method='per_kg', min_weight=Decimal('.5'), max_weight=Decimal('5'), step_weight=Decimal('.5'),
                      per_kg=Decimal('2'), first_weight=None, first_price=None, step_price=None,
                      fixed_fee=Decimal('1'), fuel_basis='freight', volume_divisor=None,
                      effective_from=timezone.localdate(), effective_until=None, source_url='', notes='Controlled fixture only')
        return ShippingRate.objects.create(**values, owner=self.user, source='manual', fingerprint=rate_fingerprint(values))

    def test_get_does_not_preselect_ten_percent_reduction_or_result(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context['form']['discount_rate'].value(), 0)
        self.assertIsNone(response.context['result'])
        self.assertContains(response, 'data-has-result="false"')
        self.assertContains(response, '售价减价比例（%）')
        self.assertContains(response, '按原价的 90% 成交')

    def test_current_user_shape_then_second_and_third_htmx_posts_match_inputs(self):
        first = self.post()
        result = first.context['result']
        self.assertEqual([result[x] for x in ('revenue', 'expenses', 'net', 'margin', 'roi', 'breakeven', 'target_price')],
                         [Decimal(x) for x in ('54', '52', '2', '3.70', '3.85', '52', '65')])
        self.assertEqual(first.context['form']['discount_rate'].value(), '10')
        self.assertEqual(first.context['form']['selling_price'].value(), '60')
        self.assertContains(first, '本次售价减价比例 10%')
        second = self.post(discount_rate='0')
        self.assertEqual(second.context['result']['revenue'], Decimal('60'))
        self.assertEqual(second.context['result']['net'], Decimal('8'))
        self.assertEqual(second.context['form']['discount_rate'].value(), '0')
        third = self.post(discount_rate='0', fee_rate='5', payment_fee_rate='3', payment_fixed='.3')
        self.assertEqual(third.context['result']['fee'], Decimal('3'))
        self.assertEqual(third.context['result']['payment_fee'], Decimal('2.10'))
        self.assertEqual(third.context['result']['expenses'], Decimal('57.10'))
        self.assertEqual(third.context['result']['net'], Decimal('2.90'))
        self.assertContains(third, 'data-has-result="true"')

    def test_htmx_error_replaces_result_then_corrected_submit_recovers(self):
        self.assertEqual(self.post().context['result']['net'], Decimal('2'))
        invalid = self.post(cost_currency='CNY', exchange_rate='')
        self.assertIsNone(invalid.context['result'])
        self.assertContains(invalid, '不同币种需要填写汇率')
        self.assertContains(invalid, 'data-has-result="false"')
        corrected = self.post(cost_currency='CNY', exchange_rate='7')
        self.assertEqual(corrected.context['result']['revenue'], Decimal('378'))
        self.assertEqual(corrected.context['result']['expenses'], Decimal('52'))
        self.assertEqual(corrected.context['result']['net'], Decimal('326'))
        self.assertEqual(corrected.context['form']['exchange_rate'].value(), '7')

    def test_quote_to_manual_to_quote_posts_use_only_active_method(self):
        quote = self.quote()
        params = {'shipping_mode': 'quote', 'shipping_quote': 'user:'+str(quote.pk), 'package_weight': '.75',
                  'package_units': '1', 'fuel_rate': '0', 'shipping_extra': '0', 'shipping_exchange_rate': '', 'shipping': '999'}
        result = self.post(**params).context['result']
        self.assertEqual(result['net'], Decimal('9'))  # 54 - (40+2+3), ignore forged manual999.
        manual = self.post(shipping='10', shipping_quote='invalid-ignored', package_weight='bad-ignored')
        self.assertEqual(manual.context['result']['net'], Decimal('2'))
        params.update(package_weight='1.25', package_units='3')
        quoted = self.post(**params)
        self.assertEqual(quoted.context['shipping_result']['converted'], Decimal('1.33'))
        self.assertEqual(quoted.context['result']['net'], Decimal('10.67'))

    def test_htmx_workspace_contains_fresh_quote_metadata_when_quote_changes(self):
        quote = self.quote()
        initial = self.client.get(self.url)
        metadata = WorkspaceMetadata(initial.content.decode()).metadata()
        self.assertIsNotNone(metadata, 'HTMX selects only workspace; external metadata will stay stale')
        self.assertEqual(metadata['user:'+str(quote.pk)]['volume_divisor'], None)
        quote.volume_divisor = 5000
        quote.notes = 'Updated quote conditions'
        quote.save()
        response = self.post()
        fresh = WorkspaceMetadata(response.content.decode()).metadata()
        self.assertIsNotNone(fresh)
        self.assertEqual(fresh['user:'+str(quote.pk)]['volume_divisor'], 5000)
        self.assertEqual(fresh['user:'+str(quote.pk)]['notes'], 'Updated quote conditions')

    def test_invalid_quote_or_missing_dimensions_has_visible_error_no_profit(self):
        quote = self.quote()
        quote.volume_divisor = 5000
        quote.save()
        fields = {'shipping_mode': 'quote', 'shipping_quote': 'user:'+str(quote.pk),
                  'package_weight': '1', 'package_units': '1', 'fuel_rate': '0', 'shipping_extra': '0'}
        response = self.post(**fields)
        self.assertIsNone(response.context['result'])
        self.assertContains(response, '该线路计算体积重，需要包装尺寸')
        self.assertContains(response, '输入无效')
        response = self.post(**{**fields, 'shipping_quote': 'user:999999'})
        self.assertIsNone(response.context['result'])
        self.assertContains(response, '输入无效')
