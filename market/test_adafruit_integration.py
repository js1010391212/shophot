"""Controlled source dispatch integration with real adapters, not live evidence."""
from unittest.mock import patch
import httpx
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .catalog_prices import collect_catalog_prices
from .collectors import CollectionError, MAX_BYTES
from .discovery import discover
from .models import CatalogPriceObservation, Product, Snapshot, StoreDiscovery, StorePriceJob

ROOT = 'https://www.adafruit.com'
URL = ROOT + '/product/4864'
ROBOTS = 'User-agent: *\nAllow: /\nDisallow: /api\nDisallow: /cart\nDisallow: /account\nCrawl-delay: 12'


def sitemap(urls):
    return '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">'+''.join(
        '<url><loc>'+url+'</loc><lastmod>2026-10-20</lastmod><image:image><image:title>Controlled source title</image:title></image:image></url>' for url in urls)+'</urlset>'


class AdafruitDispatchTests(SimpleTestCase):
    def test_catalog_uses_strict_product_urls_dedup_original_limit_and_delay(self):
        urls=[URL,URL,ROOT+'/api/products/4864',ROOT+'/product/0',ROOT+'/product/4864?variant=1',ROOT+'/product/4864#x',
              'https://adafruit.com/product/99','https://evil.example/product/3',ROOT+'/products/shopify-shaped']
        urls += [ROOT+'/product/'+str(i) for i in range(1,102)]
        calls=[];pauses=[]
        def handler(request):
            calls.append(str(request.url))
            self.assertIn(request.url.path,('/robots.txt','/sitemap.xml'))
            return httpx.Response(200,text=ROBOTS if request.url.path=='/robots.txt' else sitemap(urls))
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result=discover(ROOT,client=client,pause=pauses.append)
        self.assertEqual(len(result['products']),100)
        self.assertTrue(result['limited'])
        self.assertEqual(result['products'][0],{'url':URL,'title':'Controlled source title','lastmod':'2026-10-20'})
        self.assertEqual(calls,[ROOT+'/robots.txt',ROOT+'/sitemap.xml'])
        self.assertEqual(pauses,[12.1])
        self.assertTrue(all('sku' not in item for item in result['products']))
        self.assertTrue(all('/product/' in item['url'] and '?' not in item['url'] and '#' not in item['url'] for item in result['products']))

    def test_source_delay_keeps_larger_robots_value(self):
        pauses=[]
        def handler(request):
            return httpx.Response(200,text='User-agent: *\nAllow: /\nCrawl-delay: 20' if request.url.path=='/robots.txt' else sitemap([URL]))
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            discover(ROOT,client=client,pause=pauses.append)
        self.assertEqual(pauses,[20])

    def test_sitemap_robots_prohibition_makes_no_sitemap_request(self):
        calls=[]
        def handler(request):
            calls.append(request.url.path)
            return httpx.Response(200,text='User-agent: *\nDisallow: /sitemap.xml')
        with httpx.Client(transport=httpx.MockTransport(handler)) as client, self.assertRaises(CollectionError):
            discover(ROOT,client=client,pause=lambda _:None)
        self.assertEqual(calls,['/robots.txt'])

    def test_product_robots_prohibition_saves_error_without_product_request(self):
        calls=[];rows=[]
        def handler(request):
            calls.append(request.url.path)
            return httpx.Response(200,text='User-agent: *\nDisallow: /product/')
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            collect_catalog_prices(ROOT,[{'url':URL}],lambda i,row:rows.append(row),client=client,pause=lambda _:None)
        self.assertEqual(calls,['/robots.txt'])
        self.assertEqual(len(rows),1)
        self.assertIn('robots',rows[0]['price_error'])

    def test_invalid_host_path_query_and_fragment_never_make_product_request(self):
        for invalid in ('https://adafruit.com/product/4864',ROOT+'.evil.test/product/4864',ROOT+'/product/0',ROOT+'/product/4864?x=1',ROOT+'/product/4864#x',ROOT+'/api/products/4864',ROOT+'/products/not-native'):
            calls=[]
            def handler(request):
                calls.append(request.url.path)
                return httpx.Response(200,text=ROBOTS)
            with self.subTest(url=invalid),httpx.Client(transport=httpx.MockTransport(handler)) as client,self.assertRaises((ValidationError,CollectionError)):
                collect_catalog_prices(ROOT,[{'url':invalid}],lambda *_:self.fail('invalid URL saved'),client=client,pause=lambda _:None)
            self.assertEqual(calls,['/robots.txt'])

    def test_http_429_stops_before_following_product(self):
        calls=[];rows=[];pauses=[]
        def handler(request):
            calls.append(request.url.path)
            return httpx.Response(200,text=ROBOTS) if request.url.path=='/robots.txt' else httpx.Response(429)
        with httpx.Client(transport=httpx.MockTransport(handler)) as client,self.assertRaisesMessage(CollectionError,'429'):
            collect_catalog_prices(ROOT,[{'url':URL},{'url':ROOT+'/product/1'}],lambda i,r:rows.append(r),client=client,pause=pauses.append)
        self.assertEqual(calls,['/robots.txt','/product/4864'])
        self.assertEqual(rows,[])
        self.assertEqual(pauses,[12.1])

    def test_redirect_non_html_and_oversize_stop_without_callback(self):
        failures=[httpx.Response(302,headers={'location':'https://adafruit.com/product/4864'}),
                  httpx.Response(200,text='{}',headers={'content-type':'application/json'}),
                  httpx.Response(200,content=b'x'*(MAX_BYTES+1),headers={'content-type':'text/html'})]
        for response in failures:
            calls=[]
            def handler(request):
                calls.append(request.url.path)
                return httpx.Response(200,text=ROBOTS) if request.url.path=='/robots.txt' else response
            with httpx.Client(transport=httpx.MockTransport(handler)) as client,self.assertRaises(CollectionError):
                collect_catalog_prices(ROOT,[{'url':URL}],lambda *_:self.fail('invalid HTTP response saved'),client=client,pause=lambda _:None)
            self.assertEqual(calls,['/robots.txt','/product/4864'])

    def test_sitemap_redirect_and_oversize_are_not_followed(self):
        for response in (httpx.Response(301,headers={'location':'https://adafruit.com/sitemap.xml'}),httpx.Response(200,content=b'x'*(MAX_BYTES+1))):
            calls=[]
            def handler(request):
                calls.append(request.url.path)
                return httpx.Response(200,text=ROBOTS) if request.url.path=='/robots.txt' else response
            with httpx.Client(transport=httpx.MockTransport(handler)) as client,self.assertRaises(CollectionError):
                discover(ROOT,client=client,pause=lambda _:None)
            self.assertEqual(calls,['/robots.txt','/sitemap.xml'])

    def test_other_stores_keep_original_shopify_sitemap_and_delay(self):
        other='https://controlled.example.com'
        pauses=[]
        def handler(request):
            return httpx.Response(200,text='User-agent: *\nAllow: /\nCrawl-delay: 2' if request.url.path=='/robots.txt' else sitemap([other+'/products/coat',other+'/product/4864']))
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result=discover(other,client=client,pause=pauses.append)
        self.assertEqual([item['url'] for item in result['products']],[other+'/products/coat'])
        self.assertEqual(pauses,[2])

    def test_batch_limit_stays_ten_even_when_more_items_are_supplied(self):
        calls=[];rows=[]
        def handler(request):
            calls.append(request.url.path)
            return httpx.Response(200,text='User-agent: *\nDisallow: /product/')
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            collect_catalog_prices(ROOT,[{'url':ROOT+'/product/'+str(i)} for i in range(1,12)],lambda i,r:rows.append((i,r)),client=client,pause=lambda _:None)
        self.assertEqual([i for i,_ in rows],list(range(10)))
        self.assertTrue(all('price_error' in row for _,row in rows))
        self.assertEqual(calls,['/robots.txt'])


class AdafruitWorkerFailureTests(TestCase):
    def test_parser_failure_keeps_old_quote_and_report_does_not_claim_new_price(self):
        from datetime import timedelta
        from django.utils import timezone
        from .jobs import run_store_prices
        old=timezone.now()-timedelta(days=2)
        item={'url':URL,'title':'Controlled saved product','sku':'4864','price_low':'4.00','price_high':'4.00',
              'currency':'USD','price_observed_at':old.isoformat()}
        scan=StoreDiscovery.objects.create(url=ROOT,status='succeeded',analyze_prices=True,products=[item])
        previous=StorePriceJob.objects.create(discovery=scan,status='succeeded',indices=[0],processed=1,total=1)
        CatalogPriceObservation.objects.create(discovery=scan,job=previous,url=URL,title=item['title'],price_low='4.00',price_high='4.00',currency='USD',observed_at=old)
        current=StorePriceJob.objects.create(discovery=scan,indices=[0],total=1)
        calls=[]
        def handler(request):
            calls.append(request.url.path)
            if request.url.path=='/robots.txt':return httpx.Response(200,text=ROBOTS)
            self.assertEqual(request.url.path,'/product/4864')
            return httpx.Response(200,text='<html><h1>No attributable product quote</h1></html>',headers={'content-type':'text/html'})
        original=collect_catalog_prices
        with httpx.Client(transport=httpx.MockTransport(handler)) as http:
            with patch('market.catalog_prices.collect_catalog_prices',side_effect=lambda root,items,save:original(root,items,save,client=http,pause=lambda _:None)):
                self.assertTrue(run_store_prices())
        self.assertEqual(calls,['/robots.txt','/product/4864'])
        scan.refresh_from_db();current.refresh_from_db()
        self.assertEqual(current.status,'failed')
        self.assertEqual(scan.products[0]['price_low'],'4.00')
        self.assertEqual(scan.products[0]['sku'],'4864')
        self.assertEqual(scan.products[0]['price_observed_at'],old.isoformat())
        self.assertTrue(scan.products[0]['price_error'])
        self.assertEqual(CatalogPriceObservation.objects.count(),1)
        self.assertFalse(Product.objects.exists())
        self.assertFalse(Snapshot.all_objects.exists())
        user=get_user_model().objects.create_user('adafruit-failure-ordinary')
        self.client.force_login(user)
        response=self.client.get(reverse('store_research',args=[scan.pk]))
        self.assertEqual(response.context['report_coverage']['new_count'],0)
        self.assertEqual(response.context['report_coverage']['failed_count'],1)
        self.assertEqual(response.context['report_coverage']['historical_count'],1)
        self.assertContains(response,'沿用已保存报价')


class AdafruitWorkerSuccessTests(TestCase):
    def test_home_directory_price_observation_report_and_private_candidate_use_real_adapter(self):
        from .jobs import run_next
        from .models import CatalogCandidate, CollectionJob
        from .test_adafruit_catalog import page
        ordinary=get_user_model().objects.create_user('adafruit-success-ordinary')
        self.assertFalse(ordinary.is_staff or ordinary.is_superuser)
        self.client.force_login(ordinary)
        pauses=[];calls=[]
        def handler(request):
            calls.append(str(request.url))
            if request.url.path=='/robots.txt':return httpx.Response(200,text=ROBOTS)
            if request.url.path=='/sitemap.xml':return httpx.Response(200,text=sitemap([URL]))
            self.assertEqual(str(request.url),URL)
            return httpx.Response(200,text=page(),headers={'content-type':'text/html'})
        original_discover=discover
        original_collect=collect_catalog_prices
        with httpx.Client(transport=httpx.MockTransport(handler)) as http:
            with patch('market.discovery.discover',side_effect=lambda url:original_discover(url,client=http,pause=pauses.append)),patch('market.catalog_prices.collect_catalog_prices',side_effect=lambda root,items,save:original_collect(root,items,save,client=http,pause=pauses.append)):
                posted=self.client.post(reverse('analyze_competitor'),{'url':ROOT,'platform':'Auto','scope':'prices'})
                self.assertEqual(posted.status_code,302)
                scan=StoreDiscovery.objects.get()
                self.assertTrue(scan.analyze_prices)
                self.assertTrue(run_next())
                self.assertTrue(run_next())
                self.assertFalse(run_next())
        scan.refresh_from_db()
        job=StorePriceJob.objects.get()
        quote=CatalogPriceObservation.objects.get()
        self.assertEqual(job.status,'succeeded')
        self.assertEqual((quote.price_low,quote.price_high,quote.currency),(4,4,'USD'))
        self.assertEqual(quote.job_id,job.pk)
        self.assertEqual(quote.url,URL)
        self.assertEqual(quote.availability,'OutOfStock')
        self.assertEqual(quote.quote_scope['variant_count'],1)
        self.assertEqual(quote.quote_scope['identities'][0]['sku'],'4864')
        self.assertEqual(scan.products[0]['variants'][0]['name'],'Bare board')
        self.assertEqual(scan.products[0]['variants'][0]['url'],URL)
        self.assertEqual(scan.products[0]['content_policy'],'facts_only')
        self.assertEqual(scan.products[0]['description'],'')
        self.assertEqual(scan.products[0]['images'],[])
        self.assertEqual(calls,[ROOT+'/robots.txt',ROOT+'/sitemap.xml',ROOT+'/robots.txt',URL])
        self.assertEqual(pauses,[12.1,12.1])
        progress=self.client.get(posted.url,{'format':'json'}).json()
        self.assertFalse(progress['active'])
        self.assertEqual(progress['coverage']['new_count'],1)
        report=self.client.get(progress['redirect_url'])
        self.assertContains(report,'Controlled Board')
        self.assertContains(report,'USD 4.00')
        self.assertEqual(report.context['priced_count'],1)
        detail=self.client.get(reverse('catalog_detail',args=[scan.pk,0]))
        for expected in ('4864','Bare board','4.00','缺货'):
            self.assertContains(detail,expected)
        saved=self.client.post(reverse('candidate_add',args=[scan.pk,0]))
        self.assertEqual(saved.status_code,302)
        candidate=CatalogCandidate.objects.get(owner=ordinary)
        self.assertEqual(candidate.url,URL)
        self.assertEqual(candidate.saved_item['variants'][0]['sku'],'4864')
        self.assertEqual(self.client.get(reverse('candidates')).status_code,200)
        self.assertEqual(CatalogPriceObservation.objects.count(),1)
        self.assertFalse(Product.objects.exists())
        self.assertFalse(Snapshot.all_objects.exists())
        self.assertFalse(CollectionJob.objects.exists())
