"""Controlled one-unit fixtures; no live requests, source prose, or database."""
import json

from bs4 import BeautifulSoup
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .collectors import CollectionError, MAX_BYTES
from .pololu_catalog import ROOT, is_pololu_store, normalize_pololu_product_url, parse_pololu_price

URL = ROOT + '/product/5759'


def page():
    node = {'@type': 'Product', 'name': 'Controlled regulator', 'sku': 5759,
            'description': 'Do not return prose', 'image': 'https://example.com/asset.jpg',
            'offers': {'@type': 'Offer', 'URL': URL, 'price': '8.95',
                       'priceCurrency': 'USD', 'availability': 'InStock'}}
    return '<script type="application/ld+json">' + json.dumps(node) + '</script>' + '''
      <title>Pololu - Controlled regulator</title><h1 id="page_title">Controlled regulator</h1>
      <div class="order_form_with_price_notification"><form action="/cart/add">
      <input type="hidden" name="product[id]" value="5759">
      <input name="product[quantity]" value="1">
      <table class="part_number_and_stock"><tr><td class="part_number">Pololu item #: 5759</td></tr>
      <tr><td><span class="label">Status:</span><span class="value">Active and Preferred</span></td></tr></table>
      <table class="pricing"><tr><th>Price break</th><th>Unit price (US$)</th></tr>
      <tr><td>1</td><td>8.95</td></tr><tr><td>5</td><td>8.23</td></tr>
      <tr><td>100</td><td>6.97</td></tr></table></form></div>'''


def changed_node(edit):
    soup = BeautifulSoup(page(), 'html.parser')
    script = soup.find('script')
    node = json.loads(script.string)
    edit(node)
    script.string = json.dumps(node)
    return str(soup)


def changed_dom(edit):
    soup = BeautifulSoup(page(), 'html.parser')
    edit(soup)
    return str(soup)


class PololuCatalogTests(SimpleTestCase):
    def rejects(self, html, target=URL):
        with self.assertRaises(CollectionError):
            parse_pololu_price(html, target)

    def test_fixed_store_and_strict_target(self):
        self.assertTrue(is_pololu_store(ROOT))
        self.assertEqual(normalize_pololu_product_url(URL), URL)
        for root in (ROOT + '/', 'https://pololu.com', ROOT + ':443', None):
            self.assertFalse(is_pololu_store(root))
        for value in (None, URL + '/', URL + '?', URL + '#', URL + '?quantity=5',
                      URL.replace('www.', ''), URL.replace('.com', '.com:443'),
                      URL.replace('www.', 'user@www.'), URL.replace('.com', '.com.evil.example'),
                      URL.replace('5759', '0'), URL.replace('5759', '05759'),
                      URL.replace('5759', '５７５９'), URL.replace('https:', 'http:'),
                      ' ' + URL, URL + '\n'):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                normalize_pololu_product_url(value)

    def test_one_unit_major_currency_never_minimum_tier_or_variants(self):
        result = parse_pololu_price(page().encode(), URL)
        self.assertEqual((result['price_low'], result['price_high'], result['currency']), ('8.95', '8.95', 'USD'))
        self.assertEqual(result['sku'], '5759')
        self.assertEqual(len(result['variants']), 1)
        self.assertEqual(result['variants'][0]['sku'], '5759')
        self.assertEqual(result['variants'][0]['url'], URL)
        self.assertFalse(result['variants'][0]['is_range'])
        self.assertEqual(result['availability'], 'InStock')
        self.assertEqual((result['content_policy'], result['images'], result['description']), ('facts_only', [], ''))
        for field in ('stock_quantity', 'country', 'shipping', 'tax', 'review_count', 'rating'):
            self.assertNotIn(field, result)

    def test_explicit_schema_visible_and_form_sku_must_match(self):
        for sku in (5758, None, True, 5759.0, '05759', ''):
            self.rejects(changed_node(lambda n: n.update(sku=sku)))
        self.assertEqual(parse_pololu_price(changed_node(lambda n: n.update(sku='5759')), URL)['sku'], '5759')
        self.rejects(changed_dom(lambda s: setattr(s.select_one('.part_number'), 'string', 'Pololu item #: 5758')))
        self.rejects(changed_dom(lambda s: s.select_one('input[name="product[id]"]').__setitem__('value', '5758')))
        self.rejects(page(), ROOT + '/product/5758')

    def test_offer_identity_alias_external_and_extra_conflicting_identity(self):
        for value in (ROOT + '/product/5758', URL + '?x=1', URL + '#p', URL.replace('www.', ''),
                      URL.replace('.com', '.com.evil.example'), URL.replace('.com', '.com:443')):
            self.rejects(changed_node(lambda n: n['offers'].update(URL=value)))
        self.rejects(changed_node(lambda n: n['offers'].update(url=ROOT + '/product/5758')))
        self.rejects(changed_node(lambda n: n.update(url=ROOT + '/product/5758')))
        self.rejects(changed_node(lambda n: n['offers'].update(sku=5758)))
        self.rejects(page() + '<link rel="canonical" href="https://evil.example/product/5759">')

    def test_default_quantity_and_tiers_cannot_be_reinterpreted(self):
        self.rejects(changed_dom(lambda s: s.select_one('input[name="product[quantity]"]').__setitem__('value', '5')))
        self.rejects(changed_node(lambda n: n['offers'].update(price='6.97')))
        self.rejects(changed_dom(lambda s: setattr(s.select('table.pricing td')[0], 'string', '5')))
        self.rejects(changed_dom(lambda s: setattr(s.select('table.pricing td')[2], 'string', '1')))
        self.rejects(changed_dom(lambda s: setattr(s.select('table.pricing td')[1], 'string', '9.00')))
        self.rejects(changed_dom(lambda s: s.select_one('table.pricing tr').decompose()))
        self.rejects(page().replace('8.23', '8.2?'))

    def test_title_price_currency_and_status_conflicts(self):
        self.rejects(changed_node(lambda n: n.update(name='Another regulator')))
        self.rejects(changed_dom(lambda s: setattr(s.title, 'string', 'Pololu - Another regulator')))
        self.rejects(changed_node(lambda n: n['offers'].update(priceCurrency='GBP')))
        self.rejects(page().replace('Unit price (US$)', 'Unit price (EUR)'))
        for state in ('OutOfStock', 'Discontinued', None):
            self.rejects(changed_node(lambda n: n['offers'].update(availability=state)))
        self.rejects(changed_dom(lambda s: setattr(s.select_one('span.value'), 'string', 'Discontinued')))

    def test_unknown_selection_or_wrong_cart_identity_rejected(self):
        self.rejects(page().replace('</form>', '<select name="product[variant]"><option>Unknown</option></select></form>'))
        self.rejects(changed_dom(lambda s: s.find('form').__setitem__('action', '/cart/add-other')))
        self.rejects(page().replace('</form>', '<input name="product[id]" value="5758"></form>'))

    def test_missing_or_duplicate_required_main_evidence_rejected(self):
        for selector in ('h1', 'title', '.part_number', 'input[name="product[id]"]',
                         'input[name="product[quantity]"]', 'table.pricing', 'span.value'):
            self.rejects(changed_dom(lambda s: s.select_one(selector).decompose()))
        self.rejects(page() + '<div class="order_form_with_price_notification"></div>')
        self.rejects(page() + '<script type="application/ld+json">{"@type":"Product"}</script>')

    def test_groups_ranges_and_conditioned_offers_rejected(self):
        self.rejects(changed_node(lambda n: n.update({'@type': 'ProductGroup'})))
        self.rejects(changed_node(lambda n: n.update(offers=[n['offers']])))
        for field, value in (('@type', 'AggregateOffer'), ('lowPrice', '6.97'), ('eligibleQuantity', 5),
                             ('eligibleRegion', 'US'), ('priceSpecification', {}), ('eligibleCustomerType', 'Member')):
            self.rejects(changed_node(lambda n: n['offers'].update({field: value})))

    def test_malformed_json_invalid_amount_encoding_and_size(self):
        self.rejects(page().replace('"sku": 5759', '"sku": 1, "sku": 5759'))
        self.rejects(page() + '<script type="application/ld+json">{</script>')
        for value in ('NaN', '-1', '8.951', None):
            self.rejects(changed_node(lambda n: n['offers'].update(price=value)))
        self.rejects(b'\xff')
        self.rejects(b' ' * (MAX_BYTES + 1))
        self.rejects(None)
