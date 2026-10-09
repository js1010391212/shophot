"""受控离线响应覆盖官方包裹结构；不是实站或获批接口调用证据。"""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
import json
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from .aliexpress_affiliate import (
    AffiliateRequestContext, AffiliateResponseError, MAX_RESPONSE_BYTES,
    METHOD, PRICE_FIELDS, TARGET_CURRENCIES, normalize_affiliate_response,
)


ENVELOPE = 'aliexpress_affiliate_productdetail_get_response'
SECRET = 'private-example-token-must-not-be-displayed'


class AffiliateResponseTests(SimpleTestCase):
    def setUp(self):
        self.context = AffiliateRequestContext(
            product_id='1005001234567890', country='US', target_currency='USD',
            requested_at=datetime(2026, 10, 9, 1, tzinfo=timezone.utc),
            received_at=datetime(2026, 10, 9, 1, 0, 3, tzinfo=timezone.utc),
        )
        self.product = {
            'product_id': 1005001234567890, 'product_title': 'Controlled offline product',
            'product_detail_url': 'https://www.aliexpress.com/item/1005001234567890.html',
            'sale_price': '15.9', 'sale_price_currency': 'USD',
            'original_price': '30', 'original_price_currency': 'EUR',
            'app_sale_price': '14.99', 'app_sale_price_currency': 'GBP',
            'target_sale_price': '15.900', 'target_sale_price_currency': 'USD',
            'target_original_price': '32.20', 'target_original_price_currency': 'USD',
            'target_app_sale_price': '14.50', 'target_app_sale_price_currency': 'USD',
            'evaluate_rate': '89.22%', 'lastest_volume': 300,
            'discount': '50%', 'promo_code_info': {'code_value': 'Minimum order required',
                'code_mini_spend': '10', 'code_availabletime_end': '2026-10-31 00:00:00',
                'unknown_token': SECRET}, 'unknown_secret': SECRET,
        }

    def payload(self, products=None, count=200):
        return {ENVELOPE: {'resp_result': {'resp_code': 200, 'resp_msg': SECRET,
            'result': {'current_record_count': count,
                       'products': {'product': [deepcopy(self.product)] if products is None else products}}}}}

    def parse(self, payload=None, context=None):
        raw = json.dumps(self.payload() if payload is None else payload).encode()
        return normalize_affiliate_response(raw, self.context if context is None else context)

    def assert_error(self, raw, code, context=None):
        with self.assertRaises(AffiliateResponseError) as caught:
            normalize_affiliate_response(raw, self.context if context is None else context)
        error = caught.exception
        self.assertEqual(error.code, code)
        self.assertNotIn(SECRET, str(error))
        self.assertNotIn(SECRET, repr(error.args))
        self.assertNotIn(SECRET, json.dumps(error.as_dict()))
        self.assertEqual(error.messages, [str(error)])
        return error

    def test_official_json_wrapper_preserves_six_prices_and_context_without_selecting_sku(self):
        before = self.payload()
        result = self.parse(before)
        self.assertEqual(before, self.payload())
        self.assertEqual(result.status, 'ok')
        self.assertEqual(result.context, self.context)
        self.assertEqual(result.reported_record_count, 200)  # Doc count is not inferred from list length.
        self.assertEqual(len(result.product.prices), 6)
        self.assertIsInstance(result.product.prices[0].amount, Decimal)
        data = result.as_dict()
        self.assertEqual(data['source']['method'], METHOD)
        self.assertEqual(data['request']['requested_at'], self.context.requested_at.isoformat())
        self.assertEqual(data['request']['received_at'], self.context.received_at.isoformat())
        self.assertEqual(data['product']['prices']['target_sale_price'], {'amount': '15.90', 'currency': 'USD'})
        self.assertEqual(data['product']['prices']['original_price']['currency'], 'EUR')
        self.assertEqual(data['product']['evaluate_rate'], '89.22%')
        self.assertEqual(data['product']['lastest_volume'], 300)
        self.assertIsNone(data['product']['recent_volume_window'])
        self.assertIsNone(data['product']['sku_id'])
        self.assertFalse(data['product']['may_use_as_selected_sku_cost'])
        self.assertNotIn('rating', data['product'])
        self.assertEqual(data['product']['promo_code_info']['code_mini_spend'], '10')
        self.assertNotIn(SECRET, json.dumps(data))

    def test_unknown_values_remain_missing_instead_of_zero(self):
        product = {'product_id': self.context.product_id, 'product_title': 'No requested price fields'}
        result = self.parse(self.payload([product])).as_dict()['product']
        self.assertEqual(result['prices'], dict.fromkeys(PRICE_FIELDS))
        self.assertIsNone(result['evaluate_rate'])
        self.assertIsNone(result['lastest_volume'])
        self.assertEqual(result['promo_code_info'], {})

    def test_explicit_zero_is_preserved_and_not_confused_with_missing(self):
        self.product.update(sale_price='0.000', lastest_volume=0, evaluate_rate='0%')
        product = self.parse().as_dict()['product']
        self.assertEqual(product['prices']['sale_price']['amount'], '0.00')
        self.assertEqual(product['lastest_volume'], 0)
        self.assertEqual(product['evaluate_rate'], '0%')

    def test_empty_array_returns_empty_without_claiming_product_coverage(self):
        result = self.parse(self.payload([], 0))
        self.assertEqual(result.status, 'empty')
        self.assertIsNone(result.product)
        self.assertIsNone(result.as_dict()['product'])
        payload = self.payload([])
        del payload[ENVELOPE]['resp_result']['result']['current_record_count']
        self.assertIsNone(self.parse(payload).reported_record_count)

    def test_partial_pairs_rejected_for_every_price_type(self):
        for field in PRICE_FIELDS:
            for missing in (field, field + '_currency'):
                with self.subTest(field=field, missing=missing):
                    product = deepcopy(self.product)
                    product.pop(missing)
                    self.assert_error(json.dumps(self.payload([product])).encode(), 'incomplete_price')
            product = deepcopy(self.product)
            product[field] = None
            product[field + '_currency'] = ''
            self.assertIsNone(self.parse(self.payload([product])).as_dict()['product']['prices'][field])

    def test_exact_cent_precision_accepts_trailing_zeros_without_rounding(self):
        for price, expected in (('15.900', '15.90'), ('15.90000000000000000000', '15.90'),
                                ('9999999999.99', '9999999999.99'), ('0001.20', '1.20')):
            with self.subTest(price=price):
                self.product['sale_price'] = price
                self.assertEqual(self.parse().as_dict()['product']['prices']['sale_price']['amount'], expected)
        for price in ('15.901', '0.001', '9999999999.991', '10000000000.00', '-1',
                      '1e2', 'NaN', 'Infinity', '15-20', ' 15.9 ', True, 15.9):
            with self.subTest(price=price):
                self.product['sale_price'] = price
                self.assert_error(json.dumps(self.payload()).encode(), 'unsupported_price')

    def test_target_currency_must_match_request_but_original_currency_can_differ(self):
        for field in ('target_sale_price', 'target_original_price', 'target_app_sale_price'):
            product = deepcopy(self.product)
            product[field + '_currency'] = 'EUR'
            self.assert_error(json.dumps(self.payload([product])).encode(), 'currency_mismatch')
        self.product['sale_price_currency'] = 'usd'
        self.assertEqual(self.parse().product.prices[0].currency, 'USD')
        self.assertEqual(self.parse(context=replace(self.context, target_currency=None)).status, 'ok')

    def test_invalid_currency_is_not_inferred_from_price_or_country(self):
        for value in (None, '$', 'US', 1, {'USD': SECRET}):
            self.product['sale_price_currency'] = value
            code = 'incomplete_price' if value is None else 'invalid_field'
            self.assert_error(json.dumps(self.payload()).encode(), code)

    def test_context_preserves_unknown_conditions_and_restricts_documented_target_currencies(self):
        context = replace(self.context, country=None, target_currency=None)
        self.assertIsNone(self.parse(context=context).as_dict()['request']['country'])
        for currency in TARGET_CURRENCIES:
            self.assertEqual(replace(self.context, target_currency=currency).target_currency, currency)
        for fields in ({'country': ''}, {'country': 'usa'}, {'country': 'us'}, {'country': True},
                       {'target_currency': 'CNY'}, {'target_currency': 'XXX'}, {'target_currency': 'usd'},
                       {'product_id': 123}, {'product_id': '1,2'}, {'product_id': SECRET}):
            with self.subTest(fields=fields), self.assertRaises(AffiliateResponseError) as caught:
                replace(self.context, **fields)
            self.assertEqual(caught.exception.code, 'invalid_context')

    def test_time_order_uses_aware_instant_not_wall_clock_or_timezone_identity(self):
        start = datetime(2026, 10, 9, 10, tzinfo=timezone(timedelta(hours=9)))
        equal = datetime(2026, 10, 8, 18, tzinfo=timezone(timedelta(hours=-7)))
        context = replace(self.context, requested_at=start, received_at=equal)
        self.assertEqual(self.parse(context=context).context.received_at, equal)
        for fields in ({'received_at': equal - timedelta(microseconds=1)},
                       {'requested_at': start.replace(tzinfo=None)}, {'received_at': 'not a date'}):
            with self.subTest(fields=fields), self.assertRaises(AffiliateResponseError):
                replace(context, **fields)

    def test_repeated_dst_hour_compares_actual_utc_instants(self):
        zone = ZoneInfo('America/New_York')
        first = datetime(2026, 11, 1, 1, 50, tzinfo=zone, fold=0)
        second = datetime(2026, 11, 1, 1, 10, tzinfo=zone, fold=1)
        context = replace(self.context, requested_at=first, received_at=second)
        self.assertEqual(self.parse(context=context).status, 'ok')
        with self.assertRaises(AffiliateResponseError):
            replace(self.context, requested_at=second, received_at=first)

    def test_price_precision_is_independent_of_callers_decimal_context(self):
        with localcontext() as context:
            context.prec = 3
            self.assertEqual(self.parse().as_dict()['product']['prices']['sale_price']['amount'], '15.90')

    def test_identity_mismatch_and_ambiguous_multiple_items_rejected(self):
        for identity in (1, '1005001234567891'):
            product = {**self.product, 'product_id': identity}
            self.assert_error(json.dumps(self.payload([product])).encode(), 'identity_mismatch')
        self.assert_error(json.dumps(self.payload([self.product, self.product])).encode(), 'ambiguous_product')
        for identity in (True, 1.5, None, '001', 'x', ['1005001234567890']):
            product = {**self.product, 'product_id': identity}
            self.assert_error(json.dumps(self.payload([product])).encode(), 'invalid_field')

    def test_response_url_binds_to_id_and_strips_tracking_or_secret_query(self):
        self.product['product_detail_url'] += '?token=' + SECRET + '#fragment'
        self.assertNotIn(SECRET, json.dumps(self.parse().as_dict()))
        self.product['product_detail_url'] = 'https://www.aliexpress.com/item/123.html'
        self.assert_error(json.dumps(self.payload()).encode(), 'identity_mismatch')
        for url in ('http://www.aliexpress.com/item/1005001234567890.html',
                    'https://www.aliexpress.com.evil.invalid/item/1005001234567890.html',
                    'https://user:' + SECRET + '@www.aliexpress.com/item/1005001234567890.html',
                    'https://www.aliexpress.com:bad/item/1005001234567890.html'):
            self.product['product_detail_url'] = url
            self.assert_error(json.dumps(self.payload()).encode(), 'invalid_field')

    def test_top_error_has_fixed_messages_and_only_bounded_numeric_vendor_code(self):
        for code in (50, '50', SECRET, True, -1, 2147483648):
            raw = json.dumps({'error_response': {'code': code, 'msg': SECRET + '\napp_secret=' + SECRET,
                                                'sub_msg': '<script>' + SECRET, 'sub_code': SECRET}}).encode()
            error = self.assert_error(raw, 'vendor_error')
            self.assertEqual(error.vendor_code, 50 if type(code) is int and code == 50 else None)

    def test_non_success_codes_not_guessed_as_auth_or_rate_limit_errors(self):
        for code in (0, 403, 429, -1):
            payload = self.payload()
            payload[ENVELOPE]['resp_result'] = {'resp_code': code, 'resp_msg': SECRET}
            self.assert_error(json.dumps(payload).encode(), 'service_error')
        for code in (True, '200', None, 200.0):
            payload = self.payload()
            payload[ENVELOPE]['resp_result']['resp_code'] = code
            self.assert_error(json.dumps(payload).encode(), 'invalid_structure')

    def test_unsupported_wrappers_and_unverified_empty_layouts_rejected(self):
        for payload in (None, [], {}, {'result': self.product}, {ENVELOPE: None},
                        {ENVELOPE: self.payload()[ENVELOPE], 'error_response': {'code': 50}}):
            self.assert_error(json.dumps(payload).encode(), 'invalid_structure')
        for products in (None, self.product, 'not an array', [None]):
            payload = self.payload()
            payload[ENVELOPE]['resp_result']['result']['products']['product'] = products
            self.assert_error(json.dumps(payload).encode(), 'invalid_structure')

    def test_duplicate_keys_rejected_even_in_unconsumed_fields(self):
        for raw in (b'{"error_response":{"code":50,"code":200}}',
                    b'{"unknown":{"token":"first","token":"second"}}'):
            self.assert_error(raw, 'duplicate_key')

    def test_html_encoding_malformed_json_and_nonstandard_numbers_do_not_leak_input(self):
        for raw in (b'<html>' + SECRET.encode(), b'\xff', b'{"secret":"' + SECRET.encode(),
                    b'{"secret":NaN}', b'{"secret":Infinity}', b'{} trailing',
                    b'{"secret":1e10000000000000000000000000000000000000}',
                    b'{"secret":' + b'1' * 81 + b'}', json.dumps(self.payload())):
            self.assert_error(raw, 'invalid_json')

    def test_response_size_depth_nodes_and_unknown_text_bounded(self):
        self.assert_error(b' ' * (MAX_RESPONSE_BYTES + 1), 'response_too_large')
        for extra in ([[[[[[[[[[[[[[[[[[[[[[[[[[None]]]]]]]]]]]]]]]]]]]]]]]]]],
                      [None] * 10001, 'x' * 8193):
            payload = self.payload()
            payload[ENVELOPE]['unknown'] = extra
            self.assert_error(json.dumps(payload).encode(), 'invalid_structure')

    def test_known_text_fields_reject_controls_and_invalid_types_without_truncation(self):
        for title in ('', 'x' * 241, SECRET + '\x00', None):
            self.product['product_title'] = title
            self.assert_error(json.dumps(self.payload()).encode(), 'invalid_field')
        self.product['product_title'] = 'Valid'
        self.product['promo_code_info']['code_value'] = 'line\nbreak'
        self.assert_error(json.dumps(self.payload()).encode(), 'invalid_field')

    def test_vendor_metrics_retained_only_with_explicit_valid_semantics(self):
        for field, value in (('evaluate_rate', '101%'), ('evaluate_rate', 4.7),
                             ('evaluate_rate', '89.222%'), ('lastest_volume', True),
                             ('lastest_volume', '300'), ('lastest_volume', -1),
                             ('lastest_volume', 2147483648), ('promo_code_info', []),
                             ('current_record_count', True)):
            payload = self.payload()
            target = payload[ENVELOPE]['resp_result']['result']
            if field != 'current_record_count':
                target = target['products']['product'][0]
            target[field] = value
            self.assert_error(json.dumps(payload).encode(), 'invalid_field')

    def test_results_are_immutable_and_json_export_does_not_modify_original(self):
        result = self.parse()
        for obj, field, value in ((self.context, 'country', 'DE'), (result, 'product', None),
                                  (result.product, 'title', 'Changed'),
                                  (result.product.prices[0], 'amount', Decimal('999'))):
            with self.assertRaises(FrozenInstanceError):
                setattr(obj, field, value)
        output = result.as_dict()
        output['product']['prices']['sale_price']['amount'] = '999'
        self.assertEqual(result.as_dict()['product']['prices']['sale_price']['amount'], '15.90')
        json.dumps(result.as_dict(), allow_nan=False)

    def test_wrong_context_type_is_fixed_error(self):
        self.assert_error(json.dumps(self.payload()).encode(), 'invalid_context', context={'token': SECRET})
