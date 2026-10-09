"""报价及利润核算使用独立测试库；受控金额不写入业务库。"""
import csv
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal as D
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import patch
import zipfile
from xml.etree import ElementTree as ET
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from .models import ShippingRate
from .shipping import Quote, estimate, public_quotes, quotes_for, rate_fingerprint
from .shipping_forms import ShippingRateForm, ShippingEstimateForm
from .shipping_import import HEADERS, COLUMNS, parse_rates
from .shipping_views import SALT


def rate_data(**changes):
    data = dict(name='受控测试报价，非真实运价', carrier='测试物流商', origin='CN', destination='US', currency='USD',
                method='per_kg', min_weight='0.1', max_weight='10', step_weight='0.1', per_kg='20',
                first_weight='', first_price='', step_price='', fixed_fee='2', fuel_basis='freight',
                volume_divisor='5000', effective_from='2026-01-01', effective_until='', source_url='', notes='仅测试')
    return dict(data, **changes)


def csv_bytes(rows):
    out = StringIO()
    writer = csv.writer(out)
    writer.writerow(HEADERS)
    for row in rows:
        writer.writerow([row.get(key, '') for key, _ in COLUMNS])
    return ('\ufeff' + out.getvalue()).encode('utf-8')


def xlsx_bytes(row=None, formula=False, epoch1904=False, serial=None):
    # 修改正式空模板的副本，验证真实导入格式；不使用应用运行期的 Excel 写库。
    source = Path(settings.BASE_DIR) / 'market/data/outputs/logistics-20261008/shipping_rates_template.xlsx'
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    blob = BytesIO()
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(blob, 'w', zipfile.ZIP_DEFLATED) as output:
        for info in original.infolist():
            content = original.read(info.filename)
            if info.filename == 'xl/workbook.xml' and epoch1904:
                root = ET.fromstring(content)
                props = root.find(f'{{{ns}}}workbookPr')
                if props is None:
                    props = ET.SubElement(root, f'{{{ns}}}workbookPr')
                props.set('date1904', '1')
                content = ET.tostring(root)
            if info.filename == 'xl/worksheets/sheet1.xml' and row is not None:
                root = ET.fromstring(content)
                sheet_data = root.find(f'{{{ns}}}sheetData')
                for old in list(sheet_data)[1:]:
                    sheet_data.remove(old)
                element = ET.SubElement(sheet_data, f'{{{ns}}}row', {'r': '2'})
                for index, (key, _) in enumerate(COLUMNS):
                    address = f'{chr(65 + index)}2'
                    cell = ET.SubElement(element, f'{{{ns}}}c', {'r': address, 't': 'inlineStr'})
                    if key == 'effective_from' and serial is not None:
                        cell.set('t', 'n')
                        ET.SubElement(cell, f'{{{ns}}}v').text = str(serial)
                    else:
                        ET.SubElement(ET.SubElement(cell, f'{{{ns}}}is'), f'{{{ns}}}t').text = row.get(key, '')
                    if formula and key == 'per_kg':
                        ET.SubElement(cell, f'{{{ns}}}f').text = '10+10'
                content = ET.tostring(root)
            output.writestr(info.filename, content)
    return blob.getvalue()


class ShippingCalculationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('shipping-calculation')
        self.quote = Quote(key='test', name='测试', carrier='测试', origin='CN', destination='US', currency='USD',
            method='per_kg', min_weight=D('.1'), max_weight=D('10'), step_weight=D('.1'), fixed_fee=D('2'),
            volume_divisor=5000, per_kg=D('20'), effective_from=date(2026, 1, 1))

    def calc(self, quote=None, **changes):
        data = dict(weight=D('.5'), length=D('10'), width=D('10'), height=D('10'),
                    fuel_rate=D('10'), extra=D('3'), exchange_rate=D('7'), currency='CNY')
        return estimate(quote or self.quote, **dict(data, **changes))

    def test_per_kg_components_fx_and_reconciliation(self):
        result = self.calc()
        self.assertEqual(result['freight'], D('10'))
        self.assertEqual(result['fixed_fee'], D('2'))
        self.assertEqual(result['fuel'], D('1'))
        self.assertEqual(result['total'], D('16'))
        self.assertEqual(result['converted'], D('112'))
        self.assertEqual(result['total'], result['freight'] + result['fixed_fee'] + result['fuel'] + result['extra'])

    def test_fuel_basis_includes_fixed_fee_only_when_contract_says_so(self):
        self.assertEqual(self.calc(replace(self.quote, fuel_basis='subtotal'))['fuel'], D('1.20'))
        self.assertEqual(self.calc()['fuel'], D('1'))

    def test_exact_step_and_next_thousandth(self):
        for weight, billed in [('.1', '.1'), ('.5', '.5'), ('.501', '.6'), ('1.001', '1.1')]:
            self.assertEqual(self.calc(weight=D(weight), length=D('1'), width=D('1'), height=D('1'))['billed_weight'], D(billed))

    def test_volume_weight_wins_and_is_not_rounded_before_billing(self):
        result = self.calc(length=D('10'), width=D('10'), height=D('25.01'))
        self.assertEqual(result['volume_weight'], D('.5002'))
        self.assertEqual(result['billed_weight'], D('.6'))
        self.assertEqual(result['volume_display'], '0.5002')

    def test_maximum_billing_boundary_and_missing_dimensions(self):
        self.assertEqual(self.calc(weight=D('10'))['billed_weight'], D('10'))
        for changes in [dict(weight=D('10.001')), dict(length=None), dict(width=None), dict(height=None)]:
            with self.assertRaises(ValidationError):
                self.calc(**changes)

    def test_first_weight_and_continuation_are_rounded_from_first_weight(self):
        quote = replace(self.quote, method='first_step', min_weight=D('.5'), first_weight=D('.5'),
                        first_price=D('8'), step_weight=D('.2'), step_price=D('3'), fixed_fee=D('0'), volume_divisor=None)
        for weight, billed, freight in [('.001', '.5', '8'), ('.5', '.5', '8'), ('.501', '.7', '11'), ('.7', '.7', '11'), ('.701', '.9', '14')]:
            result = self.calc(quote, weight=D(weight))
            self.assertEqual(result['billed_weight'], D(billed))
            self.assertEqual(result['freight'], D(freight))

    def test_same_currency_ignores_tampered_conversion_and_zero_fees_remain_zero(self):
        result = self.calc(currency='USD', exchange_rate=D('99'), fuel_rate=D('0'), extra=D('0'))
        self.assertEqual(result['exchange_rate'], D('1'))
        self.assertEqual(result['converted'], D('12'))
        self.assertEqual(result['fuel'], D('0'))

    def test_half_up_and_package_allocation_tail_difference(self):
        quote = replace(self.quote, per_kg=D('0'), fixed_fee=D('10.01'), fuel_basis='subtotal')
        result = self.calc(quote, fuel_rate=D('0'), extra=D('0'), currency='USD', units=3)
        self.assertEqual(result['converted'], D('3.34'))
        self.assertEqual(result['allocation_delta'], D('.01'))
        self.assertEqual(self.calc(replace(quote, fixed_fee=D('1.05')), fuel_rate=D('10'), extra=D('0'), currency='USD')['fuel'], D('.11'))

    def test_official_reference_tariff_route_parcel_and_boundary(self):
        quotes = {q.destination: q for q in public_quotes()}
        for country, first, one, five in [('US','299','372','868'), ('GB','309','363','792'), ('DE','309','363','792'),
                                          ('FR','309','363','792'), ('CA','299','372','868'), ('AU','232','291','733'),
                                          ('JP','205','237','478'), ('SG','150','180','413')]:
            for weight, expected in [('.5', first), ('.501', one), ('1', one), ('5', five)]:
                result = self.calc(quotes[country], weight=D(weight), currency='CNY')
                self.assertEqual(result['freight'], D(expected))
        with self.assertRaises(ValidationError):
            self.calc(quotes['US'], weight=D('19.501'))

    def test_expired_or_not_yet_effective_quote_cannot_calculate(self):
        for quote in [replace(self.quote, effective_until=timezone.localdate() - timedelta(days=1)),
                      replace(self.quote, effective_from=timezone.localdate() + timedelta(days=1))]:
            with self.assertRaises(ValidationError):
                self.calc(quote)


class ShippingWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('shipping-owner')
        self.other = get_user_model().objects.create_user('shipping-other')
        self.client.force_login(self.user)
        self.estimate_data = dict(shipping_quote='public:sf-economy-US', package_weight='.5', package_length='10',
                                 package_width='10', package_height='10', fuel_rate='10', shipping_extra='2',
                                 cost_currency='CNY', package_units='1', shipping_exchange_rate='')

    def saved(self, owner=None, **changes):
        form = ShippingRateForm(rate_data(**changes))
        self.assertTrue(form.is_valid(), form.errors)
        rate = form.save(commit=False)
        rate.owner = owner or self.user
        rate.source = 'manual'
        rate.save()
        return rate

    def upload(self, content, name='rates.csv'):
        return self.client.post(reverse('shipping_import'), {'file': SimpleUploadedFile(name, content)})

    def test_get_has_no_writes_and_default_public_rate_is_not_contract_price(self):
        response = self.client.get(reverse('shipping'))
        self.assertContains(response, '非协议价')
        self.assertEqual(ShippingRate.objects.count(), 0)
        self.assertEqual(len(response.context['form'].quotes), 8)

    def test_manual_rate_date_is_browser_iso_and_destination_is_explicit(self):
        response = self.client.get(reverse('shipping_rate_add'))
        self.assertIn(f'value="{timezone.localdate().isoformat()}"', str(response.context['form']['effective_from']))
        self.assertEqual(response.context['form']['destination'].value(), None)
        form = ShippingRateForm(rate_data(destination=''))
        self.assertFalse(form.is_valid())
        self.assertIn('destination', form.errors)

    def test_required_dimensions_and_unknown_fees_block_estimate(self):
        for name in ('package_weight', 'package_units', 'package_length', 'package_width', 'package_height', 'fuel_rate', 'shipping_extra'):
            response = self.client.post(reverse('shipping'), dict(self.estimate_data, **{name: ''}))
            self.assertIsNone(response.context['result'])
            self.assertTrue(response.context['form'].errors)

    def test_estimate_breakdown_and_profit_link(self):
        response = self.client.post(reverse('shipping'), self.estimate_data)
        self.assertEqual(response.context['result']['total'], D('330.90'))
        self.assertIn('shipping_mode=quote', response.context['profit_url'])
        self.assertContains(response, '330.90')

    def test_private_quotes_are_isolated_expired_or_paused_excluded(self):
        owned = self.saved()
        other = self.saved(self.other)
        expired = self.saved(name='旧报价', effective_until='2026-01-02')
        paused = self.saved(name='已暂停')
        paused.active = False
        paused.save()
        available = {q.key for q in quotes_for(self.user)}
        self.assertIn(f'user:{owned.pk}', available)
        self.assertNotIn(f'user:{other.pk}', available)
        self.assertNotIn(f'user:{expired.pk}', available)
        self.assertNotIn(f'user:{paused.pk}', available)
        response = self.client.post(reverse('shipping'), dict(self.estimate_data, shipping_quote=f'user:{other.pk}'))
        self.assertIsNone(response.context['result'])
        for route in ('shipping_rate_edit', 'shipping_rate_toggle'):
            response = self.client.post(reverse(route, args=[other.pk]), rate_data())
            self.assertEqual(response.status_code, 404)

    def test_manual_save_edit_duplicate_and_recoverable_pause(self):
        response = self.client.post(reverse('shipping_rate_add'), rate_data())
        self.assertEqual(response.status_code, 302)
        rate = ShippingRate.objects.get()
        self.assertEqual(rate.owner, self.user)
        self.assertEqual(rate.source, 'manual')
        response = self.client.post(reverse('shipping_rate_add'), rate_data(per_kg='20.00'))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ShippingRate.objects.count(), 1)
        self.assertEqual(self.client.get(reverse('shipping_rate_toggle', args=[rate.pk])).status_code, 405)
        self.client.post(reverse('shipping_rate_toggle', args=[rate.pk]))
        rate.refresh_from_db()
        self.assertFalse(rate.active)
        self.client.post(reverse('shipping_rate_toggle', args=[rate.pk]))
        self.client.post(reverse('shipping_rate_edit', args=[rate.pk]), rate_data(per_kg='21'))
        rate.refresh_from_db()
        self.assertTrue(rate.active)
        self.assertEqual(rate.per_kg, D('21'))

    def test_invalid_contract_conditions_never_saved(self):
        cases = [{'per_kg': ''}, {'min_weight': '0'}, {'step_weight': '0'}, {'min_weight': '-1'},
                 {'fixed_fee': '-1'}, {'volume_divisor': '0'}, {'max_weight': '.01'}, {'fuel_basis': ''},
                 {'per_kg': 'NaN'}, {'currency': '美元'}, {'effective_until': '2025-01-01'}, {'step_weight': '.0001'},
                 {'method': 'first_step', 'first_weight': '.01', 'first_price': '1', 'step_price': '1'}]
        for changes in cases:
            with self.subTest(changes=changes):
                self.assertEqual(self.client.post(reverse('shipping_rate_add'), rate_data(**changes)).status_code, 400)
        self.assertEqual(ShippingRate.objects.count(), 0)

    def test_csv_preview_confirm_atomic_and_duplicate_skip(self):
        response = self.upload(csv_bytes([rate_data(), rate_data(name='第二条', destination='GB')]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ShippingRate.objects.count(), 0)
        token = response.context['preview']
        for _ in range(2):
            self.assertEqual(self.client.post(reverse('shipping_import'), {'action': 'confirm', 'preview': token}).status_code, 302)
        self.assertEqual(ShippingRate.objects.count(), 2)
        self.assertEqual(set(ShippingRate.objects.values_list('source', flat=True)), {'import'})
        response = self.upload(csv_bytes([rate_data(name='新报价'), rate_data(per_kg='')]))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ShippingRate.objects.count(), 2)
        self.assertNotIn('preview', response.context)

    def test_import_signed_owner_tamper_and_expiry_protection(self):
        token = self.upload(csv_bytes([rate_data()])).context['preview']
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse('shipping_import'), {'action': 'confirm', 'preview': token}).status_code, 400)
        self.client.force_login(self.user)
        for bad in [token + 'x', '']:
            self.assertEqual(self.client.post(reverse('shipping_import'), {'action': 'confirm', 'preview': bad}).status_code, 400)
        with patch('django.core.signing.time.time', return_value=timezone.now().timestamp() + 1201):
            self.assertEqual(self.client.post(reverse('shipping_import'), {'action': 'confirm', 'preview': token}).status_code, 400)
        self.assertEqual(ShippingRate.objects.count(), 0)

    def test_xlsx_blank_template_and_numeric_date_systems_and_formulas(self):
        with self.assertRaisesMessage(ValidationError, '没有报价数据'):
            parse_rates(xlsx_bytes(), 'template.xlsx')
        for epoch, start in [(False, date(1899, 12, 30)), (True, date(1904, 1, 1))]:
            serial = (date(2026, 1, 1) - start).days
            parsed = parse_rates(xlsx_bytes(rate_data(), epoch1904=epoch, serial=serial), 'quote.xlsx')
            self.assertEqual(parsed[0]['effective_from'], '2026-01-01')
            self.assertEqual(parsed[0]['per_kg'], '20')
        response = self.upload(xlsx_bytes(rate_data()), 'rates.xlsx')
        self.assertEqual(response.status_code, 200)
        with self.assertRaisesMessage(ValidationError, '含公式'):
            parse_rates(xlsx_bytes(rate_data(), formula=True), 'formula.xlsx')

    def test_csv_encoding_header_limit_and_invalid_spreadsheet(self):
        utf8 = csv_bytes([rate_data()])
        self.assertEqual(parse_rates(utf8.decode('utf-8-sig').encode('gb18030'), 'gb.csv')[0]['name'], '受控测试报价，非真实运价')
        for raw, name in [(b'a,b\n1,2', 'bad.csv'), (csv_bytes([rate_data()] * 101), 'large.csv'),
                          (b'not a zip', 'broken.xlsx'), (b'x' * (2 * 1024 * 1024 + 1), 'big.csv')]:
            with self.assertRaises(ValidationError):
                parse_rates(raw, name)

    def test_fx_direction_and_no_guess_from_selling_exchange_rate(self):
        rate = self.saved()
        data = dict(self.estimate_data, shipping_quote=f'user:{rate.pk}', fuel_rate='10', shipping_extra='3')
        self.assertFalse(ShippingEstimateForm(data, user=self.user).is_valid())
        form = ShippingEstimateForm(dict(data, shipping_exchange_rate='7'), user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.estimate['converted'], D('112'))
        form = ShippingEstimateForm(dict(data, cost_currency='USD', shipping_exchange_rate='99'), user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.estimate['converted'], D('16'))

    def test_profit_uses_server_computed_shipping_and_keeps_manual_compatibility(self):
        data = dict(self.estimate_data, shipping_mode='quote', sale_currency='CNY', selling_price='1000',
                    cost='100', shipping='0', fee_rate='0', other_cost='0', ad_cost='0', payment_fee_rate='0')
        response = self.client.post(reverse('profit'), data)
        self.assertIsNotNone(response.context['result'], response.context['form'].errors)
        self.assertEqual(response.context['result']['net'], D('569.10'))
        self.assertEqual(response.context['form'].cleaned_data['shipping'], D('330.90'))
        self.assertContains(response, '物流核算明细')
        response = self.client.post(reverse('profit'), dict(data, shipping_mode='manual', shipping='20', shipping_quote='hacked'))
        self.assertEqual(response.context['result']['net'], D('880'))
        self.assertIsNone(response.context['shipping_result'])

    def test_quote_params_carry_into_profit_without_get_writes_and_invalid_inputs_fail(self):
        response = self.client.get(reverse('profit'), dict(self.estimate_data, shipping_mode='quote'))
        self.assertEqual(response.context['form']['shipping_quote'].value(), 'public:sf-economy-US')
        self.assertEqual(ShippingRate.objects.count(), 0)
        self.assertIsNone(response.context['result'])
        data = dict(self.estimate_data, shipping_mode='quote', sale_currency='CNY', selling_price='1000', cost='100', fee_rate='0')
        response = self.client.post(reverse('profit'), dict(data, package_weight='19.501'))
        self.assertIsNone(response.context['result'])
        self.assertContains(response, '不能外推价格')

    def test_downloads_login_and_csrf(self):
        for kind in ('xlsx', 'csv'):
            response = self.client.get(reverse('shipping_template', args=[kind]))
            self.assertEqual(response.status_code, 200)
            self.assertIn('attachment', response.headers['Content-Disposition'])
            if response.streaming:
                self.assertGreater(len(b''.join(response.streaming_content)), 100)
        protected = Client(enforce_csrf_checks=True)
        protected.force_login(self.user)
        self.assertEqual(protected.post(reverse('shipping_rate_add'), rate_data()).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('shipping')).status_code, 302)
