from decimal import Decimal
from django import forms
from .models import Product, CatalogCandidate
from .validation import clean_url


class CandidateForm(forms.ModelForm):
    class Meta:
        model = CatalogCandidate
        fields = ['stage', 'notes']
        widgets = {'notes': forms.Textarea(attrs={'rows':3, 'placeholder':'例如：关注利润，核对尺寸相关评价'})}


class ProductForm(forms.ModelForm):
    platform = forms.ChoiceField(label="平台", choices=[("AliExpress", "AliExpress · 速卖通"), ("Shopify", "Shopify · 独立站"), ("OTTO", "OTTO · 浏览器 / 页面导入"), ("eBay", "eBay · 浏览器采集"), ("Other", "其他平台（手动 / CSV）")])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        existing = set(Product.objects.values_list('platform', flat=True))
        known = {key for key, label in self.fields['platform'].choices}
        self.fields['platform'].choices += [(value, value) for value in sorted(existing - known)]
        self.fields['platform'].initial = "AliExpress"

    def clean(self):
        data = super().clean()
        if data.get('platform') == 'eBay' and data.get('url'):
            from .ebay import normalize_ebay_url
            try:
                data['url'] = normalize_ebay_url(data['url'])
            except forms.ValidationError as exc:
                self.add_error('url', exc)
        if data.get('platform') == 'OTTO' and data.get('url'):
            from .otto import normalize_otto_url
            try: data['url'] = normalize_otto_url(data['url'])
            except forms.ValidationError as exc: self.add_error('url', exc)
        if data.get('platform') == 'Shopify' and data.get('url'):
            from .shopify import normalize_shopify_url
            try:
                data['url'] = normalize_shopify_url(data['url'])
            except forms.ValidationError as exc:
                self.add_error('url', exc)
        return data

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


CURRENCIES = [("USD", "USD · 美元"), ("CNY", "CNY · 人民币"), ("EUR", "EUR · 欧元"),
              ("GBP", "GBP · 英镑"), ("BRL", "BRL · 巴西雷亚尔"), ("AUD", "AUD · 澳元"),
              ("CAD", "CAD · 加元"), ("HKD", "HKD · 港币"), ("JPY", "JPY · 日元"),
              ("KRW", "KRW · 韩元"), ("SGD", "SGD · 新加坡元"), ("MXN", "MXN · 墨西哥比索")]


class ProfitForm(forms.Form):
    sale_currency = forms.ChoiceField(label="售价币种", choices=CURRENCIES, initial="USD")
    cost_currency = forms.ChoiceField(label="成本与结果币种", choices=CURRENCIES, initial="CNY")
    selling_price = forms.DecimalField(label="商品售价", min_value=0, max_digits=12, decimal_places=2)
    exchange_rate = forms.DecimalField(label="手动汇率", required=False, min_value=Decimal("0.000001"), max_digits=12, decimal_places=6,
                                       widget=forms.NumberInput(attrs={"placeholder": "填写实际换算汇率"}))
    discount_rate = forms.DecimalField(label="售价减价比例（%）", help_text="0% 为原价；10% 表示减去原价的 10%，按原价的 90% 成交。", required=False, min_value=0, max_value=100, decimal_places=2, initial=0)
    cost = forms.DecimalField(label="单件采购成本", min_value=0, max_digits=12, decimal_places=2)
    shipping = forms.DecimalField(label="单件履约运费", min_value=0, max_digits=12, decimal_places=2)
    ad_cost = forms.DecimalField(label="单件广告成本", required=False, min_value=0, max_digits=12, decimal_places=2, initial=0)
    fee_rate = forms.DecimalField(label="平台费率（%）", min_value=0, max_value=100, decimal_places=2, initial=0)
    payment_fee_rate = forms.DecimalField(label="支付手续费率（%）", required=False, min_value=0, max_value=100, decimal_places=2, initial=0)
    payment_fixed = forms.DecimalField(label="单笔固定支付手续费", required=False, min_value=0, max_digits=12, decimal_places=2, initial=0)
    other_cost = forms.DecimalField(label="单件其他成本", required=False, min_value=0, max_digits=12, decimal_places=2, initial=0)
    target_margin = forms.DecimalField(label="目标利润率（%）", required=False, min_value=0, max_value=100, decimal_places=2, initial=20)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Snapshot
        known = {code for code, label in CURRENCIES}
        extra = sorted(set(Snapshot.objects.values_list('currency', flat=True)) - known)
        for name in ('sale_currency', 'cost_currency'):
            self.fields[name].choices = CURRENCIES + [(code, code) for code in extra]

    def clean(self):
        data = super().clean()
        for key in ('discount_rate', 'ad_cost', 'payment_fee_rate', 'payment_fixed', 'other_cost', 'target_margin'):
            if key not in self.errors:
                data[key] = data.get(key) or Decimal('0')
        sale, cost = data.get('sale_currency'), data.get('cost_currency')
        if sale and sale == cost:
            data['exchange_rate'] = Decimal('1')
        elif 'exchange_rate' not in self.errors and not data.get('exchange_rate'):
            self.add_error('exchange_rate', '不同币种需要填写汇率：1 单位售价币种兑换多少成本币种。')
        if data.get('fee_rate') is not None and data.get('payment_fee_rate') is not None:
            if data['fee_rate'] + data['payment_fee_rate'] > 100:
                self.add_error('payment_fee_rate', '平台费率与支付手续费率合计不能超过 100%。')
        return data


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
    platform = forms.ChoiceField(label="研究平台", choices=[("AliExpress", "速卖通"), ("Shopify", "Shopify 独立站"), ("OTTO", "OTTO · 浏览器 / 页面导入"), ("eBay", "eBay · 浏览器采集")], required=False, initial="AliExpress")
    url = forms.URLField(label="竞品商品链接", max_length=500, widget=forms.URLInput(
        attrs={"placeholder": "速卖通 /item/…html 或 Shopify /products/…"}))

    def __init__(self, *args, allow_store=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.allow_store = allow_store
        if allow_store:
            self.fields['platform'].choices = [('Auto', '自动识别链接')] + list(self.fields['platform'].choices)
            self.fields['platform'].initial = 'Auto'
            self.fields['url'].label = '竞品商品或 Shopify 店铺链接'
            self.fields['url'].widget.attrs['placeholder'] = 'https://店铺域名/ 或完整商品链接'

    def clean_url(self):
        from urllib.parse import urlsplit
        platform = self.cleaned_data.get('platform')
        from .platforms import check_analysis_support
        from .platforms import known_platform
        if self.allow_store and known_platform(self.cleaned_data['url']) == 'eBay':
            from .ebay import normalize_ebay_url
            self.cleaned_data['platform'] = 'eBay'
            return normalize_ebay_url(self.cleaned_data['url'])
        if self.allow_store and known_platform(self.cleaned_data['url']) == 'OTTO':
            from .otto import normalize_otto_url
            self.cleaned_data['platform'] = 'OTTO'
            return normalize_otto_url(self.cleaned_data['url'])
        recognized = check_analysis_support(self.cleaned_data['url'])
        if self.allow_store and platform in ('Auto', ''):
            host = urlsplit(self.cleaned_data['url']).hostname or ''
            platform = 'AliExpress' if recognized == 'AliExpress' else 'Shopify'
            self.cleaned_data['platform'] = platform
        if platform == 'Shopify':
            if self.allow_store and urlsplit(self.cleaned_data['url']).path in ('', '/'):
                from .discovery import store_url
                return store_url(self.cleaned_data['url'])

            from .shopify import normalize_shopify_url
            return normalize_shopify_url(self.cleaned_data["url"])
        import re
        from urllib.parse import urlsplit, urlunsplit
        from django.core.exceptions import ValidationError
        url = clean_url(self.cleaned_data["url"])
        parts = urlsplit(url)
        host = parts.hostname or ""
        if parts.scheme != "https" or not (host == "aliexpress.com" or host.endswith(".aliexpress.com")) or parts.port not in (None, 443):
            raise ValidationError("自动分析目前支持速卖通 HTTPS 商品链接，其他平台可先导入 CSV。")
        from urllib.parse import parse_qs
        if 'sku_id' in parse_qs(parts.query, keep_blank_values=True):
            from .page_import import normalize_aliexpress_url
            normalized = normalize_aliexpress_url(url)
            if self.allow_store:
                return normalized
            raise ValidationError('带 sku_id 的速卖通规格目前只支持页面导入，自动采集尚不能确认规格。')
        # 标准商品链接去掉营销参数，以商品 ID 识别同一个竞品，避免重复跟踪。
        if re.fullmatch(r"/item/\d+\.html", parts.path):
            return urlunsplit(("https", "www.aliexpress.com", parts.path, "", ""))
        raise ValidationError("请填写完整的速卖通商品链接（/item/商品编号.html），不要使用首页或短链接。")


class StoreDiscoveryForm(forms.Form):
    url = forms.URLField(label='Shopify 店铺首页', max_length=500,
                         widget=forms.URLInput(attrs={'placeholder': 'https://example.com'}))

    def clean_url(self):
        from .discovery import store_url
        return store_url(self.cleaned_data['url'])


class ResearchFilterForm(forms.Form):
    availability = forms.ChoiceField(label='公开库存状态', required=False, choices=[
        ('','全部状态'),('InStock','有货'),('OutOfStock','缺货'),('SoldOut','售罄'),
        ('PreOrder','预售'),('BackOrder','可延期订购'),('Mixed','不同规格状态不同'),('unknown','未知')])
    coverage = forms.ChoiceField(label='数据覆盖', required=False, choices=[
        ('','全部商品'),('quoted','有有效报价'),('unquoted','报价未知'),
        ('reviews','有有效评论样本'),('no_reviews','无有效评论样本'),
        ('failed','最近采集失败'),('unattempted','尚未采集报价')])
    q = forms.CharField(label='商品标题搜索', required=False, max_length=200,
                        widget=forms.TextInput(attrs={'placeholder':'例如 Shampoo'}))
    term = forms.CharField(label='精确标题词条', required=False, max_length=100)
    currency = forms.ChoiceField(label='报价币种', required=False)
    price_min = forms.DecimalField(label='最低筛选价', required=False, min_value=0, max_digits=12, decimal_places=2)
    price_max = forms.DecimalField(label='最高筛选价', required=False, min_value=0, max_digits=12, decimal_places=2)
    min_rating = forms.DecimalField(label='最低商品评分', required=False, min_value=0, max_value=5, decimal_places=2)
    min_reviews = forms.IntegerField(label='最低评价数', required=False, min_value=0, max_value=2147483647)
    sort = forms.ChoiceField(label='排序', required=False, choices=[('catalog','目录顺序'),('title','标题 A–Z'),
        ('price_asc','最低报价从低到高'),('price_desc','最低报价从高到低'),('rating_desc','商品评分从高到低'),('reviews_desc','评价数从多到少')])

    def __init__(self, *args, currencies=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['currency'].choices=[('','全部币种')]+[(code,code) for code in currencies]

    def clean(self):
        data=super().clean()
        low, high=data.get('price_min'),data.get('price_max')
        if low is not None and high is not None and low > high:
            self.add_error('price_max','最高筛选价不能低于最低筛选价。')
        if not data.get('currency') and (low is not None or high is not None or data.get('sort','').startswith('price_')):
            self.add_error('currency','价格筛选或排序前，请选择一个币种。')
        data['term']=data.get('term','').lower()
        data['sort']=data.get('sort') or 'catalog'
        return data
