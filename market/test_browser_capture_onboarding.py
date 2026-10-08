"""安装包版本和上手提示使用真实GET/错误响应，不连接业务数据库。"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse
from .browser_capture_package import extension_package, extension_version, PACKAGE_FILES
from .browser_capture_views import preview


class CaptureOnboardingTests(SimpleTestCase):
    def manifest(self, directory, value):
        root = Path(directory) / 'extensions' / 'shophot-capture'
        root.mkdir(parents=True)
        path = root / 'manifest.json'
        path.write_text(json.dumps(value), encoding='utf-8')
        return path

    def request(self, method='get'):
        factory = RequestFactory()
        request = factory.get(reverse('browser_capture')) if method == 'get' else factory.post(reverse('browser_capture'), '{}', content_type='application/json')
        request.user = SimpleNamespace(is_authenticated=True, username='setup-qa')
        return request

    def test_setup_reads_version_from_manifest_and_preserves_bridge_contract(self):
        with TemporaryDirectory() as directory, override_settings(BASE_DIR=directory):
            self.manifest(directory, {'manifest_version': 3, 'version': '2.4.6'})
            response = preview(self.request())
        self.assertContains(response, '可下载扩展版本：<strong>2.4.6</strong>')
        self.assertContains(response, '下载 Chrome 扩展 2.4.6')
        self.assertContains(response, '已安装版本')
        self.assertContains(response, 'id="browser-capture-form"')
        self.assertContains(response, 'data-browser-capture-bridge="ready"')
        self.assertContains(response, '第二个商品及规格切换仍待验证')
        self.assertNotContains(response, '速卖通和 eBay 适配尚未通过实站验收')

    def test_missing_version_stays_unknown_and_setup_remains_usable(self):
        with TemporaryDirectory() as directory, override_settings(BASE_DIR=directory):
            response = preview(self.request())
        self.assertContains(response, '版本信息暂不可用')
        self.assertContains(response, '更新已安装扩展')
        self.assertContains(response, 'data-browser-capture-bridge="ready"')

    def test_validation_error_keeps_upgrade_guidance_and_no_save_notice(self):
        with TemporaryDirectory() as directory, override_settings(BASE_DIR=directory):
            self.manifest(directory, {'manifest_version': 3, 'version': '1.2.3'})
            response = preview(self.request('post'))
        self.assertContains(response, '未保存观测', status_code=400)
        self.assertContains(response, '可下载扩展版本：<strong>1.2.3</strong>', status_code=400)
        self.assertContains(response, '更新已安装扩展', status_code=400)
        self.assertNotContains(response, 'data-browser-capture-bridge="ready"', status_code=400)

    def test_invalid_manifest_does_not_invent_version_or_fail_page(self):
        for value in [[], {'manifest_version': 3, 'version': '<script>x</script>'},
                      {'manifest_version': 2, 'version': '1.2.3'}, {'manifest_version': 3, 'version': 123}]:
            with self.subTest(value=value), TemporaryDirectory() as directory, override_settings(BASE_DIR=directory):
                self.manifest(directory, value)
                self.assertIsNone(extension_version())
                self.assertContains(preview(self.request()), '版本信息暂不可用')
        with TemporaryDirectory() as directory, override_settings(BASE_DIR=directory):
            path = self.manifest(directory, {})
            path.write_text('invalid JSON')
            self.assertIsNone(extension_version())

    def test_outside_or_oversized_manifest_is_not_read(self):
        with TemporaryDirectory() as directory, override_settings(BASE_DIR=directory):
            path = self.manifest(directory, {})
            outside = Path(directory) / 'outside.txt'
            outside.write_text('{"manifest_version":3,"version":"9.9.9"}')
            path.unlink()
            path.symlink_to(outside)
            with patch.object(Path, 'read_text', side_effect=AssertionError('must not read outside')):
                self.assertIsNone(extension_version())
            path.unlink()
            path.write_text('x' * (16 * 1024 + 1))
            with patch.object(Path, 'read_text', side_effect=AssertionError('must not read oversized')):
                self.assertIsNone(extension_version())

    def test_actual_package_version_matches_advertised_version_and_fixed_resources(self):
        with ZipFile(extension_package()) as archive:
            manifest = json.loads(archive.read('shophot-capture/manifest.json'))
            self.assertEqual(manifest['version'], extension_version())
            self.assertEqual(set(archive.namelist()), {'shophot-capture/' + name for name in PACKAGE_FILES})
            self.assertIn(b'popup.mjs', archive.read('shophot-capture/popup.html'))
