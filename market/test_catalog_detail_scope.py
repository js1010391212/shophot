"""Display policy for directory-only/rejected quotes, using isolated test data."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from .models import StoreDiscovery, StorePriceJob, CatalogPriceObservation

ROOT='https://www.adafruit.com'
URL=ROOT+'/product/4864'


class CatalogDetailScopeTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user('scope-reader'))

    def scan(self, root=ROOT, url=URL, **fields):
        return StoreDiscovery.objects.create(url=root, status='succeeded',
            products=[{'url':url,'title':'Directory title',**fields}])

    def test_unobserved_and_failed_without_policy_show_known_scope_without_writes(self):
        for fields in ({}, {'price_error':'Strict quote identity rejected'}):
            with self.subTest(fields=fields):
                scan=self.scan(**fields)
                before=scan.products
                response=self.client.get(reverse('catalog_detail',args=[scan.pk,0]))
                self.assertEqual(response.status_code,200)
                self.assertTrue(response.context['facts_only'])
                for text in ('不保存或热链商品图片','不保存商品描述','不采集或保存评论','尚未取得报价'):
                    self.assertContains(response,text)
                for text in ('读取公开内容','更新当前商品后，可读取','可更新当前商品尝试取得公开评论'):
                    self.assertNotContains(response,text)
                if fields:
                    self.assertContains(response,'Strict quote identity rejected')
                scan.refresh_from_db()
                self.assertEqual(scan.products,before)
                self.assertNotIn('content_policy',scan.products[0])
        self.assertFalse(StorePriceJob.objects.exists())
        self.assertFalse(CatalogPriceObservation.objects.exists())

    def test_success_and_explicit_policy_preserve_fact_display(self):
        scan=self.scan(content_policy='facts_only',price_observed_at='2026-10-22T07:05:00+00:00',
            price_low='4.00',price_high='4.00',currency='USD',sku='4864',
            images=['https://example.com/forbidden.jpg'],description='stale unlicensed prose')
        response=self.client.get(reverse('catalog_detail',args=[scan.pk,0]))
        self.assertContains(response,'USD 4.00')
        self.assertContains(response,'4864')
        self.assertNotContains(response,'forbidden.jpg')
        self.assertNotContains(response,'stale unlicensed prose')
        self.assertContains(response,'不采集或保存评论')

    def test_other_store_and_noncanonical_identity_do_not_inherit_source_scope(self):
        cases=[('https://store.example.com','https://store.example.com/products/a'),
            ('https://adafruit.com',URL),(ROOT,URL+'?x=1'),(ROOT,URL+'#x'),
            (ROOT,'https://adafruit.com/product/4864'),(ROOT,ROOT+'/api/products/4864'),
            ('https://www.adafruit.com.evil.example',URL)]
        for root,url in cases:
            with self.subTest(root=root,url=url):
                scan=self.scan(root,url)
                response=self.client.get(reverse('catalog_detail',args=[scan.pk,0]))
                self.assertFalse(response.context['facts_only'])
                self.assertContains(response,'可更新当前商品尝试取得公开评论')

    def test_refresh_notice_matches_source_scope_and_generic_stays_compatible(self):
        for root,url,facts in [(ROOT,URL,True),('https://store.example.com','https://store.example.com/products/a',False)]:
            scan=self.scan(root,url)
            response=self.client.post(reverse('refresh_catalog_product',args=[scan.pk,0]),follow=True)
            self.assertEqual(StorePriceJob.objects.filter(discovery=scan).count(),1)
            if facts:
                self.assertContains(response,'仅核验身份、所选规格、价格、币种与库存标注')
                self.assertNotContains(response,'报价、图片、描述、公开规格及可取得的商品评价')
            else:
                self.assertContains(response,'报价、图片、描述、公开规格及可取得的商品评价')
