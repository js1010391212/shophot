"""Only account-derived choices are valid; malformed filters never become broad queries."""
from django import forms
from .browser_quote_library import filter_options


class BrowserQuoteLibraryForm(forms.Form):
    q = forms.CharField(label='报价标题', required=False, max_length=120,
                        widget=forms.TextInput(attrs={'placeholder': '搜索保存时的商品标题', 'maxlength': 120}))
    platform = forms.ChoiceField(label='平台', required=False)
    currency = forms.ChoiceField(label='报价币种', required=False)

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        platforms, currencies = filter_options(owner)
        self.fields['platform'].choices = [('', '全部平台')] + [(value, value) for value in platforms]
        self.fields['currency'].choices = [('', '全部币种')] + [(value, value) for value in currencies]
        self.fields['currency'].error_messages['invalid_choice'] = '请选择自己报价中已有的三位币种。'
        self.fields['platform'].error_messages['invalid_choice'] = '请选择自己报价中已有的平台。'

    def clean(self):
        data = super().clean()
        if hasattr(self.data, 'getlist'):
            for name in ('q', 'platform', 'currency'):
                if len(self.data.getlist(name)) > 1:
                    self.add_error(name, '该筛选条件不能重复，请清除后重新选择。')
        return data
