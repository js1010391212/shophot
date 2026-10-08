"""个人选品清单，按商品链接保存；目录位置变化不会改变收藏身份。"""
from urllib.parse import urlsplit, urlunsplit
from types import SimpleNamespace
from django.core.exceptions import ValidationError
from django.db.models import OuterRef, Subquery
from .models import StoreDiscovery, CatalogCandidate
from .catalog_research import catalog_rows
from .validation import clean_url


def candidate_url(value):
    parts = urlsplit(clean_url(value))
    if parts.scheme != 'https' or parts.port not in (None,443):
        raise ValidationError('候选商品须为 HTTPS 商品链接。')
    # 目录收藏代表商品，保留影响市场/规格的查询参数，仅归一化端口与尾斜线。
    return urlunsplit(('https',parts.hostname,parts.path.rstrip('/'),parts.query,''))


def save_candidate(owner, scan, index):
    if index >= len(scan.products):
        raise ValidationError('目录中没有此商品。')
    item=scan.products[index]
    url=candidate_url(item.get('url',''))
    candidate, created=CatalogCandidate.objects.get_or_create(owner=owner,url=url,defaults={
        'store_url':scan.url,'saved_item':item,'discovery':scan})
    if not created and not candidate.active:
        candidate.active=True
        candidate.save(update_fields=['active','updated_at'])
    return candidate, created


def candidate_rows(candidates):
    candidates=list(candidates)
    stores={c.store_url for c in candidates}
    scans=StoreDiscovery.objects.filter(url__in=stores,status='succeeded',pk=Subquery(
        StoreDiscovery.objects.filter(url=OuterRef('url'),status='succeeded').order_by('-created_at','-pk').values('pk')[:1]))
    current={}
    for scan in scans:
        for row in catalog_rows([scan]):
            try: current[(scan.url,candidate_url(row['url']))]=row
            except ValidationError: continue
    result=[]
    for candidate in candidates:
        row=current.get((candidate.store_url,candidate.url))
        from_latest=row is not None
        if row is None:
            # 最新截取目录未包含商品时保留收藏时数据，避免错配到相同索引的其他商品。
            snapshot=SimpleNamespace(pk=0,url=candidate.store_url,products=[candidate.saved_item])
            rows=catalog_rows([snapshot])
            row=rows[0] if rows else {'display_title':candidate.url,'valid_quote':False}
            row={**row,'scan_pk':None,'selection_id':None}
            if candidate.discovery_id and candidate.discovery.status == 'succeeded':
                for original in catalog_rows([candidate.discovery]):
                    if candidate_url(original['url']) == candidate.url:
                        row={**row,'scan_pk':original['scan_pk'],'catalog_index':original['catalog_index']}
                        break
        result.append({**row,'candidate':candidate,'from_latest':from_latest})
    return result
