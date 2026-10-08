"""B3受控协议回归；不请求外站，不使用业务数据库。"""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch
from urllib.parse import urlencode
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, transaction
from django.test import Client, TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from .browser_capture import sign_preview
from .browser_capture_records import private_groups, save_preview
from .importing import import_csv
from .models import Product, ProductReviewBatch, Snapshot

URL = 'https://www.aliexpress.com/item/1005001234567890.html?sku_id=123'


def payload(**changes):
    return {
        'schema_version': 1, 'capture_id': str(uuid4()), 'adapter_version': 'aliexpress-dom/1',
        'platform': 'AliExpress', 'url': URL, 'product_id': '1005001234567890', 'sku_id': '123',
        'title': '<script>private title</script>', 'price': '987.65', 'currency': 'USD',
        'quote_type': 'current', 'market_country': None, 'conditions': [],
        'observed_at': timezone.now().isoformat(), 'evidence': '<script>private evidence</script>',
        **changes,
    }


class BrowserFlowTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username='browser-one')
        self.other = get_user_model().objects.create_user(username='browser-two')
        self.client.force_login(self.owner)
        self.data = payload()
        self.product = Product.objects.create(url=URL, platform='AliExpress', title='Shared product')

    def token(self, data=None, product=None, owner=None):
        product = product or self.product
        return sign_preview(json.dumps(data or self.data).encode(), product.url,
                            owner_id=(owner or self.owner).pk, product_pk=product.pk)

    def post(self, path, fields):
        return self.client.post(path, urlencode(fields), content_type='application/x-www-form-urlencoded')

    def confirm(self, token=None, product=None):
        return self.post(reverse('browser_capture_confirm', args=[(product or self.product).pk]),
                         {'preview': token or self.token()})

    def save(self):
        return save_preview(self.token(), owner=self.owner, product_pk=self.product.pk)[0]

    def test_login_and_get_are_read_only(self):
        before = Product.objects.count()
        response = self.client.get(reverse('browser_capture'))
        self.assertContains(response, 'data-browser-capture-bridge="ready"')
        self.assertContains(response, 'id="browser-capture-form"')
        self.client.get(reverse('browser_report', args=[self.product.pk]))
        self.assertEqual(Product.objects.count(), before)
        self.assertFalse(Snapshot.all_objects.exists())
        self.assertEqual(self.client.get(reverse('browser_capture_confirm', args=[self.product.pk])).status_code, 405)
        self.client.logout()
        for path in (reverse('browser_capture'), reverse('browser_report', args=[self.product.pk])):
            self.assertEqual(self.client.get(path).status_code, 302)
        self.assertEqual(self.confirm().status_code, 302)
        self.assertFalse(Snapshot.all_objects.exists())

    def test_preview_creates_product_but_not_observation_and_escapes(self):
        self.product.delete()
        response = self.post(reverse('browser_capture'), {'target_url': URL + '&tracking=x', 'capture': json.dumps(self.data)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.get().url, URL)
        self.assertFalse(Snapshot.all_objects.exists())
        self.assertNotContains(response, 'data-browser-capture-bridge="ready"')
        self.assertContains(response, '&lt;script&gt;private evidence&lt;/script&gt;')
        self.assertNotContains(response, '<script>private evidence</script>')
        self.assertContains(response, '尚未保存')
        self.assertEqual(Product.objects.get().title, '待识别竞品 · 1005001234567890')
        at = timezone.localtime(response.context['capture_time'], ZoneInfo('Asia/Shanghai'))
        self.assertContains(response, at.strftime('%Y-%m-%d %H:%M'))
        self.assertContains(response, self.data['observed_at'])

    def test_preview_failure_does_not_create_product(self):
        self.product.delete()
        for changes in ({'price': None}, {'sku_id': '456'}, {'capture_id': 'bad'}, {'currency': None}):
            response = self.post(reverse('browser_capture'), {'target_url': URL, 'capture': json.dumps({**self.data, **changes})})
            self.assertEqual(response.status_code, 400)
            self.assertFalse(Product.objects.exists())
            self.assertFalse(Snapshot.all_objects.exists())

    def test_csrf_required_for_preview_and_confirm(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        for path, fields in ((reverse('browser_capture'), {'target_url': URL, 'capture': json.dumps(self.data)}),
                             (reverse('browser_capture_confirm', args=[self.product.pk]), {'preview': self.token()})):
            self.assertEqual(client.post(path, urlencode(fields), content_type='application/x-www-form-urlencoded').status_code, 403)
        client.get(reverse('browser_capture'))
        csrf = client.cookies['csrftoken'].value
        response = client.post(reverse('browser_capture'), urlencode({'target_url': URL, 'capture': json.dumps(self.data), 'csrfmiddlewaretoken': csrf}), content_type='application/x-www-form-urlencoded')
        self.assertEqual(response.status_code, 200)
        response = client.post(reverse('browser_capture_confirm', args=[self.product.pk]), urlencode({'preview': response.context['preview'], 'csrfmiddlewaretoken': csrf}), content_type='application/x-www-form-urlencoded')
        self.assertEqual(response.status_code, 302)

    def test_body_encoding_type_duplicates_unknown_and_bounds(self):
        path = reverse('browser_capture')
        good = {'target_url': URL, 'capture': json.dumps(self.data)}
        for body, content_type in ((urlencode(good)+'&target_url='+URL, 'application/x-www-form-urlencoded'),
                                   (urlencode({**good, 'owner': self.other.pk}), 'application/x-www-form-urlencoded'),
                                   (urlencode({'target_url': URL}), 'application/x-www-form-urlencoded'),
                                   (urlencode({**good, 'capture': ' ' * 16385}), 'application/x-www-form-urlencoded'),
                                   (b'capture=%FF&target_url=x', 'application/x-www-form-urlencoded'),
                                   (b'a' * (128*1024+1), 'application/x-www-form-urlencoded'),
                                   (json.dumps(good), 'application/json')):
            with self.subTest(content_type=content_type, length=len(body)):
                self.assertEqual(self.client.post(path, body, content_type=content_type).status_code, 400)
        self.assertFalse(Snapshot.all_objects.exists())
        self.assertEqual(Product.objects.count(), 1)
        response = self.post(reverse('browser_capture_confirm', args=[self.product.pk]), [('preview', self.token()), ('preview', self.token())])
        self.assertEqual(response.status_code, 400)

    def test_confirm_preserves_original_data_unknowns_and_idempotence(self):
        token = self.token()
        response = self.confirm(token)
        self.assertRedirects(response, reverse('browser_report', args=[self.product.pk]))
        row = Snapshot.all_objects.get()
        self.assertEqual(row.owner, self.owner)
        self.assertEqual(row.source, 'browser')
        self.assertEqual(row.observed_at.isoformat(), self.data['observed_at'])
        self.assertIsNone(row.sales)
        self.assertIsNone(row.rating)
        self.assertIsNone(row.review_count)
        self.assertIsNone(row.capture_data['market_country'])
        self.assertEqual(row.capture_data['conditions'], [])
        self.assertRedirects(self.confirm(token), reverse('browser_report', args=[self.product.pk]))
        self.assertEqual(Snapshot.all_objects.count(), 1)
        report = self.client.get(reverse('browser_report', args=[self.product.pk]))
        self.assertContains(report, '&lt;script&gt;private evidence&lt;/script&gt;')
        self.assertContains(report, '报价条件未知')
        at = timezone.localtime(row.observed_at, ZoneInfo('Asia/Shanghai'))
        self.assertContains(report, at.strftime('%Y-%m-%d %H:%M'))
        self.assertContains(report, self.data['observed_at'])

    def test_conflicting_content_and_product_never_overwrite(self):
        original = self.save()
        for changes in ({'price': '1.00'}, {'conditions': ['new promotion']}, {'evidence': 'other'}):
            self.assertEqual(self.confirm(self.token({**self.data, **changes})).status_code, 400)
        other_data = {**self.data, 'url': URL.replace('1234567890', '1234567891'), 'product_id': '1005001234567891'}
        other_product = Product.objects.create(url=other_data['url'], platform='AliExpress', title='other')
        self.assertEqual(self.confirm(self.token(other_data, other_product), other_product).status_code, 400)
        original.refresh_from_db()
        self.assertEqual(str(original.price), '987.65')
        self.assertEqual(Snapshot.all_objects.count(), 1)

    def test_wrong_account_product_expiry_tampering_and_changed_target(self):
        token = self.token()
        self.assertEqual(self.confirm(token+'x').status_code, 400)
        with patch('django.core.signing.time.time', return_value=timezone.now().timestamp()+1201):
            self.assertEqual(self.confirm(token).status_code, 400)
        self.client.force_login(self.other)
        self.assertEqual(self.confirm(token).status_code, 400)
        self.client.force_login(self.owner)
        other_product = Product.objects.create(url=URL.replace('sku_id=123', 'sku_id=456'), platform='AliExpress', title='other')
        self.assertEqual(self.confirm(token, other_product).status_code, 400)
        other_product.delete()
        for url, platform in ((URL.replace('sku_id=123', 'sku_id=456'), 'AliExpress'), (URL, 'OTTO')):
            Product.objects.filter(pk=self.product.pk).update(url=url, platform=platform)
            self.assertEqual(self.confirm(token).status_code, 400)
        self.assertFalse(Snapshot.all_objects.exists())

    def test_preview_transaction_rolls_back_new_product_on_sign_failure(self):
        self.product.delete()
        with patch('market.browser_capture_views.sign_preview', side_effect=ValidationError('changed')):
            self.assertEqual(self.post(reverse('browser_capture'), {'target_url': URL, 'capture': json.dumps(self.data)}).status_code, 400)
        self.assertFalse(Product.objects.exists())

    def test_same_uuid_and_time_are_independent_across_owners(self):
        self.save()
        self.client.force_login(self.other)
        self.assertEqual(self.confirm(self.token(owner=self.other)).status_code, 302)
        self.assertEqual(Snapshot.all_objects.count(), 2)
        response = self.client.get(reverse('browser_report', args=[self.product.pk]))
        self.assertEqual(len(response.context['groups'][0]['rows']), 1)
        third = get_user_model().objects.create_user(username='empty')
        self.client.force_login(third)
        self.assertContains(self.client.get(reverse('browser_report', args=[self.product.pk])), '还没有保存报价')
        self.assertFalse(Snapshot.objects.exists())
        self.assertFalse(self.product.snapshots.exists())

    def test_full_conditions_separate_groups_beyond_truncated_context(self):
        common = ['x'*160, 'y'*160]
        records = []
        for country, sku, currency, suffix in ((None, '123', 'USD', 'a'), (None, '123', 'USD', 'b'), ('US', '123', 'USD', 'a'), (None, '123', 'EUR', 'a')):
            data = payload(conditions=common+[suffix], market_country=country, currency=currency)
            records.append(save_preview(self.token(data), owner=self.owner, product_pk=self.product.pk)[0])
        self.assertEqual(records[0].context, records[1].context)
        self.assertEqual(len(private_groups(records)), 4)

    def test_public_report_export_compare_profit_and_reviews_exclude_browser(self):
        private = self.save()
        ProductReviewBatch.objects.create(snapshot=private, source_url=URL, file_fingerprint='private', samples=[{'body': 'private evidence'}])
        Snapshot.objects.create(product=self.product, price='12.34', currency='USD', source='manual', observed_at=timezone.now()-timedelta(days=1))
        other_product = Product.objects.create(title='other', url='https://example.org/product')
        Snapshot.objects.create(product=other_product, price='10', currency='USD', source='manual', observed_at=timezone.now())
        paths = [reverse('product_detail', args=[self.product.pk]), reverse('csv_export'),
                 reverse('compare')+'?'+urlencode({'products': [self.product.pk, other_product.pk], 'currency': 'USD', 'days': 0}, doseq=True),
                 reverse('profit')+'?product='+str(self.product.pk), reverse('product_reviews', args=[self.product.pk])]
        for path in paths:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, '987.65')
            self.assertNotContains(response, 'private evidence')
            if path.startswith(reverse('compare')):
                self.assertTrue(response.context['form'].is_valid())
                self.assertEqual(len(response.context['rows']), 2)
            if path.startswith(reverse('product_reviews', args=[self.product.pk])):
                self.assertIsNone(response.context['batch'])
            if path.startswith(reverse('profit')):
                self.assertEqual(str(response.context['form'].initial['selling_price']), '12.34')
        self.assertEqual(self.product.snapshots.count(), 1)
        self.assertEqual(Snapshot.objects.count(), 2)
        home = self.client.get(reverse('dashboard'))
        self.assertEqual(home.context['snapshot_count'], 2)
        self.assertEqual(home.context['browser_home']['count'], 1)
        self.assertContains(home, '987.65')
        self.assertNotContains(home, 'private evidence')
        self.client.force_login(self.other)
        other_home = self.client.get(reverse('dashboard'))
        self.assertEqual(other_home.context['browser_home']['count'], 0)
        self.assertNotContains(other_home, '987.65')
        self.assertNotContains(other_home, 'private title')

    def test_home_shows_latest_record_per_product_and_only_current_owner(self):
        self.save()
        latest_data = payload(title='My newest quote', price='24.99')
        latest = save_preview(self.token(latest_data), owner=self.owner, product_pk=self.product.pk)[0]
        foreign = payload(title='Other account secret', price='888.88')
        save_preview(self.token(foreign, owner=self.other), owner=self.other, product_pk=self.product.pk)
        for number in range(4):
            target = URL.replace('1234567890', f'123456789{number+1}')
            product = Product.objects.create(url=target, platform='AliExpress', title=f'Product {number}')
            data = payload(url=target, product_id=f'100500123456789{number+1}', title=f'Own product {number}')
            save_preview(self.token(data, product), owner=self.owner, product_pk=product.pk)
        response = self.client.get(reverse('dashboard'))
        recent = list(response.context['browser_home']['recent'])
        self.assertEqual(response.context['browser_home']['count'], 6)
        self.assertEqual(len(recent), 3)
        self.assertEqual(len({row.product_id for row in recent}), 3)
        self.assertTrue(all(row.owner_id == self.owner.pk for row in recent))
        self.assertNotContains(response, 'Other account secret')
        self.assertNotContains(response, '888.88')
        self.assertEqual(response.context['snapshot_count'], 0)
        # Remove later products so the two observations of the original product are in the visible range.
        Product.objects.exclude(pk=self.product.pk).delete()
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(list(response.context['browser_home']['recent']), [latest])
        self.assertContains(response, 'My newest quote')
        self.assertContains(response, '24.99')
        self.assertNotContains(response, '987.65')

    def test_csv_cannot_forge_browser_source(self):
        content = f'title,url,price,currency,observed_at,source\nx,{URL},1,USD,{self.data["observed_at"]},browser\n'.encode()
        with self.assertRaisesMessage(ValidationError, '账号私有'):
            import_csv(content)
        self.assertFalse(Snapshot.all_objects.exists())

    def test_database_constraints_enforce_owner_and_uuid_and_public_uniqueness(self):
        base = {'product': self.product, 'price': 1, 'currency': 'USD', 'observed_at': timezone.now()}
        for fields in ({'source': 'browser'}, {'source': 'browser', 'owner': self.owner},
                       {'source': 'manual', 'owner': self.owner}, {'source': 'manual', 'capture_id': uuid4()}):
            with self.subTest(fields=fields), self.assertRaises(IntegrityError), transaction.atomic():
                Snapshot.all_objects.create(**base, **fields)
        row = self.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Snapshot.all_objects.create(**base, source='browser', owner=self.owner, capture_id=row.capture_id)
        Snapshot.objects.create(**base, source='manual')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Snapshot.objects.create(**base, source='manual')


class BrowserConcurrencyTests(TransactionTestCase):
    @skipUnlessDBFeature('has_select_for_update')
    def test_concurrent_confirm_is_idempotent(self):
        owner = get_user_model().objects.create_user(username='concurrent')
        product = Product.objects.create(url=URL, platform='AliExpress', title='Shared')
        token = sign_preview(json.dumps(payload()).encode(), URL, owner_id=owner.pk, product_pk=product.pk)
        barrier = Barrier(2)

        def confirm_once():
            close_old_connections()
            try:
                current_owner = get_user_model().objects.get(pk=owner.pk)
                barrier.wait(timeout=10)
                return save_preview(token, owner=current_owner, product_pk=product.pk)[1]
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: confirm_once(), range(2)))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(Snapshot.all_objects.count(), 1)
