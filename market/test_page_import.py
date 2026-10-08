import json
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, Client
from django.urls import reverse
from django.utils import timezone
from .page_import import identify_target, normalize_aliexpress_url, parse_page
from .models import Product, Snapshot, CollectionJob
from .jobs import run_next

URL='https://www.aliexpress.com/item/1005001234567890.html'


def page(**changes):
    node={'@type':'Product','url':URL,'name':'Controlled Ali fixture','sku':'SKU1',
          'offers':{'@type':'Offer','price':'19.50','priceCurrency':'USD'}}
    node.update(changes)
    return ('<script type="application/ld+json">'+json.dumps(node)+'</script>').encode()


class FileAdapterTests(SimpleTestCase):
    def test_identity_and_sku_normalization(self):
        self.assertEqual(identify_target(URL+'?sku_id=123&utm_source=a'),('AliExpress',URL+'?sku_id=123'))
        for url in [URL+'?sku_id=1&sku_id=2',URL+'?sku_id=',URL.replace('.com/', '.com:99999/'),'https://www.otto.de:99999/p/test-S0123/',URL.replace('aliexpress.com','aliexpress.com.example.org'),
                    URL.replace('aliexpress.com','aliexpress.us'),'https://www.aliexpress.com/store/1','https://www.ozon.ru/product/test/']:
            with self.subTest(url=url), self.assertRaises(ValidationError):identify_target(url)

    def test_explicit_quote_unknown_and_zero(self):
        result=parse_page(page(),URL,'AliExpress')
        self.assertEqual((result['price'],result['currency']),('19.50','USD'))
        self.assertIsNone(result['rating']);self.assertIsNone(result['review_count'])
        self.assertEqual(len(result['file_fingerprint']),16)
        result=parse_page(page(aggregateRating={'ratingValue':0,'reviewCount':0}),URL,'AliExpress')
        self.assertEqual((result['rating'],result['review_count']),('0.00',0))

    def test_rejects_unattributed_foreign_recommendation_and_ambiguous_offers(self):
        for raw in [page(url=None),page(url=URL.replace('7890','7891')),page(url='https://evil.example/item/1005001234567890.html'),
                    page()+page(),page(offers={'@type':'AggregateOffer','lowPrice':1,'priceCurrency':'USD'}),
                    page(offers=[{'@type':'Offer','price':1,'priceCurrency':'USD'}]*2),page(offers={'@type':'Offer','price':1,'priceCurrency':None}),
                    b'<script>x5secdata={}</script>',b'_____tmd_____',b'\xff',b'x'*(2*1024*1024+1)]:
            with self.subTest(raw=raw[:70]),self.assertRaises(ValidationError):parse_page(raw,URL,'AliExpress')
        with self.assertRaises(ValidationError):parse_page(page(),URL,'OTTO')

    def test_exact_sku_offer_only(self):
        target=URL+'?sku_id=123'
        with self.assertRaises(ValidationError):parse_page(page(),target,'AliExpress')
        offers=[{'@type':'Offer','url':URL+'?sku_id='+sku,'price':price,'priceCurrency':'USD'} for sku,price in [('123',10),('456',20)]]
        result=parse_page(page(offers=offers),target,'AliExpress')
        self.assertEqual((result['price'],result['specification']),('10.00','123'))
        with self.assertRaises(ValidationError):parse_page(page(offers=offers[0]),URL,'AliExpress')


class PageImportFlowTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('file-import',password='test')
        self.client.force_login(self.user)
        self.product=Product.objects.create(title='待识别竞品 · test',url=URL,platform='AliExpress')
        self.path=reverse('page_import',args=[self.product.pk])
        self.at=timezone.localtime(timezone.now()-timedelta(hours=1)).replace(second=0,microsecond=0)

    def preview(self,raw=None):
        return self.client.post(self.path,{'file':SimpleUploadedFile('fixture.html',page() if raw is None else raw),
            'observed_at':self.at.strftime('%Y-%m-%dT%H:%M'),'context':'fixture only'})

    def test_entry_get_post_idempotent_and_no_queue(self):
        start=reverse('page_import_start')
        self.client.get(start);self.assertEqual(Product.objects.count(),1)
        for _ in range(2):
            self.assertRedirects(self.client.post(start,{'url':URL+'?utm_source=test'}),self.path)
        self.assertEqual(Product.objects.count(),1);self.assertFalse(CollectionJob.objects.exists())
        self.assertContains(self.client.post(start,{'url':'https://www.ozon.ru/product/test/'}),'尚未接入',status_code=400)

    def test_preview_confirm_manual_source_and_no_duplicate(self):
        response=self.preview();self.assertEqual(response.status_code,200)
        self.assertFalse(Snapshot.objects.exists())
        token=response.context['preview']
        for _ in range(2):self.assertRedirects(self.client.post(self.path,{'action':'confirm','preview':token}),reverse('product_detail',args=[self.product.pk]))
        quote=Snapshot.objects.get()
        self.assertEqual((str(quote.price),quote.currency,quote.source),('19.50','USD','manual'))
        self.assertEqual(quote.observed_at,self.at);self.assertIsNone(quote.sales)
        self.assertIn('AliExpress 页面文件导入',quote.context);self.assertIn('文件 ',quote.context)

    def test_signed_preview_owner_platform_binding_expiry_and_csrf(self):
        token=self.preview().context['preview']
        for bad in ['',token+'bad']:
            self.assertEqual(self.client.post(self.path,{'action':'confirm','preview':bad}).status_code,400)
        with patch('django.core.signing.time.time',return_value=timezone.now().timestamp()+1201):
            self.assertEqual(self.client.post(self.path,{'action':'confirm','preview':token}).status_code,400)
        strict=Client(enforce_csrf_checks=True);strict.force_login(self.user)
        self.assertEqual(strict.post(self.path,{'action':'confirm','preview':token}).status_code,403)
        self.client.force_login(get_user_model().objects.create_user('another-importer'))
        self.assertEqual(self.client.post(self.path,{'action':'confirm','preview':token}).status_code,400)
        self.assertFalse(Snapshot.objects.exists())

    def test_failures_and_changed_product_preserve_history(self):
        old=Snapshot.objects.create(product=self.product,observed_at=self.at,source='manual',price=99,currency='USD')
        token=self.preview().context['preview']
        self.assertContains(self.client.post(self.path,{'action':'confirm','preview':token}),'未覆盖历史',status_code=400)
        self.assertEqual(self.preview(b'_____tmd_____').status_code,400)
        self.product.url=URL+'?sku_id=123';self.product.save()
        self.assertEqual(self.client.post(self.path,{'action':'confirm','preview':token}).status_code,400)
        old.refresh_from_db();self.assertEqual(old.price,99);self.assertEqual(Snapshot.objects.count(),1)

    def test_sku_home_entry_and_worker_do_not_collect_generic_price(self):
        target=URL+'?sku_id=123'
        response=self.client.post(reverse('analyze_competitor'),{'platform':'Auto','url':target})
        product=Product.objects.get(url=target)
        self.assertRedirects(response,reverse('browser_report',args=[product.pk]))
        self.client.post(reverse('collect_product',args=[product.pk]));self.assertFalse(CollectionJob.objects.exists())
        job=CollectionJob.objects.create(product=product)
        with patch('market.jobs.collect') as collect:run_next();collect.assert_not_called()
        job.refresh_from_db();self.assertEqual(job.status,'failed');self.assertFalse(Snapshot.objects.exists())

    def test_unsupported_product_and_login(self):
        self.product.platform='Shopify';self.product.save()
        self.assertEqual(self.client.get(self.path).status_code,404)
        self.client.logout();self.assertEqual(self.client.get(reverse('page_import_start')).status_code,302)
