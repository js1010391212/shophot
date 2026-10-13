"""Private successful scenarios, bounded signatures and immutable history."""
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
import os
import shutil
import subprocess
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, SimpleTestCase, Client
from django.urls import reverse
from django.utils import timezone
from .models import Product, Snapshot, ProfitStudyRecord
from .profit_studies import SALT, unpack, MAX_STATE, save_study
from .test_trial_budget import inputs
from . import test_profit_flow


class ProfitStudyTests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_user('study-owner')
        self.other=get_user_model().objects.create_user('study-other')
        self.user=self.owner
        self.client.force_login(self.owner)
        self.product=Product.objects.create(title='Controlled history',url='https://www.ebay.com/itm/123456789012',platform='eBay')
        self.quote=Snapshot.all_objects.create(product=self.product,owner=self.owner,source='browser',capture_id=uuid4(),price='30',currency='USD',observed_at=timezone.now(),capture_data={'price':'30.00','title':'Saved private title','sku_id':'blue','market_country':'US','conditions':['Coupon unknown tax']})
        self.profit=reverse('profit');self.save=reverse('profit_study_save')

    def token(self, **changes):
        data=inputs();data.update(assessment_enabled='on',assessment_costs_confirmed='on');data.update(changes)
        response=self.client.post(self.profit,data)
        self.assertIsNotNone(response.context['result'],response.context['form'].errors)
        self.assertIsNotNone(response.context['save_form'],response.context['save_error'])
        return response.context['save_form']['state'].value()

    def save_token(self, token, name='Research name',notes='Controlled note'):
        return self.client.post(self.save,dict(state=token,name=name,notes=notes))

    def test_valid_save_copies_exact_results_and_does_not_write_quotes(self):
        token=self.token(observation=self.quote.pk)
        response=self.save_token(token)
        self.assertEqual(response.status_code,302)
        row=ProfitStudyRecord.objects.get()
        self.assertEqual(row.owner,self.owner)
        self.assertEqual(row.snapshot,unpack(self.owner,token))
        snap=row.snapshot['scenario']
        self.assertEqual(snap['unit']['net'],'9.60');self.assertEqual(snap['trial']['net'],'152.00')
        self.assertEqual(snap['assessment']['status'],'meets_target')
        self.assertEqual(Snapshot.all_objects.count(),1)
        self.assertEqual(Product.objects.count(),1)
        detail=self.client.get(response.url)
        self.assertContains(detail,'Saved private title');self.assertContains(detail,'Coupon unknown tax')
        self.assertContains(detail,'历史情景');self.assertContains(detail,'单件采购成本')

    def test_blank_missing_and_explicit_zero_metadata_resume_as_empty(self):
        data=inputs();data.pop('trial_enabled')
        data.pop('ad_cost');data.update(other_cost='',payment_fee_rate='0',payment_fixed='',discount_rate='',target_margin='')
        response=self.client.post(self.profit,data)
        token=response.context['save_form']['state'].value()
        self.save_token(token);row=ProfitStudyRecord.objects.get();saved=row.snapshot['scenario']
        self.assertEqual(saved['optional_presence']['ad_cost'],'missing')
        self.assertEqual(saved['optional_presence']['other_cost'],'blank')
        self.assertEqual(saved['optional_presence']['payment_fee_rate'],'explicit')
        self.assertIn('ad_cost',saved['missing_optional']);self.assertNotIn('payment_fee_rate',saved['missing_optional'])
        get=self.client.get(self.profit,{'study':row.pk})
        for key in ('ad_cost','other_cost','payment_fixed','discount_rate','target_margin'):
            self.assertEqual(get.context['form'][key].value(),'')
        self.assertEqual(get.context['form']['payment_fee_rate'].value(),'0')
        self.assertIsNone(get.context['result'])
        self.assertEqual(ProfitStudyRecord.objects.count(),1)

    def test_signature_tamper_expiry_owner_and_length_rejected_without_writes(self):
        token=self.token()
        for bad in (token+'x','x'*(MAX_STATE+1),''):
            self.assertEqual(self.save_token(bad).status_code,400)
        with patch('django.core.signing.time.time',return_value=timezone.now().timestamp()+3601):
            self.assertEqual(self.save_token(token).status_code,400)
        self.client.force_login(self.other)
        self.assertEqual(self.save_token(token).status_code,400)
        self.assertFalse(ProfitStudyRecord.objects.exists())
        with patch('market.profit_studies.signing.loads',side_effect=AssertionError('must not decode')):
            with self.assertRaises(ValidationError):unpack(self.owner,'x'*(MAX_STATE+1))

    def test_signed_but_invalid_shape_and_version_rejected(self):
        original=unpack(self.owner,self.token())
        for change in ({'version':2},{'owner':True},{'nonce':'no'},{'scenario':{}},{'calculated_at':'not a timestamp'}):
            token=signing.dumps({**original,**change},salt=SALT)
            self.assertEqual(self.save_token(token).status_code,400)
        payload={**original,'scenario':{**original['scenario'],'inputs':{**original['scenario']['inputs'],'secret':'unexpected'}}}
        self.assertEqual(self.save_token(signing.dumps(payload,salt=SALT)).status_code,400)
        self.assertFalse(ProfitStudyRecord.objects.exists())

    def test_amount_owner_nonce_extra_post_is_ignored_not_merged(self):
        token=self.token();payload=unpack(self.owner,token)
        response=self.client.post(self.save,dict(state=token,name='A',notes='',net='999',owner=self.other.pk,nonce=str(uuid4())))
        self.assertEqual(response.status_code,302)
        row=ProfitStudyRecord.objects.get();self.assertEqual(row.snapshot,payload);self.assertEqual(row.owner,self.owner)

    def test_nonce_repeat_conflict_and_archived_repeat_never_overwrites_or_restores(self):
        token=self.token();first=self.save_token(token);row=ProfitStudyRecord.objects.get()
        self.assertEqual(self.save_token(token).url,first.url)
        self.assertEqual(self.save_token(token,name='Changed').status_code,400)
        self.assertEqual(self.save_token(token,notes='Changed').status_code,400)
        self.client.post(reverse('profit_study_toggle',args=[row.pk]),{'active':'0'})
        self.assertEqual(self.save_token(token).url,first.url)
        row.refresh_from_db();self.assertFalse(row.active);self.assertEqual(row.name,'Research name')
        self.assertEqual(ProfitStudyRecord.objects.count(),1)

    def test_name_notes_limits_error_correction_and_html_escape(self):
        token=self.token()
        for name,notes in [('', ''),('x'*121,''),('Valid','x'*1001)]:
            response=self.save_token(token,name,notes)
            self.assertEqual(response.status_code,400);self.assertContains(response,'这次测算未保存',status_code=400)
        self.assertFalse(ProfitStudyRecord.objects.exists())
        response=self.save_token(token,'<script>name</script>','<img src=x onerror=alert(1)>')
        detail=self.client.get(response.url)
        self.assertContains(detail,'&lt;script&gt;name&lt;/script&gt;');self.assertNotContains(detail,'<img src=x')

    def test_get_endpoints_do_not_create_and_save_and_toggle_require_post_csrf(self):
        self.assertEqual(self.client.get(self.save).status_code,405)
        self.client.get(reverse('profit_study_list'));self.client.get(self.profit)
        self.assertFalse(ProfitStudyRecord.objects.exists())
        csrf=Client(enforce_csrf_checks=True);csrf.force_login(self.owner)
        token=self.token()
        self.assertEqual(csrf.post(self.save,dict(state=token,name='A')).status_code,403)
        self.save_token(token);row=ProfitStudyRecord.objects.get()
        self.assertEqual(self.client.get(reverse('profit_study_toggle',args=[row.pk])).status_code,405)
        self.assertEqual(csrf.post(reverse('profit_study_toggle',args=[row.pk]),{'active':'0'}).status_code,403)
        row.refresh_from_db();self.assertTrue(row.active)

    def test_two_accounts_cannot_read_continue_archive_restore_or_list(self):
        self.save_token(self.token());row=ProfitStudyRecord.objects.get()
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse('profit_study_list')),'Research name')
        for path in (reverse('profit_study_detail',args=[row.pk]),self.profit+'?study='+str(row.pk)):
            self.assertEqual(self.client.get(path).status_code,404)
        for active in ('0','1'):
            self.assertEqual(self.client.post(reverse('profit_study_toggle',args=[row.pk]),{'active':active}).status_code,404)
        row.refresh_from_db();self.assertTrue(row.active)

    def test_source_changes_deleted_or_reassigned_before_save_rejected(self):
        token=self.token(observation=self.quote.pk)
        self.quote.capture_data={**self.quote.capture_data,'conditions':['Changed conditions']};self.quote.save()
        self.assertEqual(self.save_token(token).status_code,400)
        token=self.token(observation=self.quote.pk)
        self.quote.owner=self.other;self.quote.save()
        self.assertEqual(self.save_token(token).status_code,400)
        self.quote.delete();self.assertEqual(self.save_token(token).status_code,400)
        self.assertFalse(ProfitStudyRecord.objects.exists())

    def test_shipping_changed_or_archived_before_save_rejected(self):
        quote=test_profit_flow.ProfitFlowTests.quote(self)
        data=dict(shipping_mode='quote',shipping_quote='user:'+str(quote.pk),package_weight='1',package_units='1',fuel_rate='0',shipping_extra='0')
        token=self.token(**data)
        quote.notes='Changed contract';quote.save()
        self.assertEqual(self.save_token(token).status_code,400)
        token=self.token(**data)
        quote.active=False;quote.save()
        self.assertEqual(self.save_token(token).status_code,400)
        self.assertFalse(ProfitStudyRecord.objects.exists())

    def test_history_uses_saved_copy_after_source_reassignment_and_continuation_fails(self):
        self.save_token(self.token(observation=self.quote.pk));row=ProfitStudyRecord.objects.get();old=row.snapshot
        self.quote.owner=self.other;self.quote.capture_data={'title':'OTHER PRIVATE SECRET'};self.quote.save()
        detail=self.client.get(reverse('profit_study_detail',args=[row.pk]))
        self.assertContains(detail,'Saved private title');self.assertNotContains(detail,'OTHER PRIVATE SECRET')
        self.assertEqual(detail.context['source_link'],'')
        continued=self.client.get(self.profit,{'study':row.pk})
        self.assertEqual(continued.status_code,400)
        self.assertContains(continued,'原报价已不可访问',status_code=400)
        self.assertContains(continued,'name="study"',status_code=400)
        self.assertIsNone(continued.context['result'])
        row.refresh_from_db();self.assertEqual(row.snapshot,old)

    def test_continue_loads_assumptions_then_recalculates_without_modifying_record(self):
        self.save_token(self.token(observation=self.quote.pk));row=ProfitStudyRecord.objects.get();old=row.snapshot
        response=self.client.get(self.profit,{'study':row.pk})
        self.assertIsNone(response.context['result']);self.assertTrue(response.context['form']['trial_enabled'].value())
        data=inputs();data.update(study=row.pk,selling_price='40',assessment_enabled='on',assessment_costs_confirmed='on')
        response=self.client.post(self.profit,data,HTTP_HX_REQUEST='true')
        self.assertEqual(str(response.context['result']['net']),'18.30')
        self.assertContains(response,'name="study"');self.assertNotContains(response,'name="observation"')
        row.refresh_from_db();self.assertEqual(row.snapshot,old);self.assertEqual(ProfitStudyRecord.objects.count(),1)

    def test_duplicate_and_conflicting_study_parameters_rejected(self):
        self.save_token(self.token());row=ProfitStudyRecord.objects.get()
        for query in (f'study={row.pk}&study={row.pk}',f'study={row.pk}&observation={self.quote.pk}',
                      f'study={row.pk}&shipping_mode=manual','study=abc','study='+('9'*100)):
            self.assertEqual(self.client.get(self.profit+'?'+query).status_code,400)
        data=inputs();data.update(study=row.pk,observation=self.quote.pk)
        response=self.client.post(self.profit,data,HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code,400);self.assertIsNone(response.context['save_form'])

    def test_only_carrier_change_rejects_save_and_retains_historical_carrier(self):
        quote=test_profit_flow.ProfitFlowTests.quote(self)
        quote.carrier='Carrier A';quote.save()
        data=dict(shipping_mode='quote',shipping_quote='user:'+str(quote.pk),package_weight='1',package_units='1',fuel_rate='0',shipping_extra='0')
        token=self.token(**data)
        self.save_token(token);row=ProfitStudyRecord.objects.get();old=row.snapshot
        self.assertEqual(old['scenario']['shipping']['quote']['carrier'],'Carrier A')
        quote.carrier='Carrier B';quote.save()
        self.assertEqual(self.save_token(token).status_code,400)
        detail=self.client.get(reverse('profit_study_detail',args=[row.pk]))
        self.assertContains(detail,'承运商：Carrier A');self.assertNotContains(detail,'Carrier B')
        row.refresh_from_db();self.assertEqual(row.snapshot,old)
        self.assertEqual(ProfitStudyRecord.objects.count(),1)

    def test_preexisting_inconsistent_reference_allows_legacy_result_but_never_signs(self):
        self.quote.capture_data={**self.quote.capture_data,'price':'31.00'};self.quote.save()
        data=inputs();data['observation']=self.quote.pk
        response=self.client.post(self.profit,data,HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code,200)
        self.assertIsNotNone(response.context['result'])
        self.assertIsNone(response.context['save_form'])
        self.assertContains(response,'不能准确带入利润工具')
        self.assertContains(response,'不能保存为有效引用')
        self.assertContains(response,'重新选择报价，或重建无来源情景')
        self.assertNotContains(response,'name="state"')
        self.assertEqual(self.save_token('').status_code,400)
        self.assertFalse(ProfitStudyRecord.objects.exists())

    def test_issued_signature_revalidation_rejects_now_inconsistent_reference(self):
        token=self.token(observation=self.quote.pk)
        self.quote.capture_data={**self.quote.capture_data,'price':'31.00'};self.quote.save()
        response=self.save_token(token)
        self.assertEqual(response.status_code,400)
        self.assertContains(response,'不能保存为有效引用',status_code=400)
        self.assertFalse(ProfitStudyRecord.objects.exists())

    def test_manual_scenario_remains_savable_despite_unrelated_bad_quote(self):
        self.quote.capture_data={**self.quote.capture_data,'price':'31.00'};self.quote.save()
        token=self.token()
        response=self.save_token(token)
        self.assertEqual(response.status_code,302)
        self.assertIsNone(ProfitStudyRecord.objects.get().snapshot['scenario']['source'])

    def test_history_times_and_choice_labels_are_readable_saved_facts(self):
        quote=test_profit_flow.ProfitFlowTests.quote(self)
        data=dict(observation=self.quote.pk,shipping_mode='quote',shipping_quote='user:'+str(quote.pk),package_weight='1',package_units='1',fuel_rate='0',shipping_extra='0')
        self.save_token(self.token(**data));row=ProfitStudyRecord.objects.get()
        self.quote.owner=self.other;self.quote.save()
        quote.name='OTHER CURRENT SECRET';quote.save()
        response=self.client.get(reverse('profit_study_detail',args=[row.pk]))
        self.assertContains(response,'北京时间')
        from django.utils.dateparse import parse_datetime
        expected=timezone.localtime(parse_datetime(row.snapshot['calculated_at'])).strftime('%Y-%m-%d %H:%M:%S')
        observed=timezone.localtime(parse_datetime(row.snapshot['scenario']['source']['observed_at'])).strftime('%Y-%m-%d %H:%M:%S')
        self.assertContains(response,expected);self.assertContains(response,observed)
        self.assertContains(response,dict(Snapshot.Source.choices)['browser'])
        self.assertContains(response,'按物流报价估算');self.assertContains(response,'Controlled USD quote')
        self.assertNotContains(response,'OTHER CURRENT SECRET');self.assertNotContains(response,'user:'+str(quote.pk))
        self.assertNotContains(response,row.snapshot['calculated_at'])
        self.assertNotContains(response,row.snapshot['scenario']['source']['observed_at'])
        self.assertEqual(response.context['source_link'],'')

    def test_updated_public_quote_notice_keeps_old_assumptions_and_history(self):
        Snapshot.objects.create(product=self.product,price='30',currency='USD',source='manual',observed_at=timezone.now())
        self.save_token(self.token(product=self.product.pk));row=ProfitStudyRecord.objects.get();old=row.snapshot
        current=Snapshot.objects.create(product=self.product,price='45',currency='EUR',source='manual',observed_at=timezone.now())
        response=self.client.get(self.profit,{'study':row.pk})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'公共报价已更新，历史售价仍是假设，请重新核对')
        self.assertEqual(response.context['form']['selling_price'].value(),'30')
        self.assertEqual(response.context['form']['sale_currency'].value(),'USD')
        self.assertEqual(response.context['quote_reference']['snapshot'].pk,current.pk)
        self.assertIsNone(response.context['result']);self.assertIsNone(response.context['save_form'])
        self.assertEqual(response.context['reference_error'],'')
        row.refresh_from_db();self.assertEqual(row.snapshot,old)
        self.assertEqual(ProfitStudyRecord.objects.count(),1)

    def test_deleted_last_public_quote_cannot_fall_back_to_manual_when_continuing(self):
        public=Snapshot.objects.create(product=self.product,price='30',currency='USD',source='manual',observed_at=timezone.now())
        self.save_token(self.token(product=self.product.pk));row=ProfitStudyRecord.objects.get();old=row.snapshot
        public.delete()
        counts=(ProfitStudyRecord.objects.count(),Product.objects.count(),Snapshot.all_objects.count())
        get=self.client.get(self.profit,{'study':row.pk})
        data=inputs();data.update(study=row.pk)
        post=self.client.post(self.profit,data,HTTP_HX_REQUEST='true')
        for response in (get,post):
            self.assertEqual(response.status_code,400)
            self.assertContains(response,'原报价已不可访问',status_code=400)
            self.assertIsNone(response.context['result']);self.assertIsNone(response.context['save_form'])
            self.assertContains(response,'name="study"',status_code=400)
        self.assertEqual(post.headers['X-ShopHot-Profit-Workspace-Error'],'1')
        detail=self.client.get(reverse('profit_study_detail',args=[row.pk]))
        self.assertEqual(detail.status_code,200);self.assertEqual(detail.context['source_link'],'')
        self.assertContains(detail,'原来源目前不可访问')
        row.refresh_from_db();self.assertEqual(row.snapshot,old)
        self.assertEqual(counts,(ProfitStudyRecord.objects.count(),Product.objects.count(),Snapshot.all_objects.count()))

    def test_nonce_database_constraint_applies_even_when_archived(self):
        self.save_token(self.token());row=ProfitStudyRecord.objects.get()
        row.active=False;row.save(update_fields=['active'])
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProfitStudyRecord.objects.create(owner=self.owner,nonce=row.nonce,request_fingerprint='other',name='Other',snapshot={})
        self.assertEqual(ProfitStudyRecord.objects.count(),1)
        ProfitStudyRecord.objects.create(owner=self.other,nonce=row.nonce,request_fingerprint='other',name='Other',snapshot={})
        self.assertEqual(ProfitStudyRecord.objects.count(),2)

    def test_invalid_calculation_never_offers_signed_save_state(self):
        data=inputs();data['cost']='bad'
        response=self.client.post(self.profit,data,HTTP_HX_REQUEST='true')
        self.assertIsNone(response.context['result']);self.assertIsNone(response.context['save_form'])
        self.assertNotContains(response,'name="state"')

    def test_expired_logistics_continue_keeps_quote_mode_and_requires_reselection(self):
        quote=test_profit_flow.ProfitFlowTests.quote(self)
        token=self.token(shipping_mode='quote',shipping_quote='user:'+str(quote.pk),package_weight='1',package_units='1',fuel_rate='0',shipping_extra='0')
        self.save_token(token);row=ProfitStudyRecord.objects.get()
        quote.active=False;quote.save()
        get=self.client.get(self.profit,{'study':row.pk})
        self.assertEqual(get.context['form']['shipping_mode'].value(),'quote')
        self.assertContains(get,'原物流引用已不可用')
        data=inputs();data.update(study=row.pk,shipping_mode='quote',shipping_quote='user:'+str(quote.pk),package_weight='1',package_units='1',fuel_rate='0',shipping_extra='0')
        post=self.client.post(self.profit,data,HTTP_HX_REQUEST='true')
        self.assertIsNone(post.context['result']);self.assertIsNone(post.context['save_form'])
        self.assertEqual(ProfitStudyRecord.objects.count(),1)

    def test_raw_source_price_changed_without_db_price_also_rejected(self):
        token=self.token(observation=self.quote.pk)
        self.quote.capture_data={**self.quote.capture_data,'price':'29.99'};self.quote.save()
        self.assertEqual(self.save_token(token).status_code,400)
        self.assertFalse(ProfitStudyRecord.objects.exists())

    def test_list_search_pagination_errors_empty_and_archive_restore(self):
        self.assertContains(self.client.get(reverse('profit_study_list')),'暂无匹配')
        for index in range(21):
            ProfitStudyRecord.objects.create(owner=self.owner,nonce=uuid4(),request_fingerprint=str(index),name='Search row '+str(index),notes='find me',snapshot={})
        response=self.client.get(reverse('profit_study_list'),{'q':'find me','page':'2'})
        self.assertEqual(len(response.context['page']),1);self.assertContains(response,'上一页')
        self.assertContains(self.client.get(reverse('profit_study_list'),{'q':'x'*121}),'筛选条件无效')
        ProfitStudyRecord.objects.all().delete()
        self.save_token(self.token());row=ProfitStudyRecord.objects.get();old=row.snapshot
        url=reverse('profit_study_toggle',args=[row.pk])
        self.assertEqual(self.client.post(url,{'active':'invalid'}).status_code,400)
        self.client.post(url,{'active':'0'});self.assertNotContains(self.client.get(reverse('profit_study_list')),'Research name')
        self.assertContains(self.client.get(reverse('profit_study_list'),{'archived':'on'}),'Research name')
        self.client.post(url,{'active':'1'});row.refresh_from_db();self.assertTrue(row.active);self.assertEqual(row.snapshot,old)


class ProfitStudyScriptTests(SimpleTestCase):
    def test_actual_script_invalidates_only_main_inputs_not_save_notes(self):
        node=os.environ.get('SHOPHOT_NODE_BIN') or shutil.which('node')
        if not node:self.skipTest('Node required for script test')
        script=r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const callbacks={},fields={disabled:false},notice={hidden:true};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{document:{addEventListener:(n,f)=>callbacks[n]=f,getElementById:id=>id==='profit-study-save-fields'?fields:notice}});
for(const kind of ['input','change']){
 fields.disabled=false;notice.hidden=true;callbacks[kind]({target:{closest:()=>null}});assert.equal(fields.disabled,false);assert.equal(notice.hidden,true);
 callbacks[kind]({target:{closest:()=>({id:'profit-form'})}});assert.equal(fields.disabled,true);assert.equal(notice.hidden,false);
}
"""
        result=subprocess.run([node,'-e',script,str(Path(__file__).parent/'static'/'market'/'profit_studies.js')],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


# PostgreSQL-only contract. SQLite cannot prove row-lock concurrency.
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, skipUnlessDBFeature
from .profit import calculate_profit
from .trial_budget import calculate_trial_budget
from .selection_assessment_forms import SelectionAssessmentProfitForm
from .profit_studies import signed_state


class ProfitStudyConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_user('study-concurrent-owner')
        form=SelectionAssessmentProfitForm(inputs(),user=self.owner)
        self.assertTrue(form.is_valid(),form.errors)
        result=calculate_profit(form.cleaned_data)
        self.state=signed_state(self.owner,form,result,calculate_trial_budget(result,form.cleaned_data),None,None)

    def concurrent(self,names):
        gate=Barrier(2)
        def submit(name):
            close_old_connections()
            try:
                owner=get_user_model().objects.get(pk=self.owner.pk)
                gate.wait(timeout=10)
                try:return ('saved',save_study(owner,self.state,name,'').pk)
                except ValidationError:return ('conflict',None)
            finally:connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(submit,name) for name in names]
            return [future.result(timeout=20) for future in futures]

    @skipUnlessDBFeature('has_select_for_update')
    def test_concurrent_same_nonce_identical_content_creates_one_record(self):
        results=self.concurrent(('Same','Same'))
        self.assertEqual(results[0],results[1]);self.assertEqual(results[0][0],'saved')
        self.assertEqual(ProfitStudyRecord.objects.count(),1)

    @skipUnlessDBFeature('has_select_for_update')
    def test_concurrent_same_nonce_conflicting_content_never_overwrites(self):
        results=self.concurrent(('First','Second'))
        self.assertEqual(sorted(status for status,_ in results),['conflict','saved'])
        self.assertEqual(ProfitStudyRecord.objects.count(),1)
        self.assertIn(ProfitStudyRecord.objects.get().name,('First','Second'))
