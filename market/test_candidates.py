from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from .models import StoreDiscovery, CatalogCandidate
from .candidates import candidate_rows, save_candidate


def product(name, price='10.00', currency='GBP'):
    value={'title':name,'url':'https://shop.example.com/products/'+name,'price_title':name}
    if price is not None:
        value.update(price_low=price,price_high=price,currency=currency,availability='InStock',price_observed_at='2026-10-08T00:00:00Z')
    return value


class CandidateTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('buyer',password='test-pass-123')
        self.other=get_user_model().objects.create_user('other',password='test-pass-123')
        self.client.force_login(self.user)
        self.scan=StoreDiscovery.objects.create(url='https://shop.example.com',status='succeeded',products=[product('Comb'),product('Oil','20.00'),product('Unknown',None)])

    def add(self,index=0,owner=None):
        return save_candidate(owner or self.user,self.scan,index)[0]

    def test_add_duplicate_and_detail_and_research_status(self):
        route=reverse('candidate_add',args=[self.scan.pk,0])
        self.assertEqual(self.client.get(route).status_code,405)
        self.assertRedirects(self.client.post(route),reverse('candidates'))
        candidate=CatalogCandidate.objects.get(owner=self.user)
        candidate.notes='Keep note';candidate.save()
        self.client.post(route)
        self.assertEqual(CatalogCandidate.objects.filter(owner=self.user).count(),1)
        candidate.refresh_from_db();self.assertEqual(candidate.notes,'Keep note')
        self.assertContains(self.client.get(reverse('catalog_detail',args=[self.scan.pk,0])),'已加入候选清单')
        self.assertContains(self.client.get(reverse('catalog_market')),'已收藏 · 查看清单')
        self.assertEqual(self.client.post(reverse('candidate_add',args=[self.scan.pk,99])).status_code,400)
        bad=StoreDiscovery.objects.create(url=self.scan.url,status='failed',products=self.scan.products)
        self.assertEqual(self.client.post(reverse('candidate_add',args=[bad.pk,0])).status_code,404)
        csrf=Client(enforce_csrf_checks=True);csrf.force_login(self.user)
        self.assertEqual(csrf.post(route).status_code,403)

    def test_ownership_edit_limits_and_html_escape(self):
        own=self.add();other=self.add(1,self.other)
        for name in ['candidate_edit','candidate_archive','candidate_restore']:
            self.assertEqual(self.client.post(reverse(name,args=[other.pk]),{'notes':'leak','stage':'priority'}).status_code,404)
        url=reverse('candidate_edit',args=[own.pk])
        response=self.client.post(url,{'stage':'priority','notes':'<script>alert(1)</script>尺寸待核实'})
        self.assertRedirects(response,reverse('candidates'))
        response=self.client.get(reverse('candidates'),{'q':'尺寸','stage':'priority'})
        self.assertEqual(response.context['page'].paginator.count,1)
        self.assertContains(response,'&lt;script&gt;')
        self.assertNotContains(response,'<script>alert(1)</script>')
        for data in [{'stage':'bad','notes':'bad'},{'stage':'research','notes':'x'*2001}]:
            self.assertEqual(self.client.post(url,data).status_code,200)
            own.refresh_from_db();self.assertEqual(own.stage,'priority')
        self.client.logout()
        for name in ['candidates','candidate_compare']:
            self.assertEqual(self.client.get(reverse(name)).status_code,302)

    def test_soft_archive_restore_and_readd_keep_notes(self):
        saved=self.add();saved.notes='my selection';saved.save()
        archive=reverse('candidate_archive',args=[saved.pk])
        self.assertEqual(self.client.get(archive).status_code,405)
        self.client.post(archive)
        self.assertEqual(self.client.get(reverse('candidates')).context['page'].paginator.count,0)
        self.assertContains(self.client.get(reverse('candidates'),{'archived':'1'}),'my selection')
        self.client.post(reverse('candidate_restore',args=[saved.pk]))
        saved.refresh_from_db();self.assertTrue(saved.active)
        self.client.post(archive);self.add()
        saved.refresh_from_db();self.assertTrue(saved.active);self.assertEqual(saved.notes,'my selection')
        self.assertEqual(CatalogCandidate.objects.count(),1)

    def test_latest_reorders_identity_missing_uses_saved_snapshot(self):
        saved=self.add()
        latest=StoreDiscovery.objects.create(url=self.scan.url,status='succeeded',products=[product('Oil'),product('Comb','15.00')])
        row=candidate_rows([saved])[0]
        self.assertTrue(row['from_latest']);self.assertEqual(row['scan_pk'],latest.pk)
        self.assertEqual(row['catalog_index'],1);self.assertEqual(row['price_low'],'15.00')
        latest.products=[product('Oil')];latest.limited=True;latest.save()
        row=candidate_rows([saved])[0]
        self.assertFalse(row['from_latest']);self.assertEqual(row['price_low'],'10.00')
        self.assertEqual(row['scan_pk'],self.scan.pk);self.assertIsNone(row['selection_id'])
        self.assertContains(self.client.get(reverse('candidates')),'不代表商品已下架')
        self.scan.delete();saved.refresh_from_db()
        self.assertIsNone(saved.discovery_id)
        row=candidate_rows([saved])[0];self.assertEqual(row['price_low'],'10.00');self.assertIsNone(row['scan_pk'])

    def test_normalized_url_and_compare_validations(self):
        first=self.add();second=self.add(1)
        view=reverse('candidate_compare')
        self.assertEqual(self.client.get(view,{'items':[first.pk,second.pk]}).status_code,200)
        duplicate=StoreDiscovery.objects.create(url=self.scan.url,status='succeeded',products=[{**self.scan.products[0],'url':first.url+'/'}])
        self.assertEqual(save_candidate(self.user,duplicate,0)[0].pk,first.pk)
        self.assertEqual(CatalogCandidate.objects.count(),2)
        # 最新目录缺失第二商品，不能静默以旧数据比较。
        self.assertEqual(self.client.get(view,{'items':[first.pk,second.pk]}).status_code,400)
        duplicate.products=self.scan.products;duplicate.save()
        foreign=self.add(1,self.other)
        unknown=self.add(2)
        for values in [[first.pk,first.pk],[first.pk,foreign.pk],[first.pk,unknown.pk],['01',second.pk],['bad',second.pk],[],[first.pk]]:
            self.assertEqual(self.client.get(view,{'items':values}).status_code,400)
        duplicate.products[1]['currency']='USD';duplicate.save()
        self.assertEqual(self.client.get(view,{'items':[first.pk,second.pk]}).status_code,400)
        self.client.post(reverse('candidate_archive',args=[second.pk]))
        self.assertEqual(self.client.get(view,{'items':[first.pk,second.pk]}).status_code,400)

    def test_pagination_and_invalid_stage(self):
        for i in range(32):
            CatalogCandidate.objects.create(owner=self.user,url=f'https://shop.example.com/products/test-{i}',store_url=self.scan.url,saved_item=product(f'test-{i}'))
        response=self.client.get(reverse('candidates'),{'page':2})
        self.assertEqual(len(response.context['products']),2)
        self.assertEqual(self.client.get(reverse('candidates'),{'stage':'bad'}).status_code,400)
