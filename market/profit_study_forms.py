from django import forms


class ProfitStudySaveForm(forms.Form):
    state = forms.CharField(max_length=65536, widget=forms.HiddenInput)
    name = forms.CharField(label='记录名称', max_length=120)
    notes = forms.CharField(label='研究备注', max_length=1000, required=False, widget=forms.Textarea(attrs={'rows':3}))


class ProfitStudyFilterForm(forms.Form):
    q = forms.CharField(label='搜索名称或备注', max_length=120, required=False)
    archived = forms.BooleanField(label='查看已移出记录', required=False)
