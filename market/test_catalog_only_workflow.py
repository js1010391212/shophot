"""Controlled directory-only regressions; not evidence of live merchant access."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .jobs import run_next
from .models import CatalogPriceObservation, StoreDiscovery, StorePriceJob
from .workflows import start_store_analysis

ROOT = 'https://directory.example.com'
CATALOG = {'products': [{'url': ROOT+'/products/real-shape', 'title': 'Directory title'}], 'limited': True}


class CatalogOnlyWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('directory-only-ordinary')
        self.client.force_login(self.user)

    @patch('market.catalog_prices.collect_catalog_prices')
    @patch('market.discovery.discover', return_value=CATALOG)
    def test_home_input_directory_mode_finishes_without_any_price_request(self, discover, prices):
        response = self.client.post(reverse('analyze_competitor'), {'url': ROOT, 'platform': 'Auto', 'scope': 'catalog'})
        scan = StoreDiscovery.objects.get()
        self.assertFalse(scan.analyze_prices)
        self.assertEqual(response.url, reverse('store_analysis', args=[scan.pk]))
        self.assertTrue(run_next())
        self.assertFalse(run_next())
        prices.assert_not_called()
        discover.assert_called_once_with(ROOT)
        scan.refresh_from_db()
        self.assertEqual(scan.status, 'succeeded')
        self.assertFalse(StorePriceJob.objects.exists())
        self.assertFalse(CatalogPriceObservation.objects.exists())
        with CaptureQueriesContext(connection) as queries:
            progress = self.client.get(response.url, {'format': 'json'})
        self.assertTrue(all(q['sql'].lstrip().upper().startswith('SELECT') for q in queries.captured_queries))
        self.assertFalse(progress.json()['active'])
        report = reverse('store_research', args=[scan.pk])
        self.assertEqual(progress.json()['redirect_url'], report)
        page = self.client.get(report)
        self.assertContains(page, '公开商品目录分析')
        self.assertContains(page, '不请求商品详情或报价')
        self.assertContains(page, 'Directory title')
        self.assertContains(page, 'name="scope" value="catalog"')
        self.assertNotContains(page, '<button>继续采集下一批</button>')
        self.assertEqual(page.context['priced_count'], 0)

    @patch('market.discovery.discover', return_value=CATALOG)
    def test_default_scope_keeps_automatic_first_quote_batch(self, discover):
        self.client.post(reverse('analyze_competitor'), {'url': ROOT, 'platform': 'Auto'})
        scan = StoreDiscovery.objects.get()
        self.assertTrue(scan.analyze_prices)
        run_next()
        self.assertEqual(StorePriceJob.objects.get().indices, [0])

    def test_invalid_scope_is_rejected_before_queue(self):
        for endpoint in ('analyze_competitor', 'discover_store'):
            response = self.client.post(reverse(endpoint), {'url': ROOT, 'platform': 'Auto', 'workflow': '1', 'scope': 'invented'})
            self.assertEqual(response.status_code, 400)
        self.assertFalse(StoreDiscovery.objects.exists())

    def test_catalog_refresh_uses_csrf_and_never_changes_saved_report(self):
        saved = StoreDiscovery.objects.create(url=ROOT, status='succeeded', products=CATALOG['products'])
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.user)
        secure.get(reverse('store_research', args=[saved.pk]))
        payload = {'url': ROOT, 'workflow': '1', 'scope': 'catalog'}
        self.assertEqual(secure.post(reverse('discover_store'), payload).status_code, 403)
        payload['csrfmiddlewaretoken'] = secure.cookies['csrftoken'].value
        response = secure.post(reverse('discover_store'), payload)
        fresh = StoreDiscovery.objects.exclude(pk=saved.pk).get()
        self.assertFalse(fresh.analyze_prices)
        self.assertEqual(response.url, reverse('store_analysis', args=[fresh.pk]))
        self.assertEqual(secure.post(reverse('discover_store'), payload).url, response.url)
        self.assertEqual(StoreDiscovery.objects.count(), 2)
        saved.refresh_from_db()
        self.assertEqual(saved.products, CATALOG['products'])

    def test_directory_request_does_not_demote_already_active_price_task(self):
        scan = start_store_analysis(ROOT)
        self.assertEqual(start_store_analysis(ROOT, include_prices=False).pk, scan.pk)
        scan.refresh_from_db()
        self.assertTrue(scan.analyze_prices)
        scan.status = 'failed'
        scan.save()
        directory = start_store_analysis(ROOT, include_prices=False)
        self.assertFalse(directory.analyze_prices)
        self.assertEqual(start_store_analysis(ROOT).pk, directory.pk)
        directory.refresh_from_db()
        self.assertTrue(directory.analyze_prices)

    def test_legacy_manual_directory_with_price_job_is_not_labelled_catalog_only(self):
        scan = StoreDiscovery.objects.create(url=ROOT, status='succeeded', products=CATALOG['products'])
        StorePriceJob.objects.create(discovery=scan, status='failed', indices=[0], total=1)
        page = self.client.get(reverse('store_research', args=[scan.pk]))
        self.assertFalse(page.context['report_coverage']['catalog_only'])
        self.assertNotContains(page, '本次选择仅目录分析')
        self.assertContains(page, '<button>继续采集下一批</button>')

    def test_eff_attribution_is_explicit_and_not_applied_to_other_merchants(self):
        scan = StoreDiscovery.objects.create(url='https://shopeff.org', status='succeeded', products=[])
        page = self.client.get(reverse('store_research', args=[scan.pk]))
        self.assertContains(page, 'Electronic Frontier Foundation')
        self.assertContains(page, 'https://www.eff.org/copyright')
        self.assertContains(page, 'CC BY 4.0')
        scan.url = ROOT
        scan.save()
        self.assertNotContains(self.client.get(reverse('store_research', args=[scan.pk])), 'CC BY 4.0')

    def test_completed_directory_can_upgrade_via_post_without_overwriting_history(self):
        saved=StoreDiscovery.objects.create(url=ROOT,status='succeeded',products=CATALOG['products'],analyze_prices=False)
        report=reverse('store_research',args=[saved.pk])
        self.assertEqual(self.client.get(report).status_code,200)
        self.assertEqual(StoreDiscovery.objects.count(),1)
        response=self.client.post(reverse('analyze_competitor'),{'url':ROOT,'platform':'Auto','scope':'prices'})
        fresh=StoreDiscovery.objects.exclude(pk=saved.pk).get()
        self.assertTrue(fresh.analyze_prices)
        self.assertEqual(fresh.status,'queued')
        self.assertEqual(response.url,reverse('store_analysis',args=[fresh.pk]))
        saved.refresh_from_db()
        self.assertFalse(saved.analyze_prices)
        self.assertEqual(saved.products,CATALOG['products'])
        self.assertEqual(self.client.get(report).status_code,200)

    def test_completed_full_analysis_still_reuses_saved_report(self):
        saved=StoreDiscovery.objects.create(url=ROOT,status='succeeded',products=CATALOG['products'],analyze_prices=True)
        self.assertEqual(start_store_analysis(ROOT).pk,saved.pk)
        self.assertEqual(StoreDiscovery.objects.count(),1)

    def test_legacy_scope_omission_preserves_saved_directory_reuse(self):
        saved=StoreDiscovery.objects.create(url=ROOT,status='succeeded',products=CATALOG['products'],analyze_prices=False)
        response=self.client.post(reverse('analyze_competitor'),{'url':ROOT,'platform':'Auto'})
        self.assertEqual(response.url,reverse('store_analysis',args=[saved.pk]))
        self.assertEqual(StoreDiscovery.objects.count(),1)
        self.assertEqual(start_store_analysis(ROOT).pk,saved.pk)
