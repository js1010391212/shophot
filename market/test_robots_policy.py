"""Controlled responses, including the blank-line shape of the live robots.

No network requests or production database access; no mock is a live sample.
"""
import httpx
from django.test import SimpleTestCase

from .collectors import CollectionError, MAX_BYTES
from .robots_policy import RobotsPolicy, load_robots

ROOT = 'https://store.example.com'
BLANK_RULES = 'User-agent: *\n\nDisallow: /cart\n\n# comment\nDisallow: /policies/\n\n'


class RobotsPolicyTests(SimpleTestCase):
    def policy(self, text, agent='ShopHot'):
        return RobotsPolicy(text, ROOT, agent)

    def test_blank_lines_comments_do_not_discard_prohibitions(self):
        policy = self.policy(BLANK_RULES)
        self.assertFalse(policy.can_fetch(ROOT + '/cart.js'))
        self.assertFalse(policy.can_fetch(ROOT + '/policies/terms-of-service'))
        self.assertTrue(policy.can_fetch(ROOT + '/products/coat'))

    def test_groups_merge_exact_agents_and_override_wildcard(self):
        policy = self.policy('User-agent: *\nDisallow: /\n'
                             'User-agent: Other\n\nUser-agent: shophot\nDisallow: /one\n'
                             'User-agent: SHOPHOT\nDisallow: /two\n')
        self.assertFalse(policy.can_fetch(ROOT + '/one'))
        self.assertFalse(policy.can_fetch(ROOT + '/two'))
        self.assertTrue(policy.can_fetch(ROOT + '/three'))
        self.assertFalse(self.policy('User-agent: Shop\nDisallow: /\nUser-agent: *\nAllow: /').can_fetch('https://other.example/path'))
        self.assertTrue(self.policy('User-agent: Shop\nDisallow: /').can_fetch(ROOT + '/'))

    def test_empty_group_and_metadata_do_not_merge_wrong_agents(self):
        policy = self.policy('User-agent: Other\nDisallow:\nUser-agent: ShopHot\n'
                             'Sitemap: https://store.example.com/sitemap.xml\nDisallow: /private')
        self.assertFalse(policy.can_fetch(ROOT + '/private'))
        self.assertTrue(self.policy('User-agent: Other\nDisallow: /\nUser-agent: ShopHot').can_fetch(ROOT + '/'))
        self.assertTrue(self.policy('# comments only\n\n').can_fetch(ROOT + '/'))

    def test_longest_allow_and_ties_are_independent_of_rule_order(self):
        for rules in ('Disallow: /\nAllow: /public\nDisallow: /public/no\nAllow: /tie\nDisallow: /tie',
                      'Disallow: /tie\nAllow: /tie\nDisallow: /public/no\nAllow: /public\nDisallow: /'):
            p = self.policy('User-agent: *\n' + rules)
            self.assertTrue(p.can_fetch(ROOT + '/public/yes'))
            self.assertFalse(p.can_fetch(ROOT + '/public/no'))
            self.assertTrue(p.can_fetch(ROOT + '/tie'))
            self.assertTrue(p.can_fetch(ROOT + '/robots.txt'))

    def test_wildcards_query_terminal_anchor_and_case(self):
        p = self.policy('User-agent: *\nDisallow: /*?preview=*\nDisallow: /*.gif$\nDisallow: /Case')
        self.assertFalse(p.can_fetch(ROOT + '/products/a?preview=one'))
        self.assertFalse(p.can_fetch(ROOT + '/images/a.gif'))
        self.assertTrue(p.can_fetch(ROOT + '/images/a.gif?width=10'))
        self.assertTrue(p.can_fetch(ROOT + '/case'))
        self.assertFalse(p.can_fetch(ROOT + '/Case'))

    def test_utf8_percent_unreserved_and_literal_special_characters(self):
        p = self.policy('User-agent: *\nDisallow: /ツ\nDisallow: /foo/baz\nDisallow: /literal-%2A\nDisallow: /dollar-%24\nDisallow: /amount-$-file')
        for path in ('/%E3%83%84', '/foo/%62%61%7A', '/literal-*', '/dollar-$', '/amount-$-file'):
            with self.subTest(path=path):
                self.assertFalse(p.can_fetch(ROOT + path))
        self.assertTrue(p.can_fetch(ROOT + '/foo%2Fbaz'))

    def test_crawl_delay_uses_strictest_matching_group_and_bounds(self):
        p = self.policy('User-agent: *\nCrawl-delay: 100\nUser-agent: ShopHot\nCrawl-delay: 1.5\n'
                        'User-agent: ShopHot\nCrawl-delay: 3')
        self.assertEqual(p.delay, 3)
        self.assertEqual(self.policy('User-agent: *\nCrawl-delay: 0').delay, 1)
        for value in ('31', 'NaN', 'Infinity', '-1', 'unknown', ''):
            with self.subTest(value=value), self.assertRaises(CollectionError):
                self.policy('User-agent: *\nCrawl-delay: ' + value)

    def test_non_200_never_redirects_or_retries(self):
        for status in (301, 302, 401, 403, 404, 429, 500):
            calls = []
            def handler(request):
                calls.append(str(request.url))
                return httpx.Response(status, headers={'location': 'https://other.example/robots.txt', 'retry-after': '1'})
            with self.subTest(status=status), httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
                with self.assertRaisesMessage(CollectionError, str(status)):
                    load_robots(client, ROOT)
                self.assertEqual(calls, [ROOT + '/robots.txt'])

    def test_body_type_encoding_size_and_parse_fail_closed(self):
        responses = [httpx.Response(200, text='<html>challenge</html>', headers={'content-type': 'text/html'}),
                     httpx.Response(200, content=b'\xff', headers={'content-type': 'text/plain'}),
                     httpx.Response(200, content=b'#' + b'x' * MAX_BYTES, headers={'content-type': 'text/plain'}),
                     httpx.Response(200, text='access denied'),
                     httpx.Response(200, text='{"error":"denied"}'),
                     httpx.Response(200, text='User-agent: *\nDisallow: /\x00'),
                     httpx.Response(200, text='User-agent: *\nDisallow: invalid')]
        for response in responses:
            with httpx.Client(transport=httpx.MockTransport(lambda request: response)) as client, self.assertRaises(CollectionError):
                load_robots(client, ROOT)

    def test_bom_and_foreign_or_unsafe_targets(self):
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b'\xef\xbb\xbf' + BLANK_RULES.encode(), headers={'content-type': 'text/plain'}))) as client:
            p = load_robots(client, ROOT)
        self.assertFalse(p.can_fetch(ROOT + '/cart.js'))
        self.assertFalse(p.can_fetch('https://other.example/products/a'))
        for url in ('http://store.example.com/', 'https://name@store.example.com/', ROOT + ':8443/'):
            with self.subTest(url=url):
                self.assertFalse(p.can_fetch(url))
