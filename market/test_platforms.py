from django.test import TestCase, SimpleTestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from .platforms import known_platform
from .forms import AnalyzeForm
from .models import StoreDiscovery, StorePriceJob, CollectionJob, Product


class PlatformIdentityTests(SimpleTestCase):
    def test_real_hosts_regions_and_domain_boundaries(self):
        for url,expected in [('https://us.shein.com/store/home?store_code=1','SHEIN'),
                             ('https://m.shein.com.mx/store/home?store_code=1','SHEIN'),
                             ('https://www.otto.de/p/test-S0123/','OTTO'),
                             ('https://www.ozon.ru/seller/test/','Ozon')]:
            self.assertEqual(known_platform(url),expected)
            for selected in ('Auto','Shopify','AliExpress'):
                form=AnalyzeForm({'platform':selected,'url':url},allow_store=True)
                if expected == 'OTTO':
                    self.assertTrue(form.is_valid(),form.errors)
                    self.assertEqual(form.cleaned_data['platform'],'OTTO')
                    continue
                self.assertFalse(form.is_valid());self.assertIn(expected,str(form.errors['url']))
                self.assertIn('尚未接入',str(form.errors['url']))
        for url in ('https://otto.de.example.com/','https://evilshein.com/','https://ozon.ru.example.com/'):
            self.assertIsNone(known_platform(url))

    def test_existing_shopify_and_aliexpress_paths_remain_valid(self):
        for url,expected in [('https://millys.co.uk/','Shopify'),('https://www.beardbrand.com/products/beard-combs','Shopify'),
                             ('https://www.aliexpress.com/item/1005001234567890.html','AliExpress')]:
            form=AnalyzeForm({'platform':'Auto','url':url},allow_store=True)
            self.assertTrue(form.is_valid(),form.errors);self.assertEqual(form.cleaned_data['platform'],expected)
        form=AnalyzeForm({'platform':'Auto','url':'https://www.aliexpress.us/item/123.html'},allow_store=True)
        self.assertFalse(form.is_valid());self.assertIn('美国站',str(form.errors))


class UnsupportedPlatformFlowTests(TestCase):
    def test_post_keeps_input_and_reports_platform_without_enqueuing(self):
        self.client.force_login(get_user_model().objects.create_user('platform-validation',password='test-pass-123'))
        for url,name in [('https://www.ozon.ru/seller/tefal-ofitsialnyy-magazin/','Ozon'),
                         ('https://us.shein.com/store/home?store_code=1061637975','SHEIN')]:
            response=self.client.post(reverse('analyze_competitor'),{'platform':'Auto','url':url})
            self.assertContains(response,'已识别为 '+name,status_code=400)
            self.assertContains(response,'尚未接入',status_code=400)
            self.assertContains(response,url,status_code=400)
        self.assertFalse(Product.objects.exists());self.assertFalse(StoreDiscovery.objects.exists())
        self.assertFalse(StorePriceJob.objects.exists());self.assertFalse(CollectionJob.objects.exists())
