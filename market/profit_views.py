"""Profit workspace with account-owned quote references and existing logistics math."""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.http import Http404
from django.views.decorators.http import require_http_methods

from .profit import calculate_profit
from .profit_references import resolve_reference, quote_initial, reference_money
from .catalog_profit_references import catalog_report_link, catalog_source
from .shipping_forms import ShippingEstimateForm
from .selection_assessment_forms import SelectionAssessmentProfitForm
from .selection_assessment import assess_selection
from .trial_budget import calculate_trial_budget
from .profit_studies import study_from_request, current_reference, signed_state
from .profit_study_forms import ProfitStudySaveForm


@login_required
@require_http_methods(['GET', 'POST'])
def profit(request):
    reference = None
    study = None
    reference_error = ''
    study_source_notice = ''
    status = 200
    hx_post = request.method == 'POST' and request.headers.get('HX-Request') == 'true'
    try:
        study = study_from_request(request)
        reference = current_reference(request.user,study.snapshot['scenario']) if study else resolve_reference(request)
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
    if study and request.method == 'GET':
        initial = study.snapshot['scenario']['inputs'].copy()
        source = study.snapshot['scenario']['source']
        if source and source['kind'] == 'product' and reference and source['snapshot_id'] != reference['snapshot'].pk:
            study_source_notice = '公共报价已更新，历史售价仍是假设，请重新核对。'
    if not study and request.method == 'GET' and request.GET.get('shipping_mode') == 'quote':
        initial.update({name: request.GET[name] for name in ShippingEstimateForm.base_fields if name in request.GET})
        initial['shipping_mode'] = 'quote'
    form = SelectionAssessmentProfitForm(request.POST if request.method == 'POST' else None,
                               initial=initial if request.method == 'GET' else {}, user=request.user)
    if study and request.method == 'GET' and initial.get('shipping_mode') == 'quote' and initial.get('shipping_quote') not in form.shipping_form.quotes:
        reference_error = reference_error or '原物流引用已不可用，请重新选择物流并核算。'
    # Private currency codes must come from the resolved owned row, not the query.
    currency = reference_money(reference)[1] if reference else None
    if reference and currency not in dict(form.fields['sale_currency'].choices):
        if len(currency) == 3 and currency.isascii() and currency.isupper() and currency.isalpha():
            form.fields['sale_currency'].choices = [*form.fields['sale_currency'].choices, (currency, currency)]
    result = calculate_profit(form.cleaned_data) if status == 200 and request.method == 'POST' and form.is_valid() else None
    trial_result = calculate_trial_budget(result, form.cleaned_data) if result and form.cleaned_data.get('trial_enabled') else None
    assessment_result = assess_selection(result, form.cleaned_data, trial_result, reference) if result and form.cleaned_data.get('assessment_enabled') else None
    save_form = None
    save_error = ''
    if result:
        try:
            token = signed_state(request.user,form,result,trial_result,assessment_result,reference)
            save_form = ProfitStudySaveForm(initial={'state':token})
        except ValidationError as error:
            save_error = ' '.join(error.messages)
    response = render(request, 'market/profit.html', {
        'form': form, 'result': result, 'study':study, 'save_form':save_form, 'save_error':save_error, 'study_source_notice':study_source_notice,
        'trial_result': trial_result, 'assessment_result': assessment_result, 'quote_reference': reference, 'reference_error': reference_error,
        'catalog_source': catalog_source(reference) if reference and reference['kind']=='catalog' else None,
        'catalog_report_link': catalog_report_link(reference) if reference and reference['kind']=='catalog' else '',
        'shipping_result': form.shipping_estimate,
        'quote_metadata': {key: quote.metadata() for key, quote in form.shipping_form.quotes.items()},
    }, status=status)
    if hx_post and status in (400, 404):
        response['X-ShopHot-Profit-Workspace-Error'] = '1'
    return response
