"""Signed, account-private immutable copies of successful profit calculations."""
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, QueryDict
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone

from .models import ProfitStudyRecord, ShippingRate, Snapshot, Product
from .profit import calculate_profit
from .profit_references import resolve_reference, quote_initial
from .selection_assessment import assess_selection
from .selection_assessment_forms import SelectionAssessmentProfitForm
from .trial_budget import calculate_trial_budget
from .shipping_forms import ShippingEstimateForm

SALT = 'shophot.profit-study.v1'
MAX_STATE = 65536
INPUT_FIELDS = tuple(dict.fromkeys((*SelectionAssessmentProfitForm.base_fields, *ShippingEstimateForm.base_fields)))
OPTIONAL_UNIT = ('discount_rate', 'ad_cost', 'other_cost', 'payment_fee_rate', 'payment_fixed', 'target_margin')
RECALCULATE = '测算状态已失效或条件已改变，请返回利润工具重新核算后保存。'


def plain(value):
    if isinstance(value, Decimal): return format(value, 'f')
    if isinstance(value, (date, datetime)): return value.isoformat()
    if isinstance(value, dict): return {key: plain(item) for key,item in value.items()}
    if isinstance(value, (list,tuple)): return [plain(item) for item in value]
    if value is None or isinstance(value,(str,bool,int)): return value
    raise ValidationError(RECALCULATE)


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def reference_request(owner, source):
    query=QueryDict('',mutable=True)
    if source: query[source['kind']]=str(source['id'])
    return SimpleNamespace(user=owner,GET=query,POST=QueryDict())


def source_facts(reference):
    if not reference:return None
    row,capture=reference['snapshot'],reference['data']
    return plain(dict(kind=reference['kind'],id=reference['id'],snapshot_id=row.pk,
        title=capture.get('title') or reference['product'].title,url=reference['product'].url,
        price=row.price,captured_price=capture.get('price',row.price),currency=row.currency,observed_at=row.observed_at,source=row.source,
        sku_id=capture.get('sku_id'),market_country=capture.get('market_country'),conditions=capture.get('conditions') or [],
        conditions_unknown=not bool(capture.get('conditions'))))


def scenario_snapshot(form, result, trial, assessment, reference):
    inputs={name:plain(form.cleaned_data.get(name)) for name in INPUT_FIELDS}
    missing=[]
    optional_presence={}
    for name in OPTIONAL_UNIT:
        optional_presence[name] = 'missing' if form.add_prefix(name) not in form.data else ('blank' if form[name].value() is None or str(form[name].value()).strip()=='' else 'explicit')
        if not form.fields[name].required and (form[name].value() is None or str(form[name].value()).strip()==''):
            inputs[name]='';missing.append(name)
    # Manual shipping is ignored in quote mode. Disabled garbage is never copied.
    if form.cleaned_data.get('shipping_mode') == 'quote':inputs['shipping']=None
    quote=None
    estimate=None
    if form.shipping_estimate:
        current=form.shipping_form.quotes[form.cleaned_data['shipping_quote']]
        quote=current.metadata()
        quote.update({name:getattr(current,name) for name in ('key','carrier','origin','destination','method','effective_until','per_kg','first_weight','first_price','step_price','fixed_fee')})
        quote['table']={format(weight,'f'):price for weight,price in current.table.items()}
        estimate={key:value for key,value in form.shipping_estimate.items() if key!='quote'}
    return plain(dict(inputs=inputs,missing_optional=missing,optional_presence=optional_presence,unit=result,trial=trial,
                      assessment=assessment,source=source_facts(reference),
                      shipping=dict(quote=quote,estimate=estimate)))


def require_consistent_reference(reference):
    _, transfer_error = quote_initial(reference)
    if transfer_error:
        raise ValidationError('引用报价的金额或币种无法准确核对，不能保存为有效引用。请重新选择报价，或重建无来源情景后核算保存。')


def signed_state(owner, form, result, trial, assessment, reference):
    if not form.is_bound or not form.is_valid() or result is None:raise ValidationError(RECALCULATE)
    require_consistent_reference(reference)
    payload=dict(version=1,owner=owner.pk,nonce=str(uuid4()),calculated_at=timezone.now().isoformat(),
                 scenario=scenario_snapshot(form,result,trial,assessment,reference))
    token=signing.dumps(payload,salt=SALT,compress=False)
    unpack(owner,token)
    if len(token)>MAX_STATE:raise ValidationError('来源条件过长，暂不能保存这次测算；请使用有界条件重新核算。')
    return token


def unpack(owner, token):
    try:
        if not isinstance(token,str) or not 1<=len(token)<=MAX_STATE or token.startswith('.'):raise ValueError
        payload=signing.loads(token,salt=SALT,max_age=3600)
        if set(payload)!={'version','owner','nonce','calculated_at','scenario'} or type(payload['version']) is not int or payload['version']!=1 or payload['owner']!=owner.pk:raise ValueError
        if type(payload['owner']) is not int or not isinstance(payload['nonce'],str) or str(UUID(payload['nonce']))!=payload['nonce']:raise ValueError
        if not isinstance(payload['calculated_at'],str) or len(payload['calculated_at'])>40 or datetime.fromisoformat(payload['calculated_at']).tzinfo is None:raise ValueError
        scenario=payload['scenario']
        if set(scenario)!= {'inputs','missing_optional','optional_presence','unit','trial','assessment','source','shipping'} or set(scenario['inputs'])!=set(INPUT_FIELDS):raise ValueError
        if any(not (value is None or type(value) in (str,bool,int)) or (isinstance(value,str) and len(value)>200) for value in scenario['inputs'].values()):raise ValueError
        if not isinstance(scenario['missing_optional'],list) or any(key not in OPTIONAL_UNIT for key in scenario['missing_optional']):raise ValueError
        if not isinstance(scenario['optional_presence'],dict) or set(scenario['optional_presence'])!=set(OPTIONAL_UNIT) or any(v not in ('missing','blank','explicit') for v in scenario['optional_presence'].values()):raise ValueError
        source=scenario['source']
        if source is not None:
            if not isinstance(source,dict) or set(source)!={'kind','id','snapshot_id','title','url','price','captured_price','currency','observed_at','source','sku_id','market_country','conditions','conditions_unknown'}:raise ValueError
            if source['kind'] not in ('observation','product') or any(type(source[k]) is not int or source[k]<1 for k in ('id','snapshot_id')):raise ValueError
            if not isinstance(source['conditions'],list) or len(source['conditions'])>50 or any(not isinstance(v,str) or len(v)>1000 for v in source['conditions']):raise ValueError
            for key in ('title','url','price','captured_price','currency','observed_at','source','sku_id','market_country'):
                if source[key] is not None and (not isinstance(source[key],str) or len(source[key])>1000):raise ValueError
        if not isinstance(scenario['shipping'],dict) or set(scenario['shipping'])!={'quote','estimate'}:raise ValueError
        if not isinstance(scenario['unit'],dict) or not all(v is None or isinstance(v,dict) for v in (scenario['trial'],scenario['assessment'])):raise ValueError
        plain(payload)
        return payload
    except (signing.BadSignature,ValueError,TypeError,KeyError,AttributeError):
        raise ValidationError(RECALCULATE) from None


def owned_record(owner, pk):
    return get_object_or_404(ProfitStudyRecord,pk=pk,owner=owner)


def current_reference(owner, snapshot):
    try:
        reference=resolve_reference(reference_request(owner,snapshot['source']))
        if snapshot['source'] is not None and reference is None:
            raise ValidationError('原报价已不可访问，请重新选择报价并核算。')
        return reference
    except (Http404,ValidationError):raise ValidationError('原报价已不可访问，请重新选择报价并核算。') from None


def recalculated(owner, snapshot):
    reference=current_reference(owner,snapshot)
    require_consistent_reference(reference)
    raw=snapshot['inputs'].copy()
    for key, presence in snapshot['optional_presence'].items():
        if presence=='missing':raw.pop(key,None)
    form=SelectionAssessmentProfitForm(raw,user=owner)
    if reference:
        code=reference['snapshot'].currency
        if code not in dict(form.fields['sale_currency'].choices):
            if len(code)==3 and code.isascii() and code.isupper() and code.isalpha():
                form.fields['sale_currency'].choices=[*form.fields['sale_currency'].choices,(code,code)]
    if not form.is_valid():raise ValidationError('原物流或输入条件已不可用，请重新选择并核算。')
    result=calculate_profit(form.cleaned_data)
    trial=calculate_trial_budget(result,form.cleaned_data) if form.cleaned_data['trial_enabled'] else None
    assessment=assess_selection(result,form.cleaned_data,trial,reference) if form.cleaned_data['assessment_enabled'] else None
    return scenario_snapshot(form,result,trial,assessment,reference)


def save_study(owner, token, name, notes):
    payload=unpack(owner,token)
    # Validate even direct service callers; the HTTP form applies the same limits.
    if not isinstance(name,str) or not 1<=len(name.strip())<=120 or not isinstance(notes,str) or len(notes)>1000:
        raise ValidationError('请检查记录名称与备注长度。')
    name,notes=name.strip(),notes.strip()
    fingerprint=hashlib.sha256(canonical(dict(payload=payload,name=name,notes=notes)).encode()).hexdigest()
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=owner.pk)
        source=payload['scenario']['source']
        if source:
            query=Snapshot.all_objects.filter(pk=source['snapshot_id'])
            if source['kind']=='observation':query=query.filter(owner=owner,source='browser')
            else:query=query.filter(owner__isnull=True).exclude(source='browser')
            locked=query.select_for_update().first()
            if not locked:raise ValidationError(RECALCULATE)
            Product.objects.select_for_update().get(pk=locked.product_id)
        shipping=payload['scenario']['inputs'].get('shipping_quote')
        if payload['scenario']['inputs'].get('shipping_mode')=='quote' and shipping and shipping.startswith('user:'):
            if not ShippingRate.objects.filter(pk=shipping[5:],owner=owner,active=True).select_for_update().exists():raise ValidationError(RECALCULATE)
        if recalculated(owner,payload['scenario'])!=payload['scenario']:raise ValidationError(RECALCULATE)
        record,created=ProfitStudyRecord.objects.get_or_create(owner=owner,nonce=payload['nonce'],defaults=dict(
            name=name,notes=notes,snapshot=payload,request_fingerprint=fingerprint))
        if not created and record.request_fingerprint!=fingerprint:
            raise ValidationError('这次测算已保存为另一份内容，请重新计算后保存新记录。')
        return record


def study_from_request(request):
    values=request.GET.getlist('study')+request.POST.getlist('study')
    if not values:return None
    if len(values)!=1 or len(values[0])>19 or not values[0].isascii() or not values[0].isdigit() or not 1<=int(values[0])<=9223372036854775807:
        raise ValidationError('测算记录编号无效或重复。')
    if any(request.GET.getlist(k)+request.POST.getlist(k) for k in ('observation','product')):
        raise ValidationError('测算记录不能与其它报价来源同时使用。')
    if any(name in request.GET for name in ('shipping_mode',*ShippingEstimateForm.base_fields)):
        raise ValidationError('测算记录不能同时带入其它物流参数。')
    return owned_record(request.user,int(values[0]))


def report_link(owner, snapshot):
    try:reference=current_reference(owner,snapshot)
    except ValidationError:return ''
    if not reference:return ''
    return reverse('browser_report' if reference['kind']=='observation' else 'product_detail',args=[reference['product'].pk])


def history_inputs(snapshot):
    fields={**SelectionAssessmentProfitForm.base_fields,**ShippingEstimateForm.base_fields}
    rows=[]
    for name,value in snapshot['inputs'].items():
        if value is None:continue
        shown='是' if value is True else ('否' if value is False else value)
        if name=='shipping_mode':shown=dict(fields[name].choices).get(value or 'manual','未知物流方式')
        if name=='shipping_quote':
            quote=snapshot['shipping']['quote']
            shown=' · '.join(str(quote.get(key,'')) for key in ('name','route','currency') if quote.get(key)) if quote else '未选择物流报价'
        if name in snapshot['missing_optional']:shown='未填写（原计算按 0，未确认没有）'
        rows.append((fields[name].label,shown))
    return rows
