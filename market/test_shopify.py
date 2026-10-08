from decimal import Decimal
from unittest.mock import patch
import httpx
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, SimpleTestCase
from django.urls import reverse
from .collectors import CollectionError
from .shopify import normalize_shopify_url, parse_shopify, public_address, read_json, collect_shopify, PublicShopifyTransport
from .models import Product, Snapshot, CollectionJob
from .jobs import enqueue, run_next

URL = 'https://store.example.com/products/coat'
DATA = {'handle': 'coat', 'title': 'Rain coat', 'variants': [{'id': 42, 'title': 'Small', 'price': 12900}]}
PUBLIC = [(2, 1, 6, '', ('93.184.215.14', 443))]


class ShopifyCollectorTests(SimpleTestCase):
    def test_canonical_url_preserves_variant_market_and_locale(self):
        value = normalize_shopify_url('https://store.example.com/en-us/collections/coats/products/coat/?utm_source=x&currency=usd&variant=42&country=us')
        self.assertEqual(value, 'https://store.example.com/en-us/products/coat?variant=42&currency=USD&country=US')

    def test_reject_unsafe_and_ambiguous_urls(self):
        for url in ['http://store.example.com/products/coat', 'https://127.0.0.1/products/coat',
                    'https://localhost/products/coat', URL + '?variant=1&variant=2', URL + '?variant=x',
                    'https://store.example.com:8443/products/coat', 'https://store.example.com/']:
            with self.subTest(url=url), self.assertRaises(ValidationError):
                normalize_shopify_url(url)

    def test_price_currency_and_unknown_sales(self):
        result = parse_shopify(DATA, {'currency': 'USD'}, URL)
        self.assertEqual(result['price'], Decimal('129.00'))
        self.assertEqual(result['currency'], 'USD')
        self.assertIsNone(result['sales'])
        self.assertIn('variant=42', result['context'])

    def test_multiple_variants_require_explicit_selection(self):
        product = dict(DATA, variants=DATA['variants'] + [{'id': 43, 'title': 'Large', 'price': 13900}])
        with self.assertRaises(CollectionError):
            parse_shopify(product, {'currency': 'USD'}, URL)
        result = parse_shopify(product, {'currency': 'USD'}, URL + '?variant=43')
        self.assertEqual(result['price'], Decimal('139.00'))
        self.assertIn('Large', result['context'])
        with self.assertRaises(CollectionError):
            parse_shopify(product, {'currency': 'USD'}, URL + '?variant=99')

    def test_reject_wrong_identity_currency_and_price(self):
        cases = [(dict(DATA, handle='other'), {'currency': 'USD'}, URL),
                 (DATA, {}, URL), (DATA, {'currency': 'EUR'}, URL + '?currency=USD'),
                 (dict(DATA, variants=[{'id': 42, 'price': '12900'}]), {'currency': 'USD'}, URL)]
        for product, cart, url in cases:
            with self.subTest(url=url, product=product), self.assertRaises(CollectionError):
                parse_shopify(product, cart, url)

    def test_private_or_mixed_dns_rejected(self):
        for address in ['127.0.0.1', '10.0.0.1', '169.254.169.254', '::1']:
            with patch('market.network.socket.getaddrinfo', return_value=PUBLIC + [(2, 1, 6, '', (address, 443))]), self.assertRaises(CollectionError):
                public_address('store.example.com')

    def test_transport_pins_public_ip_and_verifies_hostname(self):
        def handler(request):
            self.assertEqual(request.url.host, '93.184.215.14')
            self.assertEqual(request.headers['Host'], 'store.example.com')
            self.assertEqual(request.extensions['sni_hostname'], 'store.example.com')
            return httpx.Response(200, json={'currency': 'USD'})
        with httpx.Client(transport=PublicShopifyTransport(httpx.MockTransport(handler))) as client, patch('market.network.socket.getaddrinfo', return_value=PUBLIC):
            self.assertEqual(read_json(client, URL), {'currency': 'USD'})

    def test_domain_cookies_shared_between_endpoints(self):
        calls = []
        def handler(request):
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(200, json={'currency': 'USD'}, headers={'set-cookie': 'market=US; Domain=store.example.com; Path=/; Secure'})
            self.assertIn('market=US', request.headers.get('cookie', ''))
            return httpx.Response(200, json=DATA)
        with httpx.Client(transport=PublicShopifyTransport(httpx.MockTransport(handler))) as client, patch('market.network.socket.getaddrinfo', return_value=PUBLIC) as dns:
            read_json(client, 'https://store.example.com/cart.js')
            read_json(client, URL + '.js')
            self.assertEqual(dns.call_count, 1)

    def test_redirect_and_non_json_rejected(self):
        for response in [httpx.Response(302, headers={'location': 'http://127.0.0.1/'}),
                         httpx.Response(200, text='password required'), httpx.Response(200, content='{', headers={'content-type': 'application/json'})]:
            with httpx.Client(transport=httpx.MockTransport(lambda req: response)) as client, patch('market.network.socket.getaddrinfo', return_value=PUBLIC), self.assertRaises(CollectionError):
                read_json(client, URL)

    @patch('market.shopify.read_json', side_effect=[{'currency': 'USD'}, DATA])
    def test_endpoints_keep_locale_and_market(self, read):
        result = collect_shopify('https://store.example.com/en/products/coat?variant=42&currency=USD')
        self.assertEqual(result['price'], Decimal('129.00'))
        self.assertEqual(read.call_args_list[0].args[1], 'https://store.example.com/en/cart.js?currency=USD')
        self.assertEqual(read.call_args_list[1].args[1], 'https://store.example.com/en/products/coat.js?currency=USD')


class ShopifyWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('researcher', password='test-password')
        self.client.force_login(self.user)

    @patch('market.shopify.collect_shopify', return_value=parse_shopify(DATA, {'currency': 'USD'}, URL))
    def test_link_to_queue_to_snapshot_and_store(self, collect):
        response = self.client.post(reverse('analyze_competitor'), {'platform': 'Shopify', 'url': URL + '?variant=42&utm_source=a'})
        self.assertEqual(response.status_code, 302)
        product = Product.objects.get()
        self.assertEqual(product.platform, 'Shopify')
        self.assertEqual(product.shop, 'store.example.com')
        self.assertTrue(run_next())
        product.refresh_from_db()
        self.assertEqual(product.title, 'Rain coat')
        snapshot = Snapshot.objects.get()
        self.assertEqual(snapshot.price, Decimal('129.00'))
        self.assertIn('variant=42', snapshot.context)
        self.assertContains(self.client.get(reverse('stores')), 'store.example.com')
        self.assertContains(self.client.get(reverse('collection_center')), '采集成功')
        self.assertContains(self.client.get(reverse('dashboard') + '?q=store.example.com'), 'Rain coat')

    @patch('market.shopify.collect_shopify', side_effect=CollectionError('商品有多个规格'))
    def test_failure_preserves_history_and_retry_deduplicates(self, collect):
        product = Product.objects.create(title='Coat', platform='Shopify', url=URL)
        enqueue(product)
        run_next()
        self.assertFalse(Snapshot.objects.exists())
        self.client.post(reverse('collect_product', args=[product.pk]))
        self.client.post(reverse('collect_product', args=[product.pk]))
        self.assertEqual(CollectionJob.objects.filter(status='queued').count(), 1)
        self.assertContains(self.client.get(reverse('collection_center') + '?status=failed'), '商品有多个规格')

    def test_research_pages_require_login(self):
        self.client.logout()
        for name in ['stores', 'collection_center']:
            self.assertEqual(self.client.get(reverse(name)).status_code, 302)

    def test_product_edit_canonicalizes_shopify_and_rejects_duplicate(self):
        data = {'title': 'Coat', 'url': URL + '?utm_source=one&variant=42', 'platform': 'Shopify', 'shop': '', 'notes': ''}
        self.assertEqual(self.client.post(reverse('product_add'), data).status_code, 302)
        data['url'] = URL + '?variant=42&utm_source=two'
        response = self.client.post(reverse('product_add'), data)
        self.assertTrue(response.context['form'].errors)
        self.assertEqual(Product.objects.count(), 1)

    def test_unsupported_collection_does_not_create_task(self):
        product = Product.objects.create(title='Other', url='https://example.com/products/coat', platform='Other')
        self.client.post(reverse('collect_product', args=[product.pk]))
        self.assertFalse(CollectionJob.objects.exists())

    def test_analysis_updates_existing_imported_platform(self):
        product = Product.objects.create(title='Imported', url=URL, platform='Other')
        self.client.post(reverse('analyze_competitor'), {'platform': 'Shopify', 'url': URL})
        product.refresh_from_db()
        self.assertEqual(product.platform, 'Shopify')
        self.assertEqual(product.shop, 'store.example.com')
        self.assertEqual(product.jobs.count(), 1)


class ShopifyLiveFormatTests(SimpleTestCase):
    def test_shopify_javascript_mime_is_valid_json(self):
        with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, content='{"currency":"USD"}', headers={'content-type': 'text/javascript; charset=utf-8'}))) as client:
            self.assertEqual(read_json(client, URL)['currency'], 'USD')

    @patch('market.shopify.time.sleep')
    def test_rate_limit_respects_retry_after(self, sleep):
        responses = iter([httpx.Response(429, headers={'retry-after': '60'}), httpx.Response(200, json={'currency': 'USD'})])
        with httpx.Client(transport=httpx.MockTransport(lambda req: next(responses))) as client:
            self.assertEqual(read_json(client, URL)['currency'], 'USD')
        sleep.assert_called_once_with(60)

    @patch('market.shopify.httpx.Client')
    @patch('market.network.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('198.18.0.23', 443))])
    def test_fake_ip_uses_verified_public_doh(self, dns, client):
        response = httpx.Response(200, request=httpx.Request('GET', 'https://cloudflare-dns.com/dns-query'), json={'Status': 0, 'Answer': [{'type': 1, 'data': '23.227.38.32'}]})
        client.return_value.__enter__.return_value.get.return_value = response
        self.assertEqual(public_address('store.example.com'), '23.227.38.32')
        response = httpx.Response(200, request=httpx.Request('GET', 'https://cloudflare-dns.com/dns-query'), json={'Status': 0, 'Answer': [{'type': 1, 'data': '127.0.0.1'}]})
        client.return_value.__enter__.return_value.get.return_value = response
        with self.assertRaises(CollectionError):
            public_address('store.example.com')
