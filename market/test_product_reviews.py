import json
from datetime import timedelta
from django.test import SimpleTestCase, TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from .models import Product, Snapshot, ProductReviewBatch
from .page_import import parse_page

URL='https://www.aliexpress.com/item/1005001234567890.html'


def sample(body,rating='5',**extra):
    return {'reviewBody':body,'name':'Fixture title','reviewRating':{'ratingValue':rating},**extra}


def page(reviews,**extra):
    node={'@type':'Product','url':URL,'name':'Controlled fixture comb',
          'offers':{'@type':'Offer','price':'19.50','priceCurrency':'USD'},'review':reviews}
    node.update(extra)
    return ('<script type="application/ld+json">'+json.dumps(node)+'</script>').encode()


class FileReviewParsingTests(SimpleTestCase):
    def test_sanitize_deduplicate_limit_and_optional_fields(self):
        reviews=[sample('<b>Good quality</b>',datePublished='2026-09-01'),sample('good quality'),sample('Too small','9')]
        reviews += [sample('Fixture review '+str(i)) for i in range(20)]
        parsed=parse_page(page(reviews),URL,'AliExpress')['review_samples']
        self.assertEqual(len(parsed),10)
        self.assertEqual(parsed[0]['body'],'Good quality')
        self.assertEqual(parsed[0]['title'],'Fixture title')
        self.assertEqual(parsed[0]['date'],'2026-09-01')
        self.assertIsNone(parsed[1]['rating'])
        self.assertEqual(parsed[0]['source_url'],URL)

    def test_reject_store_foreign_product_and_keep_matching_alias(self):
        reviews=[sample('Wrong store',itemReviewed={'@type':'Organization','url':URL}),
                 sample('Wrong item',itemReviewed={'url':URL.replace('7890','7891')}),
                 sample('Wrong string item',itemReviewed=URL.replace('7890','7891')),
                 sample('Foreign host',itemReviewed={'url':'https://evil.example/item/1005001234567890.html'}),
                 sample('Correct alias',itemReviewed={'url':URL.replace('www.aliexpress.com','aliexpress.com')})]
        parsed=parse_page(page(reviews),URL,'AliExpress')['review_samples']
        self.assertEqual([s['body'] for s in parsed],['Correct alias'])

    def test_missing_reviews_do_not_invent_body_from_aggregate(self):
        result=parse_page(page([],aggregateRating={'ratingValue':5,'reviewCount':500}),URL,'AliExpress')
        self.assertEqual(result['review_count'],500);self.assertEqual(result['review_samples'],[])

    def test_otto_parent_reviews_not_labelled_variant_only(self):
        target='https://www.otto.de/p/fixture-S0123/?variationId=AAA'
        raw=page([sample('Public fixture',itemReviewed={'url':target.split('?')[0]})],url=target,
            offers={'@type':'Offer','price':10,'priceCurrency':'EUR'})
        self.assertEqual(parse_page(raw,target,'OTTO')['review_samples'][0]['source_url'],target)


class ProductReviewFlowTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('product-reviews',password='test')
        self.client.force_login(self.user)
        self.product=Product.objects.create(title='Fixture comb',url=URL,platform='AliExpress')
        self.at=timezone.localtime(timezone.now()-timedelta(hours=2)).replace(second=0,microsecond=0)
        self.path=reverse('page_import',args=[self.product.pk])
        self.reviews=[sample('Good quality but too small','5'),sample('Good quality and smooth','4'),sample('Broken, bad smell','1')]

    def preview(self,reviews=None,at=None):
        return self.client.post(self.path,{'file':SimpleUploadedFile('fixture.html',page(self.reviews if reviews is None else reviews)),
            'observed_at':(at or self.at).strftime('%Y-%m-%dT%H:%M')})

    def confirm(self,response):
        return self.client.post(self.path,{'action':'confirm','preview':response.context['preview']})

    def test_preview_then_atomic_save_and_repeat_preserve_batch(self):
        preview=self.preview();self.assertContains(preview,'本文件可读取的评论 · 3 条')
        self.assertContains(preview,'Good quality but too small')
        self.assertFalse(ProductReviewBatch.objects.exists());self.assertFalse(Snapshot.objects.exists())
        for _ in range(2):self.assertRedirects(self.confirm(preview),reverse('product_detail',args=[self.product.pk]))
        batch=ProductReviewBatch.objects.get()
        self.assertEqual(batch.snapshot.source,'manual');self.assertEqual(batch.snapshot.observed_at,self.at)
        self.assertEqual(len(batch.samples),3);self.assertEqual(batch.source_url,URL)
        self.assertEqual(Snapshot.objects.count(),1)

    def test_same_time_different_reviews_rejected_without_history_overwrite(self):
        self.confirm(self.preview())
        original=ProductReviewBatch.objects.get()
        self.assertContains(self.confirm(self.preview([sample('Different body')])),'未覆盖历史',status_code=400)
        original.refresh_from_db();self.assertEqual(len(original.samples),3)
        self.assertEqual(ProductReviewBatch.objects.count(),1);self.assertEqual(Snapshot.objects.count(),1)

    def test_commentless_new_quote_keeps_previous_batch_and_latest_date_explicit(self):
        self.confirm(self.preview())
        self.confirm(self.preview([],self.at+timedelta(hours=1)))
        self.assertEqual(Snapshot.objects.count(),2);self.assertEqual(ProductReviewBatch.objects.count(),1)
        response=self.client.get(reverse('product_reviews',args=[self.product.pk]))
        self.assertEqual(response.context['batch'].snapshot.observed_at,self.at)
        self.assertContains(response,'没有评论的新报价不会清除之前的样本')

    def test_report_frequency_issues_and_evidence_links(self):
        self.confirm(self.preview())
        response=self.client.get(reverse('product_reviews',args=[self.product.pk]))
        self.assertContains(response,'尺寸偏小表述');self.assertContains(response,'品质肯定表述')
        self.assertContains(response,'id="review-sample-0"');self.assertContains(response,'href="#review-sample-0"')
        self.assertContains(response,'review-analysis-data')
        self.assertEqual(response.context['review_analysis']['chart']['counts'],[2,0,1,0])
        words={k['word']:k['count'] for k in response.context['review_analysis']['keywords']}
        self.assertEqual(words['quality'],2)

    def test_history_selected_product_boundary_and_get_is_readonly(self):
        self.confirm(self.preview())
        first=ProductReviewBatch.objects.get()
        self.confirm(self.preview([sample('New fixture')],self.at+timedelta(hours=1)))
        response=self.client.get(reverse('product_reviews',args=[self.product.pk]),{'batch':first.pk})
        self.assertEqual(response.context['review_analysis']['sample_count'],3)
        other=Product.objects.create(title='Other',url=URL.replace('7890','7891'))
        response=self.client.get(reverse('product_reviews',args=[other.pk]),{'batch':first.pk})
        self.assertEqual(response.status_code,400)
        self.assertEqual(ProductReviewBatch.objects.count(),2);self.assertEqual(Snapshot.objects.count(),2)

    def test_empty_and_login_and_unsafe_text(self):
        response=self.client.get(reverse('product_reviews',args=[self.product.pk]))
        self.assertContains(response,'还没有保存可归属该商品的评论正文')
        self.assertNotContains(response,'review-analysis-data')
        self.confirm(self.preview([sample('<img src=x onerror=alert(1)>Public fixture')]))
        response=self.client.get(reverse('product_reviews',args=[self.product.pk]))
        self.assertNotContains(response,'<img src=x')
        self.client.logout()
        self.assertEqual(self.client.get(reverse('product_reviews',args=[self.product.pk])).status_code,302)

    def test_saved_catalog_comments_reused_without_mutation_and_import_selected_separately(self):
        from .models import StoreDiscovery
        scan=StoreDiscovery.objects.create(url='https://www.aliexpress.com',status='succeeded',products=[{
            'url':URL,'title':'Catalog fixture','price_observed_at':'2026-10-07 10:00 UTC',
            'review_samples':[{'body':'Catalog public sample','rating':'4','source_url':URL}]}])
        response=self.client.get(reverse('product_reviews',args=[self.product.pk]))
        self.assertContains(response,'Catalog public sample')
        self.assertContains(response,'店铺目录公开采集')
        self.assertContains(response,'value="-1"')
        self.assertFalse(Snapshot.objects.exists());self.assertFalse(ProductReviewBatch.objects.exists())
        self.confirm(self.preview())
        response=self.client.get(reverse('product_reviews',args=[self.product.pk]))
        self.assertNotContains(response,'Catalog public sample')
        response=self.client.get(reverse('product_reviews',args=[self.product.pk]),{'batch':-1})
        self.assertContains(response,'Catalog public sample')
        self.assertEqual(response.context['review_analysis']['sample_count'],1)
        self.assertEqual(Snapshot.objects.count(),1);self.assertEqual(ProductReviewBatch.objects.count(),1)

    def test_legacy_invalid_url_does_not_break_empty_report(self):
        self.product.url='legacy-invalid-link';self.product.save()
        response=self.client.get(reverse('product_reviews',args=[self.product.pk]))
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context['review_analysis']['sample_count'],0)
