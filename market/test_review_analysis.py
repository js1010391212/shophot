from django.test import SimpleTestCase, TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import StoreDiscovery
from .review_analysis import analyze_reviews

URL='https://shop.example.com/products/comb'

class ReviewAnalysisTests(SimpleTestCase):
    def test_review_coverage_not_occurrences_and_dedup(self):
        item={'url':URL,'title':'Beard Comb','brand':'Brand','review_samples':[
            {'body':'Nice nice nice comb. Good quality','rating':'5'},
            {'body':'Nice design and quality comb','rating':'4'},
            {'body':'Nice nice nice comb. Good quality','rating':'1'}]}
        data=analyze_reviews(item)
        self.assertEqual(data['sample_count'],2)
        words={row['word']:row for row in data['keywords']}
        self.assertEqual(words['nice']['count'],2)
        self.assertEqual(words['quality']['share'],100)
        self.assertNotIn('comb',words)
        self.assertEqual(data['positive_count'],2)

    def test_rating_not_sentiment_and_self_inflicted_breakage(self):
        data=analyze_reviews({'url':URL,'review_samples':[
            {'body':"Nice quality but too small, doesn't do enough",'rating':'5'},
            {'body':'broke because of my own doing','rating':'5'},
            {'body':'Bad smell','rating':'0'},
            {'body':'fine','rating':'3'}, {'body':'not rated','rating':None}]})
        self.assertEqual(data['chart']['counts'],[2,1,1,1])
        issues={r['name']:r['evidence'] for r in data['issues']}
        self.assertEqual(issues['尺寸偏小表述'],[0])
        self.assertEqual(issues['效果不足表述'],[0])
        self.assertNotIn('破损表述',issues)
        self.assertEqual(data['low_count'],1)
        self.assertEqual(data['praise'][0]['evidence'],[0])
        negative=analyze_reviews({'url':URL,'review_samples':[{'body':'Not good quality. 不好用','rating':'1'}]})
        self.assertEqual(negative['praise'],[])
        negated=analyze_reviews({'url':URL,'review_samples':[{'body':'No bad smell, not too small, no pulling','rating':'5'}]})
        self.assertEqual(negated['issues'],[])
        self.assertEqual(negated['praise'][0]['name'],'使用顺滑表述')

    def test_unknown_empty_wrong_product_and_chinese(self):
        for item in [{},{'review_samples':None},{'url':URL,'review_samples':[{'body':'Other','source_url':'https://shop.example.com/products/other'}]}]:
            self.assertEqual(analyze_reviews(item)['sample_count'],0)
        data=analyze_reviews({'url':URL,'review_samples':[{'body':'质量不错，但是太小','rating':'5'}, {'body':'质量好但尺寸偏小','rating':'9'}]})
        self.assertEqual(data['unknown_count'],1)
        self.assertEqual(next(k['count'] for k in data['keywords'] if k['word']=='质量'),2)
        self.assertEqual(next(i['count'] for i in data['issues'] if i['name']=='尺寸偏小表述'),2)

class ReviewAnalysisViewTests(TestCase):
    def test_evidence_anchors_safe_text_and_missing_samples(self):
        self.client.force_login(get_user_model().objects.create_user('reviews',password='test-pass-123'))
        scan=StoreDiscovery.objects.create(url='https://shop.example.com',status='succeeded',products=[
            {'url':URL,'title':'Comb','review_samples':[{'body':'Nice quality too small','rating':'5'},{'body':'Nice quality','rating':'4'}]}])
        response=self.client.get(reverse('catalog_detail',args=[scan.pk,0]))
        self.assertContains(response,'评论样本分析')
        self.assertContains(response,'尺寸偏小表述')
        self.assertContains(response,'id="review-sample-0"')
        self.assertContains(response,'href="#review-sample-0"')
        self.assertContains(response,'review-analysis-data')
        scan.products[0]['review_samples']=[];scan.save()
        response=self.client.get(reverse('catalog_detail',args=[scan.pk,0]))
        self.assertContains(response,'尚无有效商品评论')
        self.assertNotContains(response,'review-analysis-data')
