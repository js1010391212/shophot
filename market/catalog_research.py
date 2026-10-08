"""跨店研究已保存的公开目录；不进行请求、不估算成交或销量。"""
import re
from urllib.parse import urlsplit
from django.core.exceptions import ValidationError
from django.db.models import OuterRef, Subquery
from .models import StoreDiscovery
from .research import build_research, sort_products


def latest_catalogs():
    return list(StoreDiscovery.objects.filter(status='succeeded',pk=Subquery(
        StoreDiscovery.objects.filter(url=OuterRef('url'),status='succeeded').order_by('-created_at','-pk').values('pk')[:1]))[:30])


def catalog_rows(scans, filters=None):
    filters=filters or {}
    result=[]
    for scan in scans:
        for row in build_research(scan, **filters)['products']:
            result.append({**row,'scan_pk':scan.pk,'store_url':scan.url,'store_name':urlsplit(scan.url).hostname,
                           'selection_id':f'{scan.pk}:{row["catalog_index"]}', 'valid_quote':row['_low'] is not None and bool(row.get('currency'))})
    sort_products(result,filters.get('sort','catalog'),filters.get('currency',''))
    return result


def comparison_rows(values):
    if not 2 <= len(values) <= 8 or len(set(values)) != len(values):
        raise ValidationError('请选择 2–8 件不同商品进行对比。')
    if any(not re.fullmatch(r'[1-9][0-9]{0,9}:[0-9]{1,4}',value) for value in values):
        raise ValidationError('商品选择无效，请重新选择。')
    selections=[tuple(map(int,value.split(':'))) for value in values]
    scans={scan.pk:scan for scan in StoreDiscovery.objects.filter(pk__in=[pk for pk,_ in selections],status='succeeded')}
    rows=[]
    for pk,index in selections:
        scan=scans.get(pk)
        if scan is None or index >= len(scan.products):
            raise ValidationError('选择的商品目录已不可用，请重新选择。')
        row=next((row for row in catalog_rows([scan]) if row['catalog_index']==index),None)
        if row is None or not row['valid_quote'] or not row.get('currency'):
            raise ValidationError('对比商品须有有效公开报价与币种；未知报价无法对比。')
        rows.append(row)
    if len({row['url'] for row in rows}) != len(rows):
        raise ValidationError('同一商品链接不能重复对比，请重新选择。')
    if len({row['currency'] for row in rows}) != 1:
        raise ValidationError('请选择同一个币种的商品；不同币种不能直接对比。')
    return rows
