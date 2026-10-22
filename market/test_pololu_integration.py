"""Controlled integration of exact Pololu source, never live-site evidence."""
from copy import deepcopy
from unittest.mock import patch
import httpx
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from .collectors import CollectionError, MAX_BYTES
from .discovery import discover
from .catalog_prices import collect_catalog_prices
from .models import StoreDiscovery, StorePriceJob, CatalogPriceObservation, PriceMonitor, Product, Snapshot
from .test_pololu_catalog import ROOT, URL, page
from .pololu_catalog import parse_pololu_price

ROBOTS='User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /cart/\nDisallow: /account/\n'


def home():
    return '<html><head><title>Pololu - Robotics and Electronics</title></head><body><a href="/product/749">Controlled service</a><a href="/product/5759">Controlled regulator</a><a href="/product/749">Duplicate</a></body></html>'


class PololuDispatchTests(SimpleTestCase):
    def test_directory_home_only_robots_filter_order_limited_and_delay(self):
        calls=[];pauses=[]
        def handler(req):
            calls.append(req.url.path)
            self.assertIn(req.url.path,('/robots.txt','/'))
            if req.url.path=='/robots.txt':self.assertEqual(pauses,[12.1])
            return httpx.Response(200,text=(ROBOTS+'Disallow: /product/749\n') if req.url.path=='/robots.txt' else home(),headers={'content-type':'text/plain' if req.url.path=='/robots.txt' else 'text/html'})
        with httpx.Client(transport=httpx.MockTransport(handler)) as http:
            result=discover(ROOT,client=http,pause=pauses.append)
        self.assertEqual(calls,['/robots.txt','/'])
        self.assertEqual(pauses,[12.1,12.1])
        self.assertTrue(result['limited'])
        self.assertEqual([p['url'] for p in result['products']],[URL])
        self.assertTrue(all('sku' not in p and 'price_low' not in p for p in result['products']))

    def test_home_robots_block_and_non200_redirect_nonhtml_oversize_stop(self):
        cases=[('block',200,'text/html',home()),('429',429,'text/html',''),
            ('redirect',302,'text/html',''),('nonhtml',200,'application/json','{}'),
            ('large',200,'text/html','x'*(MAX_BYTES+1))]
        for label,status,ctype,body in cases:
            calls=[]
            def handler(req):
                calls.append(req.url.path)
                if req.url.path=='/robots.txt':
                    return httpx.Response(200,text='User-agent: *\nDisallow: /' if label=='block' else ROBOTS)
                self.assertEqual(req.url.path,'/')
                return httpx.Response(status,text=body,headers={'content-type':ctype,'location':ROOT+'/product/5759'})
            with self.subTest(label=label),httpx.Client(transport=httpx.MockTransport(handler)) as http,self.assertRaises(CollectionError):
                discover(ROOT,client=http,pause=lambda _:None)
            self.assertEqual(calls,['/robots.txt'] if label=='block' else ['/robots.txt','/'])

    def test_larger_robots_delay_applies_to_home_and_product(self):
        pauses=[]
        def handler(req):
            return httpx.Response(200,text=(ROBOTS+'Crawl-delay: 20\n') if req.url.path=='/robots.txt' else home() if req.url.path=='/' else page(),headers={'content-type':'text/plain' if req.url.path=='/robots.txt' else 'text/html'})
        with httpx.Client(transport=httpx.MockTransport(handler)) as http:
            discover(ROOT,client=http,pause=pauses.append)
            collect_catalog_prices(ROOT,[{'url':URL}],lambda *_:None,client=http,pause=pauses.append)
        self.assertEqual(pauses,[12.1,20,12.1,20])

    def test_price_dispatch_real_parser_single_unit_not_lowest_tier_and_batch_cap(self):
        calls=[];rows=[];pauses=[]
        def handler(req):
            calls.append(req.url.path)
            self.assertIn(req.url.path,('/robots.txt','/product/5759'))
            if req.url.path=='/robots.txt':self.assertEqual(pauses,[12.1])
            return httpx.Response(200,text=ROBOTS if req.url.path=='/robots.txt' else page(),headers={'content-type':'text/plain' if req.url.path=='/robots.txt' else 'text/html'})
        with httpx.Client(transport=httpx.MockTransport(handler)) as http:
            collect_catalog_prices(ROOT,[{'url':URL}]*11,lambda i,row:rows.append((i,row)),client=http,pause=pauses.append)
        self.assertEqual(len(rows),10)
        self.assertEqual(pauses,[12.1]*11)
        for _,row in rows:
            self.assertEqual((row['sku'],row['price_low'],row['price_high'],row['currency']),('5759','8.95','8.95','USD'))
            self.assertEqual(len(row['variants']),1)
            self.assertEqual(row['content_policy'],'facts_only')
            self.assertEqual((row['images'],row['description']),([],''))

    def test_existing_generic_and_adafruit_dispatch_and_delays_unchanged(self):
        from .test_catalog_content import page as generic_page, product as generic_product
        from .test_adafruit_catalog import page as adafruit_page
        cases=[('https://store.example.com','https://store.example.com/products/comb',
                generic_page(generic_product()),'19.00',1.0),
               ('https://www.adafruit.com','https://www.adafruit.com/product/4864',
                adafruit_page(),'4.00',12.1)]
        for root,url,body,price,delay in cases:
            calls=[];pauses=[];rows=[]
            def handler(req):
                calls.append(req.url.path)
                if req.url.path=='/robots.txt':return httpx.Response(200,text=ROBOTS)
                if req.url.path=='/sitemap.xml':
                    return httpx.Response(200,text='<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>'+url+'</loc></url></urlset>')
                self.assertEqual(str(req.url),url)
                return httpx.Response(200,text=body,headers={'content-type':'text/plain' if req.url.path=='/robots.txt' else 'text/html'})
            with self.subTest(root=root),httpx.Client(transport=httpx.MockTransport(handler)) as http:
                result=discover(root,client=http,pause=pauses.append)
                collect_catalog_prices(root,result['products'],lambda i,row:rows.append(row),client=http,pause=pauses.append)
            self.assertEqual(calls,['/robots.txt','/sitemap.xml','/robots.txt',url.replace(root,'')])
            self.assertEqual(pauses,[delay,delay])
            self.assertEqual(rows[0]['price_low'],price)

    def test_product_redirect_nonhtml_and_size_stop_without_callback(self):
        for status,ctype,body in [(302,'text/html',''),(200,'application/json','{}'),
                                  (200,'text/html','x'*(MAX_BYTES+1))]:
            calls=[]
            def handler(req):
                calls.append(req.url.path)
                if req.url.path=='/robots.txt':return httpx.Response(200,text=ROBOTS)
                return httpx.Response(status,text=body,headers={'content-type':ctype,'location':ROOT+'/product/1'})
            with self.subTest(status=status,ctype=ctype),httpx.Client(transport=httpx.MockTransport(handler)) as http,self.assertRaises(CollectionError):
                collect_catalog_prices(ROOT,[{'url':URL},{'url':ROOT+'/product/1'}],lambda *_:self.fail('callback after transport stop'),client=http,pause=lambda _:None)
            self.assertEqual(calls,['/robots.txt','/product/5759'])

    def test_invalid_target_robots_rejection_and_http_failure_do_not_continue(self):
        for invalid in [ROOT+'/product/5759?x=1','https://pololu.com/product/5759',ROOT+'/api/product/5759']:
            calls=[]
            def handler(req):
                calls.append(req.url.path);return httpx.Response(200,text=ROBOTS)
            with self.subTest(invalid=invalid),httpx.Client(transport=httpx.MockTransport(handler)) as http,self.assertRaises((ValidationError,CollectionError)):
                collect_catalog_prices(ROOT,[{'url':invalid}],lambda *_:self.fail('unexpected result'),client=http,pause=lambda _:None)
            self.assertEqual(calls,['/robots.txt'])
        for blocked in [False,True]:
            calls=[];rows=[]
            def handler(req):
                calls.append(req.url.path)
                if req.url.path=='/robots.txt':return httpx.Response(200,text=ROBOTS+'Disallow: /product/\n' if blocked else ROBOTS)
                return httpx.Response(429)
            with httpx.Client(transport=httpx.MockTransport(handler)) as http:
                if blocked:
                    collect_catalog_prices(ROOT,[{'url':URL}],lambda i,row:rows.append(row),client=http,pause=lambda _:None)
                else:
                    with self.assertRaises(CollectionError):
                        collect_catalog_prices(ROOT,[{'url':URL},{'url':ROOT+'/product/1'}],lambda i,row:rows.append(row),client=http,pause=lambda _:None)
            self.assertEqual(calls,['/robots.txt'] if blocked else ['/robots.txt','/product/5759'])
            self.assertEqual(len(rows),int(blocked))


class PololuWorkflowTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('pololu-ordinary')
        self.client.force_login(self.user)

    def test_real_adapter_queue_monitor_second_observation_history_and_reporting(self):
        from .jobs import run_store_discovery, run_store_prices
        from .price_monitoring import tick
        calls=[];pauses=[]
        def handler(req):
            calls.append(req.url.path)
            if req.url.path=='/robots.txt':return httpx.Response(200,text=ROBOTS+'Disallow: /product/749\n')
            self.assertIn(req.url.path,('/','/product/5759'))
            return httpx.Response(200,text=home() if req.url.path=='/' else page(),headers={'content-type':'text/plain' if req.url.path=='/robots.txt' else 'text/html'})
        original_discover=discover;original_collect=collect_catalog_prices
        with httpx.Client(transport=httpx.MockTransport(handler)) as http,patch('market.discovery.discover',side_effect=lambda root:original_discover(root,client=http,pause=pauses.append)),patch('market.catalog_prices.collect_catalog_prices',side_effect=lambda root,items,save:original_collect(root,items,save,client=http,pause=pauses.append)):
            response=self.client.post(reverse('analyze_competitor'),{'url':ROOT,'platform':'Auto','scope':'prices'})
            self.assertEqual(response.status_code,302)
            self.assertTrue(run_store_discovery());self.assertTrue(run_store_prices())
            scan=StoreDiscovery.objects.get();quote=CatalogPriceObservation.objects.get()
            self.assertEqual((str(quote.price_low),quote.currency),('8.95','USD'))
            self.assertEqual(quote.quote_scope['identities'][0]['sku'],'5759')
            self.assertEqual(quote.quote_scope['variant_count'],1)
            self.assertEqual(quote.quote_scope['identities'][0]['size'],'')
            configured=self.client.post(reverse('monitor_config',args=[scan.pk,0]),{'interval_hours':24})
            self.assertEqual(configured.status_code,302)
            tick();monitor=PriceMonitor.objects.get(owner=self.user)
            self.assertIsNotNone(monitor.pending_job_id)
            self.assertTrue(run_store_prices());tick()
        self.assertEqual(CatalogPriceObservation.objects.count(),2)
        monitor.refresh_from_db();self.assertEqual(monitor.last_status,'succeeded')
        self.assertIsNone(monitor.pending_job_id)
        scan.refresh_from_db();before=deepcopy(scan.products)
        report=self.client.get(reverse('store_research',args=[scan.pk]))
        self.assertContains(report,'仅发现首页展示的有限商品链接')
        self.assertContains(report,'不计批量折扣')
        self.assertContains(report,'不保证现货或履约')
        self.assertEqual(report.context['report_coverage']['new_count'],1)
        detail=self.client.get(reverse('catalog_detail',args=[scan.pk,0]))
        self.assertContains(detail,'不采集或保存评论')
        history=self.client.get(reverse('catalog_history',args=[scan.pk,0]))
        self.assertEqual(history.context['comparison_count'],1)
        self.assertEqual(history.context['change_count'],0)
        self.assertEqual(CatalogPriceObservation.objects.count(),2)
        scan.refresh_from_db();self.assertEqual(scan.products,before)
        self.assertEqual(pauses,[12.1]*6)
        self.assertNotIn('/sitemap.xml',calls)
        self.assertFalse(Product.objects.exists());self.assertFalse(Snapshot.all_objects.exists())

    def test_unverified_product_or_store_identity_does_not_inherit_facts_policy(self):
        for root,url in [('https://pololu.com',URL),(ROOT,URL+'?x=1'),
                         (ROOT,'https://pololu.com/product/5759'),(ROOT,ROOT+'/api/products/5759')]:
            with self.subTest(root=root,url=url):
                scan=StoreDiscovery.objects.create(url=root,status='succeeded',products=[{'url':url,'title':'Unverified'}])
                response=self.client.get(reverse('catalog_detail',args=[scan.pk,0]))
                self.assertFalse(response.context['facts_only'])
        self.assertFalse(CatalogPriceObservation.objects.exists())
        self.assertFalse(StorePriceJob.objects.exists())

    def test_failure_no_policy_scope_notice_and_success_history_survives(self):
        from .jobs import run_store_prices
        row={'url':URL,'title':'Controlled directory'}
        scan=StoreDiscovery.objects.create(url=ROOT,status='succeeded',products=[row])
        before=deepcopy(scan.products)
        response=self.client.get(reverse('catalog_detail',args=[scan.pk,0]))
        self.assertTrue(response.context['facts_only'])
        self.assertContains(response,'不保存或热链商品图片')
        self.assertNotContains(response,'可更新当前商品尝试取得公开评论')
        scan.refresh_from_db();self.assertEqual(scan.products,before)
        old=parse_pololu_price(page(),URL)
        scan.products=[{**row,**old}];scan.save(update_fields=['products'])
        oldjob=StorePriceJob.objects.create(discovery=scan,status='succeeded')
        from django.utils import timezone
        CatalogPriceObservation.objects.create(discovery=scan,job=oldjob,url=URL,title='Old',price_low='8.95',price_high='8.95',currency='USD',availability='InStock',observed_at=timezone.now())
        StorePriceJob.objects.create(discovery=scan,indices=[0])
        def handler(req):
            return httpx.Response(200,text=ROBOTS if req.url.path=='/robots.txt' else 'invalid page',headers={'content-type':'text/plain' if req.url.path=='/robots.txt' else 'text/html'})
        original=collect_catalog_prices
        with httpx.Client(transport=httpx.MockTransport(handler)) as http,patch('market.catalog_prices.collect_catalog_prices',side_effect=lambda root,items,save:original(root,items,save,client=http,pause=lambda _:None)):
            self.assertTrue(run_store_prices())
        scan.refresh_from_db()
        self.assertEqual(scan.products[0]['price_low'],'8.95')
        self.assertEqual(scan.products[0]['price_observed_at'],old['price_observed_at'])
        self.assertTrue(scan.products[0]['price_error'])
        self.assertEqual(CatalogPriceObservation.objects.count(),1)
        response=self.client.get(reverse('store_research',args=[scan.pk]))
        self.assertEqual(response.context['report_coverage']['historical_count'],1)
        self.assertEqual(response.context['report_coverage']['new_count'],0)
