"""Private runtime configuration and loopback-only HTTPS proxy boundary."""
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit
from django.core.exceptions import ImproperlyConfigured

KEYS = {'SHOPHOT_PERSONAL_ORIGIN', 'SHOPHOT_PERSONAL_SECRET_KEY', 'SHOPHOT_PERSONAL_DB_CONFIG'}


def load_private_config():
    filename = os.environ.get('SHOPHOT_PERSONAL_CONFIG')
    if not filename:
        return
    path = Path(filename)
    try:
        if not path.is_absolute() or path.is_symlink():
            raise ValueError
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 8192:
            raise ValueError
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or set(data) != KEYS or any(not isinstance(v, str) for v in data.values()):
            raise ValueError
    except (OSError, ValueError, TypeError):
        raise ImproperlyConfigured('个人运行配置须为当前用户拥有的私有JSON文件（权限0600），包含三个指定字段。') from None
    os.environ.update(data)


def required(name):
    value = os.environ.get(name, '')
    if not value or value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ImproperlyConfigured(f'个人访问配置缺少或无效：{name}。')
    return value


def origin_host(origin):
    try:
        url = urlsplit(origin)
        host = url.hostname
        if (url.scheme != 'https' or not host or origin != 'https://'+host or url.netloc != host or url.path or url.query or url.fragment
                or not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+', host)
                or len(host) > 253):
            raise ValueError
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return host
        raise ValueError
    except (ValueError, TypeError):
        raise ImproperlyConfigured('个人访问地址须为一个精确HTTPS主机名，不含端口、路径、通配或认证信息。') from None


def local_database(filename):
    path = Path(filename)
    try:
        if not path.is_absolute() or path.name != 'database.json' or path.parent.name != '.local':
            raise ValueError
        if path.stat().st_size > 8192:
            raise ValueError
        data = json.loads(path.read_text())
        host = data.get('host')
        if data.get('engine') != 'postgresql' or not isinstance(host, str) or any(ord(c) < 32 or ord(c) == 127 for c in host):
            raise ValueError
        socket = host.startswith('/') and '..' not in Path(host).parts
        if host not in ('127.0.0.1', '::1') and not socket:
            raise ValueError
        port = str(data.get('port', ''))
        if not re.fullmatch(r'[0-9]{1,5}', port) or not 1 <= int(port) <= 65535:
            raise ValueError
        for key in ('name', 'user'):
            if not isinstance(data.get(key), str) or not data[key].strip() or any(ord(c) < 32 or ord(c) == 127 for c in data[key]):
                raise ValueError
        password = data.get('password', '')
        if not isinstance(password, str) or any(ord(c) < 32 for c in password):
            raise ValueError
    except (OSError, ValueError, TypeError, AttributeError):
        raise ImproperlyConfigured('个人访问只接受明确的项目.local/database.json、本机回环或显式Unix socket PostgreSQL配置。') from None
    return {'ENGINE': 'django.db.backends.postgresql', 'NAME': data['name'], 'USER': data['user'],
            'PASSWORD': password, 'HOST': host, 'PORT': port, 'CONN_MAX_AGE': 60}  # Existing local transport; production remains verify-full.


class LoopbackHTTPSBoundary:
    """Reject non-local peers and unverified host/proto before app or static files."""
    def __init__(self, application, host):
        self.application, self.host = application, host

    def __call__(self, environ, start_response):
        if (environ.get('REMOTE_ADDR') not in ('127.0.0.1', '::1')
                or environ.get('HTTP_HOST', '').lower() not in (self.host, self.host+':443')
                or environ.get('HTTP_X_FORWARDED_PROTO') != 'https'):
            body = b'Personal access proxy boundary rejected this request.'
            start_response('403 Forbidden', [('Content-Type', 'text/plain; charset=utf-8'),
                                            ('Content-Length', str(len(body))), ('Cache-Control', 'no-store')])
            return [body]
        return self.application(environ, start_response)
