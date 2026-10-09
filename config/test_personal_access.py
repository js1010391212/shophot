"""Synthetic personal-entry regression; no real config, DB, network or service."""
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.middleware.csrf import CsrfViewMiddleware, _get_new_csrf_string
from django.test import SimpleTestCase, RequestFactory, override_settings
from .personal_runtime import LoopbackHTTPSBoundary, load_private_config

KEY = 'synthetic-personal-only-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-not-a-real-secret'


class PersonalAccessTests(SimpleTestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.local = Path(self.tmp.name)/'.local'
        self.local.mkdir()
        self.db_file = self.local/'database.json'
        self.db = dict(engine='postgresql', host='127.0.0.1', port='55432', name='synthetic', user='synthetic', password='not-real')
        self.db_file.write_text(json.dumps(self.db))
        self.env = {'SHOPHOT_PERSONAL_SECRET_KEY': KEY, 'SHOPHOT_PERSONAL_ORIGIN': 'https://synthetic.example.test',
                    'SHOPHOT_PERSONAL_DB_CONFIG': str(self.db_file)}

    def load(self, changes=None, omit=()):
        env = {**self.env, **(changes or {})}
        for name in omit: env.pop(name, None)
        with patch.dict(os.environ, env, clear=True), patch('socket.socket.connect', side_effect=AssertionError('network')):
            return runpy.run_module('config.personal_access', run_name='__personal_test__')

    def test_required_config_has_no_development_or_production_fallback(self):
        for key in self.env:
            with self.subTest(key=key), self.assertRaises(ImproperlyConfigured):
                self.load({'SHOPHOT_DEBUG':'1', 'SHOPHOT_SECRET_KEY':KEY}, omit=(key,))
        for value in ('short-private', 'x'*80, 'django-insecure-'+KEY, 'development-only-'+KEY):
            with self.assertRaises(ImproperlyConfigured) as caught:
                self.load({'SHOPHOT_PERSONAL_SECRET_KEY':value})
            self.assertNotIn(value, str(caught.exception))

    def test_origin_rejects_wildcard_http_path_port_and_credential_without_echo(self):
        for value in ('http://synthetic.example.test','https://*.example.test','https://.example.test',
                      'https://synthetic.example.test/','https://synthetic.example.test:443',
                      'https://person:private@example.test','https://127.0.0.1','https://example.test?x=1',
                      'https://example.test#x','https://example.test#','https://example.test?','https://EXAMPLE.test','https://example.test\n'):
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured) as caught:
                self.load({'SHOPHOT_PERSONAL_ORIGIN':value})
            self.assertNotIn(value, str(caught.exception))

    def test_local_pg_only_without_remote_dns_or_sqlite(self):
        for changes in ({'host':'db.example.test'}, {'host':'localhost'}, {'host':'0.0.0.0'}, {'host':'192.168.1.3'},
                        {'host':'/tmp/../private'}, {'engine':'sqlite'}, {'port':'0'}, {'port':'65536'}):
            self.db_file.write_text(json.dumps({**self.db, **changes}))
            with self.subTest(changes=changes), self.assertRaises(ImproperlyConfigured):self.load()
        for host in ('127.0.0.1', '::1', '/private/tmp/synthetic-pg'):
            self.db_file.write_text(json.dumps({**self.db, 'host':host}))
            db = self.load()['DATABASES']['default']
            self.assertEqual(db['HOST'], host)
            self.assertEqual(db['ENGINE'], 'django.db.backends.postgresql')

    def test_secure_isolated_cookies_static_and_proxy_contract(self):
        config = self.load({'SHOPHOT_DEBUG':'1','SHOPHOT_CSRF_TRUSTED_ORIGINS':'https://*.test'})
        self.assertIs(config['DEBUG'], False)
        self.assertEqual(config['ALLOWED_HOSTS'], ['synthetic.example.test'])
        self.assertEqual(config['CSRF_TRUSTED_ORIGINS'], [])
        self.assertIs(config['SESSION_COOKIE_SECURE'], True)
        self.assertIs(config['CSRF_COOKIE_SECURE'], True)
        self.assertEqual(config['SESSION_COOKIE_NAME'], 'shophot_personal_session')
        self.assertEqual(config['CSRF_COOKIE_NAME'], 'shophot_personal_csrf')
        self.assertIsNone(config['SESSION_COOKIE_DOMAIN'])
        self.assertEqual(config['STATIC_ROOT'], config['BASE_DIR']/'.local'/'personal-static')
        self.assertIs(config['WHITENOISE_USE_FINDERS'], False)
        self.assertIs(config['WHITENOISE_AUTOREFRESH'], False)
        self.assertEqual(config['MIDDLEWARE'][1], 'whitenoise.middleware.WhiteNoiseMiddleware')
        self.assertEqual(config['SECURE_PROXY_SSL_HEADER'], ('HTTP_X_FORWARDED_PROTO','https'))

    def test_private_runtime_json_rejects_open_permissions_unknown_keys_and_missing_values(self):
        file = self.local/'personal.json'
        file.write_text(json.dumps(self.env));file.chmod(0o600)
        with patch.dict(os.environ, {'SHOPHOT_PERSONAL_CONFIG':str(file)}, clear=True):
            load_private_config();self.assertEqual(os.environ['SHOPHOT_PERSONAL_ORIGIN'], self.env['SHOPHOT_PERSONAL_ORIGIN'])
        for data, mode in [(self.env,0o644), ({**self.env,'DEBUG':'1'},0o600), ({},0o600)]:
            file.write_text(json.dumps(data));file.chmod(mode)
            with patch.dict(os.environ, {'SHOPHOT_PERSONAL_CONFIG':str(file)}, clear=True), self.assertRaises(ImproperlyConfigured):
                load_private_config()

    def test_proxy_gate_protects_app_and_static_before_any_downstream_call(self):
        seen=[]
        def app(environ, respond):
            seen.append(environ['PATH_INFO']);respond('200 OK',[]);return[b'controlled']
        gate=LoopbackHTTPSBoundary(app,'synthetic.example.test')
        base={'REMOTE_ADDR':'127.0.0.1','HTTP_HOST':'synthetic.example.test','HTTP_X_FORWARDED_PROTO':'https'}
        for path in ('/tools/profit/','/static/market/ui.css'):
            for changes in ({'REMOTE_ADDR':'192.168.1.2'}, {'HTTP_HOST':'evil.test'},
                            {'HTTP_X_FORWARDED_PROTO':'http'}, {'HTTP_X_FORWARDED_PROTO':'https,http'},
                            {'REMOTE_ADDR':''}, {'HTTP_X_FORWARDED_PROTO':''}):
                responses=[]
                self.assertEqual(gate({**base,'PATH_INFO':path,**changes},lambda status,headers:responses.append(status)),
                                 [b'Personal access proxy boundary rejected this request.'])
                self.assertEqual(responses,['403 Forbidden'])
        self.assertEqual(seen,[])
        for path in ('/tools/profit/','/static/market/ui.css'):
            self.assertEqual(gate({**base,'PATH_INFO':path},lambda status,headers:None),[b'controlled'])
        self.assertEqual(seen,['/tools/profit/','/static/market/ui.css'])

    @override_settings(ALLOWED_HOSTS=['synthetic.example.test'], CSRF_TRUSTED_ORIGINS=[],
                       CSRF_COOKIE_NAME='shophot_personal_csrf', SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https'))
    def test_same_origin_csrf_accepts_valid_token_and_rejects_foreign_origin(self):
        csrf=_get_new_csrf_string()
        for origin, allowed in [('https://synthetic.example.test',True),('https://evil.test',False)]:
            request=RequestFactory().post('/tools/profit/',{'csrfmiddlewaretoken':csrf},
                                          HTTP_HOST='synthetic.example.test',HTTP_X_FORWARDED_PROTO='https',HTTP_ORIGIN=origin)
            request.COOKIES['shophot_personal_csrf']=csrf
            middleware=CsrfViewMiddleware(lambda request:HttpResponse())
            middleware.process_request(request)
            response=middleware.process_view(request,lambda request:HttpResponse(),(),{})
            if allowed:self.assertIsNone(response)
            else:self.assertEqual(response.status_code,403)

    def test_start_script_missing_config_stops_before_database_or_server_commands(self):
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run([sys.executable,'scripts/start_personal.py','--config',str(self.local/'missing.json')],
                              cwd=root,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,2)
        self.assertNotIn(KEY,result.stderr)
        self.assertNotIn('Starting gunicorn',result.stderr)

    def test_wsgi_entry_forces_personal_settings_even_if_development_was_inherited(self):
        with patch.dict(os.environ, {'DJANGO_SETTINGS_MODULE':'config.settings'}), \
                override_settings(PERSONAL_HOST='synthetic.example.test'), \
                patch('django.core.wsgi.get_wsgi_application', return_value=lambda env, respond:[]) as create:
            config=runpy.run_module('config.personal_wsgi', run_name='__wsgi_test__')
            self.assertEqual(os.environ['DJANGO_SETTINGS_MODULE'],'config.personal_access')
            self.assertIsInstance(config['application'],LoopbackHTTPSBoundary)
            create.assert_called_once()

    def test_fixed_server_config_has_no_external_bind_reload_or_access_log(self):
        config=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts'/'personal_gunicorn.py'))
        self.assertEqual(config['bind'],'127.0.0.1:8003')
        self.assertEqual(config['workers'],1)
        self.assertIs(config['reload'],False)
        self.assertIs(config['daemon'],False)
        self.assertIsNone(config['accesslog'])
