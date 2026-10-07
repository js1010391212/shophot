from django import forms
from .models import Product
from .validation import clean_url


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["title", "url", "platform", "shop", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

    def clean_url(self):
        return clean_url(self.cleaned_data["url"])


class ImportForm(forms.Form):
    file = forms.FileField(label="CSV 文件（UTF-8，最大 2 MB）")

    def clean_file(self):
        file = self.cleaned_data["file"]
        if file.size > 2 * 1024 * 1024:
            raise forms.ValidationError("文件不能超过 2 MB。")
        return file


class ProfitForm(forms.Form):
    selling_price = forms.DecimalField(label="售价（结算币种）", min_value=0, max_digits=12, decimal_places=2)
    exchange_rate = forms.DecimalField(label="1 单位结算币种对应人民币", min_value=0.000001, max_digits=12, decimal_places=6, initial=7)
    cost = forms.DecimalField(label="采购成本（人民币）", min_value=0, max_digits=12, decimal_places=2)
    shipping = forms.DecimalField(label="运费（人民币）", min_value=0, max_digits=12, decimal_places=2)
    fee_rate = forms.DecimalField(label="平台费率（%）", min_value=0, max_value=100, decimal_places=2, initial=8)
    other_cost = forms.DecimalField(label="其他成本（人民币）", min_value=0, max_digits=12, decimal_places=2, initial=0)
