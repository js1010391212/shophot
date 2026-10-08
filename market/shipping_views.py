from pathlib import Path
from urllib.parse import urlencode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db import transaction
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from .models import ShippingRate
from .shipping import public_quotes, rate_fingerprint, rate_payload
from .shipping_forms import ShippingEstimateForm, ShippingRateForm, ShippingImportForm
from .shipping_import import parse_rates, csv_template, MAX_ROWS

SALT = 'shipping-import-v1'


@login_required
@require_http_methods(['GET', 'POST'])
def logistics(request):
    initial = {'shipping_quote': 'public:sf-economy-US', 'cost_currency': 'CNY', 'package_units': 1}
    form = ShippingEstimateForm(request.POST if request.method == 'POST' else None, user=request.user, initial=initial)
    result = form.estimate if request.method == 'POST' and form.is_valid() else None
    profit_url = None
    if result:
        # 带回参数，利润表单仍在 POST 时重新核算，不信任浏览器传来的金额。
        query = {key: value for key, value in form.cleaned_data.items() if value is not None}
        query['shipping_mode'] = 'quote'
        from django.urls import reverse
        profit_url = reverse('profit') + '?' + urlencode(query)
    return render(request, 'market/shipping.html', {'form': form, 'result': result, 'profit_url': profit_url,
        'rates': ShippingRate.objects.filter(owner=request.user), 'public_quotes': public_quotes(),
        'quote_metadata': {key: q.metadata() for key, q in form.quotes.items()}, 'today': timezone.localdate()})


@login_required
@require_http_methods(['GET', 'POST'])
def rate_edit(request, pk=None):
    rate = get_object_or_404(ShippingRate, pk=pk, owner=request.user) if pk else None
    form = ShippingRateForm(request.POST if request.method == 'POST' else None, instance=rate,
        initial={} if rate else {'origin': 'CN', 'currency': 'CNY', 'method': 'per_kg', 'fuel_basis': 'freight',
                                'effective_from': timezone.localdate()})
    if request.method == 'POST' and form.is_valid():
        fingerprint = rate_fingerprint(form.cleaned_data)
        duplicate = ShippingRate.objects.filter(owner=request.user, fingerprint=fingerprint).exclude(pk=rate.pk if rate else None).first()
        if duplicate:
            form.add_error(None, '这条报价已保存，未重复新增。可在清单编辑或恢复原报价。')
        else:
            saved = form.save(commit=False)
            saved.owner = request.user
            saved.source = 'manual'
            saved.fingerprint = fingerprint
            saved.save()
            messages.success(request, '物流报价已保存，仅当前账号可使用。')
            return redirect('shipping')
    return render(request, 'market/shipping_rate_form.html', {'form': form, 'rate': rate}, status=400 if form.errors else 200)


@login_required
@require_POST
def rate_toggle(request, pk):
    with transaction.atomic():
        rate = get_object_or_404(ShippingRate.objects.select_for_update(), pk=pk, owner=request.user)
        rate.active = not rate.active
        rate.save(update_fields=['active', 'updated_at'])
    messages.success(request, '报价已启用。' if rate.active else '报价已暂停，可随时恢复。')
    return redirect('shipping')


@login_required
@require_http_methods(['GET', 'POST'])
def import_rates(request):
    confirm = request.method == 'POST' and request.POST.get('action') == 'confirm'
    form = ShippingImportForm(request.POST if request.method == 'POST' and not confirm else None, request.FILES or None)
    context = {'form': form}
    if confirm:
        try:
            token = request.POST.get('preview', '')
            if len(token) > 300000:
                raise ValueError
            data = signing.loads(token, salt=SALT, max_age=1200)
            if data['owner'] != request.user.pk or not isinstance(data['rows'], list) or not 1 <= len(data['rows']) <= MAX_ROWS:
                raise ValueError
            forms = [ShippingRateForm(row) for row in data['rows']]
            if not all(f.is_valid() for f in forms):
                raise ValueError
        except (signing.BadSignature, KeyError, ValueError, TypeError):
            context['confirmation_error'] = '预览无效或已过期，请重新上传表格。'
            return render(request, 'market/shipping_import.html', context, status=400)
        created = 0
        with transaction.atomic():
            for row_form in forms:
                values = {key: row_form.cleaned_data[key] for key in row_form.Meta.fields}
                _, added = ShippingRate.objects.get_or_create(owner=request.user, fingerprint=rate_fingerprint(values), defaults={**values, 'source': 'import'})
                created += int(added)
        messages.success(request, f'已导入 {created} 条报价，跳过 {len(forms) - created} 条重复报价；现有报价未覆盖。')
        return redirect('shipping')
    if request.method == 'POST' and form.is_valid():
        from django.core.exceptions import ValidationError
        try:
            upload = form.cleaned_data['file']
            rows = parse_rates(upload.read(), upload.name)
            context.update(rows=rows, preview=signing.dumps({'owner': request.user.pk, 'rows': rows}, salt=SALT, compress=True))
        except ValidationError as exc:
            form.add_error('file', exc)
    return render(request, 'market/shipping_import.html', context, status=400 if form.errors else 200)


@login_required
@require_http_methods(['GET'])
def template(request, kind):
    if kind == 'xlsx':
        path = Path(settings.BASE_DIR) / 'market' / 'data' / 'outputs' / 'logistics-20261008' / 'shipping_rates_template.xlsx'
        return FileResponse(path.open('rb'), as_attachment=True, filename='shophot-logistics.xlsx')
    if kind == 'csv':
        response = HttpResponse(csv_template(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="shophot-logistics.csv"'
        return response
    from django.http import Http404
    raise Http404
