"""Resolve a saved quote for profit assumptions; never fetch or write observations."""
import re
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404

from .forms import ProfitForm
from .models import Product, Snapshot


def reference_identifiers(request):
    """A reference is supplied exactly once; GET and POST are not precedence rules."""
    values = {}
    for name in ('observation', 'product'):
        supplied = request.GET.getlist(name) + request.POST.getlist(name)
        if len(supplied) > 1:
            raise ValidationError('报价来源编号不能重复，请从报价记录重新打开利润工具。')
        if supplied:
            value = supplied[0]
            if not re.fullmatch(r'[1-9][0-9]{0,18}', value, flags=re.ASCII) or int(value) > 9223372036854775807:
                raise ValidationError('报价来源编号无效，请从报价记录重新打开利润工具。')
            values[name] = int(value)
    if len(values) > 1:
        raise ValidationError('不能同时引用浏览器报价与公共商品，请只选择一条来源。')
    return values


def resolve_reference(request):
    ids = reference_identifiers(request)
    if 'observation' in ids:
        snapshot = get_object_or_404(
            Snapshot.all_objects.select_related('product'), pk=ids['observation'],
            owner=request.user, source=Snapshot.Source.BROWSER,
        )
        return {'kind': 'observation', 'id': snapshot.pk, 'snapshot': snapshot,
                'product': snapshot.product, 'data': snapshot.capture_data or {}}
    if 'product' in ids:
        product = get_object_or_404(Product, pk=ids['product'])
        snapshot = product.snapshots.first()  # Public manager excludes every private quote.
        if snapshot:
            return {'kind': 'product', 'id': product.pk, 'snapshot': snapshot,
                    'product': product, 'data': {}}
    return None


def quote_initial(reference):
    """Validate exact money without silently rounding a source into form precision."""
    if not reference:
        return {}, ''
    snapshot = reference['snapshot']
    raw = reference['data'].get('price', snapshot.price)
    try:
        price = ProfitForm.base_fields['selling_price'].clean(raw)
        if price != snapshot.price:
            raise ValidationError('保存金额与原始报价金额不一致。')
        currency = snapshot.currency
        if not re.fullmatch(r'[A-Z]{3}', currency, flags=re.ASCII):
            raise ValidationError('保存报价缺少明确的三位币种。')
    except (ValidationError, InvalidOperation, TypeError, ValueError):
        return {}, '这条报价的金额或币种不能准确带入利润工具（金额最多两位小数且不能超出上限）。未舍入或替换来源；请核对报价，或自行填写假设售价。'
    return {'selling_price': price, 'sale_currency': currency, 'discount_rate': Decimal('0')}, ''
