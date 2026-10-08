from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from .models import StoreDiscovery, StorePriceJob, Product, CollectionJob
from .jobs import run_store_discovery
from .workflows import start_store_analysis
from .collectors import CollectionError

ROOT='https://shop.example.com'


class WorkflowTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user('flow',password='test-pass-123'))

    @patch('market.discovery.discover')
    def test_new_store_first_batch_and_read_only_progress(self, discover):
        discover.return_value={'products':[{'url':f'{ROOT}/products/item-{i}','title':f'Item {i}'} for i in range(15)],'limited':True}
        response=self.client.post(reverse('analyze_competitor'),{'url':ROOT,'platform':'Auto'})
        scan=StoreDiscovery.objects.get()
        self.assertTrue(scan.analyze_prices)
        progress=reverse('store_analysis',args=[scan.pk])
        self.assertRedirects(response,progress)
        for _ in range(2):
            self.assertTrue(self.client.get(progress,{'format':'json'}).json()['active'])
        self.assertEqual(StorePriceJob.objects.count(),0)
        run_store_discovery()
        scan.refresh_from_db();job=StorePriceJob.objects.get()
        self.assertEqual(job.indices,list(range(10)))
        self.assertEqual(job.total,10)
        self.assertEqual(scan.status,'succeeded')
        self.assertTrue(self.client.get(progress,{'format':'json'}).json()['active'])
        job.status='succeeded';job.processed=10;job.save()
        self.assertRedirects(self.client.get(progress),reverse('store_research',args=[scan.pk]))
        self.assertEqual(self.client.get(progress,{'format':'json'}).json()['redirect_url'],reverse('store_research',args=[scan.pk]))
        self.assertEqual(StorePriceJob.objects.count(),1)

    def test_saved_store_reuses_report_and_product_preserves_variant(self):
        scan=StoreDiscovery.objects.create(url=ROOT,status='succeeded',products=[{'url':ROOT+'/products/coat','title':'Coat'}])
        response=self.client.post(reverse('analyze_competitor'),{'url':ROOT,'platform':'Auto'})
        self.assertRedirects(response,reverse('store_analysis',args=[scan.pk]),fetch_redirect_response=False)
        self.assertEqual(StoreDiscovery.objects.count(),1)
        response=self.client.post(reverse('analyze_competitor'),{'url':ROOT+'/products/coat','platform':'Auto'})
        self.assertRedirects(response,reverse('catalog_detail',args=[scan.pk,0]))
        self.assertFalse(Product.objects.exists())
        response=self.client.post(reverse('analyze_competitor'),{'url':ROOT+'/products/coat?variant=123','platform':'Auto'})
        product=Product.objects.get()
        self.assertIn('variant=123',product.url)
        self.assertRedirects(response,reverse('product_analysis',args=[product.pk]))

    @patch('market.discovery.discover',side_effect=CollectionError('目录访问失败'))
    def test_failure_empty_and_retry_keep_context(self, discover):
        scan=start_store_analysis(ROOT)
        run_store_discovery()
        page=reverse('store_analysis',args=[scan.pk])
        self.assertContains(self.client.get(page),'目录访问失败')
        self.assertFalse(self.client.get(page,{'format':'json'}).json()['active'])
        self.client.post(reverse('discover_store'),{'url':ROOT,'workflow':'1'})
        self.assertEqual(StoreDiscovery.objects.count(),2)
        empty=StoreDiscovery.objects.create(url='https://empty.example.com',status='succeeded')
        self.assertContains(self.client.get(reverse('store_analysis',args=[empty.pk])),'没有发现可分析的公开商品')
        self.assertFalse(StorePriceJob.objects.exists())

    def test_product_progress_success_failure_auth_and_retry(self):
        product=Product.objects.create(url='https://www.aliexpress.com/item/123.html',title='Item')
        job=CollectionJob.objects.create(product=product)
        url=reverse('product_analysis',args=[product.pk])
        self.assertTrue(self.client.get(url,{'format':'json'}).json()['active'])
        job.status='failed';job.message='规格需要选择';job.save()
        self.assertContains(self.client.get(url),'规格需要选择')
        self.assertFalse(self.client.get(url,{'format':'json'}).json()['active'])
        job.status='succeeded';job.save()
        self.assertEqual(self.client.get(url,{'format':'json'}).json()['redirect_url'],reverse('product_detail',args=[product.pk]))
        self.assertRedirects(self.client.post(reverse('collect_product',args=[product.pk]),{'workflow':'1'}),url)
        self.client.logout()
        self.assertEqual(self.client.get(url,{'format':'json'}).status_code,302)

    @patch('market.discovery.discover',return_value={'products':[{'url':ROOT+'/products/coat','title':'Coat'}],'limited':False})
    def test_manual_discovery_stays_manual_and_active_reuse(self, discover):
        scan=StoreDiscovery.objects.create(url=ROOT)
        self.assertEqual(start_store_analysis(ROOT).pk,scan.pk)
        scan.refresh_from_db();self.assertTrue(scan.analyze_prices)
        run_store_discovery();self.assertEqual(StorePriceJob.objects.count(),1)
        manual=StoreDiscovery.objects.create(url='https://manual.example.com')
        run_store_discovery();self.assertFalse(manual.price_jobs.exists())
