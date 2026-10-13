"""Cost-only decisions and the optional profit workspace lifecycle."""
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import os
import shutil
import subprocess

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Product, Snapshot
from .selection_assessment import assess_selection
from .selection_assessment_forms import SelectionAssessmentProfitForm, ASSESSMENT_EXPLICIT_FIELDS
from .test_trial_budget import inputs
from . import test_profit_flow


def scenario(**changes):
    data = inputs()
    data.pop('trial_enabled')
    data.update(assessment_enabled='on', assessment_costs_confirmed='on')
    data.update(changes)
    return data


class AssessmentMathTests(SimpleTestCase):
    def assess(self, revenue='100', net='20', target='20', confirmed=True, trial=None, reference=None, **changes):
        result = dict(revenue=D(revenue), net=D(net), cost_currency='USD', margin=D('20.00'), target_price=D('999'))
        data = dict(target_margin=D(target), assessment_costs_confirmed=confirmed,
                    selling_price=D('30'), sale_currency='USD')
        data.update(changes)
        return assess_selection(result, data, trial, reference)

    def test_unconfirmed_has_priority_over_zero_or_profitable_scenarios(self):
        for revenue, net in [('0','0'), ('100','-1'), ('100','50')]:
            self.assertEqual(self.assess(revenue,net,confirmed=False)['status'],'unconfirmed')

    def test_zero_revenue_loss_and_zero_net_have_specific_reasons(self):
        for revenue,net,reason in [('0','0','收入为 0'), ('100','-1','单件亏损'), ('100','0','没有利润缓冲')]:
            r=self.assess(revenue,net)
            self.assertEqual(r['status'],'adjust');self.assertTrue(any(reason in s for s in r['reasons']))

    def test_raw_decimal_boundary_not_rounded_margin_or_recommended_price(self):
        # 1/3 => displayed 33.33%; target33.33 passes, target33.34 fails.
        self.assertEqual(self.assess('3','1','33.33')['status'],'meets_target')
        self.assertEqual(self.assess('3','1','33.34')['status'],'below_target')
        # Actual margin19.996%, displays20.00 but does not reach20%.
        self.assertEqual(self.assess('2500','499.90','20')['status'],'below_target')
        self.assertEqual(self.assess('2500','500','20')['status'],'meets_target')

    def test_target_zero_still_requires_positive_net(self):
        self.assertEqual(self.assess(net='0',target='0')['status'],'adjust')
        self.assertEqual(self.assess(net='.01',target='0')['status'],'meets_target')

    def test_budget_shortfall_zero_buffer_and_recovery_beyond_quantity(self):
        trial=dict(net=D('-1'),quantity=2,recovery=3)
        r=self.assess(trial=trial)
        self.assertEqual(r['status'],'batch_shortfall');self.assertIs(r['trial'],trial)
        self.assertTrue(any('超过本批数量' in s for s in r['reasons']))
        trial=dict(net=D('0'),quantity=2,recovery=2)
        r=self.assess(trial=trial)
        self.assertEqual(r['status'],'meets_target');self.assertTrue(any('没有批次利润缓冲' in s for s in r['reasons']))
        self.assertEqual(self.assess(trial=trial,net='1')['status'],'below_target')

    def test_source_unknowns_changed_currency_price_and_manual(self):
        self.assertIn('手填',self.assess()['source_note'])
        ref=dict(kind='observation',snapshot=SimpleNamespace(price=D('30'),currency='USD'),data={})
        r=self.assess(reference=ref);self.assertEqual(len(r['unknowns']),3);self.assertFalse(r['changed'])
        for changed in (dict(selling_price=D('31')),dict(sale_currency='EUR')):
            r=self.assess(reference=ref,**changed);self.assertTrue(r['changed']);self.assertIn('用户假设',r['source_note'])
        ref['data']=dict(sku_id='blue',market_country='US',conditions=['coupon'])
        self.assertFalse(self.assess(reference=ref)['unknowns'])
        ref['kind']='product'
        self.assertIn('公共报价',self.assess(reference=ref)['unknowns'][0])


class AssessmentFlowTests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_user('assessment-owner')
        self.other=get_user_model().objects.create_user('assessment-other')
        self.user=self.owner
        self.client.force_login(self.owner);self.url=reverse('profit')
        self.product=Product.objects.create(title='Controlled assessment',url='https://www.ebay.com/itm/123456789012',platform='eBay')
        self.quote=Snapshot.all_objects.create(product=self.product,owner=self.owner,source='browser',capture_id=uuid4(),price='30',currency='USD',observed_at=timezone.now(),capture_data={'price':'30.00','title':'Own assessment quote','sku_id':'chosen-blue','market_country':'US','conditions':['Coupon condition']})

    def post(self, **changes):
        return self.client.post(self.url,scenario(**changes),HTTP_HX_REQUEST='true')

    def test_get_ignores_assessment_query_and_does_not_write(self):
        before=(Product.objects.count(),Snapshot.all_objects.count())
        response=self.client.get(self.url,dict(assessment_enabled='on',assessment_costs_confirmed='on',observation=self.quote.pk))
        self.assertIsNone(response.context['assessment_result'])
        self.assertTrue(response.context['form'].fields['assessment_costs_confirmed'].disabled)
        self.assertFalse(response.context['form']['assessment_enabled'].value())
        self.assertEqual(before,(Product.objects.count(),Snapshot.all_objects.count()))

    def test_first_post_confirmed_and_unconfirmed_keep_unit_math(self):
        response=self.post();r=response.context['assessment_result']
        self.assertEqual(r['status'],'meets_target');self.assertEqual(response.context['result']['net'],D('9.60'))
        self.assertContains(response,'需求与竞争证据尚未纳入判断')
        response=self.post(assessment_costs_confirmed='false')
        self.assertEqual(response.context['assessment_result']['status'],'unconfirmed')
        self.assertIsNotNone(response.context['result'])

    def test_enabled_each_required_empty_or_missing_rejected_but_zero_is_explicit(self):
        for name in ASSESSMENT_EXPLICIT_FIELDS:
            for value in ('',None):
                data=scenario();data[name]=value
                if value is None: data.pop(name)
                form=SelectionAssessmentProfitForm(data,user=self.owner)
                self.assertFalse(form.is_valid(),name);self.assertIn(name,form.errors)
            data=scenario();data[name]='0'
            form=SelectionAssessmentProfitForm(data,user=self.owner)
            self.assertTrue(form.is_valid(),form.errors)
        for name in ('ad_cost','target_margin','discount_rate','payment_fee_rate'):
            response=self.post(**{name:'garbage'})
            self.assertIsNone(response.context['assessment_result']);self.assertIsNone(response.context['result'])

    def test_checkbox_binding_zero_false_missing_and_prefix(self):
        for enabled,expected in [('0',True),('on',True),('false',False),('False',False),('',False),(None,False)]:
            for confirmed,known in [('0',True),('on',True),('false',False),('',False),(None,False)]:
                data=scenario(assessment_enabled=enabled,assessment_costs_confirmed=confirmed)
                data={k:v for k,v in data.items() if v is not None}
                form=SelectionAssessmentProfitForm({'qa-'+k:v for k,v in data.items()},prefix='qa',user=self.owner)
                self.assertTrue(form.is_valid(),form.errors)
                self.assertEqual(form.assessment_active,expected)
                self.assertEqual(form.cleaned_data['assessment_enabled'],expected)
                self.assertEqual(form.cleaned_data['assessment_costs_confirmed'],known if expected else False)
                self.assertEqual(bool(form['assessment_enabled'].value()),expected)

    def test_cancel_preserves_trial_required_and_old_optional_compatibility(self):
        for trial in ('on',None):
            data=scenario(assessment_enabled='false',assessment_costs_confirmed='malformed-ignored')
            if trial:data['trial_enabled']=trial
            for name in ASSESSMENT_EXPLICIT_FIELDS:data[name]=''
            form=SelectionAssessmentProfitForm(data,user=self.owner)
            self.assertEqual(form.is_valid(),not bool(trial))
            if trial:self.assertIn('ad_cost',form.errors)
        response=self.post(assessment_enabled='false')
        self.assertIsNotNone(response.context['result']);self.assertIsNone(response.context['assessment_result'])
        self.assertNotContains(response,'data-assessment-status=')

    def test_batch_scenarios_use_original_budget_values(self):
        response=self.post(trial_enabled='on')
        self.assertEqual(response.context['trial_result']['net'],D('152'))
        self.assertEqual(response.context['assessment_result']['status'],'meets_target')
        response=self.post(trial_enabled='on',trial_quantity='1')
        self.assertEqual(response.context['assessment_result']['status'],'batch_shortfall')
        self.assertContains(response,'超过本批数量');self.assertContains(response,'本批 1 件')
        response=self.post(trial_enabled='on',trial_quantity='5',trial_sample_cost='48',trial_setup_cost='0',trial_compliance_cost='0')
        self.assertEqual(response.context['trial_result']['net'],D('0'))
        self.assertEqual(response.context['assessment_result']['status'],'meets_target')
        self.assertContains(response,'没有批次利润缓冲')

    def test_owned_reference_kept_with_time_conditions_and_changed_assumptions(self):
        response=self.post(observation=self.quote.pk)
        for text in ('chosen-blue','收货国家：US','Coupon condition','观测时间','name="observation"','保存报价作为假设售价'):
            self.assertContains(response,text)
        response=self.post(observation=self.quote.pk,selling_price='31')
        self.assertTrue(response.context['assessment_result']['changed']);self.assertContains(response,'测算使用用户假设')
        response=self.post(observation=self.quote.pk,sale_currency='EUR',exchange_rate='1')
        self.assertTrue(response.context['assessment_result']['changed'])
        self.quote.capture_data={};self.quote.save()
        response=self.post(observation=self.quote.pk)
        self.assertEqual(len(response.context['assessment_result']['unknowns']),3)
        self.assertEqual(Snapshot.all_objects.count(),1)

    def test_public_reference_never_uses_other_accounts_browser_quote(self):
        public=Snapshot.objects.create(product=self.product,source='manual',price='30',currency='USD',observed_at=timezone.now())
        self.client.force_login(self.other)
        response=self.post(product=self.product.pk)
        self.assertEqual(response.context['quote_reference']['snapshot'].pk,public.pk)
        self.assertNotContains(response,'chosen-blue');self.assertNotContains(response,'Own assessment quote')
        self.assertContains(response,'公共报价未提供')

    def test_invalid_htmx_clears_judgment_and_corrected_request_recovers(self):
        self.assertIsNotNone(self.post().context['assessment_result'])
        for change in (dict(target_margin=''),dict(fee_rate='90',payment_fee_rate='20'),dict(trial_enabled='on',trial_quantity='10001')):
            r=self.post(**change)
            self.assertIsNone(r.context['assessment_result']);self.assertIsNone(r.context['trial_result']);self.assertIsNone(r.context['result'])
            self.assertContains(r,'data-has-result="false"');self.assertNotContains(r,'data-assessment-status=')
        self.assertIsNotNone(self.post().context['assessment_result'])
        reset=self.client.get(self.url)
        self.assertIsNone(reset.context['assessment_result']);self.assertNotContains(reset,'data-assessment-status=')

    def test_foreign_or_deleted_reference_clears_all_results_and_private_text(self):
        self.assertIsNotNone(self.post(observation=self.quote.pk).context['assessment_result'])
        for foreign in (True,False):
            if foreign:self.client.force_login(self.other)
            else:self.client.force_login(self.owner);self.quote.delete()
            response=self.post(observation=999999 if not foreign else self.quote.pk,trial_enabled='on')
            self.assertEqual(response.status_code,404);self.assertEqual(response.headers['X-ShopHot-Profit-Workspace-Error'],'1')
            for key in ('result','trial_result','assessment_result'):self.assertIsNone(response.context[key])
            self.assertNotContains(response,'chosen-blue',status_code=404);self.assertNotContains(response,'data-assessment-status=',status_code=404)
            self.assertContains(response,'data-has-result="false"',status_code=404)

    def test_actual_ledger_rounded_margin_and_recommended_price_are_not_decisions(self):
        response=self.post(selling_price='200.01',cost='160.01',shipping='0',ad_cost='0',other_cost='0',
                           fee_rate='0',payment_fee_rate='0',payment_fixed='0',target_margin='20')
        self.assertEqual(response.context['result']['margin'],D('20.00'))
        self.assertEqual(response.context['result']['net'],D('40.00'))
        self.assertEqual(response.context['assessment_result']['required_net'],D('40.002'))
        self.assertEqual(response.context['assessment_result']['status'],'below_target')
        response=self.post(selling_price='.03',cost='0',shipping='0',ad_cost='0',other_cost='0',
                           fee_rate='20',payment_fee_rate='30',payment_fixed='0',target_margin='50')
        self.assertEqual(response.context['result']['target_price'],D('.01'))
        self.assertEqual(response.context['result']['net'],D('.01'))
        self.assertEqual(response.context['assessment_result']['status'],'below_target')

    def test_independent_five_unit_shortfall_and_zero_batch_buffer(self):
        response=self.post(trial_enabled='on',trial_quantity='5',trial_sample_cost='100',trial_setup_cost='0',trial_compliance_cost='0')
        self.assertEqual(response.context['trial_result']['net'],D('-52'))
        self.assertEqual(response.context['trial_result']['recovery'],11)
        self.assertEqual(response.context['assessment_result']['status'],'batch_shortfall')
        self.assertContains(response,'超过本批数量')
        response=self.post(trial_enabled='on',trial_quantity='5',trial_sample_cost='48',trial_setup_cost='0',trial_compliance_cost='0')
        self.assertEqual(response.context['trial_result']['recovery'],5)
        self.assertContains(response,'没有批次利润缓冲')

    def test_private_shipping_rejected_for_other_user(self):
        quote=test_profit_flow.ProfitFlowTests.quote(self)
        self.client.force_login(self.other)
        response=self.post(shipping_mode='quote',shipping_quote='user:'+str(quote.pk),package_weight='1',package_units='1',fuel_rate='0',shipping_extra='0')
        self.assertIsNone(response.context['assessment_result']);self.assertIsNone(response.context['result'])
        self.assertContains(response,'输入无效')


class AssessmentJavascriptTests(SimpleTestCase):
    def test_real_trial_and_assessment_scripts_cooperate_and_clear_stale(self):
        node=os.environ.get('SHOPHOT_NODE_BIN') or shutil.which('node')
        if not node:self.skipTest('Node unavailable for real script execution')
        script=r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const listeners={},elements={},button={firstChild:{nodeType:3,textContent:''}},stale={hidden:true},details={open:false};
for(const name of ['trial_enabled','assessment_enabled','assessment_costs_confirmed','trial_quantity','trial_sample_cost','trial_setup_cost','trial_compliance_cost','trial_reserve_cost','ad_cost','other_cost','payment_fee_rate','payment_fixed','discount_rate','target_margin']) elements[name]={checked:false,disabled:false,required:false};
const form={elements,querySelector:()=>button},document={addEventListener:(n,f)=>(listeners[n]??=[]).push(f),getElementById:id=>({'profit-form':form,'trial-budget-details':details,'profit-result':{dataset:{hasResult:'true'}},'profit-stale':stale}[id])};
const context={document,Node:{TEXT_NODE:3}};
for(const file of process.argv.slice(1)) vm.runInNewContext(fs.readFileSync(file,'utf8'),context);
function fire(name,id){for(const f of listeners[name]??[])f({target:{id}});}
function shared(expected){for(const n of ['ad_cost','other_cost','payment_fee_rate','payment_fixed'])assert.equal(elements[n].required,expected,n);}
fire('DOMContentLoaded');assert.equal(elements.assessment_costs_confirmed.disabled,true);shared(false);
elements.assessment_enabled.checked=true;fire('change','id_assessment_enabled');shared(true);assert.equal(stale.hidden,false);assert.equal(elements.discount_rate.required,true);assert.equal(elements.assessment_costs_confirmed.disabled,false);
elements.trial_enabled.checked=true;fire('change','id_trial_enabled');shared(true);assert.equal(elements.trial_quantity.disabled,false);
elements.assessment_enabled.checked=false;fire('change','id_assessment_enabled');shared(true);assert.equal(elements.target_margin.required,false);assert.equal(elements.assessment_costs_confirmed.disabled,true);
elements.assessment_enabled.checked=true;elements.trial_enabled.checked=false;fire('change','id_trial_enabled');shared(true);assert.equal(elements.trial_quantity.disabled,true);
fire('htmx:afterSwap');shared(true);
stale.hidden=true;fire('change','id_assessment_costs_confirmed');assert.equal(stale.hidden,false);
elements.assessment_enabled.checked=false;fire('change','id_assessment_enabled');shared(false);
"""
        base=Path(__file__).parent/'static'/'market'
        result=subprocess.run([node,'-e',script,str(base/'trial_budget.js'),str(base/'selection_assessment.js')],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_real_error_events_clear_only_failed_profit_workspace_without_swapping_html(self):
        node=os.environ.get('SHOPHOT_NODE_BIN') or shutil.which('node')
        if not node:self.skipTest('Node unavailable for real script execution')
        script=r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const listeners={},input={value:'160.01'},old={textContent:'Old profit, assessment and trial totals'};
const form={getAttribute:n=>n==='hx-post'?'/tools/profit/':null,elements:{assessment_enabled:{checked:false},cost:input}};
const output={dataset:{hasResult:'true'},children:[old],replaceChildren(...nodes){this.children=nodes;}};
const workspace={contains:node=>node===output};let reloads=0;
function element(tag){return {tag,attributes:{},setAttribute(n,v){this.attributes[n]=v;},addEventListener(n,fn){this[n]=fn;}};}
const document={addEventListener:(n,f)=>(listeners[n]??=[]).push(f),createElement:element,
 getElementById:id=>({'profit-form':form,'profit-workspace':workspace,'profit-result':output}[id])};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{document,window:{location:{reload(){reloads++;}}}});
function reset(){output.children=[old];output.dataset.hasResult='true';}
function detail(status){return {elt:form,target:workspace,requestConfig:{verb:'post',path:'/tools/profit/'},
 xhr:{status,responseText:'<script>untrusted server error</script>',getResponseHeader:()=> '1'},shouldSwap:false};}
function fire(name,d){for(const f of listeners[name]??[]) f({detail:d});}
for(const status of [403,429,500,502,503,599]){
 reset();const d=detail(status);fire('htmx:responseError',d);
 assert.equal(output.dataset.hasResult,'false');assert.equal(output.children.length,2);
 assert.equal(output.children.includes(old),false);assert.equal(output.children[0].attributes.role,'alert');
 assert.match(output.children[0].textContent,/本次计算失败/);assert.match(output.children[0].textContent,/旧结果已清除/);
 assert.equal(output.children[0].textContent.includes('untrusted'),false);assert.equal(d.shouldSwap,false);
 assert.equal(form.elements.cost.value,'160.01');output.children[1].click();
}
assert.equal(reloads,6);
for(const status of [200,204,302,400,401,404,422]){
 reset();fire('htmx:responseError',detail(status));assert.equal(output.children[0],old);assert.equal(output.dataset.hasResult,'true');
}
for(const change of [{elt:{}},{target:{}},{requestConfig:{verb:'get',path:'/tools/profit/'}},
 {requestConfig:{verb:'post',path:'/other/'}},{requestConfig:undefined}]){
 reset();fire('htmx:responseError',{...detail(403),...change});assert.equal(output.children[0],old);
 reset();fire('htmx:sendError',{...detail(0),...change});assert.equal(output.children[0],old);
}
for(const name of ['htmx:sendError','htmx:timeout']){
 reset();fire(name,detail(0));assert.equal(output.dataset.hasResult,'false');assert.equal(output.children.includes(old),false);
}
reset();fire('htmx:responseError',undefined);assert.equal(output.children[0],old);
// Existing profit 400/404 safe swap callback remains the sole handler for those statuses.
const profitListeners={};vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'),{
 document:{addEventListener:(n,f)=>profitListeners[n]=f}});
for(const status of [400,404]){
 const d={target:{id:'profit-workspace'},xhr:{status,getResponseHeader:()=> '1'},shouldSwap:false,isError:true};
 profitListeners['htmx:beforeSwap']({detail:d});assert.equal(d.shouldSwap,true);assert.equal(d.isError,false);
}
"""
        base=Path(__file__).parent/'static'/'market'
        result=subprocess.run([node,'-e',script,str(base/'selection_assessment.js'),str(base/'profit.js')],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
