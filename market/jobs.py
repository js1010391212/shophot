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
        return False
    claimed = CollectionJob.objects.filter(pk=job.pk, status="queued").update(status="running", started_at=timezone.now())
    if not claimed:
        return True
    logger.info("开始采集 job=%s product=%s", job.pk, job.product_id)
    try:
        result = collect(job.product.url)
        with transaction.atomic():
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
