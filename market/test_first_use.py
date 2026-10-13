"""First-use route protection, no database access and existing workflow links."""
from html.parser import HTMLParser
from types import SimpleNamespace
from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase, RequestFactory
from django.urls import reverse, resolve
from .first_use_views import guide


class Links(HTMLParser):
    def __init__(self,html):
        super().__init__();self.anchors=[];self.feed(html)
    def handle_starttag(self,tag,attrs):
        if tag=='a':self.anchors.append(dict(attrs))


class FirstUseTests(SimpleTestCase):
    def request(self,method='get',query=None):
        request=getattr(RequestFactory(),method)(reverse('first_use'),query or {})
        request.user=SimpleNamespace(is_authenticated=True,is_staff=False,username='Ordinary seller')
        request.resolver_match=resolve(reverse('first_use'))
        return request

    def test_anonymous_get_requires_login_and_preserves_next(self):
        response=self.client.get(reverse('first_use'))
        self.assertRedirects(response,reverse('login')+'?next='+reverse('first_use'),fetch_redirect_response=False)
        request=self.request();request.user=AnonymousUser()
        self.assertEqual(guide(request).status_code,302)

    def test_authenticated_route_is_get_only(self):
        self.assertIs(resolve(reverse('first_use')).func,guide)
        for method in ('post','put','delete','head'):
            self.assertEqual(guide(self.request(method)).status_code,405)

    def test_authenticated_get_renders_without_any_database_access_or_user_data(self):
        # SimpleTestCase prohibits ALL SQL: unlike a count comparison, reads fail too.
        response=guide(self.request(query={'observation':'999','study':'999','start':'collect'}))
        self.assertEqual(response.status_code,200)
        content=response.content.decode()
        self.assertIn('从我的报价开始',content)
        self.assertIn('没有报价，先手填情景',content)
        self.assertNotIn('name="study"',content);self.assertNotIn('name="observation"',content)
        self.assertNotIn('createsuperuser',content)

    def test_flow_links_are_existing_local_get_routes_and_guide_navigation_active(self):
        links=Links(guide(self.request()).content.decode()).anchors
        hrefs={row.get('href') for row in links}
        for name in ('browser_quote_library','profit','browser_capture','shipping','shipping_import','profit_study_list','csv_import','dashboard'):
            url=reverse(name);self.assertIn(url,hrefs);self.assertEqual(resolve(url).url_name,name)
        guide_link=[row for row in links if row.get('href')==reverse('first_use')]
        self.assertEqual(len(guide_link),1);self.assertEqual(guide_link[0].get('aria-current'),'page')
        self.assertNotIn(reverse('admin:index'),hrefs)
        self.assertTrue(all(url.startswith(('/','#')) for url in hrefs if url))

    def test_login_help_is_for_ordinary_users_and_does_not_offer_privilege_creation(self):
        response=self.client.get(reverse('login'))
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'负责人提供的账号')
        self.assertContains(response,'重置密码')
        self.assertNotContains(response,'createsuperuser')
