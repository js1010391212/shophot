from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase, SimpleTestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse
from .models import StoreDiscovery, StorePriceJob, CatalogPriceObservation
from .price_history import capture_quote_scope, build_history, observations_for_url
from .jobs import run_store_prices

ROOT='https://shop.example.com'
URL=ROOT+'/products/comb'


def scope_item(price='10.00', variant='1'):
    return {'currency':'GBP','variants':[{'name':'Small','sku':'small','url':URL+'?variant='+variant,
            'price_low':price,'price_high':price,'currency':'GBP'}]}


class ScopeTests(SimpleTestCase):
    def test_scope_ignores_prices_and_stock_but_preserves_specification(self):
        first=capture_quote_scope(scope_item(),URL)
        second=capture_quote_scope(scope_item('12.00'),URL)
        self.assertEqual(first['signature'],second['signature'])
        self.assertNotEqual(first['signature'],capture_quote_scope(scope_item(variant='2'),URL)['signature'])
        first_item=scope_item();first_item['variants'].append({**first_item['variants'][0],'sku':'large','url':URL+'?variant=2'})
        reversed_item={**first_item,'variants':list(reversed(first_item['variants']))}
        self.assertEqual(capture_quote_scope(first_item,URL),capture_quote_scope(reversed_item,URL))
        first_item['variants_limited']=True
        self.assertEqual(capture_quote_scope(first_item,URL),{})
        wrong=scope_item();wrong['variants'][0]['url']=ROOT+'/products/another'
        self.assertEqual(capture_quote_scope(wrong,URL),{})
        wrong=scope_item();wrong['variants'][0]['currency']='USD'
        self.assertEqual(capture_quote_scope(wrong,URL),{})
        anonymous=scope_item();anonymous['variants'][0].update(url=URL,sku='',price_high='20.00')
        self.assertEqual(capture_quote_scope(anonymous,URL),{})
        self.assertEqual(capture_quote_scope({},URL),{})


class HistoryTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user('history',password='test-pass-123'))
        self.scan=StoreDiscovery.objects.create(url=ROOT,status='succeeded',products=[{'url':URL,'title':'Comb'}])
        self.scope=capture_quote_scope(scope_item(),URL)
        self.at=timezone.now()-timedelta(hours=1)

    def quote(self, price='10.00', high=None, currency='GBP', scope=None, scan=None, age=0, url=URL):
        scan=scan or self.scan
        job=StorePriceJob.objects.create(discovery=scan,status='succeeded')
        return CatalogPriceObservation.objects.create(discovery=scan,job=job,url=url,title='Comb',price_low=price,
            price_high=high or price,currency=currency,observed_at=self.at+timedelta(minutes=age),quote_scope=scope or {})

    def test_cross_directory_merge_currency_unknown_scope_and_changed_condition(self):
        self.quote(scope=self.scope)
        other=StoreDiscovery.objects.create(url=ROOT,status='succeeded',products=self.scan.products)
        self.quote('12.00',scope=self.scope,scan=other,age=1,url=URL+'/')
        self.quote('15.00',currency='USD',age=2)
        self.quote('20.00',scope=capture_quote_scope(scope_item(variant='2'),URL),age=3)
        self.quote('21.00',age=4)
        self.quote('99.00',url=ROOT+'/products/not-comb')
        history=build_history(observations_for_url(URL),'GBP')
        self.assertEqual(history['total_count'],4)
        self.assertEqual(history['comparison_count'],1)
        self.assertEqual(history['change_count'],1)
        self.assertEqual(history['chart_data']['segments'],[[0,1]])
        rows=history['rows']
        self.assertEqual(rows[0]['comparison']['kind'],'unknown')
        self.assertEqual(rows[1]['comparison']['kind'],'changed')
        self.assertEqual(rows[2]['comparison']['low_percent'],Decimal('20.00'))
        self.assertEqual(build_history(observations_for_url(URL),'USD')['total_count'],1)

    def test_zero_baseline_unchanged_and_window_limit(self):
        self.quote('0.00',scope=self.scope,age=0)
        self.quote('5.00',scope=self.scope,age=1)
        self.quote('5.00',scope=self.scope,age=2)
        history=build_history(observations_for_url(URL),'GBP')
        self.assertEqual(history['comparison_count'],2)
        self.assertEqual(history['change_count'],1)
        self.assertIsNone(history['rows'][1]['comparison']['low_percent'])
        self.assertEqual(history['rows'][0]['comparison']['low_change'],Decimal('0.00'))
        self.assertIn('报价上下限不变',history['rows'][0]['comparison']['label'])
        old=self.quote('3.00',age=-60*24*40)
        self.assertEqual(build_history(observations_for_url(URL),'GBP',30)['total_count'],3)
        with patch('market.price_history.MAX_POINTS',2):
            data=build_history(observations_for_url(URL),'GBP')
            self.assertTrue(data['truncated']);self.assertEqual(data['displayed_count'],2)
            self.assertEqual(data['rows'][-1]['comparison']['kind'],'first')

    def test_view_empty_errors_source_and_auth(self):
        route=reverse('catalog_history',args=[self.scan.pk,0])
        self.assertContains(self.client.get(route),'当前条件下没有历史观测')
        self.quote(scope=self.scope)
        self.quote('12.00',scope=self.scope,age=1)
        response=self.client.get(route)
        self.assertContains(response,'20.00%')
        self.assertContains(response,'本次规格依据')
        self.assertContains(response,'price-history-data')
        self.assertEqual(self.client.get(route,{'currency':'USD'}).status_code,400)
        self.assertEqual(self.client.get(route,{'days':7}).status_code,400)
        self.assertEqual(self.client.post(route).status_code,405)
        self.assertEqual(self.client.get(reverse('catalog_history',args=[self.scan.pk,99])).status_code,404)
        self.assertContains(self.client.get(reverse('catalog_detail',args=[self.scan.pk,0])),'查看报价历史分析')
        self.client.logout();self.assertEqual(self.client.get(route).status_code,302)

    @patch('market.catalog_prices.collect_catalog_prices')
    def test_worker_saves_scope_only_for_actual_success(self, collector):
        result={**scope_item(),'price_low':'10.00','price_high':'10.00','price_title':'Comb','availability':'InStock','price_error':''}
        collector.side_effect=lambda root,items,save:save(0,result.copy())
        StorePriceJob.objects.create(discovery=self.scan,indices=[0])
        run_store_prices()
        quote=CatalogPriceObservation.objects.get()
        self.assertEqual(quote.quote_scope,self.scope)
        collector.side_effect=lambda root,items,save:save(0,{'price_error':'限流'})
        StorePriceJob.objects.create(discovery=self.scan,indices=[0])
        run_store_prices()
        self.assertEqual(CatalogPriceObservation.objects.count(),1)
        self.scan.refresh_from_db();self.assertEqual(self.scan.products[0]['price_low'],'10.00')
