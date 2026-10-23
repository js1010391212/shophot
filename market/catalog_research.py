"""跨店研究已保存的公开目录；不进行请求、不估算成交或销量。"""
import re
from urllib.parse import urlsplit
from django.core.exceptions import ValidationError
from django.db.models import OuterRef, Subquery
from .models import StoreDiscovery
from .research import build_research, sort_products
from .pololu_catalog import is_pololu_store, normalize_pololu_product_url
from .catalog_coverage import quote_display_moment
from .validation import clean_price


def latest_catalogs():
    return list(StoreDiscovery.objects.filter(status='succeeded',pk=Subquery(
        StoreDiscovery.objects.filter(url=OuterRef('url'),status='succeeded').order_by('-created_at','-pk').values('pk')[:1]))[:30])


def comparison_terms(scan, row):
    """Display scope only: missing historical producer evidence stays unknown."""
    quantity = '数量条件未知；不能从规格条数推断件数。'
    try:
        target = normalize_pololu_product_url(row.get('url'))
        variants = row.get('variants')
        if (is_pololu_store(scan.url) and row.get('content_policy') == 'facts_only'
                and row.get('price_source') == target == row.get('content_source')
                and row.get('currency') == 'USD' and row.get('_low') is not None
                and row.get('_low') == row.get('_high')
                and quote_display_moment(row.get('price_observed_at'))[0] is not None
                and row.get('sku') == target.rsplit('/', 1)[-1]
                and row.get('availability') == 'InStock'
                and not row.get('variants_limited') and isinstance(variants, list)
                and len(variants) == 1 and isinstance(variants[0], dict)):
            variant = variants[0]
            if (variant.get('url') == target and variant.get('sku') == row['sku']
                    and variant.get('currency') == 'USD' and variant.get('availability') == 'InStock'
                    and variant.get('is_range') is False and variant.get('size') == ''
                    and variant.get('color') == ''
                    and clean_price(variant.get('price_low')) == row['_low']
                    and clean_price(variant.get('price_high')) == row['_high']):
                quantity = '当前适配核验范围：数量 1 的 USD 单件价，不计批量阶梯优惠；历史记录未独立保存数量字段。'
    except (ValidationError, TypeError, ValueError):
        pass
    return {'comparison_quantity_note': quantity,
            'comparison_inventory_note': '库存为来源页面标注；库存数量未知，不保证现货或履约。'}


def catalog_rows(scans, filters=None):
    filters=filters or {}
    result=[]
    for scan in scans:
        for row in build_research(scan, **filters)['products']:
            result.append({**row, **comparison_terms(scan, row), 'scan_pk':scan.pk,'store_url':scan.url,'store_name':urlsplit(scan.url).hostname,
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
