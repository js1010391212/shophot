"""Profit workspace with account-owned quote references and existing logistics math."""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.http import Http404
from django.views.decorators.http import require_http_methods

from .profit import calculate_profit
from .profit_references import resolve_reference, quote_initial
from .shipping_forms import ShippingEstimateForm
from .trial_budget_forms import TrialBudgetProfitForm
from .trial_budget import calculate_trial_budget


@login_required
@require_http_methods(['GET', 'POST'])
def profit(request):
    reference = None
    reference_error = ''
    status = 200
    hx_post = request.method == 'POST' and request.headers.get('HX-Request') == 'true'
    try:
        reference = resolve_reference(request)
    except ValidationError as error:
        reference_error = ' '.join(error.messages)
        status = 400
    except Http404:
        if not hx_post:
            raise
        reference_error = '这条报价目前不可用于测算，请返回自己的报价记录重新选择，或重新建立无来源场景。'
        status = 404
    initial, transfer_error = quote_initial(reference)
    reference_error = reference_error or transfer_error
    if request.method == 'GET' and request.GET.get('shipping_mode') == 'quote':
        initial.update({name: request.GET[name] for name in ShippingEstimateForm.base_fields if name in request.GET})
        initial['shipping_mode'] = 'quote'
    form = TrialBudgetProfitForm(request.POST if request.method == 'POST' else None,
                               initial=initial if request.method == 'GET' else {}, user=request.user)
    # Private currency codes must come from the resolved owned row, not the query.
    if reference and reference['snapshot'].currency not in dict(form.fields['sale_currency'].choices):
        currency = reference['snapshot'].currency
        if len(currency) == 3 and currency.isascii() and currency.isupper() and currency.isalpha():
            form.fields['sale_currency'].choices = [*form.fields['sale_currency'].choices, (currency, currency)]
    result = calculate_profit(form.cleaned_data) if status == 200 and request.method == 'POST' and form.is_valid() else None
    response = render(request, 'market/profit.html', {
        'form': form, 'result': result,
        'trial_result': calculate_trial_budget(result, form.cleaned_data) if result and form.cleaned_data.get('trial_enabled') else None, 'quote_reference': reference, 'reference_error': reference_error,
        'shipping_result': form.shipping_estimate,
        'quote_metadata': {key: quote.metadata() for key, quote in form.shipping_form.quotes.items()},
    }, status=status)
    if hx_post and status in (400, 404):
        response['X-ShopHot-Profit-Workspace-Error'] = '1'
    return response
