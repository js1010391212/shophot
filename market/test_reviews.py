from django.test import SimpleTestCase
from .reviews import product_reviews
from .catalog_prices import parse_catalog_price

class ReviewTests(SimpleTestCase):
    def test_missing_not_zero_and_marketing_not_product_rating(self):
        data=product_reviews({'name':'Shampoo'},'https://store.example/products/shampoo')
        self.assertIsNone(data['rating'])
        self.assertIsNone(data['review_count'])
        self.assertEqual(data['review_samples'],[])
        self.assertEqual(data['review_source'],'')
        page='<div aria-label="4/5 rating">8,000+ happy customers</div><script type="application/ld+json">{"@type":"Product","url":"https://store.example/products/shampoo","name":"Shampoo","offers":{"price":"9","priceCurrency":"GBP"}}</script>'
        self.assertIsNone(parse_catalog_price(page,'https://store.example/products/shampoo')['rating'])

    def test_counts_are_distinct_and_samples_do_not_invent_total(self):
        node={'aggregateRating':{'ratingValue':'4.7','ratingCount':100},'review':{'reviewBody':'Good coat','reviewRating':{'ratingValue':5}}}
        data=product_reviews(node,'https://store.example/products/coat')
        self.assertEqual(data['rating'],'4.70')
        self.assertEqual(data['rating_count'],100)
        self.assertIsNone(data['review_count'])
        self.assertEqual(data['review_samples'][0]['rating'],'5.00')
        self.assertEqual(data['review_samples'][0]['source_url'],'https://store.example/products/coat')

    def test_invalid_scale_count_and_actual_zero(self):
        data=product_reviews({'aggregateRating':{'ratingValue':9,'bestRating':10,'reviewCount':0,'ratingCount':-1}},'url')
        self.assertIsNone(data['rating'])
        self.assertEqual(data['review_count'],0)
        self.assertIsNone(data['rating_count'])

    def test_bounded_samples_and_plain_text(self):
        data=product_reviews({'review':[{'reviewBody':f'<b>Sample {i}</b>','datePublished':'2026-10-07'} for i in range(20)]},'url')
        self.assertEqual(len(data['review_samples']),10)
        self.assertEqual(data['review_samples'][0]['body'],'Sample 0')
        self.assertTrue(data['review_samples_limited'])

    def test_reviews_of_other_product_or_store_are_excluded(self):
        data=product_reviews({'review':[
            {'reviewBody':'Wrong product','itemReviewed':{'url':'https://store.example/products/other'}},
            {'reviewBody':'Store service','itemReviewed':{'@type':'Organization'}},
            {'reviewBody':'Correct product','itemReviewed':{'url':'/products/coat'}}]},'https://store.example/products/coat')
        self.assertEqual([r['body'] for r in data['review_samples']],['Correct product'])
