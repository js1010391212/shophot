"""安装包不得混入本地证据、账号配置或资源目录外的文件。"""
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from django.test import SimpleTestCase, override_settings

from .browser_capture_package import PACKAGE_FILES, extension_package


class BrowserPackageTests(SimpleTestCase):
    def prepare(self, directory):
        root = Path(directory) / 'extensions' / 'shophot-capture'
        root.mkdir(parents=True)
        for name in PACKAGE_FILES:
            (root / name).write_text('extension resource')
        (root / '.local').mkdir()
        (root / '.local' / 'private-evidence.json').write_text('not for export')
        (root / 'account.env').write_text('not for export')
        return root

    def test_fixed_archive_excludes_local_evidence_and_account_files(self):
        with TemporaryDirectory() as temporary, override_settings(BASE_DIR=temporary):
            self.prepare(temporary)
            with ZipFile(extension_package()) as archive:
                self.assertEqual(set(archive.namelist()), {'shophot-capture/'+name for name in PACKAGE_FILES})
                self.assertNotIn(b'not for export', b''.join(archive.read(name) for name in archive.namelist()))

    def test_resource_cannot_link_outside_extension_directory(self):
        with TemporaryDirectory() as temporary, override_settings(BASE_DIR=temporary):
            root = self.prepare(temporary)
            outside = Path(temporary) / 'outside.txt'
            outside.write_text('not for export')
            (root / 'README.md').unlink()
            (root / 'README.md').symlink_to(outside)
            with self.assertRaises(FileNotFoundError):
                extension_package()
