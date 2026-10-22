"""Controlled status display fixture, never imported into any live catalog."""
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from .candidates import save_candidate
from .forms import ResearchFilterForm
from .models import CatalogPriceObservation, StoreDiscovery, StorePriceJob
from .research import AVAILABILITY, build_research

ROOT='https://www.adafruit.com'
URL=ROOT+'/product/4864'


class AvailabilityMappingTests(SimpleTestCase):
    def test_all_known_states_and_unknown_remain_consistent(self):
        for state,label in AVAILABILITY.items():
            self.assertEqual(render_to_string('market/availability.html',{'state':state}).strip(),label)
            form=ResearchFilterForm({'availability':state})
            self.assertTrue(form.is_valid(),form.errors)
        for state in (None,'', 'unrecognised'):
            self.assertEqual(render_to_string('market/availability.html',{'state':state}).strip(),'未知')
        self.assertFalse(ResearchFilterForm({'availability':'unrecognised'}).is_valid())


class DiscontinuedDisplayTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('status-reader')
        self.client.force_login(self.user)
        self.item={'url':URL,'title':'Controlled fixture','price_title':'Controlled fixture',
            'price_low':'4.00','price_high':'4.00','currency':'USD','sku':'4864',
            'price_observed_at':timezone.now().isoformat(),'availability':'Discontinued',
            'content_policy':'facts_only','variants':[{'url':URL,'name':'Selected fixture',
                'sku':'4864','currency':'USD','price_low':'4.00','price_high':'4.00',
                'availability':'Discontinued'}]}
        self.scan=StoreDiscovery.objects.create(url=ROOT,status='succeeded',products=[self.item])
        # Explicit test-only historical observation, not derived from any real saved response.
        job=StorePriceJob.objects.create(discovery=self.scan,status='succeeded',total=1,processed=1)
        self.quote=CatalogPriceObservation.objects.create(discovery=self.scan,job=job,url=URL,
            price_low='4.00',price_high='4.00',currency='USD',availability='Discontinued',
            observed_at=timezone.now())
        save_candidate(self.user,self.scan,0)

    def test_report_detail_history_and_candidate_consistent_without_get_writes(self):
        before=list(CatalogPriceObservation.objects.values())
        for route,args in [('store_research',[self.scan.pk]),('catalog_detail',[self.scan.pk,0]),
                           ('catalog_history',[self.scan.pk,0]),('candidates',[])]:
            with self.subTest(route=route):
                response=self.client.get(reverse(route,args=args))
                self.assertContains(response,'停止供应')
                self.assertNotContains(response,'厂家停产')
        self.assertEqual(list(CatalogPriceObservation.objects.values()),before)
        self.scan.refresh_from_db()
        self.assertEqual(self.scan.products,[self.item])
        self.assertEqual(StorePriceJob.objects.count(),1)

    def test_filter_selects_observed_status_and_does_not_upgrade_unobserved(self):
        self.scan.products += [dict(self.item,url=ROOT+'/product/1',availability='InStock'),
            dict(self.item,url=ROOT+'/product/2',price_observed_at=None)]
        self.scan.save(update_fields=['products'])
        result=build_research(self.scan,availability='Discontinued')
        self.assertEqual([p['url'] for p in result['products']],[URL])
        response=self.client.get(reverse('store_research',args=[self.scan.pk]),{'availability':'Discontinued'})
        self.assertEqual(response.status_code,200)
        self.assertFalse(response.context['filter_form'].errors)
        self.assertEqual([p['url'] for p in response.context['products']],[URL])
        unknown=build_research(self.scan,availability='unknown')
        self.assertEqual([p['url'] for p in unknown['products']],[ROOT+'/product/2'])
