"""Personal HTTPS proxy entry; independent from production and development."""
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from .personal_runtime import load_private_config, required, origin_host, local_database

load_private_config()
BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = False
SECRET_KEY = required('SHOPHOT_PERSONAL_SECRET_KEY')
if (len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5 or any(marker in SECRET_KEY.lower() for marker in
        ('django-insecure-', 'development-only', 'changeme', 'change-me', 'replace-me'))):
    raise ImproperlyConfigured('个人访问必须使用独立随机密钥（至少50字符），不能使用开发或占位密钥。')
SECRET_KEY_FALLBACKS = []
PERSONAL_ORIGIN = required('SHOPHOT_PERSONAL_ORIGIN')
PERSONAL_HOST = origin_host(PERSONAL_ORIGIN)
ALLOWED_HOSTS = [PERSONAL_HOST]
DATABASES = {'default': local_database(required('SHOPHOT_PERSONAL_DB_CONFIG'))}
SESSION_COOKIE_NAME = 'shophot_personal_session'
CSRF_COOKIE_NAME = 'shophot_personal_csrf'
SESSION_COOKIE_DOMAIN = None
CSRF_COOKIE_DOMAIN = None
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = False
USE_X_FORWARDED_PORT = False
CSRF_TRUSTED_ORIGINS = []
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SILENCED_SYSTEM_CHECKS = ['security.W005', 'security.W021']

INSTALLED_APPS = [
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles', 'market',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware', 'whitenoise.middleware.WhiteNoiseMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware', 'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [], 'APP_DIRS': True,
              'OPTIONS': {'context_processors': ['django.template.context_processors.request',
                         'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION = 'config.personal_wsgi.application'
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
STATIC_ROOT = BASE_DIR / '.local' / 'personal-static'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
WHITENOISE_USE_FINDERS = False
WHITENOISE_AUTOREFRESH = False
WHITENOISE_ALLOW_ALL_ORIGINS = False
WHITENOISE_MAX_AGE = 60
LOGGING = {'version': 1, 'disable_existing_loggers': False,
           'handlers': {'console': {'class': 'logging.StreamHandler'}},
           'loggers': {'market': {'handlers': ['console'], 'level': 'INFO', 'propagate': False}}}
