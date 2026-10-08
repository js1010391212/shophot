from django import forms


class HistoryFilterForm(forms.Form):
    currency = forms.ChoiceField(label='历史报价币种', required=False)
    days = forms.TypedChoiceField(label='观测窗口', required=False, coerce=int, empty_value=0,
                                  choices=[('0','全部历史'),('30','最近 30 天'),('90','最近 90 天')])

    def __init__(self, *args, currencies=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['currency'].choices=[('','自动选择最新币种')]+[(code,code) for code in currencies]
