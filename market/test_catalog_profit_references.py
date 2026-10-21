"""Catalog source identity and private-study lifecycle; controlled isolated fixtures."""
from copy import deepcopy
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .catalog_profit_references import catalog_profit_link, valid_catalog_source
from .models import (CatalogCandidate, CatalogPriceObservation, CollectionJob, Product,
                     ProfitStudyRecord, Snapshot, StoreDiscovery, StorePriceJob)
from .price_history import capture_quote_scope
from .profit_studies import SALT, save_study, unpack
from .study_comparison import read_history
from .test_trial_budget import inputs


class CatalogProfitReferenceTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user('catalog-profit-owner')
        self.other = get_user_model().objects.create_user('catalog-profit-other')
        self.client.force_login(self.owner)
        self.url = 'https://sample.myshopify.com/products/controlled?country=US'
        item = dict(url=self.url, title='Controlled single specification')
        self.scan = StoreDiscovery.objects.create(url='https://sample.myshopify.com', status='succeeded', products=[item], limited=True)
        self.job = StorePriceJob.objects.create(discovery=self.scan, status='succeeded', processed=1, total=1)
        scope = capture_quote_scope({'currency': 'USD', 'variants': [dict(url=self.url+'&variant=123', name='One size', sku='SKU-123', size='', color='', price_low='50', price_high='50', currency='USD')]}, self.url)
        self.quote = CatalogPriceObservation.objects.create(discovery=self.scan, job=self.job, url=self.url,
            title=item['title'], price_low='50', price_high='50', currency='USD', quote_scope=scope, observed_at=timezone.now())
        self.candidate = CatalogCandidate.objects.create(owner=self.owner, url=self.url, store_url=self.scan.url, discovery=self.scan, saved_item=item)
        self.profit = reverse('profit')
        self.params = {'catalog': str(self.quote.pk), 'candidate': str(self.candidate.pk)}
        self.raw = {**inputs(), **self.params, 'selling_price': '50'}

    def calculated(self, **overrides):
        response = self.client.post(self.profit, {**self.raw, **overrides})
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context['result'])
        self.assertIsNotNone(response.context['save_form'], response.context['save_error'])
        return response

    def token(self, **overrides):
        return self.calculated(**overrides).context['save_form']['state'].value()

    def save(self, token=None):
        return save_study(self.owner, token or self.token(), 'Controlled catalog study', 'Costs are explicit QA assumptions')

    def test_exact_get_has_no_writes_no_fake_snapshot_and_preserves_scope_unknowns(self):
        before=(Product.objects.count(), Snapshot.all_objects.count(), ProfitStudyRecord.objects.count(), CollectionJob.objects.count())
        response=self.client.get(self.profit, {**self.params, 'selling_price':'999'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form']['selling_price'].value(), Decimal('50'))
        self.assertEqual(response.context['form']['sale_currency'].value(), 'USD')
        self.assertIsNone(response.context['form']['shipping'].value())
        source=response.context['catalog_source']
        self.assertEqual(source['quote_scope'],self.quote.quote_scope)
        self.assertIsNone(source['market_country'])
        self.assertTrue(source['conditions_unknown'])
        self.assertContains(response, 'SKU-123')
        self.assertNotContains(response, self.quote.quote_scope['signature'])
        self.assertContains(response, '已核对单一明确规格')
        self.assertContains(response, 'name="candidate"')
        self.assertNotIn('snapshot', response.context['quote_reference'])
        self.assertEqual(before,(Product.objects.count(), Snapshot.all_objects.count(), ProfitStudyRecord.objects.count(), CollectionJob.objects.count()))

    def test_invalid_duplicate_mixed_reference_and_study_parameters_rejected(self):
        for query in (f'catalog={self.quote.pk}&catalog={self.quote.pk}', f'catalog={self.quote.pk}&product=1',
                      f'catalog={self.quote.pk}&observation=1', 'catalog=0', 'catalog=bad', 'catalog=9223372036854775808',
                      f'catalog={self.quote.pk}&candidate=1&candidate=1', 'candidate=1'):
            with self.subTest(query=query):
                self.assertEqual(self.client.get(self.profit+'?'+query).status_code,400)
        self.assertEqual(self.client.post(self.profit+'?catalog='+str(self.quote.pk), self.raw).status_code,400)
        row=self.save()
        for params in ({'study':row.pk,**self.params}, {'study':row.pk,'candidate':self.candidate.pk}):
            self.assertEqual(self.client.get(self.profit, params).status_code,400)

    def test_candidate_owner_and_url_store_identity(self):
        self.client.force_login(self.other)
        response=self.client.get(self.profit, self.params)
        self.assertEqual(response.status_code,404)
        self.assertNotContains(response,'Controlled single specification',status_code=404)
        # Catalog observations themselves are public; never infer a private candidate.
        public=self.client.get(self.profit, {'catalog':self.quote.pk})
        self.assertEqual(public.status_code,200)
        self.assertIsNone(public.context['catalog_source']['candidate_id'])
        self.client.force_login(self.owner)
        self.candidate.url='https://sample.myshopify.com/products/different';self.candidate.save()
        self.assertEqual(self.client.get(self.profit,self.params).status_code,400)
        self.candidate.url=self.url;self.candidate.store_url='https://other.myshopify.com';self.candidate.save()
        self.assertEqual(self.client.get(self.profit,self.params).status_code,400)

    def test_range_and_equal_price_multiple_specs_unknown_or_tampered_scope_refused(self):
        original=deepcopy(self.quote.quote_scope)
        scopes=[{}, {**original,'signature':'0'*64}, {**original,'variant_count':True},
                {**original,'variant_count':2}, {**original,'identities':[{**original['identities'][0],'range':True}]},
                {**original,'identities':[{**original['identities'][0],'sku':'different'}]},
                {**original,'identities':[{**original['identities'][0],'url':'https://other.com/products/a'}]}]
        for scope in scopes:
            CatalogPriceObservation.objects.filter(pk=self.quote.pk).update(quote_scope=scope)
            response=self.client.post(self.profit,self.raw,HTTP_HX_REQUEST='true')
            self.assertEqual(response.status_code,400)
            self.assertIsNone(response.context['result'])
            self.assertIsNone(response.context['save_form'])
            self.assertEqual(response.headers['X-ShopHot-Profit-Workspace-Error'],'1')
        CatalogPriceObservation.objects.filter(pk=self.quote.pk).update(quote_scope=original,price_high='51')
        self.assertEqual(self.client.get(self.profit,self.params).status_code,400)
        self.assertEqual(ProfitStudyRecord.objects.count(),0)

    def test_scope_without_spec_identity_or_different_market_refused(self):
        for url in (self.url, self.url.replace('country=US','country=DE')+'&variant=123'):
            scope=capture_quote_scope({'currency':'USD','variants':[dict(url=url,name='No SKU',price_low='50',price_high='50',currency='USD')]},self.url)
            CatalogPriceObservation.objects.filter(pk=self.quote.pk).update(quote_scope=scope)
            self.assertEqual(self.client.get(self.profit,self.params).status_code,400)

    def test_v2_save_exact_source_and_user_assumption_repeat_is_idempotent(self):
        response=self.calculated(selling_price='60',shipping='4')
        token=response.context['save_form']['state'].value()
        payload=unpack(self.owner,token)
        self.assertEqual(payload['version'],2)
        source=payload['scenario']['source']
        self.assertEqual(source['price'],'50.00')
        self.assertEqual(payload['scenario']['inputs']['selling_price'],'60')
        self.assertNotIn('snapshot_id',source)
        self.assertEqual(source['candidate_id'],self.candidate.pk)
        row=self.save(token)
        self.assertEqual(self.save(token).pk,row.pk)
        self.assertEqual(row.snapshot,payload)
        self.assertEqual(Snapshot.all_objects.count(),0)
        self.assertEqual(Product.objects.count(),0)
        self.assertEqual(ProfitStudyRecord.objects.count(),1)
        self.assertTrue(valid_catalog_source(source))
        read_history(row)

    def test_newer_quote_does_not_drift_continuation_or_saved_history(self):
        row=self.save();before=deepcopy(row.snapshot)
        newjob=StorePriceJob.objects.create(discovery=self.scan,status='succeeded')
        CatalogPriceObservation.objects.create(discovery=self.scan,job=newjob,url=self.url,title='New title',price_low='80',price_high='80',currency='USD',quote_scope=self.quote.quote_scope,observed_at=timezone.now())
        response=self.client.get(self.profit, {'study':row.pk})
        self.assertEqual(response.context['catalog_source']['id'],self.quote.pk)
        self.assertEqual(response.context['catalog_source']['price'],'50.00')
        self.assertEqual(response.context['form']['selling_price'].value(),'50')
        continued={k:v for k,v in self.raw.items() if k not in self.params}
        calculated=self.client.post(self.profit,{**continued,'study':row.pk,'cost':'11'})
        token=calculated.context['save_form']['state'].value()
        self.assertNotEqual(self.save(token).pk,row.pk)
        row.refresh_from_db();self.assertEqual(row.snapshot,before)

    def test_mutation_or_delete_after_signing_rejects_save_and_continuation_keeps_history(self):
        token=self.token();row=self.save(token);before=deepcopy(row.snapshot)
        CatalogPriceObservation.objects.filter(pk=self.quote.pk).update(price_low='51',price_high='51')
        with self.assertRaises(ValidationError):self.save(token)
        response=self.client.get(self.profit,{'study':row.pk})
        self.assertEqual(response.status_code,400)
        self.assertIsNone(response.context['quote_reference'])
        detail=self.client.get(reverse('profit_study_detail',args=[row.pk]))
        self.assertEqual(detail.context['source_link'],'')
        self.assertEqual(detail.context['saved']['source']['price'],'50.00')
        row.refresh_from_db();self.assertEqual(row.snapshot,before)
        self.quote.delete()
        with self.assertRaises(ValidationError):self.save(token)
        self.assertEqual(self.client.get(reverse('profit_study_detail',args=[row.pk])).status_code,200)

    def test_source_currency_scope_candidate_and_job_mutations_rejected_on_save(self):
        token=self.token()
        for field,value in [('currency','EUR'),('quote_scope',{}),('title','Changed source title')]:
            original=getattr(self.quote,field)
            CatalogPriceObservation.objects.filter(pk=self.quote.pk).update(**{field:value})
            with self.assertRaises(ValidationError):self.save(token)
            CatalogPriceObservation.objects.filter(pk=self.quote.pk).update(**{field:original})
        self.candidate.owner=self.other;self.candidate.save()
        with self.assertRaises(ValidationError):self.save(token)
        self.candidate.owner=self.owner;self.candidate.save()
        other_scan=StoreDiscovery.objects.create(url='https://other.com',status='succeeded')
        self.job.discovery=other_scan;self.job.save()
        with self.assertRaises(ValidationError):self.save(token)

    def test_v2_shape_mixed_version_and_unknown_fields_rejected(self):
        original=unpack(self.owner,self.token())
        changes=[]
        v1=deepcopy(original);v1['version']=1;changes.append(v1)
        for key,value in [('id',True),('quote_scope',{}),('conditions_unknown',False),('market_country','US'),('captured_price','49.00')]:
            payload=deepcopy(original);payload['scenario']['source'][key]=value;changes.append(payload)
        payload=deepcopy(original);payload['scenario']['source']['snapshot_id']=1;changes.append(payload)
        payload=deepcopy(original);payload['scenario']['source']=None;changes.append(payload)
        for payload in changes:
            with self.assertRaises(ValidationError):unpack(self.owner,signing.dumps(payload,salt=SALT))

    def test_other_account_cannot_save_resume_read_or_compare(self):
        token=self.token();row=self.save(token)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse('profit_study_save'),{'state':token,'name':'Foreign'}).status_code,400)
        self.assertEqual(self.client.get(self.profit,{'study':row.pk}).status_code,404)
        self.assertEqual(self.client.get(reverse('profit_study_detail',args=[row.pk])).status_code,404)
        response=self.client.get(reverse('study_comparison'),{'left':row.pk,'right':row.pk})
        self.assertNotContains(response,row.name,status_code=response.status_code)

    def test_csrf_save_and_candidate_writes_are_protected(self):
        secure=Client(enforce_csrf_checks=True);secure.force_login(self.owner)
        self.assertEqual(secure.post(reverse('profit_study_save'),{'state':self.token(),'name':'No CSRF'}).status_code,403)
        self.assertEqual(secure.post(reverse('candidate_add',args=[self.scan.pk,0])).status_code,403)
        self.assertEqual(ProfitStudyRecord.objects.count(),0)

    def test_catalog_and_candidate_navigation_and_range_fallback(self):
        link=catalog_profit_link(self.quote,self.candidate)
        detail=self.client.get(reverse('catalog_detail',args=[self.scan.pk,0]))
        self.assertContains(detail,link.replace('&','&amp;'))
        candidates=self.client.get(reverse('candidates'))
        self.assertContains(candidates,'用明确历史报价测算成本')
        self.assertContains(candidates,link.replace('&','&amp;'))
        CatalogPriceObservation.objects.filter(pk=self.quote.pk).update(price_high='55')
        fallback=self.client.get(reverse('candidates'))
        self.assertContains(fallback,'手填售价与物流成本假设')
        self.assertNotContains(fallback,'?catalog=')

    def test_old_v1_manual_and_public_records_still_save_continue_compare(self):
        raw={k:v for k,v in self.raw.items() if k not in self.params}
        response=self.client.post(self.profit,raw)
        token=response.context['save_form']['state'].value()
        self.assertEqual(unpack(self.owner,token)['version'],1)
        row=self.save(token)
        read_history(row)
        self.assertEqual(self.client.get(self.profit,{'study':row.pk}).status_code,200)
        product=Product.objects.create(title='Old public',url='https://example.com/products/old')
        Snapshot.objects.create(product=product,price='30',currency='USD',observed_at=timezone.now())
        response=self.client.post(self.profit,{**raw,'product':product.pk})
        self.assertEqual(unpack(self.owner,response.context['save_form']['state'].value())['version'],1)
        catalog=self.save()
        read_history(catalog)
        # Version 2 must not turn an arbitrary version-1 payload into a supported future format.
        bad=deepcopy(row.snapshot);bad['version']=2
        row.snapshot=bad
        with self.assertRaises(ValidationError):read_history(row)

    def test_assessment_uses_catalog_money_without_snapshot_and_marks_modified_price(self):
        response=self.calculated(selling_price='60',assessment_enabled='on',assessment_costs_confirmed='on')
        self.assertTrue(response.context['assessment_result']['changed'])
        self.assertIn('用户假设',response.context['assessment_result']['source_note'])

    def test_stale_or_expired_signatures_cannot_save(self):
        token=self.token()
        with patch('django.core.signing.time.time',return_value=timezone.now().timestamp()+3601):
            with self.assertRaises(ValidationError):self.save(token)
        with self.assertRaises(ValidationError):self.save(token+'tampered')

    def test_valid_multi_spec_equal_bounds_still_refused(self):
        variants=[dict(url=self.url+'&variant='+str(i),name='Size '+str(i),sku='SKU-'+str(i),size='',color='',price_low='50',price_high='50',currency='USD') for i in (1,2)]
        scope=capture_quote_scope({'currency':'USD','variants':variants},self.url)
        self.assertEqual(scope['variant_count'],2)
        CatalogPriceObservation.objects.filter(pk=self.quote.pk).update(quote_scope=scope)
        self.assertEqual(self.client.get(self.profit,self.params).status_code,400)

    def test_catalog_id_cannot_be_used_as_private_browser_observation(self):
        # The independent row types may share an integer; the parameter chooses the type.
        product=Product.objects.create(url='https://example.com/products/collision',title='Different public product')
        Snapshot.objects.create(pk=self.quote.pk,product=product,price='999',currency='EUR',observed_at=timezone.now())
        self.assertEqual(self.client.get(self.profit,{'observation':self.quote.pk}).status_code,404)
        response=self.client.get(self.profit,{'catalog':self.quote.pk})
        self.assertEqual(response.context['form']['selling_price'].value(),Decimal('50'))
        self.assertEqual(response.context['form']['sale_currency'].value(),'USD')

    def test_foreign_cost_currency_requires_explicit_exchange_rate(self):
        response=self.client.post(self.profit,{**self.raw,'cost_currency':'CNY','exchange_rate':''})
        self.assertIsNone(response.context['result'])
        self.assertIsNone(response.context['save_form'])
        self.assertTrue(response.context['form'].errors.get('exchange_rate'))
        self.assertEqual(response.context['catalog_source']['currency'],'USD')

    def test_v1_and_v2_history_comparison_accepts_both_without_source_drift(self):
        raw={k:v for k,v in self.raw.items() if k not in self.params}
        legacy=self.client.post(self.profit,raw)
        old=self.save(legacy.context['save_form']['state'].value())
        new=self.save()
        old_read,new_read=read_history(old),read_history(new)
        from .study_comparison import compare_histories
        result=compare_histories(old_read,new_read)
        self.assertEqual(result['unit_reasons'],[])
        response=self.client.get(reverse('study_comparison'),{'left':old.pk,'right':new.pk})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'Controlled catalog study')
