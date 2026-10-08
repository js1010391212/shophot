"""受控片段验证报价归属；网络为 MockTransport，记录仅在独立测试库。"""
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import httpx
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from .collectors import CollectionError, collect, parse_product
from .jobs import enqueue, run_next
from .models import Product, Snapshot
from .page_import import parse_page


URL = 'https://www.aliexpress.com/item/1005001234567890.html'
OTHER = 'https://www.aliexpress.com/item/999.html'
PUBLIC = [(2, 1, 6, '', ('93.184.215.14', 443))]


def offer(**changes):
    return {'@type': 'Offer', 'price': '19.50', 'priceCurrency': 'USD', **changes}


def product(**changes):
    return {'@type': 'Product', 'url': URL, 'name': 'Controlled ownership fixture',
            'offers': offer(), **changes}


def html(nodes):
    return ('<script type="application/ld+json">'+json.dumps(nodes)+'</script>').encode()


def invalid_quotes():
    return [
        ('foreign_same_id', product(url=URL.replace('www.aliexpress.com', 'evil.example'))),
        ('unidentified', product(url=None)),
        ('wrong_product_and_anonymous_fallback', [product(url=OTHER), product(url=None)]),
        ('foreign_offer', product(offers=offer(url=URL.replace('www.aliexpress.com', 'evil.example')))),
        ('wrong_offer', product(offers=offer(url=OTHER))),
        ('offer_sku_on_generic_target', product(offers=offer(url=URL+'?sku_id=123'))),
        ('parent_sku_on_generic_target', product(url=URL+'?sku_id=123')),
        ('same_price_different_skus', product(offers=[offer(url=URL+'?sku_id='+sku) for sku in ('123', '456')])),
        ('aggregate_price', product(offers=offer(**{'@type': 'AggregateOffer'}))),
        ('conflicting_product_id', product(**{'@id': OTHER})),
        ('wrong_offer_id', product(offers=offer(**{'@id': OTHER}))),
        ('conflicting_offer_url_and_id', product(offers=offer(url=URL, **{'@id': OTHER}))),
        ('offer_id_sku_on_generic_parent', product(offers=offer(**{'@id': URL+'?sku_id=123'}))),
        ('fragment_is_not_identity', product(url='#recommendation')),
        ('empty_is_not_identity', product(url='')),
    ]


class QuoteOwnershipTests(SimpleTestCase):
    def assert_rejected(self, nodes, target=URL, platform='AliExpress'):
        raw = html(nodes)
        if platform == 'AliExpress':
            with self.assertRaises(CollectionError):
                parse_product(raw, target_url=target)
        with self.assertRaises(ValidationError):
            parse_page(raw, target, platform)

    def test_invalid_ownership_rejected_by_both_entry_points(self):
        for name, nodes in invalid_quotes():
            with self.subTest(case=name):
                self.assert_rejected(nodes)

    def test_no_url_product_cannot_inherit_target(self):
        node = product()
        del node['url']
        self.assert_rejected(node)

    def test_product_and_offer_sku_conflict(self):
        self.assert_rejected(product(url=URL+'?sku_id=456', offers=offer(url=URL+'?sku_id=123')), URL+'?sku_id=123')
        self.assert_rejected(product(url=URL+'?sku_id=123', offers=offer(url=URL+'?sku_id=456')), URL+'?sku_id=123')

    def test_url_and_id_sku_conflict(self):
        self.assert_rejected(product(url=URL+'?sku_id=123', **{'@id': URL+'?sku_id=456'}), URL+'?sku_id=123')

    def test_offer_id_must_agree_with_its_url_or_inherited_sku(self):
        target = URL+'?sku_id=123'
        for changes in ({'url': target, '@id': URL+'?sku_id=456'}, {'@id': URL+'?sku_id=456'}):
            with self.subTest(changes=changes):
                self.assert_rejected(product(url=target, offers=offer(**changes)), target)
        valid = product(url=target, offers=offer(**{'@id': target+'#offer'}))
        self.assertEqual(parse_page(html(valid), target, 'AliExpress')['specification'], '123')

    def test_no_url_offer_inherits_explicit_parent_sku(self):
        target = URL+'?sku_id=123'
        node = product(url=target)
        automatic = parse_product(html(node), target)
        imported = parse_page(html(node), target, 'AliExpress')
        self.assertEqual(automatic['price'], Decimal('19.50'))
        self.assertEqual((imported['price'], imported['specification']), ('19.50', '123'))

    def test_id_can_establish_parent_sku_without_guessing(self):
        target = URL+'?sku_id=123'
        node = product(**{'@id': target+'#product'})
        self.assertEqual(parse_page(html(node), target, 'AliExpress')['specification'], '123')
        with self.assertRaises(ValidationError):
            parse_page(html(node), URL, 'AliExpress')

    def test_generic_offer_url_does_not_supply_missing_sku(self):
        target = URL+'?sku_id=123'
        self.assert_rejected(product(url=target, offers=offer(url=URL)), target)
        self.assert_rejected(product(), target)

    def test_multiple_same_price_offers_remain_ambiguous(self):
        self.assert_rejected(product(offers=[offer(), offer()]))
        with self.assertRaises(CollectionError):
            parse_product(html({'@type': 'Product', 'offers': [offer(), offer()]}))

    def test_exact_offer_selected_among_parent_product_variants(self):
        node = product(offers=[offer(url=URL+'?sku_id='+sku) for sku in ('123', '456')])
        target = URL+'?sku_id=123'
        self.assertEqual(parse_product(html(node), target)['price'], Decimal('19.50'))
        self.assertEqual(parse_page(html(node), target, 'AliExpress')['specification'], '123')

    def test_relative_and_alias_urls_keep_explicit_product_identity(self):
        path = '/item/1005001234567890.html'
        node = product(url=path, offers=offer(url=URL.replace('www.aliexpress.com', 'aliexpress.com')))
        raw = html({'@graph': [product(url=OTHER), node]})
        self.assertEqual(parse_product(raw, URL)['price'], Decimal('19.50'))
        self.assertEqual(parse_page(raw, URL, 'AliExpress')['price'], '19.50')

    def test_invalid_target_and_offer_urls_are_collection_errors(self):
        for target in (URL.replace('aliexpress.com', 'evil.example'), URL+'?sku_id=', URL+'?sku_id=1&sku_id=2'):
            with self.subTest(target=target), self.assertRaises(CollectionError):
                parse_product(html(product()), target)
        for url in (None, '', '#offer', URL.replace('.com/', '.com:8443/'), URL+'?sku_id=1&sku_id=2'):
            with self.subTest(offer_url=url):
                self.assert_rejected(product(offers=offer(url=url)))

    def test_targeted_parser_requires_explicit_offer_type(self):
        node = product(offers={'price': '19.50', 'priceCurrency': 'USD'})
        self.assert_rejected(node)

    def test_legacy_no_target_call_and_result_contract(self):
        node = {'@type': 'Product', 'offers': {'price': '0', 'priceCurrency': 'usd'}}
        result = parse_product(html(node))
        self.assertEqual(result['price'], Decimal('0.00'))
        self.assertEqual(set(result), {'title', 'price', 'currency', 'sales', 'rating', 'review_count'})
        self.assertIsNone(result['sales'])
        targeted = parse_product(html(product()), URL)
        self.assertEqual(set(targeted), set(result))
        imported = parse_page(html(product()), URL, 'AliExpress')
        self.assertEqual(set(imported), {'title', 'price', 'currency', 'rating', 'review_count',
                                        'review_samples', 'specification', 'file_fingerprint'})

    def test_aggregate_offer_is_rejected_even_in_legacy_mode(self):
        with self.assertRaises(CollectionError):
            parse_product(html({'@type': 'Product', 'offers': offer(**{'@type': 'AggregateOffer'})}))

    def test_invalid_quote_is_useful_collection_failure(self):
        for changes in ({'price': 'NaN'}, {'price': -1}, {'priceCurrency': None}):
            with self.subTest(changes=changes):
                self.assert_rejected(product(offers=offer(**changes)))

    def test_otto_preserves_inheritance_and_rejects_same_conflicts(self):
        url = 'https://www.otto.de/p/test-S0123/'
        target = url+'?variationId=AAA'
        valid = product(url=target, offers=offer(priceCurrency='EUR'))
        self.assertEqual(parse_page(html(valid), target, 'OTTO')['specification'], 'AAA')
        self.assert_rejected(valid, url, 'OTTO')
        conflict = product(url=url+'?variationId=BBB', offers=offer(url=target, priceCurrency='EUR'))
        self.assert_rejected(conflict, target, 'OTTO')


class WorkerOwnershipTests(TestCase):
    def test_wrong_ownership_fails_without_changing_history_then_valid_retry(self):
        tracked = Product.objects.create(title='待识别竞品 · ownership', url=URL, platform='AliExpress')
        old = Snapshot.objects.create(product=tracked, observed_at=timezone.now()-timedelta(days=1),
                                      price=99, currency='USD', source=Snapshot.Source.WEB, context='old evidence')
        for name, nodes in invalid_quotes():
            with self.subTest(case=name):
                job, added = enqueue(tracked)
                self.assertTrue(added)
                client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
                    200, content=html(nodes), headers={'content-type': 'text/html'})))
                with patch('market.collectors.httpx.Client', return_value=client), patch(
                        'market.collectors.socket.getaddrinfo', return_value=PUBLIC):
                    self.assertTrue(run_next())
                job.refresh_from_db()
                self.assertEqual(job.status, 'failed')
                self.assertNotIn('内部错误', job.message)
                self.assertEqual(Snapshot.objects.count(), 1)
                old.refresh_from_db()
                self.assertEqual((old.price, old.currency, old.context), (Decimal('99'), 'USD', 'old evidence'))
                tracked.refresh_from_db()
                self.assertEqual(tracked.title, '待识别竞品 · ownership')
        job, added = enqueue(tracked)
        self.assertTrue(added)
        with patch('market.jobs.collect', side_effect=lambda url: parse_product(html(product()), url)):
            self.assertTrue(run_next())
        job.refresh_from_db()
        self.assertEqual(job.status, 'succeeded')
        self.assertEqual(Snapshot.objects.count(), 2)
        old.refresh_from_db()
        self.assertEqual(old.price, Decimal('99'))

    def test_collect_rejects_wrong_offer_after_normal_http_response(self):
        client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
            200, content=html(product(offers=offer(url=OTHER))), headers={'content-type': 'text/html'})))
        with patch('market.collectors.httpx.Client', return_value=client), patch(
                'market.collectors.socket.getaddrinfo', return_value=PUBLIC), self.assertRaises(CollectionError):
            collect(URL)
