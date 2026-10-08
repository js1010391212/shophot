"""打包固定扩展资源，不包含测试夹具、本地证据或账号配置。"""
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from django.conf import settings


PACKAGE_FILES = ('manifest.json', 'capture.mjs', 'controller.mjs', 'dom-reader.mjs',
                 'worker.mjs', 'bridge.js', 'popup.html', 'popup.mjs', 'popup.css', 'README.md')


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
