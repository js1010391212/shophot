"""契约测试不访问外站、业务数据库或写入历史。"""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.utils import timezone

from .browser_capture import validate_capture


URL = 'https://www.aliexpress.com/item/1005001234567890.html?sku_id=123'


class BrowserCaptureTests(SimpleTestCase):
    def setUp(self):
        self.now = timezone.now()
        self.payload = {
            'schema_version': 1,
            'capture_id': '37b9cc53-510a-4acb-97b2-9c243d1f3c56',
            'adapter_version': 'aliexpress-dom/1', 'platform': 'AliExpress',
            'url': URL, 'product_id': '1005001234567890', 'sku_id': '123',
            'title': 'Controlled contract fixture', 'price': '19.5',
            'currency': 'usd', 'quote_type': 'current', 'market_country': None,
            'conditions': [], 'observed_at': self.now.isoformat(),
            'evidence': 'Controlled fixture price USD 19.50',
        }

    def parse(self, payload=None, target=URL):
        return validate_capture(self.payload if payload is None else payload, target, now=self.now)

    def test_valid_capture_normalizes_without_mutating_input(self):
        result = self.parse()
        self.assertEqual((result['price'], result['currency']), ('19.50', 'USD'))
        self.assertIsNone(result['market_country'])
        self.assertEqual(self.payload['price'], '19.5')

    def test_foreign_product_and_sku_mismatch_rejected(self):
        for url in (URL.replace('www.aliexpress.com', 'evil.example'),
                    URL.replace('1005001234567890', '999'),
                    URL.replace('sku_id=123', 'sku_id=456'), URL.split('?')[0]):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                self.parse({**self.payload, 'url': url})
        for field, value in (('product_id', '999'), ('sku_id', '456'), ('sku_id', None), ('platform', 'OTTO')):
            with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                self.parse({**self.payload, field: value})

    def test_generic_target_cannot_receive_variant_quote(self):
        with self.assertRaises(ValidationError):
            self.parse(target=URL.split('?')[0])
        data = {**self.payload, 'url': URL.split('?')[0], 'sku_id': None}
        self.assertIsNone(self.parse(data, target=data['url'])['sku_id'])

    def test_non_decimal_unknown_and_ambiguous_prices_rejected(self):
        for price in (None, 19.5, 'NaN', 'Infinity', '-1', '1e2', '19.501', '19-25', '10000000000.00'):
            with self.subTest(price=price), self.assertRaises(ValidationError):
                self.parse({**self.payload, 'price': price})
        for quote_type in ('range', 'original', 'installment', None):
            with self.subTest(quote_type=quote_type), self.assertRaises(ValidationError):
                self.parse({**self.payload, 'quote_type': quote_type})

    def test_unexpected_credentials_and_invalid_schema_rejected(self):
        for key in ('cookies', 'html', 'owner', 'token'):
            with self.subTest(key=key), self.assertRaises(ValidationError):
                self.parse({**self.payload, key: 'not accepted'})
        for version in (True, '1', 2):
            with self.subTest(version=version), self.assertRaises(ValidationError):
                self.parse({**self.payload, 'schema_version': version})
        with self.assertRaises(ValidationError):
            self.parse({k: v for k, v in self.payload.items() if k != 'price'})

    def test_timezone_expiry_and_future_rejected(self):
        for observed in ('bad', '2026-02-30T12:00:00Z', '2026-10-08T13:00:00',
                         (self.now - timedelta(minutes=11)).isoformat(),
                         (self.now + timedelta(minutes=3)).isoformat()):
            with self.subTest(observed=observed), self.assertRaises(ValidationError):
                self.parse({**self.payload, 'observed_at': observed})

    def test_text_country_and_evidence_bounds(self):
        for field, value in (('title', ''), ('evidence', 'x' * 501), ('currency', None),
                             ('market_country', 'english'), ('conditions', ['x'] * 6),
                             ('conditions', [None]), ('capture_id', 'bad'), ('adapter_version', 'bad')):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.parse({**self.payload, field: value})

    def test_otto_url_and_variant_use_existing_identity_rules(self):
        url = 'https://www.otto.de/p/controlled-fixture-S0123/?variationId=A123'
        data = {**self.payload, 'platform': 'OTTO', 'url': url, 'product_id': 'S0123',
                'sku_id': 'A123', 'adapter_version': 'otto-dom/1', 'currency': 'EUR', 'market_country': 'DE'}
        self.assertEqual(self.parse(data, target=url)['currency'], 'EUR')
        with self.assertRaises(ValidationError):
            self.parse({**data, 'sku_id': 'other'}, target=url)
