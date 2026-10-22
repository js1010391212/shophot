"""Limited homepage candidates, not verified prices or full-store coverage."""
from django.test import SimpleTestCase

from .collectors import CollectionError, MAX_BYTES
from .pololu_catalog import ROOT, parse_pololu_home


class PololuHomeTests(SimpleTestCase):
    def test_dom_order_dedup_and_later_visible_title_without_reordering(self):
        html = ('<a href="/product/749"><img alt="Do not copy image metadata"></a>'
                '<a href="/product/5759">Visible regulator</a>'
                '<a href="https://www.pololu.com/product/749">Custom Laser Cutting</a>'
                '<a href="/product/446">SMT Stencils</a>'
                '<a href="/product/5759">Later contradictory title</a>')
        result = parse_pololu_home(html)
        self.assertEqual(result, {'products': [
            {'url': ROOT + '/product/749', 'title': 'Custom Laser Cutting'},
            {'url': ROOT + '/product/5759', 'title': 'Visible regulator'},
            {'url': ROOT + '/product/446', 'title': 'SMT Stencils'},
        ], 'limited': True})
        for item in result['products']:
            self.assertEqual(set(item), {'url', 'title'})

    def test_first_hundred_unique_links_not_selected_or_reordered_for_price(self):
        html = ''.join(f'<a href="/product/{i}">Item {i}</a>' for i in range(1, 103))
        html += '<a href="/product/5759">Known priced sample must not jump queue</a>'
        result = parse_pololu_home(html)
        self.assertTrue(result['limited'])
        self.assertEqual([x['url'] for x in result['products']],
                         [ROOT + '/product/' + str(i) for i in range(1, 101)])

    def test_noncanonical_and_other_paths_never_become_targets(self):
        invalid = ['/product/0', '/product/05759', '/product/5759/', '/product/5759/specs',
                   '/product/5759?x=1', '/product/5759#p', '/products/5759', 'product/5759',
                   '//www.pololu.com/product/5759', 'https://pololu.com/product/5759',
                   'http://www.pololu.com/product/5759', ROOT + ':443/product/5759',
                   'https://user@www.pololu.com/product/5759',
                   'https://www.pololu.com.evil.example/product/5759', '/product/５７５９']
        html = ''.join(f'<a href="{url}">Invalid</a>' for url in invalid)
        html += '<a href="/product/7">Valid</a>'
        self.assertEqual(parse_pololu_home(html)['products'], [{'url': ROOT + '/product/7', 'title': 'Valid'}])

    def test_empty_anchor_falls_back_to_pid_without_alt_description_or_price(self):
        result = parse_pololu_home(b'<a href="/product/7" title="Not visible"><img alt="Image title"></a>')
        self.assertEqual(result, {'products': [{'url': ROOT + '/product/7', 'title': '7'}], 'limited': True})
        long_title = 'a' * 301
        self.assertEqual(len(parse_pololu_home('<a href="/product/7">' + long_title + '</a>')['products'][0]['title']), 300)

    def test_bad_root_body_encoding_size_and_empty_directory_fail_closed(self):
        for root in ('https://pololu.com', ROOT + '/', ROOT + ':443', ROOT + '.evil.example', None):
            with self.subTest(root=root), self.assertRaises(CollectionError):
                parse_pololu_home('<a href="/product/7">Item</a>', root)
        for body in (None, b'\xff', b' ' * (MAX_BYTES + 1), '<a href="/ordering">Ordering</a>'):
            with self.subTest(body_type=type(body).__name__), self.assertRaises(CollectionError):
                parse_pololu_home(body)

    def test_external_base_never_reinterprets_relative_link_as_merchant_target(self):
        with self.assertRaises(CollectionError):
            parse_pololu_home('<base href="https://evil.example/"><a href="/product/7">Item</a>')
        self.assertEqual(parse_pololu_home('<base href="/"><a href="/product/7">Item</a>')['products'][0]['url'], ROOT + '/product/7')
