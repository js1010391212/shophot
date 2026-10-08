"""仅分析已保存的目录样本；不估计全市场份额、销量或搜索量。"""
from collections import Counter
from datetime import datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal, ROUND_CEILING
from statistics import median
from urllib.parse import urlencode
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.core.exceptions import ValidationError
from .candidates import candidate_url
from .catalog_content import plain_text


def prepare_rows(rows):
    result, seen = [], set()
    for row in rows:
        try:
            key = candidate_url(row['url'])
        except ValidationError:
            key = row['url']
        if key in seen:
            continue
        seen.add(key)
        brand = plain_text(row.get('brand')) if isinstance(row.get('brand'), str) else ''
        result.append({**row, 'brand_label':brand or '品牌未知',
                       'brand_key':'known:'+brand.casefold() if brand else 'unknown'})
    return result


def filter_rows(rows, data):
    return [row for row in rows if
        (not data.get('q') or data['q'].casefold() in row['display_title'].casefold()) and
        (not data.get('store') or str(row['scan_pk']) == data['store']) and
        (not data.get('brand') or row['brand_key'] == data['brand']) and
        (not data.get('currency') or row['valid_quote'] and row.get('currency') == data['currency']) and
        (data.get('price_min') is None or row['valid_quote'] and row['_low'] >= data['price_min']) and
        (data.get('price_max') is None or row['valid_quote'] and row['_low'] <= data['price_max'])]


def link_for(data, **changes):
    params = {key:str(value) for key,value in data.items() if value not in ('', None)}
    params.update({key:str(value) for key,value in changes.items()})
    return reverse('sample_market')+'?'+urlencode(params)+'#sample-results'


def observation_time(value):
    try:
        text = str(value or '')
        observed = parse_datetime(text)
        if observed is None and text.endswith(' UTC'):
            observed = datetime.strptime(text, '%Y-%m-%d %H:%M UTC').replace(tzinfo=datetime_timezone.utc)
        return observed if observed is not None and timezone.is_aware(observed) else None
    except (ValueError, TypeError, OverflowError):
        return None


def summarize(rows, data, scans, now=None):
    now = now or timezone.now()
    total = len(rows)
    def share(count):
        return round(count*100/total, 1) if total else None
    counts = {'quoted':sum(row['valid_quote'] for row in rows),
              'rating':sum(row['has_rating'] for row in rows),
              'reviews':sum(row['has_reviews'] for row in rows),
              'samples':sum(row['review_sample_count'] > 0 for row in rows),
              'failed':sum(bool(row.get('price_error')) for row in rows)}
    counts['unknown'] = total-counts['quoted']
    recent = stale = unknown_time = 0
    for row in rows:
        if not row['valid_quote']:
            continue
        observed = observation_time(row.get('price_observed_at'))
        if observed is None or timezone.is_naive(observed) or observed > now:
            unknown_time += 1
        elif observed >= now-timedelta(hours=24):
            recent += 1
        else:
            stale += 1
    brands = Counter(row['brand_key'] for row in rows)
    labels = {row['brand_key']:row['brand_label'] for row in reversed(rows)}
    brand_rows = [{'name':labels[key], 'count':count, 'share':share(count), 'url':link_for(data,brand=key)}
                  for key,count in sorted(brands.items(), key=lambda pair:(-pair[1], pair[0]))]
    groups = {}
    for row in rows:
        if row['valid_quote']:
            groups.setdefault(row['currency'], []).append(row['_low'])
    prices = []
    for currency, values in sorted(groups.items()):
        low, high = min(values), max(values)
        if low == high:
            bins = [{'name':f'{low:.2f}', 'count':len(values), 'url':link_for(data,currency=currency,price_min=low,price_max=high)}]
        else:
            step = ((high-low+Decimal('.01'))/5).quantize(Decimal('.01'), rounding=ROUND_CEILING)
            bins=[]
            for index in range(5):
                start = low+step*index
                if start > high:
                    break
                end = min(high, low+step*(index+1)-Decimal('.01'))
                bins.append({'name':f'{start:.2f}–{end:.2f}',
                             'count':sum(start <= value <= end for value in values),
                             'url':link_for(data,currency=currency,price_min=start,price_max=end)})
        prices.append({'currency':currency,'count':len(values),'minimum':low,'maximum':high,
                       'median':Decimal(median(values)).quantize(Decimal('.01')),'bins':bins})
    store_rows=[]
    for scan in scans:
        items=[row for row in rows if row['scan_pk']==scan.pk]
        if items:
            store_rows.append({'scan':scan,'count':len(items),'quoted':sum(row['valid_quote'] for row in items),
                               'samples':sum(row['review_sample_count']>0 for row in items),
                               'failed':sum(bool(row.get('price_error')) for row in items),
                               'url':link_for(data,store=scan.pk)})
    return {'matched_count':total, 'counts':counts,'quote_share':share(counts['quoted']),
            'review_share':share(counts['reviews']), 'recent':recent,'stale':stale,'unknown_time':unknown_time,
            'brands':brand_rows,'prices':prices,'stores':store_rows,
            'chart_data':{'brands':brand_rows[:12], 'prices':prices}}
