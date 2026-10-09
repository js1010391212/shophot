"""Owned quote → profit input/result lifecycle; isolated DB and controlled quotes."""
from decimal import Decimal
from html.parser import HTMLParser
from uuid import uuid4
import os
from pathlib import Path
import shutil
import subprocess

from django.contrib.auth import get_user_model
from django.http import QueryDict
from django.test import TestCase, SimpleTestCase, RequestFactory
from django.urls import reverse
from django.utils import timezone

from .models import Product, Snapshot
from .profit_references import resolve_reference


class ReferenceWorkspace(HTMLParser):
    def __init__(self, html):
        super().__init__();self.depth=0;self.workspace=None;self.source_inside=False;self.hidden=[]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag=='div':
            self.depth+=1
            if attrs.get('id')=='profit-workspace':self.workspace=self.depth
        if self.workspace is not None:
            if tag=='section' and attrs.get('aria-label')=='测算报价来源':self.source_inside=True
            if tag=='input' and attrs.get('type')=='hidden' and attrs.get('name') in ('observation','product'):
                self.hidden.append((attrs['name'],attrs['value']))

    def handle_endtag(self, tag):
        if tag=='div':
            if self.depth==self.workspace:self.workspace=None
            self.depth-=1


class ProfitReferenceTests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_user('reference-owner')
        self.other=get_user_model().objects.create_user('reference-other')
        self.client.force_login(self.owner)
        self.product=Product.objects.create(title='Controlled quote product',url='https://www.ebay.com/itm/123456789012',platform='eBay')
        self.capture=dict(price='60.00',currency='USD',title='Owned quote title',url=self.product.url,
                          sku_id='selected-123',market_country='US',conditions=['Selected blue','Coupon condition'],
                          observed_at=timezone.now().isoformat(),adapter_version='controlled-fixture')
        self.row=Snapshot.all_objects.create(product=self.product,owner=self.owner,source='browser',capture_id=uuid4(),
                                            price='60.00',currency='USD',observed_at=timezone.now(),capture_data=self.capture)
        self.url=reverse('profit')
        self.post=dict(sale_currency='USD',cost_currency='USD',selling_price='70',discount_rate='0',exchange_rate='',
                       cost='40',shipping_mode='manual',shipping='10',ad_cost='2',other_cost='0',fee_rate='0',
                       payment_fee_rate='0',payment_fixed='0',target_margin='20',observation=str(self.row.pk))

    def test_owned_get_exact_prefill_no_cost_country_fx_or_business_writes(self):
        before=(Snapshot.all_objects.count(),Product.objects.count())
        response=self.client.get(self.url,{'observation':self.row.pk,'selling_price':'999','sale_currency':'EUR','cost':'1'})
        form=response.context['form']
        self.assertEqual(form['selling_price'].value(),Decimal('60.00'))
        self.assertEqual(form['sale_currency'].value(),'USD')
        self.assertEqual(form['discount_rate'].value(),0)
        for name in ('cost','shipping','exchange_rate','shipping_quote'):
            self.assertIsNone(form[name].value())
        self.assertIsNone(response.context['result'])
        self.assertEqual(before,(Snapshot.all_objects.count(),Product.objects.count()))
        for text in ('selected-123','Coupon condition','收货国家：US','报价可能已包含优惠','测算不代表竞品真实利润'):
            self.assertContains(response,text)
        parsed=ReferenceWorkspace(response.content.decode())
        self.assertTrue(parsed.source_inside)
        self.assertEqual(parsed.hidden,[('observation',str(self.row.pk))])

    def test_source_lookup_is_one_bounded_owned_query(self):
        request=RequestFactory().get(self.url,{'observation':self.row.pk});request.user=self.owner
        with self.assertNumQueries(1):
            reference=resolve_reference(request)
            self.assertEqual(reference['product'].pk,self.product.pk)
            self.assertEqual(reference['snapshot'].owner_id,self.owner.pk)

    def test_other_owner_nonexistent_and_public_snapshot_ids_are_all_404(self):
        public=Snapshot.objects.create(product=self.product,price='20',currency='EUR',source='manual',observed_at=timezone.now())
        self.client.force_login(self.other)
        for pk in (self.row.pk,99999999,public.pk):
            self.assertEqual(self.client.get(self.url,{'observation':pk}).status_code,404)
            self.assertEqual(self.client.post(self.url,{**self.post,'observation':pk},HTTP_HX_REQUEST='true').status_code,404)

    def test_public_product_reference_never_selects_private_quote(self):
        response=self.client.get(self.url,{'product':self.product.pk})
        self.assertIsNone(response.context['quote_reference'])
        self.assertIsNone(response.context['form']['selling_price'].value())
        public=Snapshot.objects.create(product=self.product,price='20',currency='EUR',source='manual',observed_at=timezone.now())
        response=self.client.get(self.url,{'product':self.product.pk})
        self.assertEqual(response.context['quote_reference']['snapshot'].pk,public.pk)
        self.assertEqual(response.context['form']['selling_price'].value(),Decimal('20'))
        self.assertEqual(response.context['form']['sale_currency'].value(),'EUR')

    def test_duplicate_conflicting_and_invalid_reference_ids_fail_clearly(self):
        for query in (f'observation={self.row.pk}&observation={self.row.pk}',
                      f'observation={self.row.pk}&product={self.product.pk}','observation=','observation=-1',
                      'observation=abc','observation=9223372036854775808'):
            response=self.client.get(self.url+'?'+query)
            self.assertEqual(response.status_code,400)
            self.assertIsNone(response.context['result'])
            self.assertTrue(response.context['reference_error'])
        data=QueryDict('',mutable=True);data.update(self.post);data.appendlist('observation',str(self.row.pk))
        self.assertEqual(self.client.post(self.url,data.urlencode(),content_type='application/x-www-form-urlencoded').status_code,400)
        self.assertEqual(self.client.post(self.url+f'?observation={self.row.pk}',self.post).status_code,400)
        self.assertEqual(self.client.post(self.url,{**self.post,'product':self.product.pk}).status_code,400)

    def test_unrepresentable_source_never_silently_rounds_or_prefills(self):
        for amount in ('60.001','10000000000.00','59.99'):
            self.row.capture_data={**self.capture,'price':amount};self.row.save()
            response=self.client.get(self.url,{'observation':self.row.pk})
            self.assertIsNone(response.context['form']['selling_price'].value())
            self.assertContains(response,'不能准确带入利润工具')
            self.assertContains(response,'未舍入或替换来源')
            self.assertEqual(response.context['quote_reference']['snapshot'].price,Decimal('60'))

    def test_htmx_post_keeps_source_and_user_input_through_error_and_second_submit(self):
        first=self.client.post(self.url,self.post,HTTP_HX_REQUEST='true')
        self.assertEqual(first.context['result']['net'],Decimal('18'))
        self.assertEqual(first.context['form']['selling_price'].value(),'70')
        self.assertEqual(first.context['quote_reference']['snapshot'].price,Decimal('60'))
        invalid=self.client.post(self.url,{**self.post,'cost_currency':'CNY'},HTTP_HX_REQUEST='true')
        self.assertIsNone(invalid.context['result'])
        self.assertEqual(ReferenceWorkspace(invalid.content.decode()).hidden,[('observation',str(self.row.pk))])
        second=self.client.post(self.url,{**self.post,'selling_price':'80','cost':'45'},HTTP_HX_REQUEST='true')
        self.assertEqual(second.context['result']['net'],Decimal('23'))
        self.assertEqual(second.context['form']['cost'].value(),'45')
        self.assertTrue(ReferenceWorkspace(second.content.decode()).source_inside)
        self.assertEqual(Snapshot.all_objects.count(),1)
        self.assertContains(second,reverse('browser_report',args=[self.product.pk]))

    def test_unknown_quote_conditions_remain_unknown(self):
        self.row.capture_data={**self.capture,'sku_id':None,'market_country':None,'conditions':[]};self.row.save()
        response=self.client.get(self.url,{'observation':self.row.pk})
        for text in ('规格编号：未知','收货国家：未知','报价条件未知'):
            self.assertContains(response,text)
        self.assertIsNone(response.context['form']['shipping_quote'].value())

    def test_report_latest_and_historical_links_use_exact_owned_snapshots(self):
        old=Snapshot.all_objects.create(product=self.product,owner=self.owner,source='browser',capture_id=uuid4(),
                                       price='59',currency='USD',observed_at=timezone.now(),capture_data=self.capture)
        other=Snapshot.all_objects.create(product=self.product,owner=self.other,source='browser',capture_id=uuid4(),
                                         price='99',currency='USD',observed_at=timezone.now(),capture_data=self.capture)
        response=self.client.get(reverse('browser_report',args=[self.product.pk]))
        for pk in (self.row.pk,old.pk):self.assertContains(response,f'?observation={pk}')
        self.assertNotContains(response,f'?observation={other.pk}')

    def test_hx_missing_foreign_and_wrong_source_return_same_safe_workspace_error(self):
        public=Snapshot.objects.create(product=self.product,price='20',currency='EUR',source='manual',observed_at=timezone.now())
        self.client.force_login(self.other)
        errors=[]
        for pk in (self.row.pk,99999999,public.pk):
            response=self.client.post(self.url,{**self.post,'observation':pk},HTTP_HX_REQUEST='true')
            self.assertEqual(response.status_code,404)
            self.assertEqual(response.headers['X-ShopHot-Profit-Workspace-Error'],'1')
            self.assertIsNone(response.context['result'])
            self.assertIsNone(response.context['quote_reference'])
            self.assertEqual(response.context['form']['selling_price'].value(),'70')
            self.assertEqual(response.context['form']['cost'].value(),'40')
            self.assertContains(response,'data-has-result="false"',status_code=404)
            self.assertContains(response,'这条报价目前不可用于测算',status_code=404)
            for secret in ('Owned quote title','selected-123','Coupon condition'):
                self.assertNotContains(response,secret,status_code=404)
            self.assertEqual(ReferenceWorkspace(response.content.decode()).hidden,[])
            errors.append(response.context['reference_error'])
        self.assertEqual(len(set(errors)),1)
        for pk in (self.row.pk,99999999,public.pk):
            plain=self.client.post(self.url,{**self.post,'observation':pk})
            self.assertEqual(plain.status_code,404)
            self.assertNotIn('X-ShopHot-Profit-Workspace-Error',plain.headers)
            get=self.client.get(self.url,{'observation':pk},HTTP_HX_REQUEST='true')
            self.assertEqual(get.status_code,404)
            self.assertNotIn('X-ShopHot-Profit-Workspace-Error',get.headers)

    def test_only_hx_post_400_reference_error_is_marked_and_clears_previous_profit(self):
        valid=self.client.post(self.url,self.post,HTTP_HX_REQUEST='true')
        self.assertEqual(valid.context['result']['net'],Decimal('18'))
        self.assertNotIn('X-ShopHot-Profit-Workspace-Error',valid.headers)
        invalid={**self.post,'product':self.product.pk,'selling_price':'87','cost':'49'}
        hx=self.client.post(self.url,invalid,HTTP_HX_REQUEST='true')
        self.assertEqual(hx.status_code,400)
        self.assertEqual(hx.headers['X-ShopHot-Profit-Workspace-Error'],'1')
        self.assertIsNone(hx.context['result'])
        self.assertEqual(hx.context['form']['selling_price'].value(),'87')
        self.assertEqual(hx.context['form']['cost'].value(),'49')
        self.assertContains(hx,'data-has-result="false"',status_code=400)
        self.assertContains(hx,'不能同时引用',status_code=400)
        for response in (self.client.post(self.url,invalid),self.client.get(self.url,{'observation':'bad'})):
            self.assertEqual(response.status_code,400)
            self.assertNotIn('X-ShopHot-Profit-Workspace-Error',response.headers)

    def test_original_manual_and_sf_quote_compatibility(self):
        manual={k:v for k,v in self.post.items() if k!='observation'}
        response=self.client.post(self.url,manual)
        self.assertEqual(response.context['result']['net'],Decimal('18'))
        params=dict(shipping_mode='quote',shipping_quote='public:sf-economy-US',package_weight='5',package_length='30',
                    package_width='30',package_height='30',package_units='1',fuel_rate='0',shipping_extra='0',cost_currency='CNY')
        get=self.client.get(self.url,{**params,'observation':self.row.pk})
        self.assertEqual(get.context['form']['selling_price'].value(),Decimal('60'))
        self.assertEqual(get.context['form']['shipping_mode'].value(),'quote')
        result=self.client.post(self.url,{**self.post,**params,'sale_currency':'CNY','selling_price':'2000'},HTTP_HX_REQUEST='true')
        self.assertEqual(result.context['shipping_result']['converted'],Decimal('930'))
        self.assertEqual(result.context['result']['net'],Decimal('1028'))
        self.assertTrue(ReferenceWorkspace(result.content.decode()).source_inside)


class ProfitErrorSwapTests(SimpleTestCase):
    def test_actual_script_allows_only_marked_profit_400_404_responses(self):
        node=os.environ.get('SHOPHOT_NODE_BIN') or shutil.which('node')
        if not node:
            self.skipTest('Node required to execute actual profit script event contract.')
        script="""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const listeners={};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{document:{addEventListener:(name,fn)=>listeners[name]=fn}});
const callback=listeners['htmx:beforeSwap'];assert.equal(typeof callback,'function');
for(const status of [400,404]){
 const detail={target:{id:'profit-workspace'},xhr:{status,getResponseHeader:name=>name==='X-ShopHot-Profit-Workspace-Error'?'1':null},shouldSwap:false,isError:true};
 callback({detail});assert.equal(detail.shouldSwap,true);assert.equal(detail.isError,false);
}
for(const [id,status,header] of [['other',400,'1'],['other',404,'1'],['profit-workspace',500,'1'],
 ['profit-workspace',200,'1'],['profit-workspace',302,'1'],['profit-workspace',400,null],
 ['profit-workspace',404,null],['profit-workspace',404,'0']]){
 const detail={target:{id},xhr:{status,getResponseHeader:()=>header},shouldSwap:false,isError:true};
 callback({detail});assert.equal(detail.shouldSwap,false);assert.equal(detail.isError,true);
}
callback({detail:undefined});
"""
        filename=Path(__file__).resolve().parent/'static'/'market'/'profit.js'
        result=subprocess.run([node,'-e',script,str(filename)],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
