"""Controlled coverage and report-flow regressions; never platform evidence."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .catalog_coverage import build_catalog_coverage, quote_values
from .models import CatalogPriceObservation, StoreDiscovery, StorePriceJob
from .research import build_research

ROOT='https://controlled.example.com'


class CoverageQuoteValidationTests(SimpleTestCase):
    def test_timestamp_is_not_quote_and_zero_is_valid_without_currency_inference(self):
        original=dict(price_observed_at='old',price_low='0',price_high='0',currency='USD')
        self.assertEqual(quote_values(original),(Decimal('0.00'),Decimal('0.00')))
        for change in ({'price_low':'NaN'},{'price_low':'-1'},{'price_high':None},{'price_high':'-1'},
                       {'price_low':'2','price_high':'1'},{'currency':''},{'currency':'usd'},
                       {'currency':3},{'price_observed_at':''}):
            self.assertEqual(quote_values({**original,**change}),(None,None))

    def test_research_valid_quote_count_distribution_and_rows_agree(self):
        common=dict(price_observed_at='old',price_low='5',price_high='5',currency='USD')
        products=[dict(url=ROOT+'/products/'+str(i),title='Sample '+str(i),**{**common,**change})
                  for i,change in enumerate(({}, {'price_low':'NaN'}, {'currency':''}, {'price_high':None}, {'price_low':'0','price_high':'0'}, {'currency':'EUR'}))]
        data=build_research(SimpleNamespace(url=ROOT,products=products))
        self.assertEqual(data['total_count'],6)
        self.assertEqual(data['priced_count'],3)
        self.assertEqual(data['matched_priced_count'],3)
        self.assertEqual(sum(chart['total'] for chart in data['distribution']),3)
        self.assertEqual(sum(row['valid_quote'] for row in data['products']),3)
        self.assertEqual({chart['currency'] for chart in data['distribution']},{'USD','EUR'})
        unquoted=build_research(SimpleNamespace(url=ROOT,products=products),coverage='unquoted')
        self.assertEqual(unquoted['matched_count'],3)
        self.assertEqual(unquoted['matched_priced_count'],0)


class CoverageFixture:
    def setUp(self):
        self.now=timezone.now()
        self.started=self.now-timedelta(minutes=10)
        self.finished=self.now-timedelta(minutes=5)
        old=self.now-timedelta(days=2)
        attempted=self.started+timedelta(seconds=20)
        self.products=[
            dict(url=ROOT+'/products/new',title='New item',price_low='10',price_high='10',currency='USD',price_observed_at=old.isoformat()),
            dict(url=ROOT+'/products/retained',title='Retained coat',price_low='7',price_high='9',currency='USD',price_observed_at=old.isoformat(),price_error='HTTP 403',price_attempted_at=attempted.isoformat()),
            dict(url=ROOT+'/products/failed',title='Missing amount',price_error='No attributable offer',price_attempted_at=attempted.isoformat()),
            dict(url=ROOT+'/products/unresolved',title='Stopped before callback'),
            dict(url=ROOT+'/products/not-planned',title='Other currency',price_low='20',price_high='20',currency='EUR',price_observed_at=old.isoformat()),
        ]
        self.scan=StoreDiscovery.objects.create(url=ROOT,status='succeeded',products=self.products,limited=True,finished_at=old)
        self.oldjob=StorePriceJob.objects.create(discovery=self.scan,indices=[0,1,4],status='succeeded',processed=3,total=3)
        CatalogPriceObservation.objects.create(discovery=self.scan,job=self.oldjob,url=self.products[0]['url'],title='Old',price_low='10',price_high='10',currency='USD',observed_at=old)
        self.job=StorePriceJob.objects.create(discovery=self.scan,indices=[0,1,2,3],status='failed',processed=3,total=4,started_at=self.started,finished_at=self.finished,message='HTTP 429; batch stopped')
        self.quote=CatalogPriceObservation.objects.create(discovery=self.scan,job=self.job,url=self.products[0]['url'],title='Current verified offer',price_low='12',price_high='15',currency='USD',observed_at=attempted)

    def coverage(self):
        return build_catalog_coverage(self.scan,self.job)


class CatalogCoverageTests(CoverageFixture, TestCase):
    def test_partial_failure_current_job_observations_are_only_success_evidence(self):
        before=deepcopy(self.scan.products)
        with self.assertNumQueries(1):data=self.coverage()
        self.assertEqual({key:data[key] for key in ('total_count','new_count','failed_count','unresolved_count','not_scheduled_count','historical_count','quoted_count','unquoted_count')},
                         dict(total_count=5,new_count=1,failed_count=2,unresolved_count=1,not_scheduled_count=1,historical_count=2,quoted_count=3,unquoted_count=2))
        self.assertEqual(data['state'],'partial')
        self.assertEqual(data['planned_count'],4)
        self.assertEqual(self.scan.products,before)
        self.assertEqual(data['items'][0]['price_low'],Decimal('12'))
        self.assertEqual(data['items'][0]['price_high'],Decimal('15'))
        self.assertEqual(data['items'][1]['coverage_state'],'failed')
        self.assertEqual(data['items'][1]['quote_origin'],'historical')
        self.assertEqual(data['items'][4]['coverage_state'],'not_scheduled')

    def test_processed_and_status_success_without_new_observations_never_count_as_success(self):
        self.quote.delete();self.job.processed=4;self.job.status='succeeded';self.job.save()
        data=self.coverage()
        self.assertEqual(data['new_count'],0)
        self.assertEqual(data['state'],'no_new_quotes')
        self.assertEqual(data['historical_count'],3)
        self.assertEqual(data['items'][0]['coverage_state'],'unknown')

    def test_wrong_job_wrong_scan_wrong_url_and_invalid_currency_observations_excluded(self):
        self.quote.delete()
        other=StoreDiscovery.objects.create(url='https://other.example.com',status='succeeded')
        wrong=CatalogPriceObservation.objects.create(discovery=other,job=self.job,url=self.products[0]['url'],title='Wrong scan',price_low='99',price_high='99',currency='USD',observed_at=self.now)
        CatalogPriceObservation.objects.create(discovery=self.scan,job=self.job,url=ROOT+'/products/foreign',title='Wrong URL',price_low='99',price_high='99',currency='USD',observed_at=self.now)
        self.assertEqual(self.coverage()['new_count'],0)
        wrong.delete()
        CatalogPriceObservation.objects.create(discovery=self.scan,job=self.job,url=self.products[0]['url'],title='Bad currency',price_low='99',price_high='99',currency='???',observed_at=self.now)
        self.assertEqual(self.coverage()['new_count'],0)
        with self.assertRaises(ValueError):build_catalog_coverage(other,self.job)

    def test_old_or_naive_or_missing_attempt_timestamp_is_not_current_failure(self):
        for attempted in ((self.started-timedelta(days=1)).isoformat(), (self.finished+timedelta(seconds=1)).isoformat(), '2026-10-01T00:00:00', 'bad', None):
            self.scan.products[1]['price_attempted_at']=attempted
            data=self.coverage()
            self.assertEqual(data['failed_count'],1)
            self.assertEqual(data['items'][1]['coverage_state'],'unknown')
        self.job.started_at=None
        self.assertEqual(self.coverage()['failed_count'],0)

    def test_queued_running_stopped_states_do_not_claim_unattempted_requests(self):
        for status in ('queued','running','failed'):
            self.job.status=status
            data=self.coverage()
            self.assertEqual(data['active'],status!='failed')
            row=data['items'][3]
            self.assertNotIn('未请求',row['coverage_label'])
            self.assertEqual(row['coverage_state'],'unknown' if status=='failed' else 'pending')

    def test_complete_single_item_batch_is_not_full_store_and_zero_quote_is_real(self):
        self.job.indices=[0];self.job.status='succeeded';self.job.processed=1;self.job.total=1
        self.quote.price_low=Decimal('0');self.quote.price_high=Decimal('0');self.quote.save()
        data=self.coverage()
        self.assertEqual(data['state'],'completed')
        self.assertEqual(data['new_count'],1)
        self.assertEqual(data['not_scheduled_count'],4)
        self.assertEqual(data['items'][0]['price_low'],Decimal('0'))
        self.assertTrue(data['limited'])

    def test_no_price_job_directory_only_and_empty_directory_remain_different(self):
        data=build_catalog_coverage(self.scan)
        self.assertEqual(data['state'],'directory_only')
        self.assertEqual(data['new_count'],0)
        self.assertEqual(data['historical_count'],3)
        empty=StoreDiscovery.objects.create(url='https://empty.example.com',status='succeeded',finished_at=self.now)
        data=build_catalog_coverage(empty)
        self.assertEqual(data['state'],'empty')
        self.assertEqual(data['total_count'],0)
        self.assertEqual(data['directory_observed_at'],self.now)

    def test_missing_directory_observation_time_is_unknown_not_created_at(self):
        self.scan.finished_at=None
        data=self.coverage()
        self.assertIsNone(data['directory_observed_at'])
        self.assertIsNotNone(data['directory_created_at'])

    def test_invalid_indices_do_not_fabricate_scope_or_completed_quotes(self):
        for indices in ([False],[-1],[999],[0,0],{'unexpected':1}):
            self.job.indices=indices
            data=self.coverage()
            self.assertFalse(data['scope_known'])
            self.assertIsNone(data['planned_count'])
            self.assertEqual(data['new_count'],0)
            self.assertEqual(data['unresolved_count'],5)

    def test_empty_indices_default_first_ten_and_dedup_does_not_renumber_detail_links(self):
        scan=StoreDiscovery.objects.create(url='https://many.example.com',status='succeeded',products=[{'url':ROOT+'/products/'+str(i),'title':'Sample'} for i in range(15)])
        job=StorePriceJob.objects.create(discovery=scan,status='queued',indices=[])
        data=build_catalog_coverage(scan,job)
        self.assertEqual((data['planned_count'],data['not_scheduled_count']),(10,5))
        duplicate=deepcopy(self.products[0])
        self.scan.products=[{},duplicate,deepcopy(duplicate),self.products[4]]
        self.job.indices=[2]
        data=self.coverage()
        research=build_research(SimpleNamespace(url=self.scan.url,products=data['items']))
        self.assertEqual([row['catalog_index'] for row in research['products']],[1,3])
        self.assertEqual(data['total_count'],2)
        self.assertEqual(data['new_count'],1)
        self.assertEqual(data['not_scheduled_count'],1)

    def test_display_monetary_counts_and_distribution_match_coverage(self):
        data=self.coverage();research=build_research(SimpleNamespace(url=self.scan.url,products=data['items']))
        self.assertEqual(research['total_count'],data['total_count'])
        self.assertEqual(research['priced_count'],data['quoted_count'])
        self.assertEqual(sum(c['total'] for c in research['distribution']),data['quoted_count'])
        self.assertEqual({c['currency'] for c in research['distribution']},{'USD','EUR'})
        self.scan.refresh_from_db();self.assertEqual(self.scan.products,self.products)


class CatalogCoverageReportTests(CoverageFixture, TestCase):
    # Explicit report-only tests reuse controlled setup, not historical/private data.
    def setUp(self):
        super().setUp()
        self.user=get_user_model().objects.create_user('coverage-ordinary')
        self.client.force_login(self.user)
        self.report=reverse('store_research',args=[self.scan.pk])

    def test_report_partial_new_vs_retained_and_actual_source_are_visible_get_read_only(self):
        before=deepcopy(self.scan.products)
        with CaptureQueriesContext(connection) as captured:response=self.client.get(self.report)
        self.assertTrue(all(q['sql'].lstrip().upper().startswith('SELECT') for q in captured.captured_queries))
        self.assertContains(response,'本批取得部分报价')
        for text in ('目录已截断','沿用已保存报价','处理数不等于报价成功数','逐项结果未记录','重新获取店铺数据',ROOT,'USD 12.00','15.00','EUR 20','Current verified offer'):
            self.assertContains(response,text)
        self.assertContains(response,'站点地图更新时间不是上架日期')
        self.assertEqual(response.context['priced_count'],3)
        self.scan.refresh_from_db();self.assertEqual(self.scan.products,before)
        self.assertEqual(StorePriceJob.objects.count(),2)

    def test_filter_empty_error_empty_directory_and_unquoted_are_distinct(self):
        filtered=self.client.get(self.report,{'q':'there-is-no-match'})
        self.assertEqual(filtered.context['matched_count'],0)
        self.assertEqual(filtered.context['report_coverage']['total_count'],5)
        self.assertContains(filtered,'当前筛选没有匹配商品，不代表目录没有商品')
        invalid=self.client.get(self.report,{'price_min':'10'})
        self.assertContains(invalid,'筛选条件无效')
        self.assertEqual(invalid.context['report_coverage']['total_count'],5)
        self.scan.products=[dict(url=ROOT+'/products/no-price',title='Unquoted')];self.scan.save()
        self.job.delete();self.oldjob.delete()
        unquoted=self.client.get(self.report)
        self.assertEqual(unquoted.context['total_count'],1)
        self.assertEqual(unquoted.context['priced_count'],0)
        self.assertContains(unquoted,'1 件无有效报价')
        self.scan.products=[];self.scan.save()
        empty=self.client.get(self.report)
        self.assertContains(empty,'公开目录没有可识别商品链接，不代表店铺没有商品')

    def test_progress_json_counts_exact_quotes_and_redirects_to_partial_or_failed_report(self):
        url=reverse('store_analysis',args=[self.scan.pk])
        data=self.client.get(url,{'format':'json'}).json()
        self.assertEqual(data['coverage']['new_count'],1)
        self.assertEqual(data['coverage']['failed_count'],2)
        self.assertFalse(data['active'])
        self.assertEqual(data['redirect_url'],self.report)
        self.quote.delete()
        data=self.client.get(url,{'format':'json'}).json()
        self.assertEqual(data['coverage']['new_count'],0)
        self.assertEqual(data['redirect_url'],self.report)
        self.assertEqual(self.client.get(url).status_code,302)

    def test_active_refresh_has_progress_not_new_refresh_button(self):
        queued=StoreDiscovery.objects.create(url=ROOT,status='queued')
        response=self.client.get(self.report)
        self.assertContains(response,reverse('store_analysis',args=[queued.pk]))
        self.assertNotContains(response,'<button>重新获取店铺数据</button>')
        self.assertContains(response,'查看正在获取的店铺数据')
        queued.status='failed';queued.save()
        self.job.status='running';self.job.finished_at=None;self.job.save()
        response=self.client.get(self.report)
        self.assertNotContains(response,'<button>重新获取店铺数据</button>')
        self.assertEqual(response.context['refresh_progress_pk'],self.scan.pk)

    def test_refresh_post_csrf_active_reuse_failure_preserves_saved_report(self):
        secure=Client(enforce_csrf_checks=True);secure.force_login(self.user)
        response=secure.get(self.report)
        self.assertContains(response,'name="workflow" value="1"')
        self.assertEqual(secure.post(reverse('discover_store'),{'url':ROOT,'workflow':'1'}).status_code,403)
        token=secure.cookies['csrftoken'].value
        payload={'url':ROOT,'workflow':'1','csrfmiddlewaretoken':token}
        refresh=secure.post(reverse('discover_store'),payload)
        self.assertEqual(refresh.status_code,302)
        new=StoreDiscovery.objects.exclude(pk=self.scan.pk).get()
        self.assertEqual(new.status,'queued')
        repeated=secure.post(reverse('discover_store'),payload)
        self.assertEqual(repeated.url,refresh.url)
        self.assertEqual(StoreDiscovery.objects.count(),2)
        new.status='failed';new.message='Controlled refresh blocked';new.save()
        failure=secure.get(refresh.url)
        self.assertContains(failure,'Controlled refresh blocked')
        self.assertContains(failure,'查看上次保存的店铺报告')
        self.assertContains(failure,self.report)
        self.scan.refresh_from_db();self.assertEqual(self.scan.products,self.products)
        self.assertEqual(secure.get(self.report).status_code,200)

    def test_failed_refresh_without_history_empty_progress_and_anonymous_access(self):
        failed=StoreDiscovery.objects.create(url='https://blocked.example.com',status='failed',message='HTTP 403')
        page=reverse('store_analysis',args=[failed.pk])
        failure=self.client.get(page)
        self.assertContains(failure,'HTTP 403')
        self.assertNotContains(failure,'查看上次保存的店铺报告')
        empty=StoreDiscovery.objects.create(url='https://empty.example.com',status='succeeded',products=[])
        response=self.client.get(reverse('store_analysis',args=[empty.pk]))
        self.assertContains(response,'不代表店铺没有商品')
        self.client.logout()
        self.assertEqual(self.client.get(self.report).status_code,302)
        self.assertEqual(self.client.get(page,{'format':'json'}).status_code,302)

    def test_price_refresh_failure_links_back_to_previous_saved_directory(self):
        newer=StoreDiscovery.objects.create(url=ROOT,status='succeeded',products=[dict(url=self.products[0]['url'],title='Same product without new quote')],finished_at=self.now)
        StorePriceJob.objects.create(discovery=newer,status='failed',indices=[0],processed=0,total=1,started_at=self.started,finished_at=self.finished,message='HTTP 403 before callback')
        response=self.client.get(reverse('store_research',args=[newer.pk]))
        self.assertContains(response,'本批未取得新的有效报价')
        self.assertContains(response,'查看上次保存的店铺报告')
        self.assertContains(response,self.report)
        self.assertEqual(response.context['report_coverage']['unresolved_count'],1)
        self.assertEqual(response.context['total_count'],1)
        self.assertEqual(response.context['priced_count'],0)
        self.scan.refresh_from_db();self.assertEqual(self.scan.products,self.products)

    def test_invalid_saved_amount_does_not_render_nan_or_count_as_quoted(self):
        self.scan.products[4]['price_low']='NaN';self.scan.save()
        response=self.client.get(self.report)
        self.assertEqual(response.context['priced_count'],2)
        self.assertEqual(response.context['report_coverage']['quoted_count'],2)
        self.assertNotContains(response,'EUR NaN')
        self.assertNotContains(response,'EUR 0')
        self.assertContains(response,'无有效报价')
