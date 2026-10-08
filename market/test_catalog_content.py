import json
from django.test import SimpleTestCase
from .catalog_prices import parse_catalog_price
from .catalog_content import same_product
from .collectors import CollectionError

URL='https://store.example.com/products/comb'


def page(node, extra=''):
    return '<script type="application/ld+json">'+json.dumps(node).replace('<', '\\u003c')+'</script>'+extra


def product():
    return {'@type':'Product','url':URL,'name':'Beard Comb','description':'<p>Gentle <b>comb</b></p><script>bad()</script>',
            'brand':{'name':'Beardbrand'},'category':'Tools','sku':'ABC',
            'image':[{'@type':'ImageObject','url':'/cdn/comb.jpg'},'https://cdn.shopify.com/comb.jpg',
                     'http://store.example.com/unsafe.jpg','https://localhost/private.jpg','javascript:alert(1)'],
            'offers':[{'name':'Large comb','sku':'L','price':'21','priceCurrency':'USD','url':URL+'?variant=1','availability':'https://schema.org/InStock'},
                      {'name':'Pocket comb','sku':'P','price':'19','priceCurrency':'USD','url':URL+'?variant=2','availability':'https://schema.org/OutOfStock'}]}


class CatalogContentTests(SimpleTestCase):
    def test_content_and_distinct_variant_quotes(self):
        row=parse_catalog_price(page(product()),URL)
        self.assertEqual(row['description'],'Gentle comb')
        self.assertEqual(row['images'],['https://store.example.com/cdn/comb.jpg','https://cdn.shopify.com/comb.jpg'])
        self.assertEqual(row['brand'],'Beardbrand')
        self.assertEqual(row['category'],'Tools')
        self.assertEqual(row['availability'],'Mixed')
        self.assertEqual([v['sku'] for v in row['variants']],['L','P'])
        self.assertEqual([v['price_low'] for v in row['variants']],['21.00','19.00'])
        self.assertEqual(row['variants'][1]['url'],URL+'?variant=2')

    def test_other_product_offer_rejected_and_aggregate_not_single_price(self):
        node=product();node['offers'][1]['url']='https://store.example.com/products/other'
        with self.assertRaises(CollectionError):parse_catalog_price(page(node),URL)
        node['offers']={'@type':'AggregateOffer','lowPrice':'10','highPrice':'25','priceCurrency':'USD'}
        row=parse_catalog_price(page(node),URL)
        self.assertTrue(row['variants'][0]['is_range'])
        self.assertEqual(row['variants'][0]['price_high'],'25.00')
        self.assertFalse(same_product('https://user@store.example.com/products/comb',URL))
        self.assertFalse(same_product('https://store.example.com:123/products/comb',URL))

    def test_content_limits_and_product_group(self):
        node=product();node['description']='a'*6100;node['image']=['/cdn/'+str(i)+'.jpg' for i in range(12)]
        row=parse_catalog_price(page(node),URL)
        self.assertEqual(len(row['description']),6000)
        self.assertTrue(row['description_limited'])
        self.assertEqual(len(row['images']),6)
        node={'@type':'ProductGroup','url':URL,'name':'Comb','hasVariant':[
            {'@type':'Product','url':URL+'?variant=1','name':'Small comb','size':'Small','color':'Blue','image':'/cdn/small.jpg',
             'offers':{'price':'12','priceCurrency':'USD','url':URL+'?variant=1'}}]}
        row=parse_catalog_price(page(node),URL)
        self.assertEqual(row['variants'][0]['size'],'Small')
        self.assertEqual(row['variants'][0]['color'],'Blue')
        self.assertEqual(row['images'],['https://store.example.com/cdn/small.jpg'])

    def test_public_widget_comments_require_product_identity(self):
        node=product();node['aggregateRating']={'ratingValue':'4.72','reviewCount':805}
        widget='''<link rel="canonical" href="URL"><div class="jdgm-review-widget" data-product-title="Beard Comb">
        <div class="jdgm-rev" data-product-url="/products/comb"><b class="jdgm-rev__title">Nice</b><div class="jdgm-rev__body"><p>Easy to use</p></div><span class="jdgm-rev__rating" data-score="5"></span><time datetime="2026-09-18"></time></div>
        <div class="jdgm-rev" data-product-url="/products/other"><div class="jdgm-rev__body">Wrong product</div></div>
        <div class="jdgm-rev"><div class="jdgm-rev__body">Unattributed</div></div></div>'''.replace('URL',URL)
        row=parse_catalog_price(page(node,widget),URL)
        self.assertEqual(row['rating'],'4.72')
        self.assertEqual(row['review_count'],805)
        self.assertIsNone(row['rating_count'])
        self.assertEqual(len(row['review_samples']),1)
        self.assertEqual(row['review_samples'][0]['body'],'Easy to use')
        self.assertEqual(row['review_samples'][0]['rating'],'5.00')
        self.assertTrue(row['review_samples_limited'])
        for unsafe in [widget.replace('data-product-title="Beard Comb"','data-product-title="Other"'),
                       widget.replace('href="'+URL+'"','href="https://store.example.com/products/other"'),widget+widget]:
            self.assertEqual(parse_catalog_price(page(node,unsafe),URL)['review_samples'],[])

    def test_offer_identity_with_verified_canonical_and_no_product_url(self):
        node=product();node.pop('url')
        canonical='<link rel="canonical" href="'+URL+'">'
        row=parse_catalog_price(page(node,canonical),URL)
        self.assertEqual(row['price_low'],'19.00')
        self.assertEqual(row['price_title'],'Beard Comb')
        for extra in ['',canonical+canonical,canonical.replace('/products/comb','/products/other')]:
            with self.assertRaises(CollectionError):parse_catalog_price(page(node,extra),URL)

    def test_canonical_fallback_cannot_override_wrong_or_missing_offer_identity(self):
        node=product();canonical='<link rel="canonical" href="'+URL+'">'
        node['url']='https://store.example.com/products/other'
        with self.assertRaises(CollectionError):parse_catalog_price(page(node,canonical),URL)
        node.pop('url');node['offers'][0].pop('url')
        with self.assertRaises(CollectionError):parse_catalog_price(page(node,canonical),URL)
