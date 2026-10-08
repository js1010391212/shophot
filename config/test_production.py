"""合成环境配置回归；不连接数据库或网络，不使用真实凭据。"""
import ast
import os
from pathlib import Path
import runpy
import subprocess
import sys
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

SYNTHETIC_ENV = {
    'SHOPHOT_PROD_SECRET_KEY': 'synthetic-test-only-key-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-not-a-real-secret',
    'SHOPHOT_PROD_ALLOWED_HOSTS': 'pilot.example.test',
    'SHOPHOT_PROD_DB_NAME': 'synthetic_pilot', 'SHOPHOT_PROD_DB_USER': 'synthetic_user',
    'SHOPHOT_PROD_DB_PASSWORD': 'synthetic-db-password', 'SHOPHOT_PROD_DB_HOST': 'db.example.test',
    'SHOPHOT_PROD_DB_PORT': '5432',
}


def load_config(changes=None, omit=()):
    env = {**SYNTHETIC_ENV, **(changes or {})}
    for name in omit:
        env.pop(name, None)
    with patch.dict(os.environ, env, clear=True):
        return runpy.run_module('config.production', run_name='__production_test__')


class ProductionConfigTests(SimpleTestCase):
    def test_missing_and_weak_secret_errors_do_not_disclose_values(self):
        with self.assertRaisesMessage(ImproperlyConfigured, '缺少 SHOPHOT_PROD_SECRET_KEY'):
            load_config(omit=('SHOPHOT_PROD_SECRET_KEY',))
        for value in ('short-sensitive-value', 'x'*80, 'django-insecure-'+('abcdefghij'*8),
                      'DJANGO-INSECURE-'+('abcdefghij'*8), 'development-only-'+('abcdefghij'*8), 'change-me-'+('abcdefghij'*8), ' '+SYNTHETIC_ENV['SHOPHOT_PROD_SECRET_KEY']):
            with self.subTest(length=len(value)), self.assertRaises(ImproperlyConfigured) as exc:
                load_config({'SHOPHOT_PROD_SECRET_KEY': value})
            self.assertNotIn(value, str(exc.exception))

    def test_hosts_required_and_mistakes_rejected(self):
        with self.assertRaisesMessage(ImproperlyConfigured, 'SHOPHOT_PROD_ALLOWED_HOSTS'):
            load_config(omit=('SHOPHOT_PROD_ALLOWED_HOSTS',))
        for value in ('', '*', '.example.test', 'https://example.test', 'example.test:443',
                      'example.test,', 'example.test,example.test', '-bad.test', 'x/y', '[::1]:8000'):
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured):
                load_config({'SHOPHOT_PROD_ALLOWED_HOSTS': value})
        settings = load_config({'SHOPHOT_PROD_ALLOWED_HOSTS': 'pilot.example.test,127.0.0.1,[::1]'})
        self.assertEqual(settings['ALLOWED_HOSTS'], ['pilot.example.test', '127.0.0.1', '[::1]'])

    def test_all_database_fields_required_no_development_fallback(self):
        for name in ('NAME', 'USER', 'PASSWORD', 'HOST', 'PORT'):
            with self.subTest(name=name), self.assertRaisesMessage(ImproperlyConfigured, 'SHOPHOT_PROD_DB_'+name):
                load_config({'SHOPHOT_DB_'+name: 'development-fallback'}, omit=('SHOPHOT_PROD_DB_'+name,))
        # Even malformed/unavailable local files cannot affect the production import.
        with patch.object(Path, 'read_text', side_effect=AssertionError('production read a local file')):
            config = load_config({'SHOPHOT_DB_ENGINE': 'sqlite', 'SHOPHOT_DB_HOST': '127.0.0.1'})
        db = config['DATABASES']['default']
        self.assertEqual(db['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(db['HOST'], 'db.example.test')
        self.assertEqual(db['NAME'], 'synthetic_pilot')

    def test_bad_db_host_port_and_password_error_do_not_leak(self):
        for field, value in (('PORT', '0'), ('PORT', '65536'), ('PORT', 'abc'), ('HOST', 'https://db.test'),
                             ('HOST', 'db.test:5432'), ('HOST', '/tmp/db'), ('PASSWORD', 'secret\nvalue')):
            with self.subTest(field=field), self.assertRaises(ImproperlyConfigured) as exc:
                load_config({'SHOPHOT_PROD_DB_'+field: value})
            self.assertNotIn(value, str(exc.exception))

    def test_debug_secure_cookies_https_and_non_preloaded_hsts(self):
        config = load_config({'SHOPHOT_DEBUG': '1', 'DEBUG': 'true', 'SHOPHOT_PROD_DEBUG': '1',
                              'SHOPHOT_CSRF_TRUSTED_ORIGINS': 'http://*.invalid.test'})
        self.assertIs(config['DEBUG'], False)
        for name in ('SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE', 'SECURE_SSL_REDIRECT', 'SECURE_CONTENT_TYPE_NOSNIFF'):
            self.assertIs(config[name], True)
        self.assertEqual(config['SECURE_HSTS_SECONDS'], 3600)
        self.assertIs(config['SECURE_HSTS_INCLUDE_SUBDOMAINS'], False)
        self.assertIs(config['SECURE_HSTS_PRELOAD'], False)
        self.assertEqual(config['SILENCED_SYSTEM_CHECKS'], ['security.W005', 'security.W021'])
        self.assertEqual(config['CSRF_TRUSTED_ORIGINS'], [])

    def test_proxy_default_untrusted_opt_in_and_invalid_flags(self):
        self.assertIsNone(load_config()['SECURE_PROXY_SSL_HEADER'])
        config = load_config({'SHOPHOT_PROD_TRUST_PROXY_PROTO': '1'})
        self.assertEqual(config['SECURE_PROXY_SSL_HEADER'], ('HTTP_X_FORWARDED_PROTO', 'https'))
        self.assertIs(config['USE_X_FORWARDED_HOST'], False)
        self.assertIs(config['USE_X_FORWARDED_PORT'], False)
        for value in ('true', '', '2'):
            with self.assertRaisesMessage(ImproperlyConfigured, 'SHOPHOT_PROD_TRUST_PROXY_PROTO'):
                load_config({'SHOPHOT_PROD_TRUST_PROXY_PROTO': value})

    def test_hsts_invalid_values_and_positive_bounds(self):
        for value in ('0', '-1', '1.5', 'x', '', '31536001', ' 3600'):
            with self.subTest(value=value), self.assertRaisesMessage(ImproperlyConfigured, 'SHOPHOT_PROD_HSTS_SECONDS'):
                load_config({'SHOPHOT_PROD_HSTS_SECONDS': value})
        self.assertEqual(load_config({'SHOPHOT_PROD_HSTS_SECONDS': '1'})['SECURE_HSTS_SECONDS'], 1)
        self.assertEqual(load_config({'SHOPHOT_PROD_HSTS_SECONDS': '31536000'})['SECURE_HSTS_SECONDS'], 31536000)

    def test_deploy_check_no_warnings_or_database_network_connection(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith(('SHOPHOT_', 'DJANGO_'))}
        env.update(SYNTHETIC_ENV, DJANGO_SETTINGS_MODULE='config.production')
        script = """from unittest.mock import patch
from django.core.management import execute_from_command_line
with patch('socket.socket.connect', side_effect=AssertionError('unexpected network connection')), patch('django.db.backends.base.base.BaseDatabaseWrapper.connect', side_effect=AssertionError('unexpected DB connection')):
    execute_from_command_line(['manage.py', 'check', '--deploy', '--fail-level', 'WARNING'])
"""
        result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
                                env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn('no issues', result.stdout)
        self.assertNotIn('WARNINGS', result.stdout+result.stderr)
        self.assertNotIn(SYNTHETIC_ENV['SHOPHOT_PROD_SECRET_KEY'], result.stdout+result.stderr)
        self.assertNotIn(SYNTHETIC_ENV['SHOPHOT_PROD_DB_PASSWORD'], result.stdout+result.stderr)

    def test_database_tls_is_required_with_optional_controlled_ca(self):
        config = load_config({'PGSSLMODE': 'disable', 'SHOPHOT_DB_SSLMODE': 'prefer'})
        self.assertEqual(config['DATABASES']['default']['OPTIONS'], {'sslmode': 'verify-full'})
        config = load_config({'SHOPHOT_PROD_DB_SSLROOTCERT': '/controlled/ca/postgresql.crt'})
        self.assertEqual(config['DATABASES']['default']['OPTIONS']['sslrootcert'], '/controlled/ca/postgresql.crt')
        for value in ('', 'relative/ca.crt', 'bad\ncert'):
            with self.assertRaisesMessage(ImproperlyConfigured, 'SHOPHOT_PROD_DB_SSLROOTCERT'):
                load_config({'SHOPHOT_PROD_DB_SSLROOTCERT': value})

    def test_common_declarations_match_development_without_importing_it(self):
        # Only inspect explicit source declarations; never execute devsettings or read its DB/secret.
        common = {
            'INSTALLED_APPS', 'MIDDLEWARE', 'ROOT_URLCONF', 'TEMPLATES', 'WSGI_APPLICATION',
            'AUTH_PASSWORD_VALIDATORS', 'LANGUAGE_CODE', 'TIME_ZONE', 'USE_I18N', 'USE_TZ',
            'DEFAULT_AUTO_FIELD', 'LOGIN_URL', 'LOGIN_REDIRECT_URL', 'LOGOUT_REDIRECT_URL',
            'DATA_UPLOAD_MAX_MEMORY_SIZE', 'FILE_UPLOAD_MAX_MEMORY_SIZE',
        }
        def declarations(filename):
            tree = ast.parse((Path(__file__).parent / filename).read_text())
            return {target.id: ast.dump(node.value) for node in tree.body if isinstance(node, ast.Assign)
                    for target in node.targets if isinstance(target, ast.Name) and target.id in common}
        dev, production = declarations('settings.py'), declarations('production.py')
        self.assertEqual(set(dev), common)
        self.assertEqual(set(production), common)
        for field in sorted(common):
            with self.subTest(field=field):
                self.assertEqual(dev[field], production[field], 'Common settings drift: '+field)
