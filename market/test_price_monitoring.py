from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from .models import PriceMonitor, StoreDiscovery, StorePriceJob, CatalogPriceObservation
from .price_monitoring import tick
from .jobs import run_store_prices

ROOT='https://monitor.example.com'
URL=ROOT+'/products/comb'


class MonitorTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('monitor',password='test-pass-123')
        self.client.force_login(self.user)
        self.scan=StoreDiscovery.objects.create(url=ROOT,status='succeeded',products=[{'url':URL,'title':'Comb'}, {'url':ROOT+'/products/other','title':'Other'}])
        self.route=reverse('monitor_config',args=[self.scan.pk,0])

    def monitor(self, **kwargs):
        return PriceMonitor.objects.create(owner=self.user,url=URL,store_url=ROOT,title='Comb',next_run_at=timezone.now(),**kwargs)

    def test_configuration_readonly_validation_duplicate_and_csrf(self):
        self.assertContains(self.client.get(self.route),'设置价格监测')
        self.assertContains(self.client.get(reverse('price_monitors')),'还没有监测商品')
        self.assertFalse(PriceMonitor.objects.exists())
        self.assertEqual(self.client.post(self.route,{'interval_hours':1}).status_code,400)
        self.client.post(self.route,{'interval_hours':24})
        self.client.post(self.route,{'interval_hours':6})
        self.assertEqual(PriceMonitor.objects.count(),1)
        self.assertEqual(PriceMonitor.objects.get().interval_hours,6)
        self.assertFalse(StorePriceJob.objects.exists())
        secure=Client(enforce_csrf_checks=True);secure.force_login(self.user)
        self.assertEqual(secure.post(self.route,{'interval_hours':24}).status_code,403)

    def test_ownership_pause_resume_and_due_only(self):
        monitor=self.monitor()
        other=get_user_model().objects.create_user('other')
        self.client.force_login(other)
        self.assertNotContains(self.client.get(reverse('price_monitors')),'Comb')
        toggle=reverse('monitor_toggle',args=[monitor.pk])
        self.assertEqual(self.client.post(toggle,{'action':'pause'}).status_code,404)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(toggle).status_code,405)
        self.client.post(toggle,{'action':'pause'});tick()
        self.assertFalse(StorePriceJob.objects.exists())
        self.client.post(toggle,{'action':'resume'});tick();tick()
        self.assertEqual(StorePriceJob.objects.count(),1)
        monitor.refresh_from_db();self.assertIsNotNone(monitor.pending_job_id)

    def test_reordered_directory_stable_identity_shared_jobs_and_busy(self):
        monitor=self.monitor()
        other=get_user_model().objects.create_user('second')
        second=PriceMonitor.objects.create(owner=other,url=URL,store_url=ROOT,title='Comb',next_run_at=timezone.now())
        latest=StoreDiscovery.objects.create(url=ROOT,status='succeeded',products=list(reversed(self.scan.products)))
        busy=StorePriceJob.objects.create(discovery=latest,indices=[0])
        tick();monitor.refresh_from_db()
        self.assertIsNone(monitor.pending_job_id)
        self.assertGreater(monitor.next_run_at,timezone.now())
        busy.status='failed';busy.save()
        PriceMonitor.objects.update(next_run_at=timezone.now())
        tick();tick()
        jobs=StorePriceJob.objects.filter(status='queued')
        self.assertEqual(jobs.count(),1);self.assertEqual(jobs.get().indices,[1])
        monitor.refresh_from_db();second.refresh_from_db()
        self.assertEqual(monitor.pending_job_id,second.pending_job_id)

    @patch('market.catalog_prices.collect_catalog_prices')
    def test_success_history_then_failure_preserves_quote_and_backoff(self, collect):
        monitor=self.monitor()
        collect.side_effect=lambda root,items,save:save(0,{'price_low':'10.00','price_high':'12.00','currency':'GBP','price_title':'Comb','availability':'InStock','price_error':''})
        tick();run_store_prices();tick()
        monitor.refresh_from_db()
        self.assertEqual(monitor.last_status,'succeeded');self.assertEqual(CatalogPriceObservation.objects.count(),1)
        self.assertGreater(monitor.next_run_at,timezone.now()+timedelta(hours=23))
        tick();self.assertEqual(StorePriceJob.objects.count(),1)
        PriceMonitor.objects.filter(pk=monitor.pk).update(next_run_at=timezone.now())
        collect.side_effect=lambda root,items,save:save(0,{'price_error':'访问限制'})
        tick();run_store_prices();tick();monitor.refresh_from_db()
        self.assertEqual(monitor.last_status,'failed');self.assertEqual(monitor.failures,1)
        self.assertGreater(monitor.next_run_at,timezone.now()+timedelta(hours=47))
        self.assertEqual(CatalogPriceObservation.objects.count(),1)
        self.scan.refresh_from_db();self.assertEqual(self.scan.products[0]['price_low'],'10.00')

    def test_frequency_change_updates_next_due_without_duplicate_collection(self):
        monitor=self.monitor(last_checked_at=timezone.now()-timedelta(hours=7),last_status='succeeded')
        PriceMonitor.objects.filter(pk=monitor.pk).update(next_run_at=timezone.now()+timedelta(hours=17))
        self.client.post(self.route,{'interval_hours':6})
        monitor.refresh_from_db()
        self.assertLess(monitor.next_run_at,timezone.now()+timedelta(seconds=2))
        self.assertFalse(StorePriceJob.objects.exists())
        tick();tick();self.assertEqual(StorePriceJob.objects.count(),1)

    def test_missing_target_and_target_success_in_partial_failed_job(self):
        monitor=self.monitor();tick();monitor.refresh_from_db()
        job=monitor.pending_job
        CatalogPriceObservation.objects.create(discovery=self.scan,job=job,url=URL,title='Comb',price_low=0,price_high=0,currency='GBP',observed_at=timezone.now())
        job.status='failed';job.message='其它商品失败';job.save()
        tick();monitor.refresh_from_db();self.assertEqual(monitor.last_status,'succeeded')
        StoreDiscovery.objects.all().delete()
        PriceMonitor.objects.filter(pk=monitor.pk).update(next_run_at=timezone.now())
        tick();monitor.refresh_from_db();self.assertEqual(monitor.last_status,'failed')
        self.assertIn('找不到',monitor.message)
