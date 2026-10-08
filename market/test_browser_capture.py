"""契约测试不访问外站、业务数据库或写入历史。"""
import json
from datetime import timedelta
from unittest.mock import patch

from django.core import signing
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.utils import timezone

from .browser_capture import (
    MAX_CAPTURE_BYTES, load_preview, parse_capture, sign_preview, validate_capture,
)


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

    def test_utf8_json_and_exact_body_limit(self):
        payload = {**self.payload, 'title': '受控契约样本 🧪'}
        raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        padded = raw + b' ' * (MAX_CAPTURE_BYTES - len(raw))
        self.assertEqual(parse_capture(padded, URL, now=self.now)['title'], payload['title'])
        with self.assertRaises(ValidationError):
            parse_capture(padded + b' ', URL, now=self.now)

    def test_duplicate_quote_and_nested_fields_rejected(self):
        raw = json.dumps(self.payload).encode()
        for extra in (b',"price":"0.01"}', b',"sku_id":"456"}'):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                parse_capture(raw[:-1] + extra, URL, now=self.now)
        with self.assertRaises(ValidationError):
            parse_capture(b'{"conditions":[{"price":"1","price":"2"}]}', URL, now=self.now)

    def test_invalid_json_encoding_constants_and_depth_rejected(self):
        for raw in (b'', b'\xff', b'{} trailing', b'[]', b'null', b'{',
                    b'{"price":NaN}', b'{"price":Infinity}', b'{"price":-Infinity}',
                    b'[' * 2000 + b'0' + b']' * 2000, 'not bytes'):
            with self.subTest(raw_type=type(raw).__name__, size=len(raw)), self.assertRaises(ValidationError):
                parse_capture(raw, URL, now=self.now)

    def test_unpaired_unicode_surrogate_rejected_without_losing_valid_emoji(self):
        for field in ('title', 'evidence', 'url'):
            data = {**self.payload, field: 'bad\ud800'}
            with self.subTest(field=field), self.assertRaises(ValidationError):
                parse_capture(json.dumps(data).encode(), URL, now=self.now)

    def test_database_unsafe_control_text_rejected_but_multiline_evidence_preserved(self):
        for control in ('\x00', '\x07', '\x1f', '\x7f'):
            with self.subTest(control=repr(control)), self.assertRaises(ValidationError):
                self.parse({**self.payload, 'evidence': 'price' + control + '19.50'})
        data = {**self.payload, 'evidence': 'Price USD 19.50\nSelected\tSKU 123'}
        self.assertEqual(self.parse(data)['evidence'], data['evidence'])

    def preview(self):
        return sign_preview(json.dumps(self.payload).encode(), URL,
                            owner_id=1, product_pk=2, now=self.now)

    def test_signed_preview_roundtrip_and_no_price_reinterpretation(self):
        result = load_preview(self.preview(), URL, owner_id=1, product_pk=2)
        self.assertEqual((result['price'], result['sku_id']), ('19.50', '123'))
        self.assertEqual(result['observed_at'], self.payload['observed_at'])

    def test_preview_account_product_and_current_url_bound(self):
        token = self.preview()
        for owner, product_pk, url in ((3, 2, URL), (1, 3, URL),
                                      (1, 2, URL.replace('sku_id=123', 'sku_id=456')),
                                      (1, 2, URL.replace('1005001234567890', '999'))):
            with self.subTest(owner=owner, product_pk=product_pk, url=url), self.assertRaises(ValidationError):
                load_preview(token, url, owner_id=owner, product_pk=product_pk)

    def test_tampered_expired_and_other_import_tokens_rejected(self):
        token = self.preview()
        for invalid in (token + 'tamper', signing.dumps({}, salt='product-page-preview-v3'), None):
            with self.subTest(token_type=type(invalid).__name__), self.assertRaises(ValidationError):
                load_preview(invalid, URL, owner_id=1, product_pk=2)
        with patch('django.core.signing.time.time', return_value=self.now.timestamp() - 1201):
            expired = self.preview()
        with self.assertRaises(ValidationError):
            load_preview(expired, URL, owner_id=1, product_pk=2)

    def test_preview_rejects_anonymous_or_invalid_product_context(self):
        for owner, product_pk in ((None, 2), (True, 2), (1, 0), (1, '2')):
            with self.subTest(owner=owner, product_pk=product_pk), self.assertRaises(ValidationError):
                sign_preview(json.dumps(self.payload).encode(), URL,
                             owner_id=owner, product_pk=product_pk, now=self.now)

    def test_preview_does_not_sign_invalid_quote(self):
        raw = json.dumps({**self.payload, 'price': '19-25'}).encode()
        with self.assertRaises(ValidationError):
            sign_preview(raw, URL, owner_id=1, product_pk=2, now=self.now)
