"""覆盖真实业务边界：导入回滚、币种隔离、权限、采集失败和任务去重。"""
import csv
import io
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
import httpx
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from .collectors import CollectionError, collect, parse_product, validate_target
from .importing import import_csv
from .jobs import enqueue, run_next
from .models import CollectionJob, Product, Snapshot

HEADER = 'title,url,platform,shop,price,currency,sales,observed_at,source\n'
ROW = '测试商品,https://example.com/item/1,AliExpress,测试店,12.50,USD,,2026-10-01T10:00:00+08:00,csv\n'


class ImportTests(TestCase):
    def test_import_is_repeatable_and_preserves_notes(self):
        self.assertEqual(import_csv((HEADER + ROW).encode()), (1, 0))
        product = Product.objects.get()
        product.notes = '保留备注'
        product.save()
        self.assertEqual(import_csv((HEADER + ROW).encode()), (0, 1))
        self.assertEqual(Snapshot.objects.count(), 1)
        self.assertIsNone(Snapshot.objects.get().sales)
        product.refresh_from_db()
        self.assertEqual(product.notes, '保留备注')

    def test_invalid_later_row_leaves_database_unchanged(self):
        with self.assertRaisesMessage(ValidationError, '第 3 行'):
            import_csv((HEADER + ROW + ROW.replace('12.50', '-1')).encode())
        self.assertFalse(Product.objects.exists())
        self.assertFalse(Snapshot.objects.exists())

    def test_invalid_prices_currencies_sales_and_dates(self):
        for old, new in [('12.50', 'NaN'), ('12.50', '12.501'), ('USD', 'US'),
                         (',,2026', ',abc,2026'), ('2026-10-01T10:00:00+08:00', 'no-date')]:
            with self.subTest(new=new), self.assertRaises(ValidationError):
                import_csv((HEADER + ROW.replace(old, new)).encode())
        self.assertFalse(Product.objects.exists())

    def test_invalid_encoding_empty_and_missing_headers(self):
        for content in [b'\xff', HEADER.encode(), b'title,url\na,b\n']:
            with self.subTest(content=content), self.assertRaises(ValidationError):
                import_csv(content)

    def test_naive_dates_use_shanghai_timezone(self):
        import_csv((HEADER + ROW.replace('+08:00', '')).encode())
        self.assertEqual(Snapshot.objects.get().observed_at.hour, 2)

    def test_csv_round_trip_preserves_source_and_time(self):
        import_csv((HEADER + ROW.replace(',csv\n', ',demo\n')).encode())
        user = get_user_model().objects.create_user('exporter', password='test-password')
        self.client.force_login(user)
        response = self.client.get(reverse('csv_export'))
        self.assertEqual(import_csv(response.content), (0, 1))
        self.assertEqual(Snapshot.objects.get().source, 'demo')


class WebTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('seller', password='test-password')
        self.product = Product.objects.create(title='测试耳机', url='https://www.aliexpress.com/item/1.html', shop='测试店')
        self.client.force_login(self.user)

    def test_all_business_routes_require_login(self):
        client = Client()
        routes = ['dashboard', 'product_add', 'csv_import', 'csv_export', 'csv_template', 'profit']
        routes += ['product_detail', 'product_edit', 'job_status', 'collect_product']
        for name in routes:
            detail_routes = {'product_detail', 'product_edit', 'job_status', 'collect_product'}
            url = reverse(name, args=[self.product.pk]) if name in detail_routes else reverse(name)
            with self.subTest(name=name):
                self.assertEqual(client.get(url).status_code, 302)

    def test_product_create_and_duplicate_url(self):
        data = {'title': '新商品', 'url': 'https://example.com/new', 'platform': 'Other', 'shop': '', 'notes': '备注'}
        self.assertEqual(self.client.post(reverse('product_add'), data).status_code, 302)
        response = self.client.post(reverse('product_add'), data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.assertEqual(Product.objects.count(), 2)

    def test_currency_filter_and_detail_do_not_mix_currencies(self):
        now = timezone.now()
        Snapshot.objects.create(product=self.product, price=10, currency='USD', source='csv', observed_at=now)
        Snapshot.objects.create(product=self.product, price=70, currency='CNY', source='csv', observed_at=now + timedelta(seconds=1))
        response = self.client.get(reverse('product_detail', args=[self.product.pk]), {'currency': 'USD'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['chart']['prices'], ['10.00'])
        self.assertIsNone(response.context['change'])
        response = self.client.get(reverse('dashboard'), {'currency': 'USD'})
        self.assertEqual(response.context['page'].paginator.count, 0)
        response = self.client.get(reverse('dashboard'), {'q': '测试店', 'currency': 'CNY'})
        self.assertContains(response, '测试耳机')

    def test_zero_price_not_hidden(self):
        Snapshot.objects.create(product=self.product, price=0, currency='USD', source='demo', observed_at=timezone.now())
        self.assertContains(self.client.get(reverse('dashboard')), '0.00')

    def test_collect_post_only_and_deduplicates(self):
        url = reverse('collect_product', args=[self.product.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url)
        self.client.post(url)
        self.assertEqual(CollectionJob.objects.count(), 1)
        self.assertTrue(self.client.get(reverse('job_status', args=[self.product.pk])).json()['active'])

    def test_csrf_required_on_mutations(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse('collect_product', args=[self.product.pk])).status_code, 403)

    def test_import_form_and_size_limit(self):
        file = SimpleUploadedFile('data.csv', (HEADER + ROW).encode())
        self.assertEqual(self.client.post(reverse('csv_import'), {'file': file}).status_code, 302)
        file = SimpleUploadedFile('huge.csv', b'x' * (2 * 1024 * 1024 + 1))
        self.assertContains(self.client.post(reverse('csv_import'), {'file': file}), '不能超过 2 MB')

    def test_export_formula_escape_and_template_headers(self):
        self.product.title = '=HYPERLINK("evil")'
        self.product.save()
        Snapshot.objects.create(product=self.product, price=1, currency='USD', source='csv', observed_at=timezone.now())
        response = self.client.get(reverse('csv_export'))
        rows = list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
        self.assertTrue(rows[1][0].startswith("'="))
        self.assertContains(self.client.get(reverse('csv_template')), 'observed_at')

    def test_profit_math_zero_revenue_and_validation(self):
        data = {'selling_price': '20', 'exchange_rate': '7', 'cost': '50', 'shipping': '20', 'fee_rate': '10', 'other_cost': '6'}
        response = self.client.post(reverse('profit'), data)
        self.assertEqual(response.context['result']['net'], Decimal('50.00'))
        self.assertEqual(response.context['result']['margin'], Decimal('35.71'))
        data['selling_price'] = '0'
        self.assertIsNone(self.client.post(reverse('profit'), data).context['result']['margin'])
        data['exchange_rate'] = '0'
        response = self.client.post(reverse('profit'), data, HTTP_HX_REQUEST='true')
        self.assertContains(response, '输入无效')
        self.assertIsNone(response.context['result'])

    def test_demo_command_repeatable(self):
        call_command('seed_demo', stdout=io.StringIO())
        call_command('seed_demo', stdout=io.StringIO())
        self.assertEqual(Snapshot.objects.filter(source='demo').count(), 21)


class CollectorTests(TestCase):
    def test_parse_json_ld_graph_and_offer_list(self):
        data = {'@graph': [{'@type': 'Product', 'offers': [{'price': '12.50', 'priceCurrency': 'usd'}]}]}
        result = parse_product('<script type="application/ld+json">' + json.dumps(data) + '</script>')
        self.assertEqual(result['price'], Decimal('12.50'))
        self.assertEqual(result['currency'], 'USD')
        self.assertIsNone(result['sales'])

    def test_missing_ambiguous_and_invalid_price_are_failures(self):
        offers = [[], [{'price': -1, 'priceCurrency': 'USD'}], [{'lowPrice': 1, 'priceCurrency': 'USD'}],
                  [{'price': 1, 'priceCurrency': 'USD'}, {'price': 2, 'priceCurrency': 'USD'}]]
        for offer in offers:
            html = '<script type="application/ld+json">' + json.dumps({'@type': 'Product', 'offers': offer}) + '</script>'
            with self.subTest(offer=offer), self.assertRaises(CollectionError):
                parse_product(html)
        with self.assertRaises(CollectionError):
            parse_product('<html>请登录</html>')

    def test_url_and_private_address_rejection(self):
        for url in ['http://www.aliexpress.com/item/1', 'https://evil.com', 'https://aliexpress.com.evil.com',
                    'https://user:password@aliexpress.com/', 'https://aliexpress.com:8443/']:
            with self.subTest(url=url), self.assertRaises(CollectionError):
                validate_target(url)
        with patch('market.collectors.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 443))]), self.assertRaises(CollectionError):
            validate_target('https://www.aliexpress.com/')

    def test_download_redirect_validation_http_error_and_size_limit(self):
        cases = [
            (httpx.Response(302, headers={'location': 'https://evil.com/'}), '仅支持'),
            (httpx.Response(403), 'HTTP 403'),
            (httpx.Response(200, headers={'content-type': 'text/html'}, content=b'x' * (2 * 1024 * 1024 + 1)), '超过'),
        ]
        for response, message in cases:
            transport = httpx.MockTransport(lambda request: response)
            real_client = httpx.Client(transport=transport)
            with self.subTest(message=message), patch('market.collectors.httpx.Client', return_value=real_client), patch(
                'market.collectors.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('8.8.8.8', 443))]):
                with self.assertRaisesMessage(CollectionError, message):
                    collect('https://www.aliexpress.com/item/1.html')

    def test_http_success_saves_explicit_price(self):
        html = '<script type="application/ld+json">{"@type":"Product","offers":{"price":"9.90","priceCurrency":"USD"}}</script>'
        transport = httpx.MockTransport(lambda r: httpx.Response(200, headers={'content-type': 'text/html'}, text=html))
        with patch('market.collectors.httpx.Client', return_value=httpx.Client(transport=transport)), patch(
            'market.collectors.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('8.8.8.8', 443))]):
            self.assertEqual(collect('https://www.aliexpress.com/item/1.html')['price'], Decimal('9.90'))


class JobTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(title='商品', url='https://www.aliexpress.com/item/1.html')

    @patch('market.jobs.collect', return_value={'price': Decimal('9.90'), 'currency': 'USD', 'sales': None})
    def test_success_and_no_duplicate_processing(self, mock):
        job, added = enqueue(self.product)
        self.assertTrue(added)
        self.assertFalse(enqueue(self.product)[1])
        self.assertTrue(run_next())
        self.assertFalse(run_next())
        job.refresh_from_db()
        self.assertEqual(job.status, 'succeeded')
        self.assertEqual(Snapshot.objects.get().source, 'web')
        self.assertEqual(mock.call_count, 1)

    @patch('market.jobs.collect', side_effect=CollectionError('访问验证'))
    def test_failure_does_not_fabricate_data_and_can_retry(self, mock):
        job, _ = enqueue(self.product)
        run_next()
        job.refresh_from_db()
        self.assertEqual(job.status, 'failed')
        self.assertIn('访问验证', job.message)
        self.assertFalse(Snapshot.objects.exists())
        self.assertTrue(enqueue(self.product)[1])

    def test_stale_job_recovery(self):
        job = CollectionJob.objects.create(product=self.product, status='running', started_at=timezone.now() - timedelta(minutes=11))
        self.assertFalse(run_next())
        job.refresh_from_db()
        self.assertEqual(job.status, 'failed')
        self.assertTrue(enqueue(self.product)[1])

    @patch('market.jobs.collect', side_effect=RuntimeError('secret must not leak'))
    def test_unexpected_errors_do_not_expose_secrets(self, mock):
        job, _ = enqueue(self.product)
        run_next()
        job.refresh_from_db()
        self.assertNotIn('secret', job.message)
        self.assertEqual(job.status, 'failed')
