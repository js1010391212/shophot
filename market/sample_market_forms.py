from django import forms


class SampleMarketForm(forms.Form):
    q=forms.CharField(label='商品标题',required=False,max_length=200,widget=forms.TextInput(attrs={'placeholder':'例如 shampoo'}))
    store=forms.ChoiceField(label='样本店铺',required=False)
    currency=forms.ChoiceField(label='报价币种',required=False)
    brand=forms.ChoiceField(label='公开品牌',required=False)
    price_min=forms.DecimalField(label='最低报价下限',required=False,min_value=0,max_digits=12,decimal_places=2)
    price_max=forms.DecimalField(label='最低报价上限',required=False,min_value=0,max_digits=12,decimal_places=2)

    def __init__(self,*args,scans=(),rows=(),**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['store'].choices=[('','全部样本店铺')]+[(str(scan.pk),scan.url) for scan in scans]
        self.fields['currency'].choices=[('','全部币种（分别统计）')]+[(code,code) for code in sorted({r['currency'] for r in rows if r['valid_quote']})]
        brands={row['brand_key']:row['brand_label'] for row in rows}
        self.fields['brand'].choices=[('','全部品牌')]+sorted(brands.items(),key=lambda pair:pair[1].casefold())

    def clean(self):
        data=super().clean()
        low,high=data.get('price_min'),data.get('price_max')
        if low is not None and high is not None and low>high:
            self.add_error('price_max','上限不能低于下限。')
        if not data.get('currency') and (low is not None or high is not None):
            self.add_error('currency','价格段筛选前请选择币种。')
        return data
