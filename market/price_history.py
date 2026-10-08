"""公开报价历史：仅在同币种、相同已记录规格范围下计算边界变化。"""
import hashlib
import json
from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlsplit, urlunsplit
from django.utils import timezone
from django.core.exceptions import ValidationError
from .catalog_content import plain_text, same_product
from .candidates import candidate_url
from .models import CatalogPriceObservation
from .research import AVAILABILITY
from .validation import clean_price

MAX_POINTS = 500


def capture_quote_scope(item, target):
    variants = item.get('variants')
    if not isinstance(variants, list) or not variants or len(variants) > 100 or item.get('variants_limited'):
        return {}
    identities = []
    for variant in variants:
        if not isinstance(variant, dict) or not same_product(variant.get('url'), target):
            return {}
        try:
            url = candidate_url(variant['url'])
        except ValidationError:
            return {}
        name = plain_text(variant.get('name'))
        sku = plain_text(variant.get('sku'))
        size = plain_text(variant.get('size'))
        color = plain_text(variant.get('color'))
        try:
            low, high = clean_price(variant.get('price_low')), clean_price(variant.get('price_high'))
        except ValidationError:
            return {}
        if high < low or variant.get('currency') != item.get('currency'):
            return {}
        is_range = low != high
        # 无明确规格身份的范围报价不能拿来判定同一规格的涨跌。
        identified = bool(sku or size or color or 'variant=' in urlsplit(url).query)
        if not identified and (len(variants) != 1 or is_range):
            return {}
        identities.append({'url':url, 'sku':sku, 'name':name, 'size':size, 'color':color, 'range':bool(is_range)})
    identities = sorted({json.dumps(value, sort_keys=True, ensure_ascii=False) for value in identities})
    payload = {'version':1, 'target':candidate_url(target), 'currency':item.get('currency'), 'identities':identities}
    signature = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {'version':1, 'signature':signature, 'variant_count':len(identities),
            'identities':[json.loads(value) for value in identities]}


def observations_for_url(url):
    normalized = candidate_url(url)
    parts = urlsplit(normalized)
    trailing = urlunsplit((parts.scheme,parts.netloc,parts.path+'/',parts.query,''))
    return CatalogPriceObservation.objects.filter(url__in={url,normalized,trailing})


def compare_quotes(previous, current):
    if previous is None:
        return {'kind':'first','label':'当前窗口中的首条记录'}
    old_scope, new_scope = previous.quote_scope, current.quote_scope
    if not isinstance(old_scope,dict) or not isinstance(new_scope,dict) or not old_scope.get('signature') or not new_scope.get('signature'):
        return {'kind':'unknown','label':'规格范围信息不足，未判断涨跌'}
    if previous.currency != current.currency or old_scope['signature'] != new_scope['signature']:
        return {'kind':'changed','label':'报价条件变化，未直接比较'}
    low, high = current.price_low-previous.price_low, current.price_high-previous.price_high
    def percent(delta, baseline):
        return (delta/baseline*100).quantize(Decimal('.01')) if baseline else None
    return {'kind':'comparable','label':'相同已记录规格范围：报价上下限不变' if low == 0 and high == 0 else '相同已记录规格范围：报价边界有变化',
            'low_change':low,'high_change':high,'low_percent':percent(low,previous.price_low),'high_percent':percent(high,previous.price_high)}


def build_history(queryset, currency, days=0):
    selected = queryset.filter(currency=currency) if currency else queryset.none()
    if days:
        selected = selected.filter(observed_at__gte=timezone.now()-timedelta(days=days))
    total = selected.count()
    observations = list(selected.order_by('-observed_at','-pk')[:MAX_POINTS])[::-1]
    rows, segments, segment = [], {}, 0
    previous = None
    for index, quote in enumerate(observations):
        comparison = compare_quotes(previous,quote)
        if comparison['kind'] != 'comparable':
            segment += 1
        segments.setdefault(segment,[]).append(index)
        scope = quote.quote_scope if isinstance(quote.quote_scope,dict) else {}
        rows.append({'quote':quote,'comparison':comparison,'scope_count':scope.get('variant_count'),
                     'inventory_label':AVAILABILITY.get(quote.availability,'未知')})
        previous = quote
    chart = {'dates':[timezone.localtime(q.observed_at).strftime('%Y-%m-%d %H:%M:%S') for q in observations],
             'low':[str(q.price_low) for q in observations],'high':[str(q.price_high) for q in observations],
             'segments':[indices for indices in segments.values() if len(indices)>1], 'currency':currency}
    return {'rows':list(reversed(rows)), 'chart_data':chart,'total_count':total,'displayed_count':len(rows),
            'truncated':total>MAX_POINTS,'currency':currency,'latest_quote':observations[-1] if observations else None,
            'comparison_count':sum(row['comparison']['kind']=='comparable' for row in rows),
            'change_count':sum(row['comparison']['kind']=='comparable' and (row['comparison']['low_change'] != 0 or row['comparison']['high_change'] != 0) for row in rows)}
