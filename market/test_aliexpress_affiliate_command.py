"""开发命令覆盖：离线标签、无网络/DB、错误正文抑制及输入读取边界。"""
import io
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from market.aliexpress_affiliate import MAX_RESPONSE_BYTES


class AffiliatePreviewCommandTests(SimpleTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'response.json'
        self.options = {
            'fixture_path': str(self.path), 'product_id': '33006951782',
            'country': 'US', 'target_currency': 'USD',
            'requested_at': '2026-10-09T01:00:00+00:00',
            'received_at': '2026-10-09T01:00:01+00:00',
        }

    def write_response(self, products):
        self.path.write_text(json.dumps({'aliexpress_affiliate_productdetail_get_response': {
            'resp_result': {'resp_code': 200, 'result': {
                'current_record_count': len(products), 'products': {'product': products},
            }},
        }}))

    def run_command(self, **overrides):
        output = io.StringIO()
        with patch('httpx.Client', side_effect=AssertionError('must be offline')):
            call_command('preview_aliexpress_affiliate', stdout=output, **{**self.options, **overrides})
        return output.getvalue()

    def test_success_is_explicitly_an_offline_fixture(self):
        self.write_response([{
            'product_id': 33006951782, 'product_title': 'Synthetic API response',
            'product_detail_url': 'https://www.aliexpress.com/item/33006951782.html',
            'sale_price': '15.90', 'sale_price_currency': 'USD',
        }])
        data = json.loads(self.run_command())
        self.assertEqual(data['mode'], 'offline_fixture')
        self.assertIs(data['live_api_verified'], False)
        self.assertIs(data['database_written'], False)
        self.assertIn('15.90', json.dumps(data['preview']))

    def test_error_response_does_not_echo_secrets_or_raw_json(self):
        secret = 'synthetic-app-secret-do-not-print'
        self.path.write_text(json.dumps({'error_response': {
            'code': 50, 'msg': secret, 'sub_msg': secret, 'sub_code': secret,
        }}))
        with self.assertRaises(CommandError) as caught:
            self.run_command()
        self.assertNotIn(secret, str(caught.exception))
        self.assertNotIn('sub_msg', str(caught.exception))

    def test_empty_result_is_explicit_and_not_a_zero_price(self):
        self.write_response([])
        data = json.loads(self.run_command())
        self.assertEqual(data['preview']['status'], 'empty')
        self.assertIsNone(data['preview']['product'])

    def test_missing_file_is_sanitized(self):
        path = Path(self.directory.name) / 'synthetic-private-name.json'
        with self.assertRaises(CommandError) as caught:
            self.run_command(fixture_path=str(path))
        self.assertNotIn(str(path), str(caught.exception))

    def test_symlink_fifo_empty_and_oversized_files_are_rejected(self):
        self.path.write_bytes(b'{}')
        linked = Path(self.directory.name) / 'symlink.json'
        linked.symlink_to(self.path)
        fifo = Path(self.directory.name) / 'fifo'
        os.mkfifo(fifo)
        for path in (linked, fifo):
            with self.subTest(path=path.name), self.assertRaises(CommandError):
                self.run_command(fixture_path=str(path))
        for content in (b'', b' ' * (MAX_RESPONSE_BYTES + 1)):
            self.path.write_bytes(content)
            with self.subTest(size=len(content)), self.assertRaises(CommandError):
                self.run_command()

    def test_request_times_cannot_be_missing_naive_or_invalid(self):
        self.write_response([])
        for timestamp in ('not-a-time', '2026-10-09T01:00:00', '2026-99-01T01:00:00+00:00'):
            with self.subTest(timestamp=timestamp), self.assertRaises(CommandError):
                self.run_command(requested_at=timestamp)
