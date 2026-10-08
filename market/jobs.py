"""轻量数据库任务队列；原子认领任务，避免把爬虫放进网页请求。"""
import logging
from datetime import timedelta
from django.db import IntegrityError, transaction
from django.utils import timezone
from .collectors import CollectionError, collect
from .models import CollectionJob, Snapshot

logger = logging.getLogger(__name__)


def enqueue(product):
    try:
        with transaction.atomic():
            return CollectionJob.objects.create(product=product), True
    except IntegrityError:
        return CollectionJob.objects.get(product=product, status__in=["queued", "running"]), False


def run_next():
    # 崩溃或中断后不永久卡在 running；保留失败记录，用户可以手动重试。
    stale = CollectionJob.objects.filter(status="running", started_at__lt=timezone.now() - timedelta(minutes=10))
    recovered = stale.update(status="failed", finished_at=timezone.now(), message="任务进程中断或超时，请重新采集。")
    if recovered:
        logger.warning("回收超时任务 count=%s", recovered)
    job = CollectionJob.objects.filter(status="queued").order_by("created_at", "pk").first()
    if not job:
        return run_store_discovery() or run_store_prices()
    claimed = CollectionJob.objects.filter(pk=job.pk, status="queued").update(status="running", started_at=timezone.now())
    if not claimed:
        return True
    logger.info("开始采集 job=%s product=%s", job.pk, job.product_id)
    try:
        if job.product.platform.lower() == "shopify":
            from .shopify import collect_shopify
            result = collect_shopify(job.product.url)
        elif job.product.platform == 'OTTO':
            raise CollectionError('OTTO 自动采集遇到安全验证，目前请导入已保存的公开商品页面或手动记录。')
        else:
            from urllib.parse import urlsplit, parse_qs
            if 'sku_id' in parse_qs(urlsplit(job.product.url).query,keep_blank_values=True):
                raise CollectionError('速卖通 sku_id 规格请使用页面导入，自动采集尚不能确认规格。')
            result = collect(job.product.url)
        # 自动识别标题仅更新尚未命名的商品，不覆盖用户编辑的名称。
        title = result.pop("title", None)
        with transaction.atomic():
            if title and job.product.title.startswith("待识别竞品 · "):
                type(job.product).objects.filter(pk=job.product_id, title=job.product.title).update(title=title)
            Snapshot.objects.create(product=job.product, observed_at=timezone.now(), source=Snapshot.Source.WEB, **result)
            CollectionJob.objects.filter(pk=job.pk).update(status="succeeded", finished_at=timezone.now(),
                                                         message="已保存价格快照。页面未提供的销量保持为空。")
        logger.info("采集完成 job=%s", job.pk)
    except CollectionError as exc:
        CollectionJob.objects.filter(pk=job.pk).update(status="failed", finished_at=timezone.now(), message=str(exc)[:500])
        logger.warning("采集失败 job=%s reason=%s", job.pk, exc)
    except Exception as exc:
        # 日志记录类型和任务 ID；不要把第三方响应或可能携带凭据的异常正文写入日志。
        logger.error("采集异常 job=%s type=%s", job.pk, type(exc).__name__)
        CollectionJob.objects.filter(pk=job.pk).update(status="failed", finished_at=timezone.now(),
                                                     message="采集发生内部错误，请检查日志中的任务编号。")
    return True


def run_store_discovery():
    from .models import StoreDiscovery, StorePriceJob
    from django.db import transaction
    from .discovery import discover
    from django.core.exceptions import ValidationError
    StoreDiscovery.objects.filter(status='running', started_at__lt=timezone.now() - timedelta(minutes=10)).update(
        status='failed', finished_at=timezone.now(), message='目录任务中断，请重新发现。')
    job = StoreDiscovery.objects.filter(status='queued').order_by('pk').first()
    if not job:
        return False
    if not StoreDiscovery.objects.filter(pk=job.pk, status='queued').update(status='running', started_at=timezone.now()):
        return True
    try:
        data = discover(job.url)
        with transaction.atomic():
            current=StoreDiscovery.objects.select_for_update().get(pk=job.pk)
            StoreDiscovery.objects.filter(pk=job.pk).update(status='succeeded', finished_at=timezone.now(), **data,
                message='已发现公开商品目录；自动分析首批最多 10 件。' if current.analyze_prices else '已发现公开商品链接；价格与规格需另行观测。')
            if current.analyze_prices and data['products']:
                indices=list(range(min(10,len(data['products']))))
                StorePriceJob.objects.create(discovery=current,indices=indices,total=len(indices))
    except (CollectionError, ValidationError) as exc:
        StoreDiscovery.objects.filter(pk=job.pk).update(status='failed', finished_at=timezone.now(), message=str(exc)[:500])
    except Exception as exc:
        logger.error('目录采集异常 job=%s type=%s', job.pk, type(exc).__name__)
        StoreDiscovery.objects.filter(pk=job.pk).update(status='failed', finished_at=timezone.now(), message='目录任务内部错误，请检查日志。')
    return True


def run_store_prices():
    from .models import StorePriceJob, StoreDiscovery
    from .catalog_prices import collect_catalog_prices, BATCH_SIZE
    from django.core.exceptions import ValidationError
    StorePriceJob.objects.filter(status='running', started_at__lt=timezone.now() - timedelta(minutes=10)).update(
        status='failed', finished_at=timezone.now(), message='价格任务中断；已取得的报价保留，可重新采集。')
    job = StorePriceJob.objects.filter(status='queued').select_related('discovery').order_by('pk').first()
    if not job:
        return False
    if not StorePriceJob.objects.filter(pk=job.pk, status='queued').update(status='running', started_at=timezone.now()):
        return True
    from .models import CatalogPriceObservation
    from .price_history import capture_quote_scope
    items = job.discovery.products
    indices = job.indices or list(range(min(len(items), BATCH_SIZE)))
    total = len(indices)
    StorePriceJob.objects.filter(pk=job.pk).update(total=total)
    successful = processed = 0
    def save(index, result):
        nonlocal successful, processed
        now = timezone.now()
        result['price_attempted_at'] = now.isoformat()
        items[index].update(result)
        good = not result.get('price_error')
        with transaction.atomic():
            if good:
                CatalogPriceObservation.objects.create(discovery=job.discovery, job=job, url=items[index]['url'],
                    title=result['price_title'] or items[index]['title'], price_low=result['price_low'],
                    price_high=result['price_high'], currency=result['currency'], availability=result['availability'], observed_at=now,
                    quote_scope=capture_quote_scope(result, items[index]['url']))
            StoreDiscovery.objects.filter(pk=job.discovery_id).update(products=items)
            StorePriceJob.objects.filter(pk=job.pk).update(processed=processed + 1)
        successful += int(good)
        processed += 1
    try:
        if not indices or len(indices) > 100 or any(type(i) is not int or i < 0 or i >= len(items) for i in indices) or len(set(indices)) != len(indices):
            raise CollectionError('任务商品范围无效，请重新排队。')
        for offset in range(0, total, BATCH_SIZE):
            batch = indices[offset:offset + BATCH_SIZE]
            collect_catalog_prices(job.discovery.url, [items[i] for i in batch], lambda i, row: save(batch[i], row))
        StorePriceJob.objects.filter(pk=job.pk).update(status='succeeded' if successful else 'failed', finished_at=timezone.now(),
            message=f'本次处理 {total} 件，取得 {successful} 件公开报价；其余 {total - successful} 件未取得新报价。')
    except (CollectionError, ValidationError) as exc:
        StorePriceJob.objects.filter(pk=job.pk).update(status='failed', finished_at=timezone.now(), message=str(exc)[:500])
    except Exception as exc:
        logger.error('目录价格任务异常 job=%s type=%s', job.pk, type(exc).__name__)
        StorePriceJob.objects.filter(pk=job.pk).update(status='failed', finished_at=timezone.now(), message='价格任务内部错误，已取得报价保留。')
    return True
