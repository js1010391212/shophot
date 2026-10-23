"""Source terms are display copies, never new evidence or price normalization."""
from copy import deepcopy
from types import SimpleNamespace
from django.template.loader import render_to_string
from django.test import SimpleTestCase
from .catalog_research import catalog_rows

ROOT='https://www.pololu.com'
URL=ROOT+'/product/5359'


def item():
    return {'url':URL,'title':'Controlled item','sku':'5359','currency':'USD',
        'price_low':'7.95','price_high':'7.95','price_observed_at':'2026-10-22 23:13 UTC',
        'availability':'InStock','content_policy':'facts_only','price_source':URL,'content_source':URL,
        'variants_limited':False,'quote_scope':{'original':'untouched'},'variants':[{
            'url':URL,'sku':'5359','name':'Controlled item','currency':'USD','price_low':'7.95',
            'price_high':'7.95','availability':'InStock','is_range':False,'size':'','color':''}]}


class CatalogComparisonTermsTests(SimpleTestCase):
    def rows(self, value=None, root=ROOT):
        return catalog_rows([SimpleNamespace(pk=1,url=root,products=[value if value is not None else item()])])

    def test_strict_current_source_scope_does_not_change_original_facts(self):
        original=item();before=deepcopy(original)
        rows=self.rows(original)
        self.assertIn('当前适配核验范围：数量 1',rows[0]['comparison_quantity_note'])
        self.assertIn('历史记录未独立保存数量字段',rows[0]['comparison_quantity_note'])
        self.assertEqual(original,before)
        for field in before:
            self.assertEqual(rows[0][field],before[field])
        self.assertIn('库存数量未知',rows[0]['comparison_inventory_note'])

    def test_other_sources_aliases_and_insufficient_old_metadata_stay_unknown(self):
        changes=[{'content_policy':None},{'price_source':None},{'content_source':None},
            {'sku':None},{'currency':'EUR'},{'variants':[]},{'variants':None},
            {'variants_limited':True},{'price_high':'8.00'},{'price_observed_at':'old'},
            {'url':URL+'?x=1'},{'availability':'OutOfStock'}]
        for change in changes:
            with self.subTest(change=change):
                self.assertIn('数量条件未知',self.rows({**item(),**change})[0]['comparison_quantity_note'])
        for root in ['https://pololu.com','https://www.pololu.com.evil.example','https://www.adafruit.com','https://other.example']:
            with self.subTest(root=root):
                self.assertIn('数量条件未知',self.rows(root=root)[0]['comparison_quantity_note'])
        self.assertIn('数量条件未知',self.rows({'url':URL,'title':'Old metadata','price_low':'7.95','price_high':'7.95','currency':'USD','price_observed_at':'2026-10-22T23:13:40Z'})[0]['comparison_quantity_note'])

    def test_variant_conflicts_do_not_inherit_single_unit_scope(self):
        for change in [{'sku':'5358'},{'url':URL+'/other'},{'currency':'EUR'},
            {'price_low':'1.00'},{'price_high':'9.00'},{'is_range':True},
            {'availability':'OutOfStock'},{'size':'5 units'},{'color':'5'},{'price_low':'NaN'}]:
            with self.subTest(change=change):
                data=item();data['variants'][0].update(change)
                self.assertIn('数量条件未知',self.rows(data)[0]['comparison_quantity_note'])

    def test_real_comparison_template_keeps_each_source_and_boundary_visible(self):
        pololu=self.rows()[0]
        other=item();other.update(url='https://www.adafruit.com/product/5359',currency='USD')
        other_rows=catalog_rows([SimpleNamespace(pk=2,url='https://www.adafruit.com',products=[other])])
        html=render_to_string('market/catalog_compare.html',{'products':[pololu,*other_rows],'currency':'USD','chart_data':{}})
        for text in ['www.pololu.com','www.adafruit.com','数量 1 的 USD 单件价','数量条件未知',
            '库存数量未知','不保证现货或履约','同币种或相同 SKU 字符串不证明同款',
            '同件数','相同市场税运条件或可替代性','收货国家未知','7.95','2026-10-22 23:13 UTC']:
            self.assertIn(text,html)
        self.assertEqual(html.count('当前适配核验范围：数量 1'),1)
