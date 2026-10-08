from django import forms
from .models import PriceMonitor


class MonitorForm(forms.Form):
    interval_hours = forms.TypedChoiceField(label='监测频率', choices=PriceMonitor._meta.get_field('interval_hours').choices, coerce=int, initial=24)
