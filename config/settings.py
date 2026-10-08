"""开发默认配置；部署时通过环境变量设置密钥、域名和 HTTPS。"""
import os
import json
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.getenv("SHOPHOT_DEBUG", "1") == "1"
SECRET_KEY = os.getenv("SHOPHOT_SECRET_KEY", "development-only-shophot-do-not-use-in-production")
if not DEBUG and SECRET_KEY == "development-only-shophot-do-not-use-in-production":
    raise ImproperlyConfigured("生产模式必须设置 SHOPHOT_SECRET_KEY")
ALLOWED_HOSTS = os.getenv("SHOPHOT_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",")
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles", "market",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware", "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware", "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [], "APP_DIRS": True,
              "OPTIONS": {"context_processors": ["django.template.context_processors.request",
                          "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages"]}}]
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3",
                         "OPTIONS": {"timeout": 20}}}
# 本机初始化脚本生成的配置已排除 Git；环境变量仍可覆盖用于部署。
local_db_file = BASE_DIR / '.local' / 'database.json'
local_db = json.loads(local_db_file.read_text()) if local_db_file.exists() else {}
if os.getenv('SHOPHOT_DB_ENGINE', local_db.get('engine', 'sqlite')) == 'postgresql':
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("SHOPHOT_DB_NAME", local_db.get("name", "shophot")),
        "USER": os.getenv("SHOPHOT_DB_USER", local_db.get("user", "shophot")),
        "PASSWORD": os.getenv("SHOPHOT_DB_PASSWORD", local_db.get("password", "")),
        "HOST": os.getenv("SHOPHOT_DB_HOST", local_db.get("host", "127.0.0.1")),
        "PORT": os.getenv("SHOPHOT_DB_PORT", local_db.get("port", "55432")),
        "CONN_MAX_AGE": 60,
    }}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
CSRF_TRUSTED_ORIGINS = [x for x in os.getenv("SHOPHOT_CSRF_TRUSTED_ORIGINS", "").split(",") if x]
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True

# 控制台与轮转文件同时记录采集状态，不记录密码、Cookie 或完整响应正文。
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOGGING = {"version": 1, "disable_existing_loggers": False,
           "formatters": {"standard": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"}},
           "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "standard"},
                        "file": {"class": "logging.handlers.RotatingFileHandler", "filename": LOG_DIR / "shophot.log",
                                 "maxBytes": 2_000_000, "backupCount": 3, "encoding": "utf-8", "formatter": "standard"}},
           "loggers": {"market": {"handlers": ["console", "file"], "level": "INFO", "propagate": False}}}
