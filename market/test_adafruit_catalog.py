"""Controlled fixtures, no source HTML, database, or network required."""
import json

from bs4 import BeautifulSoup
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .adafruit_catalog import (
    ROOT, is_adafruit_store, normalize_adafruit_product_url, parse_adafruit_price,
)
from .collectors import CollectionError, MAX_BYTES

URL = ROOT + '/product/4864'


def page():
    node = {'@type': 'Product', 'name': 'Controlled Board', 'sku': 4864,
            'description': 'Not returned', 'image': 'https://example.com/image.png',
            'offers': {'@type': 'Offer', 'url': 'https://adafruit.com/product/4864',
                       'price': 4, 'priceCurrency': 'USD',
                       'availability': 'http://schema.org/OutOfStock'}}
    return ('<script type="application/ld+json">' + json.dumps(node) + '</script>' + '''
      <meta property="product:price:amount" content="4.00">
      <meta property="product:price:currency" content="USD">
      <div class="mobile-product-header"><h1>Controlled Board</h1>
        <div class="product_id">Product ID: <span>4864</span></div>
        <div class="product-price"><span>$4.00</span></div></div>
      <div id="prod-right-side"><h1 class="products_name">Controlled Board</h1>
        <div class="product_id">Product ID: <span>4864</span></div>
        <div id="prod-price"><span itemprop="price" content="4">
          <meta itemprop="priceCurrency" content="USD">$4.00</span></div>
        <div id="prod-stock"><label>There are multiple versions</label>
          <ol class="meta_pid_boxes"><li class="ui-selected" data-part-id="4864">
            <a aria-current="page" href="/product/4864"><span class="option_name">Bare board</span>
              <span class="option_meta">Out of stock</span></a></li>
            <li data-part-id="4883"><a href="/product/4883"><span class="option_name">Other version</span>
              <span class="option_meta">$9.00</span></a></li></ol>
          <div itemprop="availability">Out of stock</div></div></div>''')


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


def revision_page(suffix='v1.1'):
    """Controlled version of the corroborated source title convention."""
    soup = BeautifulSoup(page(), 'html.parser')
    soup.select_one('.meta_pid_boxes').decompose()
    soup.select_one('label').decompose()
    for header in soup.select('h1'):
        header.string = 'Controlled Board - ' + suffix
    title = soup.new_tag('title')
    title.string = ('Controlled Board [' + suffix + '] : Adafruit Industries, '
                    'Unique & fun DIY electronics and kits')
    soup.append(title)
    for key, value in (('property', 'og:title'), ('name', 'twitter:title')):
        meta = soup.new_tag('meta', attrs={key: value, 'content': 'Controlled Board'})
        soup.append(meta)
    return str(soup)


class AdafruitCatalogTests(SimpleTestCase):
    def rejects(self, html, target=URL):
        with self.assertRaises(CollectionError):
            parse_adafruit_price(html, target)

    def test_store_and_normalizer_are_exact(self):
        self.assertTrue(is_adafruit_store(ROOT))
        self.assertEqual(normalize_adafruit_product_url(URL), URL)
        for value in (None, ROOT + '/', 'https://adafruit.com', ROOT + ':443', ROOT.upper()):
            self.assertFalse(is_adafruit_store(value))
        for value in (None, 'https://adafruit.com/product/4864', URL + '/', URL + '?', URL + '#',
                      URL + '?currency=USD', URL + '#item', URL.replace('https:', 'http:'),
                      URL.replace('.com', '.com:443'), URL.replace('www.', 'user@www.'),
                      URL.replace('.com', '.com.evil.example'), URL.replace('4864', '0'),
                      URL.replace('4864', '04864'), URL.replace('4864', '４８６４'),
                      ' ' + URL, URL + '\n', ROOT + '/products/4864'):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                normalize_adafruit_product_url(value)

    def test_major_units_explicit_sku_selected_only_and_no_copied_content(self):
        result = parse_adafruit_price(page().encode(), URL)
        self.assertEqual((result['price_low'], result['price_high'], result['currency']),
                         ('4.00', '4.00', 'USD'))
        self.assertEqual(result['sku'], '4864')
        self.assertEqual(result['availability'], 'OutOfStock')
        self.assertEqual(result['price_source'], URL)
        self.assertTrue(result['price_observed_at'].endswith(' UTC'))
        self.assertEqual(len(result['variants']), 1)
        self.assertEqual(result['variants'][0]['name'], 'Bare board')
        self.assertEqual(result['variants'][0]['url'], URL)
        self.assertFalse(result['variants'][0]['is_range'])
        self.assertEqual((result['images'], result['description'], result['content_policy']),
                         ([], '', 'facts_only'))
        for field in ('rating', 'review_count', 'quantity', 'tax', 'shipping', 'country'):
            self.assertNotIn(field, result)

    def test_explicit_numeric_and_string_sku_only(self):
        self.assertEqual(parse_adafruit_price(changed_node(lambda n: n.update(sku='4864')), URL)['sku'], '4864')
        for sku in (None, True, 4864.0, '04864', 4883, ''):
            with self.subTest(sku=sku):
                self.rejects(changed_node(lambda n: n.update(sku=sku)))
        self.rejects(changed_node(lambda n: n.pop('sku')))
        self.rejects(page(), ROOT + '/product/4883')

    def test_wrong_visible_identity_or_title(self):
        self.rejects(changed_dom(lambda s: setattr(s.select_one('.product_id span'), 'string', '4883')))
        self.rejects(changed_node(lambda n: n.update(name='Different product')))
        self.rejects(changed_dom(lambda s: s.select_one('#prod-right-side .product_id').decompose()))

    def test_schema_alias_is_evidence_only_and_other_identity_rejected(self):
        self.assertEqual(parse_adafruit_price(changed_node(lambda n: n['offers'].update(url=URL)), URL)['sku'], '4864')
        for value in (URL + '?x=1', URL + '#item', URL.replace('.com', '.com:443'),
                      URL.replace('www.', 'www.adafruit.com@evil.'),
                      URL.replace('4864', '4883'), '/product/4864', None,
                      'https://adafruit.com.evil.example/product/4864'):
            with self.subTest(value=value):
                self.rejects(changed_node(lambda n: n['offers'].update(url=value)))
                self.rejects(changed_node(lambda n: n.update(url=value)))
        self.rejects(changed_node(lambda n: n.update({'@id': URL + '#product'})))
        self.rejects(changed_node(lambda n: n['offers'].update(sku=4883)))
        self.rejects(page() + '<link rel="canonical" href="https://evil.example/product/4864">')

    def test_multiple_products_or_group_and_range_rejected(self):
        self.rejects(page() + '<script type="application/ld+json">{"@type":"Product","sku":4883}</script>')
        self.rejects(changed_node(lambda n: n.update({'@type': 'ProductGroup'})))
        self.rejects(changed_node(lambda n: n.update(offers=[n['offers']])))
        for field, value in (('@type', 'AggregateOffer'), ('lowPrice', 4), ('priceSpecification', {}),
                             ('eligibleQuantity', {'minValue': 10}), ('eligibleCustomerType', 'Member'),
                             ('eligibleRegion', 'US')):
            self.rejects(changed_node(lambda n: n['offers'].update({field: value})))

    def test_all_price_representations_must_agree(self):
        self.rejects(changed_node(lambda n: n['offers'].update(price='4.01')))
        self.rejects(changed_dom(lambda s: s.select_one('#prod-price [itemprop=price]').__setitem__('content', '400')))
        self.rejects(changed_dom(lambda s: s.select_one('meta[property="product:price:amount"]').__setitem__('content', '9.00')))
        self.rejects(changed_dom(lambda s: setattr(s.select_one('.mobile-product-header .product-price span'), 'string', '$9.00')))
        for value in ('NaN', '-1', '4.001', None):
            self.rejects(changed_node(lambda n: n['offers'].update(price=value)))
        self.rejects(page().replace('$4.00</span></div>\n        <div id="prod-stock"', '$9.00</span></div>\n        <div id="prod-stock"'))

    def test_currency_missing_conflicting_or_unverified(self):
        self.rejects(changed_node(lambda n: n['offers'].update(priceCurrency='EUR')))
        self.rejects(changed_dom(lambda s: s.select_one('[itemprop=priceCurrency]').__setitem__('content', 'EUR')))
        self.rejects(changed_dom(lambda s: s.select_one('meta[property="product:price:currency"]').__setitem__('content', 'EUR')))
        self.rejects(page().replace('USD', 'EUR'))

    def test_missing_required_fields_and_duplicate_main_price(self):
        for selector in ('#prod-price', '[itemprop=priceCurrency]', '.products_name',
                         'meta[property="product:price:amount"]', 'meta[property="product:price:currency"]',
                         '#prod-stock [itemprop=availability]', '.option_name', '.option_meta'):
            with self.subTest(selector=selector):
                self.rejects(changed_dom(lambda s: s.select_one(selector).decompose()))
        self.rejects(page() + '<div id="prod-price">$9.00</div>')

    def test_selection_must_be_explicit_and_consistent(self):
        self.rejects(changed_dom(lambda s: s.select_one('li.ui-selected').__setitem__('data-part-id', '4883')))
        self.rejects(changed_dom(lambda s: s.select_one('a[aria-current]').__setitem__('href', '/product/4883')))
        self.rejects(changed_dom(lambda s: s.select_one('a[aria-current]').attrs.pop('aria-current')))
        self.rejects(changed_dom(lambda s: s.select_one('li.ui-selected').attrs.pop('class')))
        soup = BeautifulSoup(page(), 'html.parser')
        duplicate = BeautifulSoup(str(soup.select_one('.meta_pid_boxes')), 'html.parser').ol
        soup.append(duplicate)
        self.assertEqual(parse_adafruit_price(str(soup), URL)['variants'][0]['name'], 'Bare board')
        duplicate.select_one('.option_name').string = 'Another version'
        self.rejects(str(soup))

    def test_multiple_selected_options_or_unknown_control_rejected(self):
        self.rejects(changed_dom(lambda s: s.select_one('li[data-part-id="4883"]').__setitem__('class', 'ui-selected')))
        self.rejects(page().replace('<div id="prod-stock">', '<div id="prod-stock"><select name="variant"><option>Unknown</option></select>'))
        self.rejects(page().replace('<div id="prod-stock">', '<div id="prod-stock"><select name="options"><option>Unknown</option></select>'))

    def test_in_stock_selected_option_price_must_match(self):
        html = page().replace('schema.org/OutOfStock', 'schema.org/InStock').replace('Out of stock', 'In stock')
        self.assertEqual(parse_adafruit_price(html, URL)['availability'], 'InStock')
        soup = BeautifulSoup(html, 'html.parser')
        soup.select_one('.option_meta').string = '$4.00'
        self.assertEqual(parse_adafruit_price(str(soup), URL)['price_low'], '4.00')
        soup.select_one('.option_meta').string = '$9.00'
        self.rejects(str(soup))

    def test_absent_controls_only_with_other_strong_evidence(self):
        soup = BeautifulSoup(page(), 'html.parser')
        soup.select_one('.meta_pid_boxes').decompose()
        self.rejects(str(soup))  # A multiple-version declaration without a selection.
        soup.select_one('label').decompose()
        self.assertEqual(parse_adafruit_price(str(soup), URL)['variants'][0]['name'], 'Controlled Board')
        soup.select_one('#prod-right-side .product_id').decompose()
        self.rejects(str(soup))

    def test_availability_conflict_and_unknown_fail_closed(self):
        self.rejects(changed_node(lambda n: n['offers'].update(availability='https://schema.org/InStock')))
        self.rejects(changed_node(lambda n: n['offers'].update(availability='Unknown')))
        self.rejects(changed_dom(lambda s: setattr(s.select_one('.option_meta'), 'string', '$4.00')))

    def test_malformed_json_duplicate_keys_encoding_and_size(self):
        self.rejects(page() + '<script type="application/ld+json">{</script>')
        self.rejects(page().replace('"sku": 4864', '"sku": 4883, "sku": 4864'))
        self.rejects(page().replace('"price": 4', '"price": NaN'))
        self.rejects(b'\xff')
        self.rejects(b' ' * (MAX_BYTES + 1))
        self.rejects(None)
        self.rejects(page(), URL + '?currency=USD')

    def test_corroborated_revision_keeps_full_visible_name_and_sku(self):
        for suffix in ('v1.1', 'V 2.1a', 'v3.0', 'FT232RL'):
            with self.subTest(suffix=suffix):
                result = parse_adafruit_price(revision_page(suffix), URL)
                self.assertEqual(result['price_title'], 'Controlled Board - ' + suffix)
                self.assertEqual(result['variants'][0]['name'], result['price_title'])
                self.assertEqual((result['sku'], result['price_low'], result['currency']),
                                 ('4864', '4.00', 'USD'))

    def test_revision_prefix_alone_or_missing_corroboration_rejected(self):
        for selector in ('title', 'meta[property="og:title"]', 'meta[name="twitter:title"]',
                         '.mobile-product-header h1'):
            soup = BeautifulSoup(revision_page(), 'html.parser')
            soup.select_one(selector).decompose()
            self.rejects(str(soup))
        self.rejects(revision_page('Different product'))
        self.rejects(revision_page('v1.1 - Another board'))

    def test_revision_conflicting_metadata_or_mobile_still_rejected(self):
        for selector in ('meta[property="og:title"]', 'meta[name="twitter:title"]'):
            soup = BeautifulSoup(revision_page(), 'html.parser')
            soup.select_one(selector)['content'] = 'Other Board'
            self.rejects(str(soup))
        for selector in ('title', '.mobile-product-header h1'):
            soup = BeautifulSoup(revision_page(), 'html.parser')
            soup.select_one(selector).string = 'Controlled Board - v9.9'
            self.rejects(str(soup))
        self.rejects(revision_page() + '<title>Conflicting title</title>')

    def test_revision_does_not_relax_identity_currency_or_price(self):
        html = revision_page()
        self.rejects(html, ROOT + '/product/4883')
        self.rejects(html.replace('"sku": 4864', '"sku": 4883'))
        self.rejects(html.replace('https://adafruit.com/product/4864',
                                  'https://adafruit.com.evil.example/product/4864'))
        self.rejects(html.replace('USD', 'EUR'))
        self.rejects(html.replace('"price": 4', '"price": 9'))

    def test_discontinued_requires_matching_explicit_visible_status(self):
        html = revision_page().replace('schema.org/OutOfStock', 'schema.org/Discontinued')
        html = html.replace('Out of stock', 'No longer stocked')
        result = parse_adafruit_price(html, URL)
        self.assertEqual(result['availability'], 'Discontinued')
        self.assertEqual(result['variants'][0]['availability'], 'Discontinued')
        self.assertEqual(result['price_low'], '4.00')
        self.rejects(html.replace('No longer stocked', 'In stock'))
        self.rejects(html.replace('schema.org/Discontinued', 'schema.org/InStock'))
        self.rejects(html.replace('schema.org/Discontinued', 'schema.org/Unknown'))

    def test_out_of_stock_schema_and_in_stock_dom_remain_conflict(self):
        soup = BeautifulSoup(page(), 'html.parser')
        soup.select_one('#prod-stock [itemprop=availability]').string = 'In stock'
        self.rejects(str(soup))

    def test_revision_does_not_bypass_unselected_part_picker(self):
        soup = BeautifulSoup(revision_page(), 'html.parser')
        picker = BeautifulSoup('<select name="part_id"><option value="4864">Choose color</option>'
                               '<option value="4883">Blue ($9.00)</option></select>', 'html.parser').select_one('select')
        soup.select_one('#prod-right-side').append(picker)
        with self.assertRaisesMessage(CollectionError, '尚未支持的版本选择控件'):
            parse_adafruit_price(str(soup), URL)

    def test_revision_does_not_bypass_wrong_selected_sku(self):
        soup = BeautifulSoup(revision_page(), 'html.parser')
        widget = BeautifulSoup(page(), 'html.parser').select_one('.meta_pid_boxes')
        widget.select_one('li.ui-selected')['data-part-id'] = '4883'
        soup.select_one('#prod-stock').append(widget)
        with self.assertRaisesMessage(CollectionError, '选中版本与目标商品或 SKU 不一致'):
            parse_adafruit_price(str(soup), URL)

    def test_discontinued_selected_version_also_needs_matching_status(self):
        html = page().replace('schema.org/OutOfStock', 'schema.org/Discontinued')
        html = html.replace('Out of stock', 'No longer stocked')
        self.assertEqual(parse_adafruit_price(html, URL)['availability'], 'Discontinued')
        soup = BeautifulSoup(html, 'html.parser')
        soup.select_one('li.ui-selected .option_meta').string = 'Out of stock'
        self.rejects(str(soup))
