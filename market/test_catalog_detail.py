from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import StoreDiscovery

class CatalogDetailTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user('report',password='test-pass-123'))
        self.scan=StoreDiscovery.objects.create(url='https://millys.co.uk',status='succeeded',products=[
            {'url':'https://millys.co.uk/products/coat','title':'Coat <script>alert(1)</script>',
             'price_low':'12.00','price_high':'38.00','currency':'GBP','price_observed_at':'old','availability':'InStock'}])

    def test_report_missing_review_and_links(self):
        url=reverse('catalog_detail',args=[self.scan.pk,0])
        response=self.client.get(url)
        self.assertContains(response,'GBP 12.00')
        self.assertContains(response,'38.00')
        self.assertContains(response,'尚未取得')
        self.assertContains(response,'有货')
        self.assertNotContains(response,'<script>alert(1)</script>')
        self.assertContains(self.client.get(reverse('stores')),url)
        self.assertContains(self.client.get(reverse('store_research',args=[self.scan.pk])),url)
        self.assertEqual(self.client.get(reverse('catalog_detail',args=[self.scan.pk,99])).status_code,404)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code,302)

    def test_explicit_zero_and_sample_not_total(self):
        self.scan.products[0].update(rating='0.00',review_count=0,rating_count=7,
            review_samples=[{'body':'Real sample','date':'','rating':'4.00'}])
        self.scan.save()
        response=self.client.get(reverse('catalog_detail',args=[self.scan.pk,0]))
        self.assertContains(response,'0.00 / 5')
        self.assertContains(response,'Real sample')
        self.assertTrue(response.context['has_review_count'])
        self.assertEqual(response.context['item']['review_count'],0)

    def test_current_product_queue_deduplicates_and_uses_original_index(self):
        from .models import StorePriceJob
        self.scan.products.append({'url':'https://millys.co.uk/products/other','title':'Other'})
        self.scan.save()
        url=reverse('refresh_catalog_product',args=[self.scan.pk,1])
        self.assertEqual(self.client.get(url).status_code,405)
        for _ in range(2):
            self.assertRedirects(self.client.post(url),reverse('catalog_detail',args=[self.scan.pk,1]))
        job=StorePriceJob.objects.get()
        self.assertEqual(job.indices,[1])
        self.assertEqual(job.total,1)
        self.assertEqual(self.client.post(reverse('refresh_catalog_product',args=[self.scan.pk,99])).status_code,404)
        self.assertContains(self.client.get(reverse('catalog_detail',args=[self.scan.pk,1])),'当前商品采集')
        self.assertNotContains(self.client.get(reverse('catalog_detail',args=[self.scan.pk,0])),'当前商品采集')

    def test_content_escaped_and_variants_rendered(self):
        self.scan.products[0].update(description='<script>bad()</script>',brand='Brand',category='Tools',
            images=['https://millys.co.uk/cdn/coat.jpg'],variants=[{'name':'Blue small','sku':'A1','size':'S',
                'price_low':'12.00','price_high':'12.00','currency':'GBP','url':self.scan.products[0]['url'],
                'availability':'OutOfStock','is_range':False}])
        self.scan.save()
        response=self.client.get(reverse('catalog_detail',args=[self.scan.pk,0]))
        self.assertContains(response,'Blue small')
        self.assertContains(response,'SKU：A1')
        self.assertContains(response,'https://millys.co.uk/cdn/coat.jpg')
        self.assertNotContains(response,'<script>bad()</script>')
