"""首页分析流程的应用服务；GET 页面不会创建采集任务。"""
from django.db import transaction, IntegrityError
from .models import StoreDiscovery
from .catalog_research import latest_catalogs
from .candidates import candidate_url
from django.core.exceptions import ValidationError


def start_store_analysis(url, refresh=False):
    try:
        with transaction.atomic():
            active=StoreDiscovery.objects.select_for_update().filter(url=url,status__in=['queued','running']).first()
            if active:
                active.analyze_prices=True
                active.save(update_fields=['analyze_prices'])
                return active
            if not refresh:
                saved=StoreDiscovery.objects.filter(url=url,status='succeeded').first()
                if saved:
                    return saved
            # 条件唯一约束防并发；外层调用发生冲突时复用已入队任务。
            return StoreDiscovery.objects.create(url=url,analyze_prices=True)
    except IntegrityError:
        active=StoreDiscovery.objects.filter(url=url,status__in=['queued','running']).first()
        if active:
            StoreDiscovery.objects.filter(pk=active.pk).update(analyze_prices=True)
            return active
        raise



def saved_catalog_product(url):
    target=candidate_url(url)
    for scan in latest_catalogs():
        for index,item in enumerate(scan.products):
            try:
                if candidate_url(item.get('url','')) == target:
                    return scan.pk,index
            except ValidationError:
                continue
    return None
