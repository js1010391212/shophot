"""SF page-4 parcel range regression; official anchors are independent expected amounts."""
from dataclasses import replace
from decimal import Decimal as D
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .shipping import estimate, public_quotes, SF_SOURCE


# Page 4, explicit 5.5kg / 19.5kg bands in CNY (not linear continuation).
ANCHORS = {'US': (930, 2626), 'CA': (930, 2626), 'GB': (848, 2383),
           'DE': (848, 2383), 'FR': (848, 2383), 'AU': (787, 2328),
           'JP': (507, 1329), 'SG': (442, 1222)}
OLD_TEN = {
    'US': (299, 372, 433, 495, 558, 620, 682, 744, 806, 868),
    'GB': (309, 363, 418, 471, 525, 578, 633, 685, 738, 792),
    'AU': (232, 291, 349, 408, 467, 519, 573, 626, 680, 733),
    'JP': (205, 237, 270, 302, 335, 364, 393, 422, 451, 478),
    'SG': (150, 180, 209, 239, 269, 298, 326, 356, 384, 413),
}


def calc(quote, **changes):
    data = dict(weight=D('5'), length=D('30'), width=D('30'), height=D('30'),
                fuel_rate=D('0'), extra=D('0'), exchange_rate=D('1'), currency='CNY', units=1)
    return estimate(quote, **{**data, **changes})


class SFParcelRangeTests(SimpleTestCase):
    def test_user_cube_in_all_eight_routes_uses_explicit_five_point_five_band(self):
        self.assertEqual(len(public_quotes()), 8)
        for quote in public_quotes():
            with self.subTest(country=quote.destination):
                result = calc(quote)
                self.assertEqual(result['volume_weight'], D('5.4'))
                self.assertEqual(result['billed_weight'], D('5.5'))
                self.assertEqual(result['freight'], D(ANCHORS[quote.destination][0]))
                self.assertEqual(result['total'], result['freight'])
                self.assertEqual(result['converted'], result['freight'])
                self.assertEqual(quote.currency, 'CNY')

    def test_old_ten_bands_unchanged_and_39_contiguous_bands_present(self):
        equivalents = {'CA': 'US', 'DE': 'GB', 'FR': 'GB'}
        for quote in public_quotes():
            old = OLD_TEN[equivalents.get(quote.destination, quote.destination)]
            self.assertEqual(set(quote.table), {D(i)/2 for i in range(1, 40)})
            for index, price in enumerate(old, 1):
                result = calc(quote, weight=D(index)/2, length=D('10'), width=D('10'), height=D('10'))
                self.assertEqual(result['freight'], D(price))
            self.assertEqual(calc(quote, length=D('10'), width=D('10'), height=D('10'))['billed_weight'], D('5'))

    def test_last_band_and_metadata_report_verified_range_without_extrapolation(self):
        for quote in public_quotes():
            result = calc(quote, weight=D('19.5'))
            self.assertEqual(result['freight'], D(ANCHORS[quote.destination][1]))
            metadata = quote.metadata()
            self.assertEqual(metadata['max_weight'], '19.5')
            self.assertEqual(metadata['checked_at'], '2026-10-09')
            self.assertEqual(metadata['source_url'], SF_SOURCE)
            self.assertIn('20 kg 及以上', metadata['notes'])
            self.assertIn('尚未录入', metadata['notes'])

    def test_out_of_range_real_or_volume_weight_reports_every_component(self):
        quote = public_quotes()[0]
        for changes, volume in [(dict(weight=D('19.501')), '5.4'), (dict(weight=D('20')), '5.4'),
                                (dict(length=D('50'), width=D('50'), height=D('40')), '20')]:
            with self.subTest(changes=changes):
                with self.assertRaises(ValidationError) as caught:
                    calc(quote, **changes)
                message = str(caught.exception)
                self.assertIn('实重 ', message)
                self.assertIn('体积重 '+volume+' kg', message)
                self.assertIn('进位后计费重 20', message)
                self.assertIn('当前录入报价上限 19.5 kg', message)
                self.assertIn('改选', message)
                self.assertIn('手填实际单件运费', message)

    def test_user_quote_without_volume_weight_is_not_falsely_reported_as_zero(self):
        quote = replace(public_quotes()[0], source='manual', method='per_kg', per_kg=D('10'),
                        max_weight=D('5'), volume_divisor=None)
        with self.assertRaises(ValidationError) as caught:
            calc(quote, weight=D('5.001'), length=None, width=None, height=None)
        message = str(caught.exception)
        self.assertIn('体积重 不适用（该报价不计体积重）', message)
        self.assertIn('实重 5.001 kg', message)
        self.assertIn('进位后计费重 5.5 kg', message)
        self.assertIn('上限 5 kg', message)


class SFProfitFlowTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user('sf-range-fixture'))
        self.shipping_data = dict(shipping_quote='public:sf-economy-US', package_weight='5',
                                  package_length='30', package_width='30', package_height='30',
                                  fuel_rate='0', shipping_extra='0', shipping_exchange_rate='',
                                  cost_currency='CNY', package_units='1')
        self.profit_data = dict(sale_currency='CNY', cost_currency='CNY', selling_price='2000',
                                discount_rate='0', exchange_rate='', cost='100', ad_cost='0', other_cost='0',
                                fee_rate='0', payment_fee_rate='0', payment_fixed='0', target_margin='20',
                                shipping_mode='quote', shipping='999999')  # ignored in quote mode

    def test_shipping_post_profit_get_then_htmx_result_keeps_quote_and_money(self):
        for country, expected in [('US', '930'), ('GB', '848'), ('AU', '787')]:
            with self.subTest(country=country):
                shipping = self.client.post(reverse('shipping'), {**self.shipping_data, 'shipping_quote': 'public:sf-economy-'+country})
                self.assertEqual(shipping.context['result']['total'], D(expected))
                url = shipping.context['profit_url']
                get = self.client.get(url)
                self.assertIsNone(get.context['result'])
                self.assertEqual(get.context['form']['package_weight'].value(), '5')
                query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
                result = self.client.post(reverse('profit'), {**query, **self.profit_data}, HTTP_HX_REQUEST='true')
                shipping_result = result.context['shipping_result']
                self.assertEqual(shipping_result['quote'].key, 'public:sf-economy-'+country)
                self.assertEqual(shipping_result['freight'], D(expected))
                self.assertEqual(shipping_result['exchange_rate'], D('1'))
                self.assertEqual(result.context['result']['expenses'], D('100')+D(expected))
                self.assertEqual(result.context['result']['net'], D('1900')-D(expected))
                self.assertContains(result, SF_SOURCE)
                self.assertContains(result, '19.5')

    def test_invalid_range_has_no_profit_or_zero_estimate_then_corrected_htmx_recovers(self):
        too_heavy = {**self.shipping_data, 'package_weight': '20'}
        shipping = self.client.post(reverse('shipping'), too_heavy)
        self.assertIsNone(shipping.context['result'])
        self.assertIsNone(shipping.context['profit_url'])
        invalid = self.client.post(reverse('profit'), {**too_heavy, **self.profit_data}, HTTP_HX_REQUEST='true')
        self.assertIsNone(invalid.context['result'])
        self.assertIsNone(invalid.context['shipping_result'])
        self.assertContains(invalid, '当前录入报价上限 19.5 kg')
        self.assertContains(invalid, 'data-has-result="false"')
        corrected = self.client.post(reverse('profit'), {**self.shipping_data, **self.profit_data}, HTTP_HX_REQUEST='true')
        self.assertEqual(corrected.context['shipping_result']['converted'], D('930'))
        self.assertEqual(corrected.context['result']['net'], D('970'))
        self.assertContains(corrected, 'data-has-result="true"')

    def test_same_currency_allocation_and_existing_fuel_extra_are_unchanged(self):
        data = {**self.shipping_data, 'package_units': '3', 'fuel_rate': '10', 'shipping_extra': '2',
                'shipping_exchange_rate': '99'}  # same currency ignores forged FX
        shipping = self.client.post(reverse('shipping'), data)
        result = shipping.context['result']
        self.assertEqual(result['freight'], D('930'))
        self.assertEqual(result['fuel'], D('93'))
        self.assertEqual(result['total'], D('1025'))
        self.assertEqual(result['converted'], D('341.67'))
        self.assertEqual(result['allocation_delta'], D('.01'))
        profit = self.client.post(reverse('profit'), {**data, **self.profit_data}, HTTP_HX_REQUEST='true')
        self.assertEqual(profit.context['shipping_result']['converted'], D('341.67'))
        self.assertEqual(profit.context['result']['net'], D('1558.33'))
