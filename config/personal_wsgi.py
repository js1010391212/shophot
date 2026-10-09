"""Fixed personal entry point: the proxy gate also protects WhiteNoise static paths."""
import os
from django.core.wsgi import get_wsgi_application
from django.conf import settings
from .personal_runtime import LoopbackHTTPSBoundary

os.environ['DJANGO_SETTINGS_MODULE'] = 'config.personal_access'
application = LoopbackHTTPSBoundary(get_wsgi_application(), settings.PERSONAL_HOST)
