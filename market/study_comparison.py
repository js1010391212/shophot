"""Read historical version-1/2 economics without recalculating platform or freight."""
from decimal import Decimal, InvalidOperation, localcontext
import re
from uuid import UUID
from zoneinfo import ZoneInfo
from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_datetime
from .models import ProfitStudyRecord
from .profit_studies import INPUT_FIELDS, OPTIONAL_UNIT
from .catalog_profit_references import valid_catalog_source

UNIT_LABELS=('采购成本','履约运费','广告成本','其他成本')
UNIT_FIELDS=(('历史折后售价','discounted_price'),('单件收入','revenue'),('平台费用','fee'),
             ('支付费用','payment_fee'),('总成本与费用','expenses'),('单件净利','net'))
BATCH_FIELDS=(('基础准备资金','prepared'),('结算费用','settlement'),('全部售出收入','revenue'),
              ('销售总成本费用','expenses'),('全部售出净利','net'),('未支出预留','reserve'))
UNIT_SCOPE='一件商品一单'


def invalid():
    raise ValidationError('这份历史记录版本、字段或金额无效，暂不可比较；请返回原记录核对或重新测算。')


def amount(value, places=2):
    if not isinstance(value,str) or not re.fullmatch(r'-?[0-9]{1,24}(?:\.[0-9]{1,'+str(places)+'})?',value):invalid()
    try:
        number=Decimal(value)
        if not number.is_finite():invalid()
        return number
    except InvalidOperation:invalid()


def currency(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Z]{3}',value,re.ASCII):invalid()
    return value


def moment(value):
    if not isinstance(value,str) or len(value)>40:invalid()
    try:
        parsed=parse_datetime(value)
        if parsed is None or parsed.tzinfo is None:invalid()
        parsed.astimezone(ZoneInfo('Asia/Shanghai'))
        return parsed
    except (OverflowError,ValueError,TypeError):invalid()


def text(value, maximum=1000, nullable=False):
    if nullable and value is None:return None
    if not isinstance(value,str) or len(value)>maximum:invalid()
    return value


def read_history(record):
    """Validate the saved envelope before rendering or deriving any differences."""
    try:
        payload=record.snapshot
        if not isinstance(payload,dict) or set(payload)!={'version','owner','nonce','calculated_at','scenario'}:invalid()
        if type(payload['version']) is not int or payload['version'] not in (1,2) or type(payload['owner']) is not int or payload['owner']!=record.owner_id:invalid()
        UUID(payload['nonce']);calculated=moment(payload['calculated_at'])
        scenario=payload['scenario']
        if not isinstance(scenario,dict) or set(scenario)!={'inputs','unit','trial','assessment','shipping','source','missing_optional','optional_presence'}:invalid()
        inputs,unit=scenario['inputs'],scenario['unit']
        if not isinstance(inputs,dict) or set(inputs)!=set(INPUT_FIELDS) or not isinstance(unit,dict):invalid()
        money_inputs={'selling_price','cost','shipping','ad_cost','other_cost','fee_rate','payment_fee_rate','payment_fixed','discount_rate','target_margin','trial_sample_cost','trial_setup_cost','trial_compliance_cost','trial_reserve_cost','package_length','package_width','package_height','fuel_rate','shipping_extra'}
        for name,value in inputs.items():
            if value is not None and type(value) not in (str,bool,int):invalid()
            if isinstance(value,str) and len(value)>200:invalid()
            if name in money_inputs and value not in (None,'') and amount(value)<0:invalid()
            if name in ('exchange_rate','shipping_exchange_rate') and value is not None:amount(value,6)
            if name=='package_weight' and value is not None:amount(value,3)
            if name in ('trial_quantity','package_units') and value is not None and (type(value) is not int or not 1<=value<=10000):invalid()
        for name in ('cost','fee_rate'):amount(inputs[name])
        if inputs['shipping_mode'] not in ('','manual','quote'):invalid()
        if inputs['shipping_mode']!='quote':amount(inputs['shipping'])
        cost_currency=currency(unit['cost_currency']);sale_currency=currency(unit['sale_currency'])
        if cost_currency!=currency(inputs['cost_currency']) or sale_currency!=currency(inputs['sale_currency']):invalid()
        rate=amount(unit['rate'],6)
        if rate<=0 or rate!=amount(inputs['exchange_rate'],6):invalid()
        costs=unit['costs']
        if not isinstance(costs,list) or len(costs)!=4:invalid()
        by_label={}
        for pair in costs:
            if not isinstance(pair,list) or len(pair)!=2 or pair[0] not in UNIT_LABELS or pair[0] in by_label:invalid()
            value=amount(pair[1])
            if value<0:invalid()
            by_label[pair[0]]=value
        cost_rows=[(label,by_label[label]) for label in UNIT_LABELS]
        if set(unit)!={'revenue','fee','payment_fee','expenses','net','sale_net','margin','roi','discounted_price','breakeven','target_price','target_margin','sale_currency','cost_currency','rate','negative','costs'}:invalid()
        for key in ('sale_net','target_margin'):amount(unit[key])
        for key in ('margin','roi','breakeven','target_price'):
            if unit[key] is not None:amount(unit[key])
        if type(unit['negative']) is not bool:invalid()
        values={key:amount(unit[key]) for _,key in UNIT_FIELDS}
        selling_price=amount(inputs['selling_price'])
        if selling_price<0 or any(values[k]<0 for k in ('discounted_price','revenue','fee','payment_fee','expenses')):invalid()
        presence=scenario['optional_presence'];missing=scenario['missing_optional']
        if not isinstance(presence,dict) or set(presence)!=set(OPTIONAL_UNIT) or any(v not in ('missing','blank','explicit') for v in presence.values()):invalid()
        if not isinstance(missing,list) or len(missing)!=len(set(missing)) or any(k not in OPTIONAL_UNIT for k in missing):invalid()
        if set(missing)!={k for k,v in presence.items() if v!='explicit'}:invalid()
        for name in OPTIONAL_UNIT:
            if name in missing:
                if inputs[name]!='':invalid()
            else:amount(inputs[name])
        for key in ('trial_enabled','assessment_enabled','assessment_costs_confirmed'):
            if type(inputs[key]) is not bool:invalid()
        if inputs['trial_enabled'] or inputs['assessment_enabled']:
            for name in ('ad_cost','other_cost','payment_fee_rate','payment_fixed'):
                if presence[name]!='explicit' or inputs[name] in (None,''):invalid()
        if inputs['assessment_enabled']:
            for name in ('discount_rate','target_margin'):
                if presence[name]!='explicit' or inputs[name] in (None,''):invalid()
        if inputs['trial_enabled']:
            for name in ('trial_sample_cost','trial_setup_cost','trial_compliance_cost','trial_reserve_cost'):
                if inputs[name] in (None,'') or amount(inputs[name])<0:invalid()
        assessment=scenario['assessment']
        if inputs['assessment_enabled']:
            if not isinstance(assessment,dict):invalid()
            if set(assessment)!={'status','title','reasons','unknowns','revenue','net','target','required_net','currency','trial','source_note','changed'}:invalid()
            title=text(assessment['title'])
            text(assessment['status'],100);text(assessment['source_note'])
            if currency(assessment['currency'])!=cost_currency:invalid()
            for key in ('revenue','net','target'):amount(assessment[key])
            if amount(assessment['revenue'])!=values['revenue'] or amount(assessment['net'])!=values['net'] or amount(assessment['target'])!=amount(unit['target_margin']):invalid()
            amount(assessment['required_net'],6)
            for key in ('reasons','unknowns'):
                if not isinstance(assessment[key],list) or len(assessment[key])>50:invalid()
                for item in assessment[key]:text(item)
            if type(assessment['changed']) is not bool or assessment['trial']!=scenario['trial']:invalid()
        else:
            if assessment is not None:invalid()
            title='未启用历史选品判断'
        trial=scenario['trial'];batch=None
        if inputs['trial_enabled']:
            if not isinstance(trial,dict) or type(trial['quantity']) is not int or not 1<=trial['quantity']<=10000:invalid()
            if trial['quantity']!=inputs['trial_quantity'] or currency(trial['currency'])!=cost_currency:invalid()
            if set(trial)!={'quantity','currency','operating','once','fixed','reserve','prepared','settlement','revenue','expenses','net','recovery','status','negative'}:invalid()
            amount(trial['fixed']);text(trial['status'])
            if type(trial['negative']) is not bool or (trial['recovery'] is not None and (type(trial['recovery']) is not int or trial['recovery']<0)):invalid()
            for key,count in (('operating',4),('once',3)):
                if not isinstance(trial[key],list) or len(trial[key])!=count:invalid()
                for pair in trial[key]:
                    if not isinstance(pair,list) or len(pair)!=2:invalid()
                    text(pair[0]);amount(pair[1])
            batch={key:amount(trial[key]) for _,key in BATCH_FIELDS}
            if any(batch[k]<0 for k in ('prepared','settlement','revenue','expenses','reserve')):invalid()
        elif trial is not None:invalid()
        source=scenario['source'];observed=None
        if payload['version']==2:
            if not valid_catalog_source(source):invalid()
            observed=moment(source['observed_at'])
        elif source is not None:
            if not isinstance(source,dict) or set(source)!={'kind','id','snapshot_id','title','url','price','captured_price','currency','observed_at','source','sku_id','market_country','conditions','conditions_unknown'}:invalid()
            if source['kind'] not in ('observation','product') or any(type(source[k]) is not int or not 1<=source[k]<=9223372036854775807 for k in ('id','snapshot_id')):invalid()
            for key in ('title','url','source'):text(source[key])
            text(source['sku_id'],nullable=True);text(source['market_country'],nullable=True)
            if amount(source['price'])<0 or amount(source['captured_price'])<0:invalid()
            currency(source['currency']);observed=moment(source['observed_at'])
            if not isinstance(source['conditions'],list) or len(source['conditions'])>50:invalid()
            for condition in source['conditions']:text(condition)
            if type(source['conditions_unknown']) is not bool:invalid()
        shipping=scenario['shipping']
        if not isinstance(shipping,dict) or set(shipping)!={'quote','estimate'}:invalid()
        return dict(record=record,scenario=scenario,calculated_at=calculated,observed_at=observed,
                    cost_currency=cost_currency,sale_currency=sale_currency,rate=rate,scope=UNIT_SCOPE,
                    selling_price=selling_price,costs=cost_rows,values=values,batch=batch,
                    quantity=trial['quantity'] if trial else None,source=source,title=title,
                    confirmed=inputs['assessment_costs_confirmed'],missing=missing)
    except (KeyError,TypeError,ValueError,AttributeError,InvalidOperation):invalid()


def delta(a,b):
    with localcontext() as context:
        context.prec=64
        return b-a


def compare_histories(left,right):
    reasons=[]
    for key,label in (('cost_currency','成本币种'),('sale_currency','售价币种'),('rate','实际汇率'),('scope','单位口径')):
        if left[key]!=right[key]:reasons.append(label+'不同')
    comparable=not reasons
    rows=[dict(label='假设售价',left=left['selling_price'],right=right['selling_price'],
               difference=delta(left['selling_price'],right['selling_price']) if comparable else None,sale=True)]
    for (label,a),(_,b) in zip(left['costs'],right['costs']):
        field={'广告成本':'ad_cost','其他成本':'other_cost'}.get(label)
        left_unknown=field in left['missing'] if field else False
        right_unknown=field in right['missing'] if field else False
        rows.append(dict(label=label,left=a,right=b,left_unknown=left_unknown,right_unknown=right_unknown,
                         difference=delta(a,b) if comparable and not left_unknown and not right_unknown else None,sale=False))
    for label,key in UNIT_FIELDS:
        a,b=left['values'][key],right['values'][key]
        fields=('payment_fee_rate','payment_fixed') if key=='payment_fee' else (('discount_rate',) if key=='discounted_price' else ())
        left_unknown=any(field in left['missing'] for field in fields)
        right_unknown=any(field in right['missing'] for field in fields)
        rows.append(dict(label=label,left=a,right=b,left_unknown=left_unknown,right_unknown=right_unknown,
                         difference=delta(a,b) if comparable and not left_unknown and not right_unknown else None,sale=key=='discounted_price'))
    batch_reasons=list(reasons);batch_rows=[]
    if left['batch'] is None or right['batch'] is None:batch_reasons.append('至少一份未启用测品预算')
    elif left['quantity']!=right['quantity']:batch_reasons.append('批次数量不同')
    if left['batch'] is not None and right['batch'] is not None:
        for label,key in BATCH_FIELDS:
            a,b=left['batch'][key],right['batch'][key]
            batch_rows.append(dict(label=label,left=a,right=b,difference=delta(a,b) if not batch_reasons else None))
    return dict(unit_rows=rows,unit_reasons=reasons,batch_rows=batch_rows,batch_reasons=batch_reasons)


def choice_rows(owner):
    return list(ProfitStudyRecord.objects.filter(owner=owner,active=True)
                .order_by('-created_at','-pk').values('pk','name','created_at')[:100])


def selected_records(owner,ids):
    rows=list(ProfitStudyRecord.objects.filter(owner=owner,active=True,pk__in=ids).order_by('pk')[:2])
    if len(rows)!=2:raise ValidationError('只能比较自己的两份不同且仍在研究中的记录，请重新选择。')
    by_id={row.pk:row for row in rows}
    return [by_id[pk] for pk in ids]
