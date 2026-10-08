"""持久化定时计划；由现有单 worker 调度，复用公开报价队列。"""
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import PriceMonitor, StoreDiscovery, StorePriceJob
from .candidates import candidate_url
from .price_history import observations_for_url

ACTIVE = ['queued', 'running']


def target_for(monitor):
    # 链接为身份，目录重排不影响目标；最新截取目录缺失时查找旧目录。
    for scan in StoreDiscovery.objects.filter(url=monitor.store_url, status='succeeded').iterator():
        for index, item in enumerate(scan.products):
            try:
                if candidate_url(item.get('url', '')) == monitor.url:
                    return scan, index
            except ValidationError:
                continue
    return None


def tick():
    now = timezone.now()
    # 只有 worker 写调度结果，页面 GET 不排队。每轮最多处理 50 个计划。
    with transaction.atomic():
        pending = PriceMonitor.objects.select_for_update(of=('self',)).filter(pending_job__isnull=False).exclude(pending_job__status__in=ACTIVE).select_related('pending_job')[:50]
        for monitor in pending:
            job = monitor.pending_job
            if job.status in ACTIVE:
                continue
            quote = observations_for_url(monitor.url).filter(job=job).first()
            monitor.last_checked_at = quote.observed_at if quote else (job.finished_at or now)
            monitor.last_status = 'succeeded' if quote else 'failed'
            monitor.failures = 0 if quote else monitor.failures + 1
            target = target_for(monitor) if not quote else None
            error = target[0].products[target[1]].get('price_error') if target and target[0].pk == job.discovery_id else ''
            monitor.message = '成功保存本次公开报价。' if quote else str(error or job.message or '本次未取得该商品的有效报价。')[:500]
            hours = monitor.interval_hours if quote else min(72, monitor.interval_hours * 2 ** min(monitor.failures, 4))
            monitor.next_run_at = now + timedelta(hours=hours)
            monitor.pending_job = None
            monitor.save()
        due = PriceMonitor.objects.select_for_update().filter(active=True, pending_job__isnull=True, next_run_at__lte=now)[:50]
        for monitor in due:
            target = target_for(monitor)
            if not target:
                monitor.last_status = 'failed'
                monitor.last_checked_at = now
                monitor.message = '已保存目录中找不到此链接，请重新分析店铺；历史报价仍保留。'
                monitor.failures += 1
                monitor.next_run_at = now + timedelta(hours=24)
                monitor.save()
                continue
            scan, index = target
            # 序列化此目录的排队操作，与其它监测共享已排队的相同目标。
            StoreDiscovery.objects.select_for_update().get(pk=scan.pk)
            job = StorePriceJob.objects.filter(discovery=scan, status__in=ACTIVE).first()
            if job and index not in (job.indices or list(range(min(10, len(scan.products))))):
                monitor.next_run_at = now + timedelta(minutes=5)
                monitor.message = '店铺已有其它采集任务，5 分钟后再安排。'
            else:
                if not job:
                    job = StorePriceJob.objects.create(discovery=scan, indices=[index])
                monitor.pending_job = job
                monitor.message = '已排队；采集完成后保存结果。'
            monitor.save()
