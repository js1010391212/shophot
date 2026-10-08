"""打包固定扩展资源，不包含测试夹具、本地证据或账号配置。"""
import json
import re
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from django.conf import settings


PACKAGE_FILES = ('manifest.json', 'capture.mjs', 'controller.mjs', 'dom-reader.mjs',
                 'worker.mjs', 'bridge.js', 'popup.html', 'popup.mjs', 'popup.css', 'README.md')


def extension_version():
    """读取当前可下载资源的版本，不推断Chrome实际安装或连接状态。"""
    root = (Path(settings.BASE_DIR) / 'extensions' / 'shophot-capture').resolve()
    path = root / 'manifest.json'
    try:
        if path.resolve().parent != root or path.stat().st_size > 16 * 1024:
            return None
        manifest = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(manifest, dict):
            return None
        version = manifest.get('version')
        if manifest.get('manifest_version') == 3 and isinstance(version, str) and re.fullmatch(r'[0-9]{1,5}(?:\.[0-9]{1,5}){0,3}', version):
            return version
    except (OSError, UnicodeError, ValueError):
        pass
    return None


def extension_package():
    root = (Path(settings.BASE_DIR) / 'extensions' / 'shophot-capture').resolve()
    archive = BytesIO()
    with ZipFile(archive, 'w', ZIP_DEFLATED) as zipped:
        total = 0
        for name in PACKAGE_FILES:
            path = root / name
            if path.resolve().parent != root or not path.is_file():
                raise FileNotFoundError('浏览器扩展资源尚未安装完整。')
            size = path.stat().st_size
            total += size
            if size > 128 * 1024 or total > 512 * 1024:
                raise ValueError('浏览器扩展资源超过允许大小。')
            zipped.writestr('shophot-capture/' + name, path.read_bytes())
    archive.seek(0)
    return archive
