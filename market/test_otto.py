import json
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from .models import Product, Snapshot, CollectionJob
from .otto import normalize_otto_url, parse_page
from .jobs import run_next

URL='https://www.otto.de/p/test-S0123/'


def page(**changes):
    product={'@type':'Product','url':URL,'name':'Controlled fixture', 'sku':'SKU1',
             'offers':{'@type':'Offer','price':'10.90','priceCurrency':'EUR'},
             'aggregateRating':{'ratingValue':'5','reviewCount':1}}
    product.update(changes)
    return ('<script type="application/ld+json">'+json.dumps(product)+'</script>').encode()


class OttoParserTests(SimpleTestCase):
    def test_url_identity_and_variant(self):
        self.assertEqual(normalize_otto_url(URL+'?variationId=ABC123&utm_source=test'),URL+'?variationId=ABC123')
        for url in ['http://www.otto.de/p/test-S0123/', 'https://otto.de.example.com/p/test-S0123/',
                    'https://www.otto.de/seller/test/',URL+'?variationId=a&variationId=b',URL+'?variationId=']:
            with self.subTest(url=url),self.assertRaises(ValidationError):normalize_otto_url(url)

    def test_explicit_quote_zero_and_unknown_fields(self):
        result=parse_page(page(),URL)
        self.assertEqual((result['price'],result['currency'],result['rating'],result['review_count']),('10.90','EUR','5.00',1))
        result=parse_page(page(aggregateRating={'ratingValue':0,'reviewCount':0}),URL)
        self.assertEqual((result['rating'],result['review_count']),('0.00',0))
        result=parse_page(page(aggregateRating={'ratingValue':9,'reviewCount':'many'}),URL)
        self.assertIsNone(result['rating']);self.assertIsNone(result['review_count'])

    def test_rejects_wrong_product_ambiguous_or_missing_price(self):
        for raw in [page(url=URL.replace('S0123','S9999')),page()+page(),page(offers={'@type':'AggregateOffer','lowPrice':1,'priceCurrency':'EUR'}),
                    page(offers=[{'@type':'Offer','price':10,'priceCurrency':'EUR'}]*2),
                    page(offers={'@type':'Offer','price':'NaN','priceCurrency':'EUR'}),
                    page(offers={'@type':'Offer','price':10,'priceCurrency':None}),b'<script>window.KPSDK={}</script>',b'\xff']:
            with self.subTest(raw=raw[:80]),self.assertRaises(ValidationError):parse_page(raw,URL)

    def test_exact_variant_required(self):
        target=URL+'?variationId=AAA'
        with self.assertRaises(ValidationError):parse_page(page(),target)
        offers=[{'@type':'Offer','url':URL+'?variationId='+variant,'price':price,'priceCurrency':'EUR'} for variant,price in [('AAA','12'),('BBB','24')]]
        self.assertEqual(parse_page(page(offers=offers),target)['price'],'12.00')
        self.assertEqual(parse_page(page(offers=offers),target)['specification'],'AAA')


class OttoImportTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('otto-test',password='test')
        self.client.force_login(self.user)
        self.product=Product.objects.create(title='待识别竞品 · test',url=URL,platform='OTTO')
        self.path=reverse('otto_import',args=[self.product.pk])
        self.at=timezone.localtime(timezone.now()-timedelta(hours=1)).replace(second=0,microsecond=0)

    def preview(self,raw=None,**fields):
        data={'file':SimpleUploadedFile('controlled-fixture.html',page() if raw is None else raw,content_type='text/html'),
              'observed_at':self.at.strftime('%Y-%m-%dT%H:%M'),'context':'fixture quote conditions'}
        data.update(fields)
        return self.client.post(self.path,data)

    def test_home_flow_and_read_only_get(self):
        response=self.client.post(reverse('analyze_competitor'),{'platform':'Auto','url':URL+'?utm_source=test'})
        self.assertRedirects(response,self.path)
        self.assertEqual(Product.objects.count(),1)
        self.client.get(self.path)
        self.assertFalse(CollectionJob.objects.exists());self.assertFalse(Snapshot.objects.exists())

    def test_preview_confirmation_and_idempotency(self):
        response=self.preview();self.assertEqual(response.status_code,200)
        self.assertContains(response,'fixture quote conditions')
        self.assertFalse(Snapshot.objects.exists())
        token=response.context['preview']
        for _ in range(2):
            response=self.client.post(self.path,{'action':'confirm','preview':token})
            self.assertRedirects(response,reverse('product_detail',args=[self.product.pk]))
        quote=Snapshot.objects.get()
        self.assertEqual((str(quote.price),quote.currency,quote.source),('10.90','EUR',Snapshot.Source.MANUAL))
        self.assertEqual(quote.observed_at,self.at)
        self.assertIsNone(quote.sales);self.assertIn('SKU1',quote.context)
        self.product.refresh_from_db();self.assertEqual(self.product.title,'Controlled fixture')

    def test_invalid_tokens_and_owner_binding(self):
        token=self.preview().context['preview']
        self.assertEqual(self.client.post(self.path,{'action':'confirm','preview':token+'bad'}).status_code,400)
        self.client.force_login(get_user_model().objects.create_user('other-otto'))
        self.assertEqual(self.client.post(self.path,{'action':'confirm','preview':token}).status_code,400)
        self.assertFalse(Snapshot.objects.exists())
        self.client.logout();self.assertEqual(self.client.get(self.path).status_code,302)

    def test_failures_preserve_history_and_do_not_overwrite_title(self):
        self.product.title='My chosen name';self.product.save()
        token=self.preview().context['preview']
        old=Snapshot.objects.create(product=self.product,observed_at=self.at,source=Snapshot.Source.MANUAL,price=99,currency='EUR')
        response=self.client.post(self.path,{'action':'confirm','preview':token})
        self.assertContains(response,'未覆盖历史',status_code=400)
        self.assertEqual(self.preview(b'<script>window.KPSDK={}</script>').status_code,400)
        self.assertEqual(self.preview(observed_at=(self.at+timedelta(days=2)).strftime('%Y-%m-%dT%H:%M')).status_code,400)
        old.refresh_from_db();self.assertEqual(old.price,99);self.assertEqual(Snapshot.objects.count(),1)
        self.product.refresh_from_db();self.assertEqual(self.product.title,'My chosen name')

    def test_no_automatic_request_for_otto(self):
        self.client.post(reverse('collect_product',args=[self.product.pk]))
        self.assertFalse(CollectionJob.objects.exists())
        job=CollectionJob.objects.create(product=self.product)
        with patch('market.jobs.collect') as collect:
            run_next();collect.assert_not_called()
        job.refresh_from_db();self.assertEqual(job.status,'failed');self.assertIn('安全验证',job.message)
        self.assertFalse(Snapshot.objects.exists())

    def test_confirmation_expiry_product_binding_and_csrf(self):
        token=self.preview().context['preview']
        other=Product.objects.create(title='Other',url=URL.replace('S0123','S9999'),platform='OTTO')
        self.assertEqual(self.client.post(reverse('otto_import',args=[other.pk]),{'action':'confirm','preview':token}).status_code,400)
        with patch('django.core.signing.time.time',return_value=timezone.now().timestamp()+1201):
            self.assertEqual(self.client.post(self.path,{'action':'confirm','preview':token}).status_code,400)
        from django.test import Client
        strict=Client(enforce_csrf_checks=True);strict.force_login(self.user)
        self.assertEqual(strict.post(self.path,{'action':'confirm','preview':token}).status_code,403)
        self.assertFalse(Snapshot.objects.exists())

    def test_preview_escapes_html_and_confirm_keeps_user_title(self):
        self.product.title='Chosen title';self.product.save()
        response=self.preview(page(name='<img src=x onerror=alert(1)>Fixture'))
        self.assertNotContains(response,'<img src=x')
        self.client.post(self.path,{'action':'confirm','preview':response.context['preview']})
        self.product.refresh_from_db();self.assertEqual(self.product.title,'Chosen title')
