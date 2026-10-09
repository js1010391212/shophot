"""Read-only private quote library: ownership, stable pagination and original evidence."""
from datetime import datetime, timezone as dt_timezone
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .browser_quote_library import filter_options
from .models import Product, Snapshot, CollectionJob, ShippingRate


class BrowserQuoteLibraryTests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_user('quote-library-owner')
        self.other=get_user_model().objects.create_user('quote-library-other')
        self.product=Product.objects.create(title='Current renamed title',url='https://www.ebay.com/itm/123456789012',platform='eBay')
        self.other_product=Product.objects.create(title='Foreign product',url='https://www.otto.de/p/item-S1/',platform='OTTO')
        self.when=datetime(2026,10,9,3,4,tzinfo=dt_timezone.utc)
        self.client.force_login(self.owner)
        self.url=reverse('browser_quote_library')

    def quote(self,owner=None,product=None,currency='USD',title='Original blue title',**data):
        capture={**dict(title=title,sku_id=None,market_country=None,conditions=[]),**data}
        return Snapshot.all_objects.create(product=product or self.product,owner=owner or self.owner,source='browser',
            capture_id=uuid4(),price='12.34',currency=currency,observed_at=self.when,capture_data=capture)

    def test_private_rows_and_options_exclude_other_accounts_and_public_sources(self):
        owned=self.quote()
        foreign=self.quote(owner=self.other,product=self.other_product,currency='JPY',title='Foreign confidential title')
        public=Snapshot.objects.create(product=self.other_product,source='manual',price='88',currency='GBP',observed_at=self.when)
        response=self.client.get(self.url)
        self.assertEqual(response.context['page'].paginator.count,1)
        self.assertEqual([row.pk for row in response.context['page']],[owned.pk])
        self.assertEqual(filter_options(self.owner),(['eBay'],['USD']))
        for text in ('Foreign confidential title','JPY','GBP','OTTO'):
            self.assertNotContains(response,text)
        self.assertContains(response,f'?observation={owned.pk}')
        self.assertNotContains(response,f'?observation={foreign.pk}')
        self.assertNotContains(response,f'?observation={public.pk}')
        self.client.force_login(self.other)
        response=self.client.get(self.url)
        self.assertEqual([row.pk for row in response.context['page']],[foreign.pk])
        self.assertEqual(filter_options(self.other),(['OTTO'],['JPY']))

    def test_filters_match_original_title_and_account_owned_platform_currency(self):
        blue=self.quote()
        self.quote(title='Original green title',currency='EUR')
        otto=self.quote(product=self.other_product,currency='CNY',title='Original blue OTTO')
        self.quote(owner=self.other,product=self.other_product,currency='CNY',title='Original blue foreign')
        response=self.client.get(self.url,{'q':' blue ','platform':'OTTO','currency':'CNY'})
        self.assertEqual([row.pk for row in response.context['page']],[otto.pk])
        self.assertEqual(response.context['form'].cleaned_data['q'],'blue')
        response=self.client.get(self.url,{'q':'Current renamed title'})
        self.assertEqual(response.context['page'].paginator.count,0)
        response=self.client.get(self.url,{'q':'Original blue title','platform':'eBay','currency':'USD'})
        self.assertEqual([row.pk for row in response.context['page']],[blue.pk])
        untitled=self.quote(title=None)
        response=self.client.get(self.url,{'q':'Current renamed title'})
        self.assertEqual([row.pk for row in response.context['page']],[untitled.pk])

    def test_exact_price_fields_unknown_and_html_are_escaped(self):
        row=self.quote(title='<script>alert(1)</script>',conditions=['<img src=x onerror=alert(1)>'])
        response=self.client.get(self.url)
        for text in ('12.34','USD','规格编号：未知','收货国家：未知','2026-10-09 11:04','北京时间',
                     '&lt;script&gt;alert(1)&lt;/script&gt;','&lt;img src=x onerror=alert(1)&gt;'):
            self.assertContains(response,text)
        self.assertNotContains(response,'<script>alert(1)</script>')
        self.assertNotContains(response,'<img src=x onerror=alert(1)>')
        self.assertContains(response,reverse('browser_report',args=[row.product_id]))
        self.assertContains(response,reverse('profit')+f'?observation={row.pk}')
        row.capture_data={'title':'Known conditions','sku_id':'sku-12','market_country':'DE','conditions':['VAT included']};row.save()
        response=self.client.get(self.url)
        for text in ('sku-12','收货国家：DE','VAT included'):self.assertContains(response,text)

    def test_unknown_conditions_and_empty_accounts_are_explicit(self):
        response=self.client.get(self.url)
        self.assertContains(response,'还没有保存报价')
        self.assertContains(response,reverse('browser_capture'))
        self.assertNotContains(response,'没有符合条件')
        self.quote()
        self.assertContains(self.client.get(self.url),'报价条件未知')
        response=self.client.get(self.url,{'q':'no match'})
        self.assertContains(response,'没有符合条件的报价')
        self.assertContains(response,'清除筛选')

    def test_invalid_filters_do_not_fall_back_to_all_rows(self):
        self.quote()
        self.quote(owner=self.other,product=self.other_product,currency='JPY')
        queries=({'q':'x'*121},{'platform':'OTTO'},{'currency':'JPY'},{'currency':'usd'},
                 {'currency':'US'},{'currency':'USD,EUR'},{'platform':'eBay,OTTO'})
        for query in queries:
            with self.subTest(query=query):
                response=self.client.get(self.url,query)
                self.assertTrue(response.context['form'].errors)
                self.assertEqual(response.context['page'].paginator.count,0)
                self.assertContains(response,'筛选条件无效')
                self.assertNotContains(response,'?observation=')
        response=self.client.get(self.url+'?currency=USD&currency=USD')
        self.assertContains(response,'不能重复')
        self.assertEqual(response.context['page'].paginator.count,0)

    def test_get_has_no_business_writes_and_post_not_allowed(self):
        self.quote()
        models=(Product,Snapshot.all_objects,CollectionJob,ShippingRate)
        def counts():return [model.objects.count() if isinstance(model,type) else model.count() for model in models]
        before=counts()
        for query in ({},{'q':'no match'},{'currency':'wrong'},{'page':'99999999'}):
            self.client.get(self.url,query)
        self.assertEqual(counts(),before)
        self.assertEqual(self.client.post(self.url,{}).status_code,405)
        self.assertEqual(counts(),before)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code,302)

    def test_stable_twenty_row_pages_preserve_all_valid_filters_and_bound_query(self):
        rows=[Snapshot(product=self.product,owner=self.owner,source='browser',capture_id=uuid4(),price='12.34',currency='USD',
                       observed_at=self.when,capture_data={'title':'Blue + & item','sku_id':None,'conditions':[]}) for _ in range(45)]
        Snapshot.all_objects.bulk_create(rows)
        params={'q':'Blue + &','platform':'eBay','currency':'USD'}
        with CaptureQueriesContext(connection) as queries:
            first=self.client.get(self.url,params)
        captured=list(queries)
        page=first.context['page']
        self.assertEqual(len(page.object_list),20)
        self.assertEqual(page.paginator.count,45)
        expected=sorted([row.pk for row in rows],reverse=True)
        self.assertEqual([row.pk for row in page],expected[:20])
        self.assertContains(first,'q=Blue+%2B+%26&amp;platform=eBay&amp;currency=USD&amp;page=2')
        second=self.client.get(self.url,{**params,'page':'2'})
        third=self.client.get(self.url,{**params,'page':'3'})
        self.assertEqual([row.pk for row in second.context['page']],expected[20:40])
        self.assertEqual([row.pk for row in third.context['page']],expected[40:])
        full_rows=[q['sql'] for q in captured if q['sql'].startswith('SELECT "market_snapshot"."id",')]
        self.assertEqual(len(full_rows),1)
        self.assertIn('LIMIT 20',full_rows[0])
        self.assertLessEqual(len(captured),8)  # No per-row queries or unbounded history fetch.

    def test_home_recent_links_to_library_even_without_saved_quotes(self):
        response=self.client.get(reverse('dashboard'))
        self.assertContains(response,self.url)
        self.quote()
        response=self.client.get(reverse('dashboard'))
        self.assertContains(response,'查看全部报价')
        self.assertContains(response,self.url)
