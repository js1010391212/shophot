"""物流自有表格的账号绑定临时映射；不写库或文件。"""
import json
from django import forms
from django.core import signing
from django.core.exceptions import ValidationError
from .shipping_import import COLUMNS, MAX_ROWS, validate_rate_rows
from .shipping_forms import ShippingRateForm

SALT = 'shipping-column-mapping-v1'
MAX_TOKEN = 300000
MAX_TABLE_BYTES = 180000


def sign_table(table, owner_id):
    if len(json.dumps(table, ensure_ascii=False).encode('utf-8')) > MAX_TABLE_BYTES:
        raise ValidationError('映射数据过大，请精简文字或分批导入。')
    return signing.dumps({'owner': owner_id, 'table': table}, salt=SALT, compress=True)


def load_table(token, owner_id):
    try:
        if not isinstance(token, str) or len(token) > MAX_TOKEN:
            raise ValueError
        data = signing.loads(token, salt=SALT, max_age=1200)
        table = data['table']
        if data['owner'] != owner_id or not 2 <= len(table['rows']) <= MAX_ROWS + 1 or not 1 <= len(table['headers']) <= 40:
            raise ValueError
        if len(json.dumps(table, ensure_ascii=False).encode('utf-8')) > MAX_TABLE_BYTES:
            raise ValueError
        return table
    except (signing.BadSignature, KeyError, ValueError, TypeError):
        raise ValidationError('列映射无效或已过期，请重新上传表格。')


class ColumnMappingForm(forms.Form):
    def __init__(self, *args, table, **kwargs):
        super().__init__(*args, **kwargs)
        self.table = table
        self.pairs = []
        for key, label in COLUMNS:
            exact = [i for i, h in enumerate(table['headers']) if h == label]
            self.fields['column_' + key] = forms.ChoiceField(label=label, required=False,
                choices=[('', '共同值 / 未提供')] + [(str(i), h) for i, h in enumerate(table['headers'])],
                initial=str(exact[0]) if len(exact) == 1 else '')
            self.fields['common_' + key] = forms.CharField(label='共同值', required=False, max_length=1000,
                widget=forms.TextInput(attrs={'placeholder': '没有对应列时明确填写，不猜未知值'}))
            if key in ('method', 'fuel_basis'):
                choices = [(value, label) for value, label in ShippingRateForm.base_fields[key].choices if value]
                self.fields['common_' + key] = forms.ChoiceField(label='共同值', required=False, choices=[('', '未提供，请明确选择')] + choices)
            elif key in ('effective_from', 'effective_until'):
                self.fields['common_' + key].widget = forms.DateInput(attrs={'type': 'date'})
            self.pairs.append({'column': self['column_' + key], 'common': self['common_' + key],
                               'advanced': key in ('first_weight', 'first_price', 'step_price', 'volume_divisor', 'effective_until', 'source_url', 'notes')})

    def clean(self):
        data = super().clean()
        used, mapping, common = set(), {}, {}
        for key, _ in COLUMNS:
            column = data.get('column_' + key, '')
            value = data.get('common_' + key, '')
            if column:
                index = int(column)
                if index in used:
                    self.add_error('column_' + key, '同一源列不能用于多个字段。')
                used.add(index)
                mapping[key] = index
                if value:
                    self.add_error('common_' + key, '已选择列，请清空共同值，避免两种来源冲突。')
            else:
                mapping[key] = None
                common[key] = value
        if not self.errors:
            self.rows = validate_rate_rows(self.table, mapping, common)
        return data


def validate_post_fields(post, allowed):
    if any(key not in allowed or len(post.getlist(key)) != 1 for key in post):
        raise ValidationError('提交含重复或未允许的字段，请重新核对。')
