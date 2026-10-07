from decimal import Decimal
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


class ObservationForm(forms.Form):
    """手动记录真实页面观测，来源由后端固定，不允许伪装成自动采集。"""
    price = forms.DecimalField(label="公开价格", min_value=0, max_value=Decimal("9999999999.99"), max_digits=12, decimal_places=2)
    currency = forms.CharField(label="币种", max_length=3, initial="USD")
    observed_at = forms.DateTimeField(label="观测时间（北京时间）", widget=forms.DateTimeInput(
        attrs={"type": "datetime-local", "step": "1"}, format="%Y-%m-%dT%H:%M:%S"))
    rating = forms.DecimalField(label="公开评分（5 分制，可留空）", required=False, min_value=0, max_value=5, max_digits=3, decimal_places=2)
    review_count = forms.IntegerField(label="公开评价数（未知留空）", required=False, min_value=0, max_value=2147483647)
    sales = forms.IntegerField(label="页面公开销量（未知留空，不代表真实订单量）", required=False, min_value=0, max_value=2147483647)
    context = forms.CharField(label="报价条件 / 规格", max_length=300, required=False,
                             widget=forms.Textarea(attrs={"rows": 3, "placeholder": "例如：美国市场 / 黑色 128GB / 不含运费；记录页面上的口径"}))

    def clean_currency(self):
        from .validation import clean_currency
        return clean_currency(self.cleaned_data["currency"])

    def clean_observed_at(self):
        from datetime import timezone as datetime_timezone
        date = self.cleaned_data["observed_at"]
        try:
            date.astimezone(datetime_timezone.utc)
        except (ValueError, OverflowError):
            raise forms.ValidationError("观测时间超出可保存范围。")
        return date


class ProductChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, product):
        return f"{product.title} · {product.shop or '未知店铺'} · #{product.pk}"


class CompareForm(forms.Form):
    products = ProductChoiceField(label="选择 2–8 件竞品", queryset=Product.objects.all(),
                                              widget=forms.CheckboxSelectMultiple)
    currency = forms.ChoiceField(label="对比币种")
    days = forms.TypedChoiceField(label="观测窗口", coerce=int, initial=30,
                                   choices=[(7, "最近 7 天"), (30, "最近 30 天"), (90, "最近 90 天"), (0, "全部历史")])

    def __init__(self, *args, **kwargs):
        from .models import Snapshot
        super().__init__(*args, **kwargs)
        currencies = list(Snapshot.objects.order_by("currency").values_list("currency", flat=True).distinct())
        self.fields["currency"].choices = [(code, code) for code in currencies] or [("USD", "USD")]
        self.fields["currency"].initial = "USD" if "USD" in currencies else self.fields["currency"].choices[0][0]

    def clean_products(self):
        products = self.cleaned_data["products"]
        if not 2 <= len(products) <= 8:
            raise forms.ValidationError("请选择 2–8 件商品进行对比。")
        return products


class AnalyzeForm(forms.Form):
    url = forms.URLField(label="竞品商品链接", max_length=500, widget=forms.URLInput(
        attrs={"placeholder": "https://www.aliexpress.com/item/…html"}))

    def clean_url(self):
        import re
        from urllib.parse import urlsplit, urlunsplit
        from django.core.exceptions import ValidationError
        url = clean_url(self.cleaned_data["url"])
        parts = urlsplit(url)
        host = parts.hostname or ""
        if parts.scheme != "https" or not (host == "aliexpress.com" or host.endswith(".aliexpress.com")) or parts.port not in (None, 443):
            raise ValidationError("自动分析目前支持速卖通 HTTPS 商品链接，其他平台可先导入 CSV。")
        # 标准商品链接去掉营销参数，以商品 ID 识别同一个竞品，避免重复跟踪。
        if re.fullmatch(r"/item/\d+\.html", parts.path):
            return urlunsplit(("https", "www.aliexpress.com", parts.path, "", ""))
        raise ValidationError("请填写完整的速卖通商品链接（/item/商品编号.html），不要使用首页或短链接。")
