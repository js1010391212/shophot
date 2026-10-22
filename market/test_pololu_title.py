"""Only exact plain/prefixed titles; keep the one-unit source contract."""
from bs4 import BeautifulSoup
from django.test import SimpleTestCase

from .collectors import CollectionError
from .pololu_catalog import parse_pololu_price
from .test_pololu_catalog import URL, page, changed_dom, changed_node


def plain_title(html):
    soup = BeautifulSoup(html, 'html.parser')
    soup.title.string = 'Controlled regulator'
    return str(soup)


class PololuTitleTests(SimpleTestCase):
    def test_exact_plain_and_prefixed_titles_keep_same_quote(self):
        for html in (page(), plain_title(page())):
            with self.subTest(plain=html == plain_title(page())):
                row = parse_pololu_price(html, URL)
                self.assertEqual((row['sku'], row['price_low'], row['price_high'], row['currency']),
                                 ('5759', '8.95', '8.95', 'USD'))
                self.assertEqual(row['price_title'], 'Controlled regulator')

    def test_similar_wrong_or_duplicate_titles_and_wrong_h1_rejected(self):
        for title in ('Other regulator', 'Controlled regulator v2', 'Pololu - Other regulator',
                      'Pololu - Pololu - Controlled regulator', 'xControlled regulator'):
            soup = BeautifulSoup(page(), 'html.parser')
            soup.title.string = title
            with self.subTest(title=title), self.assertRaises(CollectionError):
                parse_pololu_price(str(soup), URL)
        for html in (plain_title(page()) + '<title>Controlled regulator</title>',
                     plain_title(changed_dom(lambda s: setattr(s.h1, 'string', 'Other regulator')))):
            with self.assertRaises(CollectionError):
                parse_pololu_price(html, URL)

    def test_plain_title_does_not_relax_identity_price_quantity_or_stock(self):
        mutations = [
            changed_node(lambda n: n.update(sku=5758)),
            changed_node(lambda n: n['offers'].update(URL='https://evil.example/product/5759')),
            changed_dom(lambda s: s.select_one('input[name="product[id]"]').__setitem__('value', '5758')),
            changed_dom(lambda s: s.select_one('input[name="product[quantity]"]').__setitem__('value', '5')),
            changed_node(lambda n: n['offers'].update(priceCurrency='EUR')),
            changed_node(lambda n: n['offers'].update(price='6.97')),
            changed_node(lambda n: n['offers'].update(availability='OutOfStock')),
            changed_dom(lambda s: setattr(s.select_one('span.value'), 'string', 'Rationed (Active and Preferred)')),
        ]
        for index, html in enumerate(mutations):
            with self.subTest(mutation=index), self.assertRaises(CollectionError):
                parse_pololu_price(plain_title(html), URL)
