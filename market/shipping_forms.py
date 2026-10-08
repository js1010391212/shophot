from copy import deepcopy
from decimal import Decimal
import re
from django import forms
from django.utils import timezone
from .forms import CURRENCIES, ProfitForm
from .models import ShippingRate
from .shipping import COUNTRIES, RATE_FIELDS, quotes_for, estimate, rate_fingerprint


class ShippingRateForm(forms.ModelForm):
    origin = forms.ChoiceField(label='始发国家 / 地区', choices=[('', '选择始发国家 / 地区')] + COUNTRIES)
    destination = forms.ChoiceField(label='目的国家 / 地区', choices=[('', '选择目的国家 / 地区')] + COUNTRIES)
    currency = forms.ChoiceField(label='报价币种', choices=CURRENCIES)

    class Meta:
        model = ShippingRate
        fields = RATE_FIELDS
        widgets = {'effective_from': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                   'effective_until': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                   'notes': forms.Textarea(attrs={'rows': 3}),
                   'volume_divisor': forms.NumberInput(attrs={'placeholder': '如 5000；留空表示合同明确不计体积重'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 未列出的 ISO 国家与三位币种仍可通过表格或已保存报价使用。
        for name, pattern in [('origin', r'[A-Z]{2}'), ('destination', r'[A-Z]{2}'), ('currency', r'[A-Z]{3}')]:
            code = str(self.data.get(name, '') or self.initial.get(name, ''))
            if re.fullmatch(pattern, code) and code not in dict(self.fields[name].choices):
                self.fields[name].choices = list(self.fields[name].choices) + [(code, code)]
        for name in ('min_weight', 'max_weight', 'step_weight', 'first_weight'):
            self.fields[name].min_value = Decimal('.001')
            self.fields[name].max_value = Decimal('10000')
        for name in ('per_kg', 'first_price', 'step_price', 'fixed_fee'):
            self.fields[name].min_value = Decimal('0')

    def clean(self):
        data = super().clean()
        positive = ('min_weight', 'max_weight', 'step_weight', 'first_weight')
        for name in positive:
            if data.get(name) is not None and not Decimal('.001') <= data[name] <= Decimal('10000'):
                self.add_error(name, '重量须在 0.001–10000 kg 之间。')
        for name in ('per_kg', 'first_price', 'step_price', 'fixed_fee'):
            if data.get(name) is not None and data[name] < 0:
                self.add_error(name, '金额不能为负数。')
        low, high, step = (data.get(key) for key in ('min_weight', 'max_weight', 'step_weight'))
        if low and high and high < low:
            self.add_error('max_weight', '上限不能小于最低计费重。')
        if high and step and high < step:
            self.add_error('step_weight', '进位单位不能大于计费重上限。')
        method = data.get('method')
        required = ('per_kg',) if method == 'per_kg' else ('first_weight', 'first_price', 'step_price')
        for name in required:
            if name not in self.errors and data.get(name) is None:
                self.add_error(name, '所选计费方式需要此项，已知免费请填 0。')
        if method == 'first_step' and data.get('first_weight') is not None:
            first_weight = data['first_weight']
            if low and first_weight < low:
                self.add_error('first_weight', '首重不能小于最低计费重。')
            if high and first_weight > high:
                self.add_error('first_weight', '首重不能大于报价上限。')
        if method == 'per_kg':
            for name in ('first_weight', 'first_price', 'step_price'):
                data[name] = None
        elif method == 'first_step':
            data['per_kg'] = None
        divisor = data.get('volume_divisor')
        if divisor is not None and not 1000 <= divisor <= 10000:
            self.add_error('volume_divisor', '体积重系数须在 1000–10000 之间；明确不计体积重才可留空。')
        start, end = data.get('effective_from'), data.get('effective_until')
        if start and end and end < start:
            self.add_error('effective_until', '失效日期不能早于生效日期。')
        url = data.get('source_url', '')
        if url and not url.startswith(('https://', 'http://')):
            self.add_error('source_url', '来源链接仅支持 HTTP / HTTPS。')
        self.instance.fingerprint = rate_fingerprint(data)
        return data


class ShippingEstimateForm(forms.Form):
    shipping_quote = forms.ChoiceField(label='物流线路 / 报价')
    package_weight = forms.DecimalField(label='整包实重（kg，含包装）', min_value=Decimal('.001'), max_value=10000, max_digits=8, decimal_places=3)
    package_length = forms.DecimalField(label='包装长（cm）', required=False, min_value=Decimal('.01'), max_value=1000, max_digits=6, decimal_places=2)
    package_width = forms.DecimalField(label='包装宽（cm）', required=False, min_value=Decimal('.01'), max_value=1000, max_digits=6, decimal_places=2)
    package_height = forms.DecimalField(label='包装高（cm）', required=False, min_value=Decimal('.01'), max_value=1000, max_digits=6, decimal_places=2)
    package_units = forms.IntegerField(label='包内同款商品件数', min_value=1, max_value=10000, initial=1)
    fuel_rate = forms.DecimalField(label='燃油附加费率（%）', min_value=0, max_value=1000, max_digits=6, decimal_places=2,
                                 widget=forms.NumberInput(attrs={'placeholder': '核实后填写，明确无此费填 0'}))
    shipping_extra = forms.DecimalField(label='整包其他物流费用（报价币种）', min_value=0, max_digits=12, decimal_places=2,
                                      widget=forms.NumberInput(attrs={'placeholder': '偏远 / 操作 / 税费等，已确认无费用填 0'}))
    cost_currency = forms.ChoiceField(label='换算后的成本币种', choices=CURRENCIES, initial='CNY')
    shipping_exchange_rate = forms.DecimalField(label='物流报价 → 成本币种汇率', required=False, min_value=Decimal('.000001'), max_digits=12, decimal_places=6)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.quotes = {q.key: q for q in quotes_for(user)}
        self.fields['shipping_quote'].choices = [('', '选择线路，按实际发货地与目的地核对')] + [(q.key, q.label) for q in self.quotes.values()]
        code = self.data.get('cost_currency', '') or self.initial.get('cost_currency', '')
        if re.fullmatch(r'[A-Z]{3}', str(code)) and code not in dict(self.fields['cost_currency'].choices):
            self.fields['cost_currency'].choices = list(CURRENCIES) + [(code, code)]
        self.estimate = None

    def clean(self):
        data = super().clean()
        quote = self.quotes.get(data.get('shipping_quote'))
        currency = data.get('cost_currency')
        if quote:
            if quote.volume_divisor:
                for key in ('package_length', 'package_width', 'package_height'):
                    if key not in self.errors and data.get(key) is None:
                        self.add_error(key, '该线路计算体积重，需要包装尺寸。')
            if currency == quote.currency:
                data['shipping_exchange_rate'] = Decimal('1')
            elif currency and not data.get('shipping_exchange_rate') and 'shipping_exchange_rate' not in self.errors:
                self.add_error('shipping_exchange_rate', f'请填写 1 {quote.currency} 可兑换多少 {currency}，与售价汇率分开。')
            if not self.errors:
                self.estimate = estimate(quote, weight=data['package_weight'], length=data['package_length'],
                    width=data['package_width'], height=data['package_height'], fuel_rate=data['fuel_rate'],
                    extra=data['shipping_extra'], exchange_rate=data['shipping_exchange_rate'], currency=currency, units=data['package_units'])
        return data


class LogisticsProfitForm(ProfitForm):
    shipping_mode = forms.ChoiceField(label='物流成本的填写方式', required=False,
                                     choices=[('manual', '直接填实际单件运费'), ('quote', '按物流报价估算')], initial='manual')

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.shipping_form = ShippingEstimateForm(user=user)
        self.shipping_estimate = None
        quote_mode = (self.data.get('shipping_mode') if self.is_bound else self.initial.get('shipping_mode')) == 'quote'
        for name, form_field in self.shipping_form.fields.items():
            if name == 'cost_currency':
                continue
            self.fields[name] = deepcopy(form_field)
            self.fields[name].required = False
            self.fields[name].disabled = not quote_mode
        self.fields['shipping'].required = not quote_mode
        self.fields['shipping'].disabled = quote_mode
        self.user = user

    def clean(self):
        data = super().clean()
        if data.get('shipping_mode') == 'quote':
            shipping = ShippingEstimateForm(self.data, user=self.user)
            if shipping.is_valid():
                self.shipping_estimate = shipping.estimate
                data['shipping'] = shipping.estimate['converted']
            else:
                for key, errors in shipping.errors.items():
                    self.add_error(key if key != '__all__' else None, errors)
        return data


class ShippingImportForm(forms.Form):
    file = forms.FileField(label='物流报价表（.xlsx / .csv）', widget=forms.FileInput(attrs={'accept': '.xlsx,.csv'}))

    def clean_file(self):
        upload = self.cleaned_data['file']
        if upload.size > 2 * 1024 * 1024:
            raise forms.ValidationError('文件不能超过 2 MB。')
        if not upload.name.lower().endswith(('.xlsx', '.csv')):
            raise forms.ValidationError('请使用模板格式的 .xlsx 或 UTF-8 .csv 文件。')
        return upload
