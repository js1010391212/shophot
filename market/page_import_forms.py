from django import forms
from django.utils import timezone
from .collectors import MAX_BYTES
from .page_import import identify_target


class PageImportTargetForm(forms.Form):
    url = forms.URLField(label='目标商品链接', max_length=500, widget=forms.URLInput(attrs={
        'placeholder': '速卖通 /item/…html 或 OTTO /p/…'}))

    def clean_url(self):
        platform, url = identify_target(self.cleaned_data['url'])
        self.platform = platform
        return url


class PageImportForm(forms.Form):
    file=forms.FileField(label='已保存的 HTML 商品页面（UTF-8，最多 2 MB）',widget=forms.ClearableFileInput(attrs={'accept':'.html,.htm'}))
    observed_at=forms.DateTimeField(label='实际查看页面的时间（北京时间）',widget=forms.DateTimeInput(attrs={'type':'datetime-local'},format='%Y-%m-%dT%H:%M'),input_formats=['%Y-%m-%dT%H:%M'])
    context=forms.CharField(label='页面规格 / 报价说明',required=False,max_length=120)

    def clean_file(self):
        file=self.cleaned_data['file']
        if file.size>MAX_BYTES:raise forms.ValidationError('文件不能超过 2 MB。')
        return file

    def clean_observed_at(self):
        at=self.cleaned_data['observed_at']
        if at>timezone.now():raise forms.ValidationError('观测时间不能在未来。')
        return at
