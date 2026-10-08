import csv
import io
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import StoreDiscovery


def item(root,name,price=None,currency='GBP'):
    row={'url':root+'/products/'+name,'title':name}
    if price is not None:row.update(price_low=price,price_high=price,currency=currency,price_observed_at='observed')
    return row


class CatalogMarketTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user('market',password='test-pass-123'))
        self.a=StoreDiscovery.objects.create(url='https://first.example.com',status='succeeded',products=[
            item('https://first.example.com','Coat A','10.00'),item('https://first.example.com','Unknown')])
        self.b=StoreDiscovery.objects.create(url='https://second.example.com',status='succeeded',products=[
            item('https://second.example.com','Coat B','30.00'),item('https://second.example.com','Dollar','15.00','USD')])

    def test_cross_store_filter_sort_original_links_and_latest_only(self):
        StoreDiscovery.objects.create(url=self.a.url,status='succeeded',products=[item(self.a.url,'Latest Coat','20.00')])
        response=self.client.get(reverse('catalog_market'),{'q':'coat','currency':'GBP','sort':'price_asc'})
        self.assertEqual(response.context['matched_count'],2)
        rows=list(response.context['page'])
        self.assertEqual([r['price_low'] for r in rows],['20.00','30.00'])
        self.assertNotContains(response,'Coat A')
        self.assertContains(response,reverse('catalog_detail',args=[self.b.pk,0]))
        self.assertEqual(sum(response.context['distribution'][0]['counts']),2)
        self.assertEqual(response.context['store_count'],2)

    def test_unknown_filter_error_and_pagination(self):
        response=self.client.get(reverse('catalog_market'))
        self.assertContains(response,'报价未知，无法加入对比')
        response=self.client.get(reverse('catalog_market'),{'price_min':10})
        self.assertContains(response,'请选择一个币种')
        self.assertEqual(response.context['matched_count'],0)
        self.b.products=[item(self.b.url,f'Coat {i}','30.00') for i in range(60)];self.b.save()
        response=self.client.get(reverse('catalog_market'),{'page':2,'q':'coat'})
        self.assertEqual(response.context['page'].number,2)
        self.assertEqual(len(response.context['page']),11)

    def test_valid_same_currency_comparison_sources_and_unknown_reviews(self):
        response=self.client.get(reverse('catalog_compare'),{'items':[f'{self.a.pk}:0',f'{self.b.pk}:0']})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'GBP 10.00')
        self.assertContains(response,'GBP 30.00')
        self.assertContains(response,'评价数未知')
        self.assertContains(response,self.a.products[0]['url'])
        self.assertEqual(response.context['chart_data']['low'],['10.00','30.00'])

    def test_invalid_comparison_selection_unknown_or_mixed_currency(self):
        for values in [[],[f'{self.a.pk}:0'],[f'{self.a.pk}:0']*2,
                       [f'{self.a.pk}:0',f'{self.b.pk}:1'],[f'{self.a.pk}:1',f'{self.b.pk}:0'],
                       [f'{self.a.pk}:0',f'{self.b.pk}:99'],['bad',f'{self.a.pk}:0'],[f'{self.a.pk}:{i}' for i in range(9)]]:
            self.assertEqual(self.client.get(reverse('catalog_compare'),{'items':values}).status_code,400)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('catalog_market')).status_code,302)
        self.assertEqual(self.client.get(reverse('catalog_compare')).status_code,302)

    def test_duplicate_url_cannot_be_compared_through_two_directories(self):
        duplicate=StoreDiscovery.objects.create(url=self.a.url,status='succeeded',products=self.a.products)
        response=self.client.get(reverse('catalog_compare'),{'items':[f'{self.a.pk}:0',f'{duplicate.pk}:0']})
        self.assertEqual(response.status_code,400)
        self.assertContains(response,'不能重复对比',status_code=400)

    def test_inventory_coverage_and_original_identity(self):
        self.a.products[0].update(availability='OutOfStock',price_error='更新失败，保留旧报价',
                                 review_samples=[{'body':'Good quality','rating':'5'},
                                                 {'body':'Wrong source','source_url':self.b.products[0]['url']}])
        self.a.products[1].update(availability='InStock')
        self.a.save()
        response=self.client.get(reverse('catalog_market'),{'availability':'OutOfStock','coverage':'reviews'})
        rows=list(response.context['page'])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['catalog_index'],0)
        self.assertEqual(rows[0]['review_sample_count'],1)
        self.assertContains(response,'缺货')
        self.assertEqual(self.client.get(reverse('catalog_market'),{'coverage':'failed'}).context['matched_count'],1)
        self.assertEqual(self.client.get(reverse('catalog_market'),{'availability':'unknown','coverage':'unattempted'}).context['matched_count'],1)
        self.assertEqual(self.client.get(reverse('catalog_market'),{'coverage':'unquoted'}).context['matched_count'],1)
        self.assertEqual(self.client.get(reverse('catalog_market'),{'availability':'bad'}).context['matched_count'],0)

    def test_filtered_export_all_pages_unknown_zero_and_formula_safety(self):
        self.b.limited=True
        self.b.products=[item(self.b.url,f'Coat {i}','30.00') for i in range(60)]
        self.b.products[0].update(title='=Coat formula',rating=0,review_count=0)
        self.b.save()
        response=self.client.get(reverse('catalog_export'),{'q':'coat','currency':'GBP','sort':'title','page':2})
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.content.startswith(b'\xef\xbb\xbf'))
        rows=list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))))
        self.assertEqual(len(rows),61)
        formula=next(r for r in rows if 'formula' in r['商品标题'])
        self.assertEqual(formula['商品标题'],"'=Coat formula")
        self.assertEqual(formula['商品评分（5分制）'],'0.00')
        self.assertEqual(formula['公开评价数'],'0')
        self.assertEqual(formula['目录是否截取'],'是')
        response=self.client.get(reverse('catalog_export'),{'coverage':'unquoted'})
        unknown=list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))))[0]
        self.assertEqual(unknown['最低公开报价'],'')
        self.assertEqual(unknown['商品评分（5分制）'],'')
        self.assertEqual(unknown['公开评价数'],'')
        self.assertEqual(self.client.get(reverse('catalog_export'),{'price_min':10}).status_code,400)
        empty=self.client.get(reverse('catalog_export'),{'q':'no matching title'})
        self.assertEqual(len(list(csv.reader(io.StringIO(empty.content.decode('utf-8-sig'))))),1)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('catalog_export')).status_code,302)
