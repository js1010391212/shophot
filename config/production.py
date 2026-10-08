"""显式生产入口；不导入开发settings，不读取本机数据库文件。"""
import ipaddress
import os
from pathlib import Path
import re

from django.core.exceptions import ImproperlyConfigured


def _required(name):
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise ImproperlyConfigured(f'生产配置缺少 {name}。')
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ImproperlyConfigured(f'生产配置 {name} 含无效控制字符。')
    return value


def _host(value):
    # 不允许Django的前导点通配、URL、端口或不完整主机名。
    if value.startswith('[') and value.endswith(']'):
        try:
            ipaddress.IPv6Address(value[1:-1])
            return True
        except ValueError:
            return False
    if len(value) > 253:
        return False
    return bool(re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*', value))


BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = False
SECRET_KEY = _required('SHOPHOT_PROD_SECRET_KEY')
if (len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5
        or SECRET_KEY != SECRET_KEY.strip()
        or SECRET_KEY.lower().startswith('django-insecure-')
        or any(marker in SECRET_KEY.lower() for marker in ('development-only', 'changeme', 'change-me', 'replace-me'))):
    raise ImproperlyConfigured('SHOPHOT_PROD_SECRET_KEY 须为独立随机密钥，至少50字符，不能使用明显弱值。')
SECRET_KEY_FALLBACKS = []
ALLOWED_HOSTS = [host.strip() for host in _required('SHOPHOT_PROD_ALLOWED_HOSTS').split(',')]
if any(not _host(host) for host in ALLOWED_HOSTS) or len(ALLOWED_HOSTS) != len(set(ALLOWED_HOSTS)):
    raise ImproperlyConfigured('SHOPHOT_PROD_ALLOWED_HOSTS 须为非重复主机名/IP，不能含通配、URL、端口或空项；IPv6须使用方括号。')

_db = {key: _required('SHOPHOT_PROD_DB_' + key) for key in ('NAME', 'USER', 'PASSWORD', 'HOST', 'PORT')}
if not re.fullmatch(r'[0-9]{1,5}', _db['PORT']) or not 1 <= int(_db['PORT']) <= 65535:
    raise ImproperlyConfigured('SHOPHOT_PROD_DB_PORT 须为1–65535的整数。')
_db_host = _db['HOST']
try:
    ipaddress.ip_address(_db_host)
except ValueError:
    if not _host(_db_host) or _db_host.startswith('['):
        raise ImproperlyConfigured('SHOPHOT_PROD_DB_HOST 须为明确主机名/IP，不支持URL、端口或本地socket路径。')
DATABASES = {'default': {
    'ENGINE': 'django.db.backends.postgresql', 'NAME': _db['NAME'], 'USER': _db['USER'],
    'PASSWORD': _db['PASSWORD'], 'HOST': _db['HOST'], 'PORT': _db['PORT'], 'CONN_MAX_AGE': 60,
    'OPTIONS': {'sslmode': 'verify-full'},
}}
if 'SHOPHOT_PROD_DB_SSLROOTCERT' in os.environ:
    _ca = _required('SHOPHOT_PROD_DB_SSLROOTCERT')
    if not Path(_ca).is_absolute():
        raise ImproperlyConfigured('SHOPHOT_PROD_DB_SSLROOTCERT 须为受控CA证书的绝对路径。')
    DATABASES['default']['OPTIONS']['sslrootcert'] = _ca
# 强制TLS与CA/主机名校验，不允许prefer明文回退；此处不读取证书或连接DB。

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SECURE_SSL_REDIRECT = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
_hsts = os.environ.get('SHOPHOT_PROD_HSTS_SECONDS', '3600')
if not re.fullmatch(r'[0-9]{1,8}', _hsts) or not 1 <= int(_hsts) <= 31536000:
    raise ImproperlyConfigured('SHOPHOT_PROD_HSTS_SECONDS 须为1–31536000的整数。')
SECURE_HSTS_SECONDS = int(_hsts)
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
# 小范围试用尚未核验全部子域，不作长期preload承诺；只静默两项相应建议。
SILENCED_SYSTEM_CHECKS = ['security.W005', 'security.W021']
_proxy = os.environ.get('SHOPHOT_PROD_TRUST_PROXY_PROTO', '0')
if _proxy not in ('0', '1'):
    raise ImproperlyConfigured('SHOPHOT_PROD_TRUST_PROXY_PROTO 只接受0或1。')
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') if _proxy == '1' else None
USE_X_FORWARDED_HOST = False
USE_X_FORWARDED_PORT = False
# 同源使用HTTPS，不继承开发环境的CSRF通配来源。
CSRF_TRUSTED_ORIGINS = []

INSTALLED_APPS = [
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles', 'market',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware', 'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [], 'APP_DIRS': True,
              'OPTIONS': {'context_processors': ['django.template.context_processors.request',
                         'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION = 'config.wsgi.application'
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
LOGGING = {'version': 1, 'disable_existing_loggers': False,
           'handlers': {'console': {'class': 'logging.StreamHandler'}},
           'loggers': {'market': {'handlers': ['console'], 'level': 'INFO', 'propagate': False}}}
