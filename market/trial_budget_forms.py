"""Optional trial inputs; unknown amounts must be explicit when enabled."""
from django import forms
from .shipping_forms import LogisticsProfitForm

TRIAL_FIELDS = ('trial_quantity', 'trial_sample_cost', 'trial_setup_cost',
                'trial_compliance_cost', 'trial_reserve_cost')
EXPLICIT_UNIT_FIELDS = ('ad_cost', 'other_cost', 'payment_fee_rate', 'payment_fixed')


class TrialBudgetProfitForm(LogisticsProfitForm):
    trial_enabled = forms.BooleanField(label='同时估算小批量测品预算', required=False)
    trial_quantity = forms.IntegerField(label='本批测品数量（件）', min_value=1, max_value=10000, required=False)
    trial_sample_cost = forms.DecimalField(label='样品及寄送一次性费用', min_value=0, max_digits=12, decimal_places=2, required=False)
    trial_setup_cost = forms.DecimalField(label='素材 / 开店准备一次性费用', min_value=0, max_digits=12, decimal_places=2, required=False)
    trial_compliance_cost = forms.DecimalField(label='合规 / 检测一次性费用', min_value=0, max_digits=12, decimal_places=2, required=False)
    trial_reserve_cost = forms.DecimalField(label='额外预留资金', min_value=0, max_digits=12, decimal_places=2, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.trial_active = self.is_bound and self.fields['trial_enabled'].to_python(self['trial_enabled'].value())
        for name in TRIAL_FIELDS:
            self.fields[name].required = self.trial_active
            self.fields[name].disabled = not self.trial_active
        for name in EXPLICIT_UNIT_FIELDS:
            self.fields[name].required = self.trial_active
