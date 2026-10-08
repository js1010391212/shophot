"""自有表格映射回归；全部受控夹具，不访问实库或运行服务。"""
import csv
import time
from decimal import Decimal
from io import StringIO, BytesIO
from unittest.mock import patch
from xml.etree import ElementTree as ET
import zipfile
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.urls import reverse
from .models import ShippingRate
from .shipping_import import read_rate_table, parse_rates, NS
from .shipping_mapping import ColumnMappingForm, sign_table, load_table
from .test_shipping import rate_data, csv_bytes, xlsx_bytes


def custom_csv(headers=('线路名', '公斤报价'), rows=None):
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows(rows or [['测试线路', '20']])
    return buffer.getvalue().encode()


def selection():
    return {**{'common_'+k: v for k, v in rate_data().items() if k not in ('name', 'per_kg')},
            'column_name': '0', 'column_per_kg': '1'}


def reordered_xlsx(epoch1904=False, formula=False, multiple=False):
    original = xlsx_bytes(rate_data(), epoch1904=epoch1904)
    buffer = BytesIO()
    main = NS['m']
    with zipfile.ZipFile(BytesIO(original)) as source, zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as output:
        for info in source.infolist():
            raw = source.read(info.filename)
            if info.filename == 'xl/workbook.xml':
                root = ET.fromstring(raw)
                sheets = root.find('m:sheets', NS)
                sheets[0].set('name', '我的货代表格')
                if not multiple:
                    for child in list(sheets)[1:]:
                        sheets.remove(child)
                raw = ET.tostring(root)
            elif info.filename == 'xl/worksheets/sheet1.xml':
                root = ET.fromstring(raw)
                sheet = root.find('m:sheetData', NS)
                for child in list(sheet):
                    sheet.remove(child)
                for number, values in ((1, ['开始日期', '运价', '线路名']), (7, ['43830' if epoch1904 else '45292', '123.45', '测试线路'])):
                    row = ET.SubElement(sheet, f'{{{main}}}row', {'r': str(number)})
                    for index, value in enumerate(values):
                        numeric = number == 7 and index < 2
                        cell = ET.SubElement(row, f'{{{main}}}c', {'r': f'{chr(65+index)}{number}', 't': 'n' if numeric else 'inlineStr'})
                        if numeric:
                            ET.SubElement(cell, f'{{{main}}}v').text = value
                        else:
                            ET.SubElement(ET.SubElement(cell, f'{{{main}}}is'), f'{{{main}}}t').text = value
                        if formula and number == 7 and index == 1:
                            ET.SubElement(cell, f'{{{main}}}f').text = 'SUM(1,2)'
                raw = ET.tostring(root)
            output.writestr(info, raw)
    return buffer.getvalue()


class ShippingMappingTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username='mapping')
        self.other = get_user_model().objects.create_user(username='other-mapping')
        self.client.force_login(self.owner)
        self.url = reverse('shipping_import')

    def upload(self, raw=None, name='custom.csv', client=None):
        return (client or self.client).post(self.url, {'file': SimpleUploadedFile(name, raw or custom_csv())})

    def mapped(self, response, changes=None):
        return self.client.post(self.url, {'action': 'map', 'mapping_token': response.context['mapping_token'], **selection(), **(changes or {})})

    def test_custom_headers_common_values_preview_confirm_idempotence(self):
        response = self.upload()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '公斤报价')
        self.assertEqual(len(response.context['samples']), 1)
        self.assertFalse(ShippingRate.objects.exists())
        response = self.mapped(response)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(response.context['rows'][0]['per_kg']), Decimal('20.00'))
        self.assertFalse(ShippingRate.objects.exists())
        self.assertNotContains(response, '上传并校验')
        self.assertContains(response, '确认保存报价')
        token = response.context['preview']
        for _ in range(2):
            self.assertEqual(self.client.post(self.url, {'action': 'confirm', 'preview': token}).status_code, 302)
        row = ShippingRate.objects.get()
        self.assertEqual(row.owner, self.owner)
        self.assertEqual(row.source, 'import')
        row.active = False
        row.save()
        self.client.post(self.url, {'action': 'confirm', 'preview': token})
        row.refresh_from_db()
        self.assertFalse(row.active)

    def test_standard_template_remains_direct_preview(self):
        for raw, name in ((csv_bytes([rate_data()]), 'template.csv'), (xlsx_bytes(rate_data()), 'template.xlsx')):
            response = self.upload(raw, name)
            self.assertEqual(response.status_code, 200)
            self.assertIn('preview', response.context)
            self.assertNotIn('mapping_form', response.context)
        self.assertFalse(ShippingRate.objects.exists())

    def test_exact_unique_header_defaults_and_common_choice_has_no_default(self):
        table = read_rate_table(custom_csv(('报价名称', '每公斤价格')), 'own.csv')
        form = ColumnMappingForm(table=table)
        self.assertEqual(form['column_per_kg'].value(), '1')
        self.assertEqual(form['common_method'].value(), None)
        self.assertEqual(form.fields['common_method'].choices[0][0], '')
        self.assertIn(('per_kg', '每公斤 + 每票'), form.fields['common_method'].choices)
        self.assertEqual(form.fields['common_effective_from'].widget.input_type, 'date')

    def test_mapping_wrong_indices_duplicates_sources_unknowns_and_missing_money(self):
        response = self.upload()
        for changes in ({'column_per_kg': '40'}, {'column_per_kg': '-1'}, {'column_per_kg': 'abc'},
                        {'column_per_kg': '0'}, {'column_per_kg': '', 'common_per_kg': ''},
                        {'common_per_kg': '1'}, {'column_unknown': '1'}, {'common_fixed_fee': ''}):
            result = self.mapped(response, changes)
            self.assertEqual(result.status_code, 400)
        duplicated = {'action': 'map', 'mapping_token': response.context['mapping_token'], **selection(), 'column_per_kg': ['1', '0']}
        self.assertEqual(self.client.post(self.url, duplicated).status_code, 400)
        self.assertFalse(ShippingRate.objects.exists())

    def test_original_row_numbers_and_sample_max_three(self):
        raw = b'line,price\n\nname,20\nname,bad\nname,20\nname,20\n'
        response = self.upload(raw)
        self.assertEqual(len(response.context['samples']), 3)
        result = self.mapped(response)
        self.assertEqual(result.status_code, 400)
        self.assertContains(result, '第 4 行', status_code=400)
        self.assertFalse(ShippingRate.objects.exists())

    def test_xlsx_reordered_date_epoch_does_not_convert_price_and_formula_rejection(self):
        for epoch in (False, True):
            response = self.upload(reordered_xlsx(epoch), 'custom.xlsx')
            self.assertEqual(response.status_code, 200)
            result = self.mapped(response, {'column_name': '2', 'column_per_kg': '1', 'column_effective_from': '0', 'common_effective_from': ''})
            self.assertEqual(result.status_code, 200)
            row = result.context['rows'][0]
            self.assertEqual(row['effective_from'], '2024-01-01')
            self.assertEqual(row['per_kg'], '123.45')
        response = self.upload(reordered_xlsx(formula=True), 'custom.xlsx')
        self.assertContains(response, '第 7 行含公式', status_code=400)
        self.assertFalse(ShippingRate.objects.exists())

    def test_xlsx_invalid_date_keeps_original_row(self):
        # Zip must be rewritten to preserve CRC.
        blob = BytesIO()
        with zipfile.ZipFile(BytesIO(reordered_xlsx())) as source, zipfile.ZipFile(blob, 'w') as output:
            for info in source.infolist():
                output.writestr(info, source.read(info.filename).replace(b'45292', b'45292.5'))
        response = self.upload(blob.getvalue(), 'custom.xlsx')
        result = self.mapped(response, {'column_name': '2', 'column_effective_from': '0', 'common_effective_from': ''})
        self.assertContains(result, '第 7 行日期无效', status_code=400)

    def test_mapping_token_account_expiry_tampering_and_salt_separation(self):
        response = self.upload()
        token = response.context['mapping_token']
        self.client.force_login(self.other)
        self.assertEqual(self.mapped(response).status_code, 400)
        self.client.force_login(self.owner)
        self.assertEqual(self.mapped(response, {'mapping_token': token+'x'}).status_code, 400)
        with patch('django.core.signing.time.time', return_value=time.time()+1201):
            self.assertEqual(self.mapped(response).status_code, 400)
        self.assertEqual(self.client.post(self.url, {'action': 'confirm', 'preview': token}).status_code, 400)
        preview = self.mapped(response).context['preview']
        self.assertEqual(self.mapped(response, {'mapping_token': preview}).status_code, 400)
        self.assertFalse(ShippingRate.objects.exists())

    def test_login_csrf_and_duplicate_confirm_parameters(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.get(self.url).status_code, 302)
        client.force_login(self.owner)
        self.assertEqual(self.upload(client=client).status_code, 403)
        response = self.upload()
        self.assertEqual(client.post(self.url, {'action': 'map', 'mapping_token': response.context['mapping_token'], **selection()}).status_code, 403)
        preview = self.mapped(response).context['preview']
        self.assertEqual(client.post(self.url, {'action': 'confirm', 'preview': preview}).status_code, 403)
        self.assertEqual(self.client.post(self.url, {'action': 'confirm', 'preview': [preview, preview]}).status_code, 400)
        self.assertFalse(ShippingRate.objects.exists())

    def test_file_safety_bounds_multisheet_duplicate_headers_and_bad_token(self):
        for raw, filename in ((custom_csv(tuple(str(i) for i in range(41)), [['x']*41]), 'many.csv'),
                              (custom_csv(rows=[['x', '20']]*101), 'many.csv'), (custom_csv(('same', 'same')), 'dup.csv'),
                              (b'x'*(2*1024*1024+1), 'big.csv'), (reordered_xlsx(multiple=True), 'multi.xlsx')):
            with self.assertRaises(ValidationError):
                read_rate_table(raw, filename)
        self.assertEqual(self.client.post(self.url, {'action': 'map', 'mapping_token': 'bad'}).status_code, 400)
        with self.assertRaises(ValidationError):
            sign_table({'rows': ['x'*180001]}, self.owner.pk)
        self.assertFalse(ShippingRate.objects.exists())
