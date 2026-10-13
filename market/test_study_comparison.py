"""Historical Decimal comparisons, bounded owner reads and invalid envelopes."""
from copy import deepcopy
from decimal import Decimal as D
from uuid import uuid4
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, RequestFactory
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse,resolve
from django.utils import timezone
from .models import ProfitStudyRecord,Product,Snapshot
from .profit import calculate_profit
from .trial_budget import calculate_trial_budget
from .selection_assessment import assess_selection
from .selection_assessment_forms import SelectionAssessmentProfitForm
from .profit_studies import signed_state,unpack
from .test_trial_budget import inputs
from .study_comparison import read_history,compare_histories,choice_rows
from .study_comparison_views import comparison


class StudyComparisonTests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_user('compare-owner')
        self.other=get_user_model().objects.create_user('compare-other')
        self.client.force_login(self.owner);self.url=reverse('study_comparison')
        self.a=self.record('Scenario A')
        self.b=self.record('Scenario B',other_cost='2')

    def record(self,name,owner=None,reference=None,**changes):
        owner=owner or self.owner
        data=inputs();data.update(assessment_enabled='on',assessment_costs_confirmed='on');data.update(changes)
        form=SelectionAssessmentProfitForm(data,user=owner);self.assertTrue(form.is_valid(),form.errors)
        unit=calculate_profit(form.cleaned_data)
        trial=calculate_trial_budget(unit,form.cleaned_data) if form.cleaned_data['trial_enabled'] else None
        assessment=assess_selection(unit,form.cleaned_data,trial,reference) if form.cleaned_data['assessment_enabled'] else None
        payload=unpack(owner,signed_state(owner,form,unit,trial,assessment,reference))
        return ProfitStudyRecord.objects.create(owner=owner,name=name,notes='',nonce=payload['nonce'],snapshot=payload,request_fingerprint='fixture')

    def get(self,left=None,right=None,**params):
        return self.client.get(self.url,{'left':left or self.a.pk,'right':right or self.b.pk,**params})

    def test_same_scope_uses_saved_decimal_unit_and_batch_differences(self):
        response=self.get();self.assertEqual(response.status_code,200)
        result=response.context['result']
        self.assertFalse(result['unit_reasons']);self.assertFalse(result['batch_reasons'])
        unit={row['label']:row['difference'] for row in result['unit_rows']}
        batch={row['label']:row['difference'] for row in result['batch_rows']}
        self.assertEqual(unit['其他成本'],D('1.00'));self.assertEqual(unit['单件净利'],D('-1.00'))
        self.assertEqual(batch['基础准备资金'],D('20.00'));self.assertEqual(batch['全部售出净利'],D('-20.00'))
        self.assertContains(response,'差额 = B − A');self.assertContains(response,'不代表谁更适合销售')
        reversed_response=self.get(self.b.pk,self.a.pk)
        self.assertEqual(reversed_response.context['histories'][0]['record'].pk,self.b.pk)
        reverse_net=next(row['difference'] for row in reversed_response.context['result']['unit_rows'] if row['label']=='单件净利')
        self.assertEqual(reverse_net,D('1.00'))

    def test_distinct_cost_or_sale_currency_withholds_every_difference(self):
        for changes,reason in [(dict(cost_currency='CNY',exchange_rate='7'),'成本币种不同'),(dict(sale_currency='EUR',exchange_rate='1'),'售价币种不同')]:
            row=self.record('Different',**changes)
            response=self.get(right=row.pk);result=response.context['result']
            self.assertIn(reason,result['unit_reasons'])
            self.assertTrue(all(item['difference'] is None for item in result['unit_rows']))
            self.assertTrue(all(item['difference'] is None for item in result['batch_rows']))
            self.assertContains(response,'不换汇或归一化')

    def test_same_currency_but_distinct_rates_is_not_a_shared_scope(self):
        a=self.record('FX7',cost_currency='CNY',exchange_rate='7')
        b=self.record('FX8',cost_currency='CNY',exchange_rate='8')
        result=self.get(a.pk,b.pk).context['result']
        self.assertEqual(result['unit_reasons'],['实际汇率不同'])
        self.assertTrue(all(row['difference'] is None for row in result['unit_rows']))

    def test_distinct_quantity_keeps_unit_difference_but_not_batch(self):
        row=self.record('Five',trial_quantity='5')
        result=self.get(right=row.pk).context['result']
        self.assertFalse(result['unit_reasons']);self.assertEqual(result['batch_reasons'],['批次数量不同'])
        self.assertTrue(all(row['difference'] is None for row in result['batch_rows']))

    def test_unenabled_budget_has_no_batch_normalization(self):
        row=self.record('No budget',trial_enabled='false')
        result=self.get(right=row.pk).context['result']
        self.assertEqual(result['batch_reasons'],['至少一份未启用测品预算'])
        self.assertEqual(result['batch_rows'],[])

    def test_missing_optional_and_unconfirmed_costs_remain_prominent(self):
        row=self.record('Unknown costs',trial_enabled='false',assessment_enabled='false',assessment_costs_confirmed='false',ad_cost='',other_cost='',payment_fee_rate='',payment_fixed='')
        response=self.get(right=row.pk)
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'成本和费率未核对')
        self.assertContains(response,'存在未填写的可选费用')
        self.assertContains(response,'未启用历史选品判断')
        self.assertEqual(response.context['histories'][1]['missing'],['ad_cost','other_cost','payment_fee_rate','payment_fixed'])
        self.assertNotContains(response,'赢家')

    def test_choice_reads_are_limited_to_metadata_and_latest_hundred(self):
        for i in range(105):
            ProfitStudyRecord.objects.create(owner=self.owner,name='Recent '+str(i),nonce=uuid4(),snapshot={},request_fingerprint='fixture')
        foreign=self.record('FOREIGN NAME',owner=self.other)
        with CaptureQueriesContext(connection) as queries:rows=choice_rows(self.owner)
        self.assertEqual(len(rows),100);self.assertEqual(len(queries),1)
        self.assertNotIn('snapshot',queries[0]['sql'].lower())
        self.assertIn('LIMIT 100',queries[0]['sql'])
        self.assertNotIn(foreign.pk,[row['pk'] for row in rows])
        self.assertEqual(set(rows[0]),{'pk','name','created_at'})

    def test_request_has_only_two_bounded_selects_for_manual_histories_and_no_writes(self):
        request=RequestFactory().get(self.url,{'left':self.a.pk,'right':self.b.pk});request.user=self.owner
        request.resolver_match=resolve(self.url)
        before=(ProfitStudyRecord.objects.count(),Product.objects.count(),Snapshot.all_objects.count())
        with CaptureQueriesContext(connection) as queries:
            response=comparison(request)
        self.assertEqual(response.status_code,200);self.assertEqual(len(queries),2)
        self.assertTrue(all(row['sql'].lstrip().upper().startswith('SELECT') for row in queries))
        self.assertIn('LIMIT 2',queries[1]['sql'])
        self.assertEqual(before,(ProfitStudyRecord.objects.count(),Product.objects.count(),Snapshot.all_objects.count()))

    def test_no_platform_freight_or_profit_recalculation(self):
        with patch('market.profit.calculate_profit',side_effect=AssertionError('No recalculation')),patch('market.shipping.estimate',side_effect=AssertionError('No freight')):
            self.assertEqual(self.get().status_code,200)

    def test_anonymous_redirect_and_post_rejected(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code,302)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(self.url,{'left':self.a.pk,'right':self.b.pk}).status_code,405)

    def test_duplicate_extra_blank_huge_or_non_ascii_ids_fail_clearly(self):
        for query in (f'left={self.a.pk}&right={self.b.pk}&left={self.a.pk}',f'left={self.a.pk}&right={self.a.pk}',
                      f'left={self.a.pk}&right={self.b.pk}&third=1',f'left={self.a.pk}',
                      'left=0&right=1','left=-1&right=2','left=１&right=2',
                      'left='+('9'*2000)+'&right=2','left=9223372036854775808&right=2'):
            response=self.client.get(self.url+'?'+query)
            self.assertEqual(response.status_code,400)
            self.assertIsNone(response.context['result'])
        self.assertEqual(self.client.get(self.url).status_code,200)

    def test_other_owner_and_archived_records_cannot_be_selected_or_shown(self):
        foreign=self.record('FOREIGN PRIVATE',owner=self.other)
        response=self.get(right=foreign.pk);self.assertEqual(response.status_code,400)
        self.assertNotContains(response,'FOREIGN PRIVATE',status_code=400)
        self.b.active=False;self.b.save(update_fields=['active'])
        response=self.get();self.assertEqual(response.status_code,400)
        self.assertIsNone(response.context['result'])

    def test_zero_and_one_record_offer_existing_start_and_continue_paths(self):
        self.a.delete();self.b.delete()
        empty=self.client.get(self.url)
        self.assertContains(empty,'还没有可选的研究记录')
        self.assertContains(empty,'建立测算情景')
        self.assertNotContains(empty,'比较两份记录')
        self.assertNotContains(empty,'name="left"')
        invalid=self.client.get(self.url,{'left':'1','right':'2'})
        self.assertEqual(invalid.status_code,400)
        self.assertContains(invalid,'选择无效',status_code=400)
        self.assertNotContains(invalid,'检查上方',status_code=400)
        row=self.record('Only')
        response=self.client.get(self.url)
        self.assertContains(response,'还需要第二份研究记录')
        self.assertContains(response,reverse('profit')+'?study='+str(row.pk))
        self.assertContains(response,'Only')
        self.assertContains(response,'class="button" href="'+reverse('profit')+'?study='+str(row.pk)+'"')
        self.assertNotContains(response,'比较两份记录')
        self.assertNotContains(response,'name="right"')
        invalid=self.client.get(self.url,{'left':row.pk,'right':row.pk})
        self.assertEqual(invalid.status_code,400)
        self.assertContains(invalid,'选择无效',status_code=400)

    def test_unknown_version_and_bad_fields_are_visible_errors_not_500(self):
        original=deepcopy(self.b.snapshot)
        changes=[]
        future=deepcopy(original);future['version']=2;changes.append(future)
        missing=deepcopy(original);del missing['scenario']['unit']['net'];changes.append(missing)
        shape=deepcopy(original);shape['scenario']['unit']['costs']={'采购成本':'10'};changes.append(shape)
        invalid_currency=deepcopy(original);invalid_currency['scenario']['unit']['cost_currency']='usd';changes.append(invalid_currency)
        absent_source=deepcopy(original);absent_source['scenario']['source']={};changes.append(absent_source)
        quantity=deepcopy(original);quantity['scenario']['trial']['quantity']=True;changes.append(quantity)
        fx=deepcopy(original);fx['scenario']['unit']['rate']='2';changes.append(fx)
        absent_cost=deepcopy(original);absent_cost['scenario']['inputs']['cost']=None;changes.append(absent_cost)
        for payload in changes:
            self.b.snapshot=payload;self.b.save(update_fields=['snapshot'])
            response=self.get();self.assertEqual(response.status_code,400)
            self.assertContains(response,'暂不可比较',status_code=400)
            self.assertIsNone(response.context['result'])
        self.b.snapshot=original;self.b.save(update_fields=['snapshot'])
        self.assertEqual(self.get().status_code,200)

    def test_nonfinite_wrong_type_precision_or_negative_costs_rejected(self):
        original=deepcopy(self.b.snapshot)
        for bad in ('NaN','Infinity','-Infinity','1e3','0.001',1.25,None,True,'9'*200):
            payload=deepcopy(original);payload['scenario']['unit']['net']=bad
            self.b.snapshot=payload;self.b.save(update_fields=['snapshot'])
            self.assertEqual(self.get().status_code,400)
        payload=deepcopy(original);payload['scenario']['unit']['costs'][0][1]='-1'
        self.b.snapshot=payload;self.b.save(update_fields=['snapshot'])
        self.assertEqual(self.get().status_code,400)

    def test_source_history_unchanged_after_transfer_and_no_other_current_details(self):
        product=Product.objects.create(title='Original product',platform='eBay',url='https://www.ebay.com/itm/123456789012')
        quote=Snapshot.all_objects.create(owner=self.owner,product=product,source='browser',capture_id=uuid4(),price='30',currency='USD',observed_at=timezone.now(),capture_data={'price':'30.00','title':'Saved source title','sku_id':'blue','market_country':'US','conditions':['Saved coupon']})
        quote.refresh_from_db()
        reference=dict(kind='observation',id=quote.pk,snapshot=quote,product=product,data=quote.capture_data)
        row=self.record('With source',reference=reference)
        old=deepcopy(row.snapshot)
        quote.owner=self.other;quote.capture_data={'title':'OTHER CURRENT SECRET'};quote.save()
        response=self.get(right=row.pk)
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'Saved source title');self.assertContains(response,'Saved coupon')
        self.assertNotContains(response,'OTHER CURRENT SECRET')
        self.assertContains(response,'当前来源不可访问')
        self.assertEqual(response.context['histories'][1]['source_link'],'')
        row.refresh_from_db();self.assertEqual(row.snapshot,old)

    def test_names_and_source_conditions_are_escaped(self):
        self.b.name='<script>name</script>';self.b.save(update_fields=['name'])
        response=self.get()
        self.assertContains(response,'&lt;script&gt;name&lt;/script&gt;');self.assertNotContains(response,'<script>name</script>')

    def test_missing_cost_rows_are_unknown_and_have_no_confirmed_differences(self):
        row=self.record('Unknown',trial_enabled='false',assessment_enabled='false',ad_cost='',other_cost='',payment_fee_rate='',payment_fixed='')
        response=self.get(right=row.pk)
        rows={item['label']:item for item in response.context['result']['unit_rows']}
        for label in ('广告成本','其他成本','支付费用'):
            self.assertTrue(rows[label]['right_unknown']);self.assertIsNone(rows[label]['difference'])
        self.assertContains(response,'未知（历史计算按')
        self.assertContains(response,'合计和净利差额仍仅是历史假设差')

    def test_equivalent_decimal_rates_old_history_and_cost_pair_order(self):
        a=self.record('FX',cost_currency='CNY',exchange_rate='7')
        b=self.record('Same FX',cost_currency='CNY',exchange_rate='7')
        b.snapshot['scenario']['unit']['rate']='7.00'
        b.snapshot['scenario']['inputs']['exchange_rate']='7.0'
        b.snapshot['calculated_at']='2026-01-01T12:00:00+00:00'
        b.snapshot['scenario']['unit']['costs'].reverse();b.save(update_fields=['snapshot'])
        response=self.get(a.pk,b.pk)
        self.assertEqual(response.status_code,200);self.assertFalse(response.context['result']['unit_reasons'])
        self.assertTrue(all(item['difference']==D('0') for item in response.context['result']['unit_rows']))

    def test_duplicate_cost_labels_bad_assessment_and_nonfinite_batch_rejected(self):
        original=deepcopy(self.b.snapshot)
        for kind in ('duplicate','required_net','batch'):
            payload=deepcopy(original)
            if kind=='duplicate':payload['scenario']['unit']['costs'][1]=deepcopy(payload['scenario']['unit']['costs'][0])
            if kind=='required_net':payload['scenario']['assessment']['required_net']='NaN'
            if kind=='batch':payload['scenario']['trial']['prepared']='1e1000000'
            self.b.snapshot=payload;self.b.save(update_fields=['snapshot'])
            self.assertEqual(self.get().status_code,400)

    def test_large_saved_amounts_and_fractional_required_net_are_not_rounded(self):
        from decimal import localcontext
        a=read_history(self.a);b=read_history(self.b)
        a['batch']['prepared']=D('99999999999999999999.98')
        b['batch']['prepared']=D('99999999999999999999.99')
        with localcontext() as context:
            context.prec=6
            result=compare_histories(a,b)
        prepared=next(row for row in result['batch_rows'] if row['label']=='基础准备资金')
        self.assertEqual(prepared['difference'],D('.01'))
        large=self.record('Actual large saved scenario',selling_price='9999999999.99',cost_currency='CNY',exchange_rate='999999.999999',trial_quantity='10000')
        response=self.get(right=large.pk)
        self.assertEqual(response.status_code,200)
        history=response.context['histories'][1]
        self.assertGreaterEqual(history['values']['revenue'],D('1000000000000000'))
        self.assertGreaterEqual(history['batch']['revenue'],D('10000000000000000000'))
        fractional=self.record('Actual fractional target',selling_price='200.01',target_margin='20')
        self.assertEqual(fractional.snapshot['scenario']['assessment']['required_net'],'40.002')
        self.assertEqual(self.get(right=fractional.pk).status_code,200)

    def test_actual_saved_twenty_one_digit_batch_expenses_remain_comparable(self):
        from .profit_studies import save_study
        data=inputs();data.update(selling_price='9999999999.99',cost_currency='CNY',exchange_rate='999999.999999',
            trial_quantity='10000',fee_rate='100',payment_fee_rate='0',cost='9999999999.99',shipping='9999999999.99',
            ad_cost='9999999999.99',other_cost='9999999999.99',assessment_enabled='on',assessment_costs_confirmed='on')
        form=SelectionAssessmentProfitForm(data,user=self.owner);self.assertTrue(form.is_valid(),form.errors)
        unit=calculate_profit(form.cleaned_data)
        trial=calculate_trial_budget(unit,form.cleaned_data)
        assessment=assess_selection(unit,form.cleaned_data,trial,None)
        token=signed_state(self.owner,form,unit,trial,assessment,None)
        row=save_study(self.owner,token,'Actual saved max-cost case','')
        self.assertEqual(row.snapshot['scenario']['unit']['expenses'],'10000039999980000.46')
        self.assertEqual(row.snapshot['scenario']['trial']['expenses'],'100000399999800004640.00')
        history=read_history(row)
        self.assertEqual(history['batch']['expenses'],D('100000399999800004640.00'))
        twin=save_study(self.owner,signed_state(self.owner,form,unit,trial,assessment,None),'Actual saved second max-cost case','')
        response=self.get(left=row.pk,right=twin.pk)
        self.assertEqual(response.status_code,200)
        self.assertFalse(response.context['result']['batch_reasons'])
        self.assertTrue(all(item['difference']==D('0') for item in response.context['result']['batch_rows']))

    def test_times_that_overflow_beijing_display_return_400_before_rendering(self):
        original=deepcopy(self.b.snapshot)
        self.b.snapshot['calculated_at']='9999-12-31T23:59:59+00:00';self.b.save(update_fields=['snapshot'])
        response=self.get()
        self.assertEqual(response.status_code,400);self.assertContains(response,'暂不可比较',status_code=400)
        self.assertIsNone(response.context['result'])
        self.b.snapshot=original;self.b.save(update_fields=['snapshot'])
        product=Product.objects.create(title='Time source',platform='eBay',url='https://www.ebay.com/itm/123456789012')
        quote=Snapshot.all_objects.create(owner=self.owner,product=product,source='browser',capture_id=uuid4(),price='30',currency='USD',observed_at=timezone.now(),capture_data={'price':'30.00','title':'Time source','conditions':[]})
        quote.refresh_from_db()
        reference=dict(kind='observation',id=quote.pk,snapshot=quote,product=product,data=quote.capture_data)
        row=self.record('Bad observed time',reference=reference)
        row.snapshot['scenario']['source']['observed_at']='9999-12-31T23:59:59+00:00';row.save(update_fields=['snapshot'])
        response=self.get(right=row.pk)
        self.assertEqual(response.status_code,400);self.assertContains(response,'暂不可比较',status_code=400)
        self.assertIsNone(response.context['result'])

    def test_enabled_budget_requires_all_once_and_reserve_input_amounts(self):
        original=deepcopy(self.b.snapshot)
        for field in ('trial_sample_cost','trial_setup_cost','trial_compliance_cost','trial_reserve_cost'):
            for bad in (None,'','NaN','-1'):
                payload=deepcopy(original);payload['scenario']['inputs'][field]=bad
                self.b.snapshot=payload;self.b.save(update_fields=['snapshot'])
                response=self.get()
                self.assertEqual(response.status_code,400)
                self.assertIsNone(response.context['result'])
        self.b.snapshot=original;self.b.save(update_fields=['snapshot'])
        self.assertEqual(self.get().status_code,200)

    def test_enabled_features_reject_missing_explicit_fee_metadata(self):
        trial_only=self.record('Trial only',assessment_enabled='false',assessment_costs_confirmed='false')
        assessment_only=self.record('Assessment only',trial_enabled='false')
        for row,fields in [(trial_only,('ad_cost','other_cost','payment_fee_rate','payment_fixed')),
                           (assessment_only,('ad_cost','other_cost','payment_fee_rate','payment_fixed','discount_rate','target_margin'))]:
            original=deepcopy(row.snapshot)
            for field in fields:
                for presence in ('missing','blank'):
                    payload=deepcopy(original)
                    payload['scenario']['inputs'][field]=''
                    payload['scenario']['optional_presence'][field]=presence
                    payload['scenario']['missing_optional'].append(field)
                    row.snapshot=payload;row.save(update_fields=['snapshot'])
                    response=self.get(right=row.pk)
                    self.assertEqual(response.status_code,400)
                    self.assertIsNone(response.context['result'])
            row.snapshot=original;row.save(update_fields=['snapshot'])
        legacy=self.record('Legacy unknown',trial_enabled='false',assessment_enabled='false',ad_cost='',other_cost='',payment_fee_rate='',payment_fixed='',discount_rate='',target_margin='')
        response=self.get(right=legacy.pk)
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'存在未填写的可选费用')

    def test_unit_scope_mismatch_never_compares(self):
        a=read_history(self.a);b=read_history(self.b);b['scope']='Different order assumption'
        result=compare_histories(a,b)
        self.assertIn('单位口径不同',result['unit_reasons'])
        self.assertTrue(all(row['difference'] is None for row in result['unit_rows']))
