from datetime import timedelta
from django.db import transaction
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from .models import PriceMonitor, StoreDiscovery
from .candidates import candidate_url
from .price_monitoring import target_for
from .price_monitoring_forms import MonitorForm


@login_required
@require_GET
def monitors(request):
    rows = []
    for monitor in PriceMonitor.objects.filter(owner=request.user).select_related('pending_job'):
        target = target_for(monitor)
        rows.append({'monitor': monitor, 'scan': target[0] if target else None, 'index': target[1] if target else None})
    return render(request, 'market/price_monitors.html', {'rows': rows})


@login_required
@require_http_methods(['GET', 'POST'])
@transaction.atomic
def configure(request, pk, index):
    scan = get_object_or_404(StoreDiscovery, pk=pk, status='succeeded')
    if index >= len(scan.products):
        raise Http404
    item = scan.products[index]
    try:
        url = candidate_url(item['url'])
    except (ValidationError, KeyError):
        raise Http404
    monitor = PriceMonitor.objects.select_for_update().filter(owner=request.user, url=url).first()
    form = MonitorForm(request.POST if request.method == 'POST' else None, initial={'interval_hours': monitor.interval_hours if monitor else 24})
    if request.method == 'POST' and form.is_valid():
        defaults = {'store_url': scan.url, 'title': (item.get('price_title') or item.get('title') or url)[:300],
                    'interval_hours': form.cleaned_data['interval_hours'], 'active': True}
        if not monitor or not monitor.active:
            defaults['next_run_at'] = timezone.now()
        elif monitor.last_checked_at and not monitor.pending_job_id and monitor.interval_hours != defaults['interval_hours']:
            hours = defaults['interval_hours'] * (2 ** min(monitor.failures, 4) if monitor.last_status == 'failed' else 1)
            defaults['next_run_at'] = max(timezone.now(), (monitor.last_checked_at or timezone.now()) + timedelta(hours=min(72, hours)))
        PriceMonitor.objects.update_or_create(owner=request.user, url=url, defaults=defaults)
        messages.success(request, '监测计划已保存。新开启的计划将由后台采集进程执行。')
        return redirect('price_monitors')
    return render(request, 'market/price_monitor_config.html', {'form': form, 'monitor': monitor, 'scan': scan, 'index': index, 'item': item}, status=400 if form.errors else 200)


@login_required
@require_POST
@transaction.atomic
def toggle(request, pk):
    monitor = get_object_or_404(PriceMonitor.objects.select_for_update(), pk=pk, owner=request.user)
    action = request.POST.get('action')
    if action not in ['pause', 'resume']:
        raise Http404
    monitor.active = action == 'resume'
    if monitor.active and not monitor.pending_job_id:
        monitor.next_run_at = timezone.now()
    monitor.save(update_fields=['active', 'next_run_at'])
    messages.success(request, '已恢复监测。' if monitor.active else '已暂停后续监测；已经排队的任务仍可能完成。')
    return redirect('price_monitors')
