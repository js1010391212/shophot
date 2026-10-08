from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlsplit, parse_qs
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from .models import StoreDiscovery, StorePriceJob, PriceMonitor
from .catalog_research import catalog_rows, latest_catalogs
from .sample_market import prepare_rows, filter_rows, summarize

ROOT='https://sample.example.com'


class SampleMarketTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user('samples',password='test-pass-123'))
        self.now=timezone.now()
        def item(name,price=None,currency='GBP',**kwargs):
            row={'url':ROOT+'/products/'+name,'title':name,**kwargs}
            if price is not None:
                row.update(price_low=str(price),price_high=str(price),currency=currency,price_observed_at=self.now.isoformat())
            return row
        self.scan=StoreDiscovery.objects.create(url=ROOT,status='succeeded',limited=True,products=[
            item('zero',0,brand='ACME',review_count=0,rating=0),item('ten',10,brand='acme'),
            item('twenty',20,brand='Other',price_error='最新采集限流'),item('unknown',brand=''),
            item('usd',100,currency='USD',brand='Other')])
        self.route=reverse('sample_market')

    def rows(self):
        scans=latest_catalogs()
        return scans,prepare_rows(catalog_rows(scans))

    def test_currency_isolation_zero_unknown_and_brand_denominator(self):
        scans,rows=self.rows();result=summarize(rows,{},scans,self.now)
        self.assertEqual(result['matched_count'],5)
        self.assertEqual(result['counts'],{'quoted':4,'rating':1,'reviews':1,'samples':0,'failed':1,'unknown':1})
        prices={g['currency']:g for g in result['prices']}
        self.assertEqual(prices['GBP']['median'],Decimal('10.00'))
        self.assertEqual(prices['USD']['median'],Decimal('100.00'))
        brands={b['name']:b for b in result['brands']}
        self.assertEqual(brands['ACME']['count'],2);self.assertEqual(brands['ACME']['share'],40.0)
        self.assertEqual(brands['品牌未知']['count'],1)
        self.assertEqual(sum(g['count'] for g in prices['GBP']['bins']),3)

    def test_latest_directory_dedup_preserves_product_identity(self):
        latest=StoreDiscovery.objects.create(url=ROOT,status='succeeded',products=[self.scan.products[2],self.scan.products[0]])
        StoreDiscovery.objects.create(url='https://duplicate.example.com',status='succeeded',products=[{**self.scan.products[0],'url':self.scan.products[0]['url']+'/'}])
        scans,rows=self.rows()
        self.assertEqual(len(rows),2)
        twenty=next(row for row in rows if row['display_title']=='twenty')
        self.assertEqual((twenty['scan_pk'],twenty['catalog_index']),(latest.pk,0))
        self.assertNotIn('unknown',[row['display_title'] for row in rows])

    def test_bin_links_roundtrip_with_inclusive_cents_and_filter_preservation(self):
        scans,rows=self.rows()
        data={'q':'t','brand':'','store':str(self.scan.pk),'currency':'GBP','price_min':None,'price_max':None}
        selected=filter_rows(rows,data);result=summarize(selected,data,scans)
        bins=result['prices'][0]['bins'];seen=[]
        for bucket in bins:
            params={key:value[0] for key,value in parse_qs(urlsplit(bucket['url']).query).items()}
            self.assertEqual(params['store'],str(self.scan.pk));self.assertEqual(params['q'],'t')
            response=self.client.get(self.route,params)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.context['matched_count'],bucket['count'])
            seen.extend(row['url'] for row in response.context['page'])
        self.assertCountEqual(seen,[row['url'] for row in selected])
        zero=summarize(filter_rows(rows,{'q':'zero'}),{'q':'zero'},scans)['prices'][0]['bins'][0]
        params=parse_qs(urlsplit(zero['url']).query)
        response=self.client.get(self.route,{k:v[0] for k,v in params.items()})
        self.assertEqual(response.context['matched_count'],1)

    def test_price_buckets_at_maximum_value_have_valid_links(self):
        self.scan.products=self.scan.products[:2]
        for item,price in zip(self.scan.products,['9999999999.98','9999999999.99']):
            item.update(price_low=price,price_high=price)
        self.scan.save()
        scans,rows=self.rows()
        bins=summarize(rows,{},scans)['prices'][0]['bins']
        self.assertEqual(sum(b['count'] for b in bins),2)
        for bucket in bins:
            params={k:v[0] for k,v in parse_qs(urlsplit(bucket['url']).query).items()}
            self.assertEqual(self.client.get(self.route,params).status_code,200)

    def test_freshness_missing_and_old_times_do_not_become_recent(self):
        scans,rows=self.rows()
        quoted=[row for row in rows if row['valid_quote']]
        quoted[0]['price_observed_at']=(self.now-timedelta(days=2)).isoformat()
        quoted[1]['price_observed_at']='invalid'
        quoted[2]['price_observed_at']=(self.now+timedelta(hours=1)).isoformat()
        quoted[3]['price_observed_at']=(self.now-timedelta(hours=2)).strftime('%Y-%m-%d %H:%M UTC')
        result=summarize(rows,{},scans,self.now)
        self.assertEqual((result['recent'],result['stale'],result['unknown_time']),(1,1,2))

    def test_view_filters_errors_auth_readonly_and_empty(self):
        response=self.client.get(self.route)
        self.assertContains(response,'sample-market-data')
        self.assertContains(response,'截取目录')
        self.assertContains(response,'评价数未知')
        self.assertEqual(response.context['matched_count'],5)
        for params in ({'currency':'EUR'},{'store':'999'},{'price_min':1},{'currency':'GBP','price_min':20,'price_max':10}):
            self.assertEqual(self.client.get(self.route,params).status_code,400)
        self.assertEqual(self.client.post(self.route).status_code,405)
        self.assertContains(self.client.get(self.route,{'q':'nonexistent'}),'没有匹配的样本商品')
        self.assertEqual(self.client.get(self.route,{'brand':'known:acme'}).context['matched_count'],2)
        self.assertEqual(self.client.get(self.route,{'currency':'USD'}).context['matched_count'],1)
        self.assertEqual(self.client.get(self.route,{'page':2}).status_code,200)
        self.assertFalse(StorePriceJob.objects.exists());self.assertFalse(PriceMonitor.objects.exists())
        self.client.logout();self.assertEqual(self.client.get(self.route).status_code,302)
