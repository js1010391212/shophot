"""Independent scenario totals and optional trial lifecycle/ownership regressions."""
from decimal import Decimal as D
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from .models import Product, Snapshot, ShippingRate
from .profit import calculate_profit
from .trial_budget import calculate_trial_budget
from .trial_budget_forms import TrialBudgetProfitForm, TRIAL_FIELDS, EXPLICIT_UNIT_FIELDS


def inputs(**overrides):
    return dict(sale_currency='USD', cost_currency='USD', selling_price='30', discount_rate='0',
                cost='10', shipping_mode='manual', shipping='3', ad_cost='2', other_cost='1',
                fee_rate='10', payment_fee_rate='3', payment_fixed='0.50', target_margin='20',
                exchange_rate='1', trial_enabled='on', trial_quantity='20', trial_sample_cost='15',
                trial_setup_cost='20', trial_compliance_cost='5', trial_reserve_cost='30', **overrides)


class TrialBudgetMathTests(SimpleTestCase):
    def calculate(self, **overrides):
        raw=inputs(); raw.update(overrides)
        data={key: value if key in ('sale_currency','cost_currency','shipping_mode','trial_enabled') else D(value) for key,value in raw.items()}
        data['trial_quantity']=int(data['trial_quantity'])
        return calculate_trial_budget(calculate_profit(data), data)

    def test_independent_twenty_unit_budget_and_sales_totals(self):
        result=self.calculate()
        for key,value in dict(prepared='390',settlement='88',revenue='600',expenses='448',net='152',fixed='40').items():
            self.assertEqual(result[key],D(value),key)
        self.assertEqual(result['recovery'],5)
        self.assertEqual([value for _,value in result['operating']],[D('200'),D('60'),D('40'),D('20')])

    def test_reserve_is_prepared_but_never_deducted_again_from_profit(self):
        a=self.calculate(trial_reserve_cost='0');b=self.calculate(trial_reserve_cost='99.99')
        self.assertEqual(b['prepared']-a['prepared'],D('99.99'))
        self.assertEqual((a['expenses'],a['net']),(b['expenses'],b['net']))

    def test_fx_batch_multiplies_rounded_unit_components_not_raw_fx(self):
        r=self.calculate(selling_price='.05',discount_rate='10',cost_currency='CNY',exchange_rate='7.123456',
            cost='.10',shipping='.03',ad_cost='.02',other_cost='.01',payment_fixed='.01',trial_quantity='3',
            trial_sample_cost='.05',trial_setup_cost='0',trial_compliance_cost='0',trial_reserve_cost='.07')
        for key,value in dict(prepared='.60',settlement='.18',revenue='1.08',expenses='.71',net='.37').items():self.assertEqual(r[key],D(value),key)
        self.assertEqual(r['recovery'],1);self.assertEqual(r['currency'],'CNY')

    def test_zero_negative_and_no_fixed_cost_recovery(self):
        for cost,net,prepared in [('6','-1','25'),('7','-3','27')]:
            r=self.calculate(selling_price='10',cost=cost,shipping='3',ad_cost='1',other_cost='0',fee_rate='0',payment_fee_rate='0',payment_fixed='0',trial_quantity='2',trial_sample_cost='1',trial_setup_cost='0',trial_compliance_cost='0',trial_reserve_cost='4')
            self.assertEqual(r['net'],D(net));self.assertEqual(r['prepared'],D(prepared));self.assertIsNone(r['recovery'])
        self.assertEqual(self.calculate(trial_sample_cost='0',trial_setup_cost='0',trial_compliance_cost='0')['recovery'],0)

    def test_positive_unit_can_fail_to_cover_once_and_maximum_quantity_is_bounded(self):
        r=self.calculate(trial_sample_cost='200');self.assertEqual(r['status'],'本批未覆盖一次性费用')
        r=self.calculate(trial_quantity='10000');self.assertEqual(r['revenue'],D('300000'));self.assertEqual(r['net'],D('95960'))


class TrialBudgetFlowTests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_user('trial-owner')
        self.other=get_user_model().objects.create_user('trial-other')
        self.client.force_login(self.owner);self.url=reverse('profit')
        self.product=Product.objects.create(title='Controlled trial quote',url='https://www.ebay.com/itm/123456789012',platform='eBay')
        self.quote=Snapshot.all_objects.create(product=self.product,owner=self.owner,source='browser',capture_id=uuid4(),price='30',currency='USD',observed_at=timezone.now(),capture_data={'price':'30.00','currency':'USD','title':'Owned trial quote','sku_id':'chosen-sku','market_country':'US','conditions':['Controlled scenario']})

    def form(self, **overrides):
        data=inputs();data.update(overrides);return TrialBudgetProfitForm(data,user=self.owner)

    def test_disabled_ignores_invalid_trial_inputs_and_preserves_optional_unit_fields(self):
        data=inputs();data.pop('trial_enabled')
        for name in TRIAL_FIELDS:data[name]='garbage'
        for name in EXPLICIT_UNIT_FIELDS:data[name]=''
        form=TrialBudgetProfitForm(data,user=self.owner);self.assertTrue(form.is_valid(),form.errors)
        self.assertFalse(form.cleaned_data['trial_enabled'])
        response=self.client.post(self.url,data);self.assertIsNotNone(response.context['result']);self.assertIsNone(response.context['trial_result'])

    def test_enabled_requires_each_new_amount_and_legacy_optional_unit_amount(self):
        for name in (*TRIAL_FIELDS,*EXPLICIT_UNIT_FIELDS):
            with self.subTest(name=name):
                form=self.form(**{name:''});self.assertFalse(form.is_valid());self.assertIn(name,form.errors)

    def test_checkbox_widget_binding_and_required_fields_cannot_disagree(self):
        for enabled in ('on','true','1','0'):
            data=inputs();data['trial_enabled']=enabled
            for name in TRIAL_FIELDS:data.pop(name)
            form=TrialBudgetProfitForm(data,user=self.owner)
            self.assertTrue(form.trial_active);self.assertFalse(form.is_valid())
            self.assertIn('trial_quantity',form.errors)
            response=self.client.post(self.url,data)
            self.assertEqual(response.status_code,200);self.assertIsNone(response.context['trial_result'])
        for enabled in ('false','False',''):
            data=inputs();data['trial_enabled']=enabled
            for name in TRIAL_FIELDS:data.pop(name)
            form=TrialBudgetProfitForm(data,user=self.owner)
            self.assertFalse(form.trial_active);self.assertTrue(form.is_valid(),form.errors)
            self.assertFalse(form.cleaned_data['trial_enabled'])

    def test_explicit_zero_amounts_are_valid(self):
        form=self.form(**{name:'0' for name in (*TRIAL_FIELDS[1:],*EXPLICIT_UNIT_FIELDS)})
        self.assertTrue(form.is_valid(),form.errors)

    def test_quantity_precision_and_money_limits_never_silently_round(self):
        for name,value in [('trial_quantity','0'),('trial_quantity','10001'),('trial_quantity','1.5'),
                           ('trial_sample_cost','-.01'),('trial_sample_cost','.001'),('trial_sample_cost','10000000000')]:
            with self.subTest(name=name,value=value):
                form=self.form(**{name:value});self.assertFalse(form.is_valid());self.assertIn(name,form.errors)
        self.assertTrue(self.form(trial_quantity='10000',trial_sample_cost='9999999999.99').is_valid())

    def test_get_does_not_guess_budget_or_write_business_records(self):
        before=(Product.objects.count(),Snapshot.all_objects.count(),ShippingRate.objects.count())
        response=self.client.get(self.url,dict(observation=self.quote.pk,trial_enabled='on',trial_quantity='999',trial_sample_cost='5'))
        form=response.context['form'];self.assertFalse(form.trial_active)
        for name in TRIAL_FIELDS:self.assertIsNone(form[name].value())
        self.assertEqual(before,(Product.objects.count(),Snapshot.all_objects.count(),ShippingRate.objects.count()))
        self.assertEqual(form['selling_price'].value(),D('30'))

    def test_owned_quote_first_post_and_invalid_htmx_correction(self):
        data=inputs();data['observation']=str(self.quote.pk)
        response=self.client.post(self.url,data,HTTP_HX_REQUEST='true')
        self.assertEqual(response.context['trial_result']['net'],D('152'));self.assertContains(response,'chosen-sku')
        bad={**data,'trial_sample_cost':'.001'};response=self.client.post(self.url,bad,HTTP_HX_REQUEST='true')
        self.assertIsNone(response.context['result']);self.assertIsNone(response.context['trial_result']);self.assertContains(response,'输入无效')
        self.assertEqual(response.context['form']['trial_sample_cost'].value(),'.001')
        response=self.client.post(self.url,data,HTTP_HX_REQUEST='true');self.assertEqual(response.context['trial_result']['prepared'],D('390'))

    def test_quote_becoming_unavailable_clears_all_outputs_and_marks_swap(self):
        self.quote.owner=self.other;self.quote.save(update_fields=['owner'])
        response=self.client.post(self.url,{**inputs(),'observation':str(self.quote.pk)},HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code,404);self.assertEqual(response['X-ShopHot-Profit-Workspace-Error'],'1')
        self.assertIsNone(response.context['result']);self.assertIsNone(response.context['trial_result'])
        self.assertNotContains(response,'Owned trial quote',status_code=404)

    def test_another_account_cannot_read_or_use_quote(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url,{'observation':self.quote.pk}).status_code,404)
        self.assertEqual(self.client.post(self.url,{**inputs(),'observation':str(self.quote.pk)}).status_code,404)

    def test_private_shipping_is_still_owner_restricted(self):
        rate=ShippingRate.objects.create(owner=self.other,name='Secret route',carrier='QA',origin='CN',destination='US',currency='USD',method='per_kg',min_weight='.5',max_weight='20',step_weight='.5',per_kg='3',fixed_fee='0',fuel_basis='freight',effective_from=timezone.localdate(),source='manual',fingerprint='trial-private')
        response=self.client.post(self.url,{**inputs(),'shipping_mode':'quote','shipping_quote':f'user:{rate.pk}','package_weight':'1','package_units':'1','fuel_rate':'0','shipping_extra':'0','shipping_exchange_rate':'1'})
        self.assertIsNone(response.context['result']);self.assertIsNone(response.context['trial_result']);self.assertIn('shipping_quote',response.context['form'].errors)

    def test_sf_five_kg_thirty_cube_reuses_existing_estimate_once(self):
        data={**inputs(),'cost_currency':'CNY','exchange_rate':'7','shipping_mode':'quote','shipping_quote':'public:sf-economy-US','package_weight':'5','package_length':'30','package_width':'30','package_height':'30','package_units':'1','fuel_rate':'0','shipping_extra':'0','shipping_exchange_rate':'1'}
        response=self.client.post(self.url,data);self.assertIsNotNone(response.context['result'],response.context['form'].errors)
        shipping=response.context['shipping_result'];self.assertEqual(shipping['billed_weight'],D('5.5'))
        r=response.context['trial_result'];self.assertEqual(dict(r['operating'])['履约运费'],shipping['converted']*20)
        self.assertEqual(r['currency'],'CNY')

    def test_bare_reset_has_no_reference_or_trial_result(self):
        response=self.client.get(self.url);self.assertIsNone(response.context['quote_reference']);self.assertIsNone(response.context['trial_result']);self.assertFalse(response.context['form'].trial_active)
