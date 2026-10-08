import json
from unittest.mock import patch
import httpx
from django.test import SimpleTestCase, TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from .catalog_prices import parse_catalog_price, collect_catalog_prices
from .collectors import CollectionError
from .models import StoreDiscovery, StorePriceJob
from .jobs import run_store_prices

ROOT = 'https://store.example.com'
URL = ROOT + '/products/coat'

def html(offers=None, url=URL):
    return '<script type="application/ld+json">'+json.dumps({'@type':'Product', 'url':url, 'name':'Coat',
        'offers': offers if offers is not None else {'price':'9.00','priceCurrency':'GBP','availability':'https://schema.org/OutOfStock'}})+'</script>'

class PriceParserTests(SimpleTestCase):
    def test_price_is_major_units_and_unavailable_not_free(self):
        row=parse_catalog_price(html(),URL)
        self.assertEqual(row['price_low'],'9.00')
        self.assertEqual(row['currency'],'GBP')
        self.assertEqual(row['availability'],'OutOfStock')

    def test_offer_range_and_identity(self):
        row=parse_catalog_price(html([{'price':'12','priceCurrency':'GBP'},{'price':'18','priceCurrency':'GBP'}]),URL)
        self.assertEqual((row['price_low'],row['price_high']),('12.00','18.00'))
        for page in [html(url=ROOT+'/products/other'),html()+html(),html({'price':'NaN','priceCurrency':'GBP'}),
                     html([{'price':'12','priceCurrency':'GBP'},{'price':'18','priceCurrency':'USD'}])]:
            with self.assertRaises(CollectionError):parse_catalog_price(page,URL)

    def test_product_group_prices_do_not_mix_other_products(self):
        group={'@type':'ProductGroup','url':URL,'name':'Coat','hasVariant':[
            {'@type':'Product','@id':'/products/coat?variant=1#variant','offers':{'price':'12','priceCurrency':'GBP'}},
            {'@type':'Product','@id':'/products/coat?variant=2#variant','offers':{'price':'38','priceCurrency':'GBP'}}]}
        def page():return '<script type="application/ld+json">'+json.dumps(group)+'</script>'
        row=parse_catalog_price(page(),URL)
        self.assertEqual((row['price_low'],row['price_high']),('12.00','38.00'))
        group['hasVariant'][1]['@id']='/products/other?variant=2'
        with self.assertRaises(CollectionError):parse_catalog_price(page(),URL)

    def test_stop_on_429_and_preserve_partial_results(self):
        urls=[]; rows=[]
        def handler(request):
            urls.append(str(request.url))
            if request.url.path=='/robots.txt':return httpx.Response(200,text='User-agent: *\nAllow: /')
            if request.url.path=='/products/coat':return httpx.Response(200,text=html(),headers={'Content-Type':'text/html'})
            return httpx.Response(429)
        with httpx.Client(transport=httpx.MockTransport(handler)) as client, self.assertRaisesMessage(CollectionError,'429'):
            collect_catalog_prices(ROOT,[{'url':URL},{'url':ROOT+'/products/second'},{'url':ROOT+'/products/third'}],
                lambda i,row:rows.append(row),client,pause=lambda n:None)
        self.assertEqual(len(rows),1)
        self.assertEqual(len(urls),3)

    def test_robots_and_cross_domain(self):
        with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,text='User-agent: *\nDisallow: /products/'))) as client:
            rows=[]
            collect_catalog_prices(ROOT,[{'url':URL}],lambda i,r:rows.append(r),client,pause=lambda n:None)
            self.assertIn('robots',rows[0]['price_error'])
            with self.assertRaisesMessage(CollectionError,'其他域名'):
                collect_catalog_prices(ROOT,[{'url':'https://evil.example.com/products/coat'}],lambda i,r:None,client,pause=lambda n:None)

class PriceWorkflowTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user('price-test',password='test-pass-123'))
        self.scan=StoreDiscovery.objects.create(url=ROOT,status='succeeded',products=[{'url':URL,'title':'Coat'}])

    @patch('market.catalog_prices.collect_catalog_prices')
    def test_queue_duplicate_worker_and_table(self, collector):
        for _ in range(2):self.client.post(reverse('collect_store_prices',args=[self.scan.pk]))
        self.assertEqual(StorePriceJob.objects.count(),1)
        collector.side_effect=lambda root,items,save:save(0,parse_catalog_price(html(),URL))
        self.assertTrue(run_store_prices())
        job=StorePriceJob.objects.get()
        self.assertEqual((job.status,job.processed,job.total),('succeeded',1,1))
        response=self.client.get(reverse('stores'))
        self.assertContains(response,'GBP 9.00')
        self.assertContains(response,'缺货')
        self.scan.refresh_from_db()
        self.assertIn('price_observed_at',self.scan.products[0])

    @patch('market.catalog_prices.collect_catalog_prices',side_effect=CollectionError('HTTP 429'))
    def test_failure_no_invented_price(self, collector):
        StorePriceJob.objects.create(discovery=self.scan)
        run_store_prices()
        self.scan.refresh_from_db()
        self.assertNotIn('price_low',self.scan.products[0])
        self.assertEqual(StorePriceJob.objects.get().status,'failed')


    def test_next_batch_skips_existing_quotes_and_empty_range(self):
        self.scan.products=[{'url':ROOT+f'/products/p{i}','title':f'P{i}',**({'price_observed_at':'old','price_low':'1.00'} if i<10 else {})} for i in range(23)]
        self.scan.save()
        self.client.post(reverse('collect_store_prices',args=[self.scan.pk]), {'mode':'next'})
        self.assertEqual(StorePriceJob.objects.get().indices,list(range(10,20)))
        self.scan.products=[{'url':URL,'title':'Coat','price_observed_at':'old'}]
        self.scan.save()
        response=self.client.post(reverse('collect_store_prices',args=[self.scan.pk]), {'mode':'remaining'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(StorePriceJob.objects.count(),1)
        self.assertEqual(self.client.post(reverse('collect_store_prices',args=[self.scan.pk]),{'mode':'unknown'}).status_code,400)

    @patch('market.catalog_prices.collect_catalog_prices')
    def test_remaining_batches_and_history_preserve_old_prices(self, collector):
        from .models import CatalogPriceObservation
        self.scan.products=[{'url':ROOT+f'/products/p{i}','title':f'P{i}',**({'price_observed_at':'old','price_low':'1.00'} if i<10 else {})} for i in range(23)]
        self.scan.save()
        self.client.post(reverse('collect_store_prices',args=[self.scan.pk]), {'mode':'remaining'})
        self.assertEqual(StorePriceJob.objects.get().indices,list(range(10,23)))
        def collect(root,items,save):
            for i,item in enumerate(items):
                save(i,parse_catalog_price(html(url=item['url']),item['url']))
        collector.side_effect=collect
        run_store_prices()
        self.assertEqual([len(call.args[1]) for call in collector.call_args_list],[10,3])
        self.scan.refresh_from_db()
        self.assertEqual(self.scan.products[0]['price_low'],'1.00')
        self.assertEqual(self.scan.products[22]['price_low'],'9.00')
        self.assertEqual(CatalogPriceObservation.objects.count(),13)
        self.assertEqual(StorePriceJob.objects.get().processed,13)
        self.client.post(reverse('collect_store_prices',args=[self.scan.pk]), {'mode':'refresh'})
        run_store_prices()
        self.assertEqual(CatalogPriceObservation.objects.count(),36)
        self.assertContains(self.client.get(reverse('stores')),'价格覆盖 23 / 23')

    @patch('market.catalog_prices.collect_catalog_prices')
    def test_partial_error_keeps_quote_and_history(self, collector):
        from .models import CatalogPriceObservation
        self.scan.products=[{'url':URL,'title':'Coat'},{'url':ROOT+'/products/second','title':'Second'}]
        self.scan.save()
        self.client.post(reverse('collect_store_prices',args=[self.scan.pk]),{'mode':'remaining'})
        def collect(root,items,save):
            save(0,parse_catalog_price(html(),URL))
            raise CollectionError('HTTP 429')
        collector.side_effect=collect
        run_store_prices()
        self.scan.refresh_from_db()
        self.assertEqual(self.scan.products[0]['price_low'],'9.00')
        self.assertNotIn('price_low',self.scan.products[1])
        self.assertEqual(CatalogPriceObservation.objects.count(),1)
        self.assertEqual(StorePriceJob.objects.get().processed,1)
        self.assertEqual(StorePriceJob.objects.get().status,'failed')
