from django.test import SimpleTestCase, TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import StoreDiscovery
from .research import build_research, title_terms

class ResearchTests(SimpleTestCase):
    def scan(self):
        return StoreDiscovery(url='https://millys.co.uk',products=[
            {'url':'https://millys.co.uk/products/one','title':'Milly’s Blue Blue Coat','price_title':'Milly’s Blue Blue Coat','price_low':'12.00','price_high':'38.00','currency':'GBP','price_observed_at':'old'},
            {'url':'https://millys.co.uk/products/two','title':'Red Coat','currency':'USD','price_observed_at':'old'},
            {'url':'https://millys.co.uk/products/three','title':'Blue Spray'},
            {'url':'https://millys.co.uk/products/three','title':'Duplicate Blue Spray'}])

    def test_product_frequency_dedup_stopwords_and_all_leaves(self):
        data=build_research(self.scan())
        self.assertEqual(data['total_count'],3)
        terms={p['term']:p for p in data['keywords']}
        self.assertEqual(terms['blue']['count'],2)
        self.assertEqual(terms['blue']['share'],66.7)
        self.assertNotIn('milly',terms)
        leaves=[child for group in data['tree_data']['children'] for child in group['children']]
        self.assertEqual(len(leaves),3)
        self.assertEqual(len({p['rowId'] for p in leaves}),3)
        self.assertEqual(title_terms('The Cat and 狗狗洗护','https://cats.example.com'),{'cat','狗狗洗护'})

    def test_term_currency_filter_preserves_whole_catalog_denominator(self):
        data=build_research(self.scan(),'blue','GBP')
        self.assertEqual(data['matched_count'],1)
        self.assertEqual(data['total_count'],3)
        self.assertEqual(data['products'][0]['price_high'],'38.00')
        self.assertEqual(build_research(self.scan(),'bl')['matched_count'],0)
        self.assertEqual(build_research(self.scan(),currency='EUR')['matched_count'],0)

class ResearchViewTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user('words',password='test-pass-123'))

    def test_empty_page_no_demo_data_and_authentication(self):
        self.assertContains(self.client.get(reverse('keyword_research')),'先发现一个店铺')
        self.client.logout()
        self.assertEqual(self.client.get(reverse('keyword_research')).status_code,302)

    def test_actual_report_links_filter_and_safe_json(self):
        scan=StoreDiscovery.objects.create(url='https://millys.co.uk',status='succeeded',products=[
            {'url':'https://millys.co.uk/products/one','title':'Blue Shampoo </script><img src=x onerror=alert(1)>',
             'price_low':'12.00','price_high':'38.00','currency':'GBP','price_observed_at':'old'},
            {'url':'https://millys.co.uk/products/two','title':'Blue Cologne'}])
        report=reverse('store_research',args=[scan.pk])
        response=self.client.get(report,{'term':'shampoo','currency':'GBP'})
        self.assertContains(response,'对应商品 · 1 件')
        self.assertContains(response,'GBP 12.00')
        self.assertNotContains(response,'<img src=x onerror=alert(1)>')
        self.assertContains(response,'\\u003C/script\\u003E')
        self.assertContains(self.client.get(reverse('stores')),report)
        self.assertContains(self.client.get(reverse('keyword_research')),'词条与商品关系')
        self.assertEqual(self.client.get(reverse('keyword_research'),{'store':'not-an-id'}).status_code,400)
        self.assertEqual(self.client.get(reverse('store_research',args=[99999])).status_code,404)

class ResearchFilterTests(SimpleTestCase):
    def setUp(self):
        self.scan=StoreDiscovery(url='https://store.example',products=[
            {'url':'https://store.example/products/a','title':'Coat Alpha','price_observed_at':'old','price_low':'10.00','price_high':'40.00','currency':'GBP','rating':'4.5','review_count':10},
            {'url':'https://store.example/products/b','title':'Coat Beta','price_observed_at':'old','price_low':'20.00','price_high':'20.00','currency':'GBP','rating':'0','review_count':0},
            {'url':'https://store.example/products/c','title':'Coat Unknown','currency':'GBP'},
            {'url':'https://store.example/products/d','title':'Coat Dollar','price_observed_at':'old','price_low':'1.00','price_high':'1.00','currency':'USD'}])

    def test_range_overlap_unknowns_and_sort_original_index(self):
        from decimal import Decimal
        rows=build_research(self.scan,currency='GBP',price_min=Decimal('30'),price_max=Decimal('35'))['products']
        self.assertEqual([r['catalog_index'] for r in rows],[0])
        rows=build_research(self.scan,q='COAT',currency='GBP',sort='price_desc')['products']
        self.assertEqual([r['catalog_index'] for r in rows],[1,0,2])
        self.assertEqual(build_research(self.scan,min_rating=Decimal('0'),min_reviews=0)['matched_count'],2)
        self.assertEqual(build_research(self.scan,min_rating=Decimal('4'))['matched_count'],1)
        self.assertEqual(build_research(self.scan,q='beta')['matched_count'],1)

    def test_distribution_is_per_currency_and_counts_each_product_once(self):
        data=build_research(self.scan)
        charts={d['currency']:d for d in data['distribution']}
        self.assertEqual(sum(charts['GBP']['counts']),2)
        self.assertEqual(charts['USD']['counts'],[1])
        self.assertEqual(data['matched_priced_count'],3)
        self.scan.products[0]['price_low']='NaN'
        self.assertEqual(build_research(self.scan)['matched_priced_count'],2)

    def test_invalid_filters_and_currency_required_for_price(self):
        from .forms import ResearchFilterForm
        for params in [{'price_min':'10'},{'sort':'price_desc'}, {'currency':'GBP','price_min':'20','price_max':'10'},
                       {'min_rating':'6'},{'min_reviews':'-1'},{'currency':'EUR'},{'price_min':'NaN'}]:
            self.assertFalse(ResearchFilterForm(params,currencies=['GBP','USD']).is_valid())
        form=ResearchFilterForm({'currency':'GBP','price_min':'0','min_rating':'0','min_reviews':'0'},currencies=['GBP'])
        self.assertTrue(form.is_valid())

class ResearchFilterViewTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user('filter',password='test-pass-123'))
        self.scan=StoreDiscovery.objects.create(url='https://store.example.com',status='succeeded',products=[
            {'url':'https://store.example.com/products/a','title':'Blue Coat','price_low':'10.00','price_high':'30.00','currency':'GBP','price_observed_at':'old','rating':'4.7','review_count':12},
            {'url':'https://store.example.com/products/b','title':'Unknown Coat'}])

    def test_form_errors_do_not_silently_show_all_and_links_preserve_filters(self):
        url=reverse('store_research',args=[self.scan.pk])
        response=self.client.get(url,{'price_min':'15'})
        self.assertContains(response,'请选择一个币种')
        self.assertEqual(response.context['matched_count'],0)
        response=self.client.get(url,{'currency':'GBP','price_min':'15','min_rating':'4','sort':'reviews_desc'})
        self.assertContains(response,'对应商品 · 1 件')
        self.assertContains(response,'4.7 / 5')
        self.assertContains(response,'12 条评价')
        self.assertContains(response,'price_min=15')
        self.assertContains(response,'price-distribution-data')
        self.assertContains(response,reverse('catalog_detail',args=[self.scan.pk,0]))
