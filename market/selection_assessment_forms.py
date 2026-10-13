"""Optional, explicit cost assumptions on top of the existing trial form."""
from django import forms
from .trial_budget_forms import TrialBudgetProfitForm, EXPLICIT_UNIT_FIELDS

ASSESSMENT_EXPLICIT_FIELDS = (*EXPLICIT_UNIT_FIELDS, 'discount_rate', 'target_margin')


class SelectionAssessmentProfitForm(TrialBudgetProfitForm):
    assessment_enabled = forms.BooleanField(label='同时做成本视角选品判断', required=False)
    assessment_costs_confirmed = forms.BooleanField(
        label='已核对成本和费率，填 0 表示确认没有', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.assessment_active = self.is_bound and self.fields['assessment_enabled'].to_python(
            self['assessment_enabled'].value())
        self.fields['assessment_costs_confirmed'].disabled = not self.assessment_active
        if self.assessment_active:
            for name in ASSESSMENT_EXPLICIT_FIELDS:
                self.fields[name].required = True
                self.fields[name].error_messages['required'] = '选品判断需要明确填写；没有这项费用或减价请填 0。'
