from unittest.mock import patch
import httpx
from django.test import TestCase, SimpleTestCase
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.contrib.auth import get_user_model
from .discovery import discover, store_url
from .collectors import CollectionError
from .models import StoreDiscovery
from .jobs import run_store_discovery

ROOT = 'https://store.example.com'
INDEX = '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://store.example.com/sitemap_products_1.xml</loc></sitemap></sitemapindex>'
PRODUCTS = '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://store.example.com/products/coat</loc><lastmod>2026-10-07</lastmod></url><url><loc>https://evil.example/products/other</loc></url></urlset>'


class DiscoveryTests(SimpleTestCase):
    def public_client(self, robots='User-agent: *\nAllow: /', product=PRODUCTS, status=200):
        def handler(request):
            if request.url.path == '/robots.txt':
                return httpx.Response(200, text=robots)
            return httpx.Response(status, text=INDEX if request.url.path == '/sitemap.xml' else product)
        return httpx.Client(transport=httpx.MockTransport(handler))

    def test_realistic_sitemap_and_domain_filter(self):
        with self.public_client() as client:
            result = discover(ROOT, client, pause=lambda n: None)
        self.assertEqual(result['products'], [{'url': ROOT+'/products/coat', 'title': 'coat', 'lastmod': '2026-10-07'}])
        self.assertFalse(result['limited'])

    def test_robots_disallow(self):
        with self.public_client(robots='User-agent: *\nDisallow: /') as client, self.assertRaisesMessage(CollectionError, 'robots.txt'):
            discover(ROOT, client, pause=lambda n: None)

    def test_limit_no_false_full_inventory(self):
        product='<urlset>'+''.join(f'<url><loc>{ROOT}/products/p{i}</loc></url>' for i in range(101))+'</urlset>'
        with self.public_client(product=product) as client:
            result=discover(ROOT,client,pause=lambda n: None)
        self.assertEqual(len(result['products']),100)
        self.assertTrue(result['limited'])

    def test_html_entity_and_rate_limit_fail(self):
        for product, status in [('<html>challenge</html>',200), ('<!DOCTYPE urlset><urlset/>',200), ('',429)]:
            with self.public_client(product=product,status=status) as client, self.assertRaises(CollectionError):
                discover(ROOT,client,pause=lambda n: None)

    def test_invalid_store_url(self):
        for url in ['http://store.example.com','https://127.0.0.1','https://store.example.com/products/coat',ROOT+'?x=1']:
            with self.assertRaises(ValidationError): store_url(url)


class DiscoveryWorkflowTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('researcher',password='test-pass-123')
        self.client.force_login(self.user)

    @patch('market.discovery.discover',return_value={'products':[{'url':ROOT+'/products/coat','title':'Coat','lastmod':''}],'limited':False})
    def test_queue_deduplication_worker_and_display(self, collector):
        for _ in range(2):
            response=self.client.post(reverse('discover_store'),{'url':ROOT})
            self.assertEqual(response.status_code,302)
        self.assertEqual(StoreDiscovery.objects.count(),1)
        self.assertTrue(run_store_discovery())
        row=StoreDiscovery.objects.get()
        self.assertEqual(row.status,'succeeded')
        self.assertContains(self.client.get(reverse('stores')),'Coat')

    @patch('market.discovery.discover',side_effect=CollectionError('目录限流'))
    def test_failure_saves_no_catalog(self, collector):
        StoreDiscovery.objects.create(url=ROOT)
        run_store_discovery()
        row=StoreDiscovery.objects.get()
        self.assertEqual(row.status,'failed')
        self.assertEqual(row.products,[])


class HomepageRoutingTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user('homepage', password='test-pass-123'))

    def test_homepage_auto_or_selected_queues_catalog_not_product(self):
        from .models import Product, CollectionJob
        for platform in ['Auto', 'Shopify', '']:
            response = self.client.post(reverse('analyze_competitor'), {'platform': platform, 'url': 'https://millys.co.uk/'})
            self.assertRedirects(response, reverse('store_analysis',args=[StoreDiscovery.objects.get().pk]))
        self.assertEqual(StoreDiscovery.objects.count(), 1)
        self.assertEqual(StoreDiscovery.objects.get().url, 'https://millys.co.uk')
        self.assertFalse(Product.objects.exists())
        self.assertFalse(CollectionJob.objects.exists())

    def test_auto_product_routing_keeps_variant(self):
        from .models import Product
        response=self.client.post(reverse('analyze_competitor'),{'platform':'Auto','url':'https://millys.co.uk/products/shampoo?variant=123'})
        product=Product.objects.get()
        self.assertEqual(product.platform,'Shopify')
        self.assertIn('variant=123',product.url)
        self.assertRedirects(response,reverse('product_analysis',args=[product.pk]))

    def test_local_homepage_rejected(self):
        response=self.client.post(reverse('analyze_competitor'),{'platform':'Auto','url':'https://127.0.0.1/'})
        self.assertEqual(response.status_code,400)
        self.assertFalse(StoreDiscovery.objects.exists())
