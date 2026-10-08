"""eBay目标及浏览器协议回归；受控数据，不是实站采集成功证据。"""
from django.core.exceptions import ValidationError
import json
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from .browser_capture import validate_capture
from .ebay import normalize_ebay_url
from .forms import AnalyzeForm, ProductForm
from .models import CollectionJob, Product, Snapshot
from .platforms import known_platform


URL = 'https://www.ebay.com/itm/112259821206?var=412674842751'


class EbayTargetTests(SimpleTestCase):
    def test_slug_tracking_and_variant_canonicalization(self):
        source = 'https://ebay.com/itm/Controlled-Listing/112259821206/?var=412674842751&tracking=test#price'
        self.assertEqual(normalize_ebay_url(source), URL)
        self.assertEqual(normalize_ebay_url(URL.split('?')[0]), URL.split('?')[0])

    def test_catalog_iid_maps_to_listing_and_preserves_variant_and_region(self):
        source = 'https://www.ebay.com/p/813169729?iid=318716291619&tracking=test#price'
        self.assertEqual(normalize_ebay_url(source), 'https://www.ebay.com/itm/318716291619')
        self.assertEqual(normalize_ebay_url(source.split('#')[0].replace('ebay.com', 'ebay.de') + '&var=412674842751'),
                         'https://www.ebay.de/itm/318716291619?var=412674842751')
        self.assertEqual(normalize_ebay_url(source.split('#')[0] + '&var=412674842751'),
                         'https://www.ebay.com/itm/318716291619?var=412674842751')

    def test_catalog_missing_duplicate_invalid_iid_and_conflicting_listing_rejected(self):
        base = 'https://www.ebay.com/p/813169729'
        for source in (base, base + '?iid=', base + '?iid=813169729x', base + '?iid=123',
                       base + '?iid=318716291619&iid=318716291619',
                       base + '?iid=318716291619&iid=377489913401',
                       base + '?iid=318716291619&var=',
                       base + '?iid=318716291619&var=111&var=222',
                       'https://www.ebay.com/itm/318716291619?iid=377489913401',
                       'https://www.ebay.com/itm/318716291619?iid=318716291619&iid=318716291619'):
            with self.subTest(source=source), self.assertRaises(ValidationError):
                normalize_ebay_url(source)

    def test_regional_hosts_remain_distinct(self):
        uk = URL.replace('ebay.com', 'ebay.co.uk')
        self.assertEqual(normalize_ebay_url(uk), uk)
        self.assertNotEqual(normalize_ebay_url(uk), URL)
        self.assertEqual(known_platform(uk), 'eBay')

    def test_invalid_hosts_paths_ports_and_variant_rejected(self):
        for url in ('https://ebay.com.example.com/itm/112259821206',
                    'https://evilebay.com/itm/112259821206',
                    'https://www.ebay.com:444/itm/112259821206',
                    'https://user:password@www.ebay.com/itm/112259821206',
                    'https://www.ebay.com/sch/i.html', 'https://www.ebay.com/str/store',
                    'http://www.ebay.com/itm/112259821206',
                    URL + '&var=111', URL.split('?')[0] + '?var=',
                    URL.split('?')[0] + '?var=bad'):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                normalize_ebay_url(url)
        self.assertIsNone(known_platform('https://ebay.com.example.com/'))

    def test_homepage_does_not_misidentify_ebay_as_shopify(self):
        for choice in ('Auto', 'Shopify', 'AliExpress'):
            form = AnalyzeForm({'platform': choice, 'url': URL}, allow_store=True)
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.cleaned_data['platform'], 'eBay')
        automatic = AnalyzeForm({'platform': 'eBay', 'url': URL})
        self.assertFalse(automatic.is_valid())
        self.assertIn('eBay', str(automatic.errors))


class EbayCaptureTests(SimpleTestCase):
    def capture(self, **changes):
        return {'schema_version': 1, 'capture_id': '37b9cc53-510a-4acb-97b2-9c243d1f3c56',
                'adapter_version': 'ebay-dom/1', 'platform': 'eBay', 'url': URL,
                'product_id': '112259821206', 'sku_id': '412674842751',
                'title': 'Controlled eBay fixture', 'price': '19.50', 'currency': 'USD',
                'quote_type': 'current', 'market_country': None, 'conditions': [],
                'observed_at': timezone.now().isoformat(), 'evidence': 'Controlled fixture', **changes}

    def test_selected_variant_capture_and_unknown_country(self):
        result = validate_capture(self.capture(), URL)
        self.assertEqual(result['sku_id'], '412674842751')
        self.assertIsNone(result['market_country'])

    def test_item_variant_and_regional_quote_conflicts_rejected(self):
        for changes in ({'url': URL.replace('ebay.com', 'ebay.co.uk')},
                        {'url': URL.replace('412674842751', '999')},
                        {'url': URL.replace('112259821206', '999')},
                        {'sku_id': None}, {'product_id': '999'}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                validate_capture(self.capture(**changes), URL)

    def test_catalog_target_accepts_only_the_selected_listing_not_catalog_or_other_offer(self):
        source = 'https://www.ebay.com/p/813169729?iid=318716291619'
        capture = self.capture(url='https://www.ebay.com/itm/318716291619',
                               product_id='318716291619', sku_id=None, price='54.99')
        result = validate_capture(capture, source)
        self.assertEqual((result['product_id'], result['currency']), ('318716291619', 'USD'))
        for changes in ({'product_id': '813169729'}, {'url': 'https://www.ebay.com/itm/377489913401',
                         'product_id': '377489913401'}, {'url': 'https://www.ebay.de/itm/318716291619'}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                validate_capture({**capture, **changes}, source)

    def test_variant_does_not_fall_back_into_generic_product(self):
        with self.assertRaises(ValidationError):
            validate_capture(self.capture(), URL.split('?')[0])


class EbayFlowTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username='ebay-review')
        self.client.force_login(self.owner)

    def test_homepage_and_manual_product_preserve_variant_without_queue(self):
        response = self.client.post(reverse('analyze_competitor'), {'platform': 'Auto', 'url': URL+'&tracking=x'})
        product = Product.objects.get()
        self.assertEqual((product.url, product.platform), (URL, 'eBay'))
        self.assertRedirects(response, reverse('browser_report', args=[product.pk]))
        self.assertFalse(CollectionJob.objects.exists())
        response = self.client.post(reverse('collect_product', args=[product.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(CollectionJob.objects.exists())
        form = ProductForm({'title': 'eBay fixture', 'platform': 'eBay', 'url': URL+'&tracking=x'}, instance=product)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['url'], URL)

    def test_catalog_home_and_capture_share_one_listing_without_automatic_queue(self):
        source = 'https://www.ebay.com/p/813169729?iid=318716291619'
        response = self.client.post(reverse('analyze_competitor'), {'platform': 'Auto', 'url': source})
        product = Product.objects.get()
        self.assertEqual(product.url, 'https://www.ebay.com/itm/318716291619')
        self.assertRedirects(response, reverse('browser_report', args=[product.pk]))
        capture = EbayCaptureTests().capture(url=product.url, product_id='318716291619',
                                             sku_id=None, price='54.99')
        response = self.client.post(reverse('browser_capture'),
            urlencode({'target_url': source, 'capture': json.dumps(capture)}),
            content_type='application/x-www-form-urlencoded')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['product'].pk, product.pk)
        self.assertEqual(Product.objects.count(), 1)
        self.assertFalse(CollectionJob.objects.exists())
        self.assertFalse(Snapshot.all_objects.exists())

    def test_preview_confirmation_and_private_report(self):
        capture = EbayCaptureTests().capture()
        response = self.client.post(reverse('browser_capture'),
            urlencode({'target_url': URL, 'capture': json.dumps(capture)}),
            content_type='application/x-www-form-urlencoded')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Snapshot.all_objects.exists())
        product = response.context['product']
        response = self.client.post(reverse('browser_capture_confirm', args=[product.pk]),
            urlencode({'preview': response.context['preview']}), content_type='application/x-www-form-urlencoded')
        self.assertRedirects(response, reverse('browser_report', args=[product.pk]))
        row = Snapshot.all_objects.get()
        self.assertEqual((row.owner_id, row.capture_data['sku_id']), (self.owner.pk, '412674842751'))
        self.assertFalse(product.snapshots.exists())
