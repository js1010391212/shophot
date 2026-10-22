"""Display timestamps must never change task-window classification or saved facts."""
from copy import deepcopy
from datetime import datetime, timezone
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from .catalog_coverage import moment, quote_display_moment, build_catalog_coverage
from .models import StoreDiscovery, StorePriceJob, CatalogPriceObservation


class QuoteDisplayParsingTests(SimpleTestCase):
    def test_explicit_utc_legacy_and_iso_preserve_precision(self):
        for raw,precision in [('2026-10-22 12:47 UTC','minute'),
            ('2026-10-22T12:47Z','minute'),('2026-10-22T12:47:23Z','second'),
            ('2026-10-22T20:47:23+08:00','second'),('2026-10-22T12:47:23.123456+0000','second')]:
            with self.subTest(raw=raw):
                parsed,actual=quote_display_moment(raw)
                self.assertEqual(actual,precision)
                self.assertEqual(parsed.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M'),'2026-10-22 12:47')
        aware=datetime(2026,10,22,12,47,23,tzinfo=timezone.utc)
        self.assertEqual(quote_display_moment(aware),(aware,'second'))
        self.assertIsNone(moment('2026-10-22 12:47 UTC'))

    def test_invalid_naive_and_unverified_formats_stay_unknown(self):
        for raw in [None,False,3,{},datetime(2026,10,22), '2026-10-22 12:47',
            '2026-10-22T12:47:23','2026-02-30 12:47 UTC','2026-10-22 24:47 UTC',
            '2026-10-22 12:60 UTC','2026-10-22 12:47 GMT','2026-10-22 12:47 CST',
            '2026-10-22 12:47 utc','2026-10-22 12:47:00 UTC','2026-10-22 12:47 UTC ',
            '２０２６-10-22 12:47 UTC','2026-02-30T12:47:00Z','2026-10-22T12:47:00+99:00','2026-10-22T12:47:00+00:60',
            '<script>alert(1)</script>', 'x'*51]:
            with self.subTest(raw=raw):
                self.assertEqual(quote_display_moment(raw),(None,''))


class QuoteTimeReportTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user('quote-time-reader'))
        self.scan=StoreDiscovery.objects.create(url='https://www.adafruit.com',status='succeeded',products=[
            {'url':'https://www.adafruit.com/product/'+str(i+1),'title':'Controlled '+str(i),
             'price_low':'4.00','price_high':'4.00','currency':'USD','sku':str(i+1),
             'price_observed_at':value,'price_error':'preserved failure',
             'price_attempted_at':'2026-10-22 12:47 UTC'}
            for i,value in enumerate(['2026-10-22 12:47 UTC','2026-10-22T12:48:23Z',
                                      '2026-10-22 12:49'])])
        self.job=StorePriceJob.objects.create(discovery=self.scan,status='failed',indices=[0,1,2],
            total=3,processed=1,started_at=datetime(2026,10,22,12,tzinfo=timezone.utc),
            finished_at=datetime(2026,10,22,13,tzinfo=timezone.utc))

    def test_report_local_timezone_minute_precision_and_unknown_without_writes(self):
        before=deepcopy(self.scan.products)
        coverage=build_catalog_coverage(self.scan,self.job)
        self.assertEqual(coverage['historical_count'],3)
        self.assertEqual(coverage['failed_count'],0)
        self.assertEqual(coverage['unresolved_count'],3)
        self.assertEqual([p['coverage_state'] for p in coverage['items']],['unknown']*3)
        self.assertEqual([p['quote_seen_precision'] for p in coverage['items']],['minute','second',''])
        response=self.client.get(reverse('store_research',args=[self.scan.pk]))
        self.assertContains(response,'2026-10-22 20:47（北京时间）')
        self.assertNotContains(response,'2026-10-22 20:47:00')
        self.assertContains(response,'2026-10-22 20:48:23（北京时间）')
        self.assertContains(response,'报价时间未知',count=1)
        self.scan.refresh_from_db()
        self.assertEqual(self.scan.products,before)
        self.assertEqual(StorePriceJob.objects.count(),1)
        self.assertFalse(CatalogPriceObservation.objects.exists())


class QuoteDisplayBoundaryTests(SimpleTestCase):
    def render_report_time(self, value):
        from types import SimpleNamespace
        from django.template.loader import render_to_string
        seen,precision=quote_display_moment(value)
        return render_to_string('market/research.html', {
            'scan':SimpleNamespace(pk=1,url='https://controlled.example.com'),
            'products':[{'catalog_index':0,'quote_seen_at':seen,'quote_seen_precision':precision}],
        })

    def test_unrenderable_upper_lower_and_aware_values_are_unknown(self):
        from datetime import timedelta
        for raw in ['9999-12-31 23:59 UTC','9999-12-31T23:59:59Z',
                    '0001-01-01T00:00:00+23:59',
                    datetime.max.replace(tzinfo=timezone.utc),
                    datetime.min.replace(tzinfo=timezone(timedelta(hours=23,minutes=59)))]:
            with self.subTest(raw=raw):
                html=self.render_report_time(raw)
                self.assertIn('报价时间未知',html)
                self.assertEqual(quote_display_moment(raw),(None,''))

    def test_valid_boundary_is_not_clamped_and_normal_minute_stays_minute(self):
        for raw,expected in [('9999-12-31 12:00 UTC','9999-12-31 20:00（北京时间）'),
                             ('2026-10-22 12:47 UTC','2026-10-22 20:47（北京时间）')]:
            with self.subTest(raw=raw):
                html=self.render_report_time(raw)
                self.assertIn(expected,html)
                self.assertNotIn('报价时间未知',html)
