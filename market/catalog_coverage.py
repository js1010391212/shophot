"""Read-only coverage of one saved directory and its latest price job.

A processed counter is progress, not successful quotes or a per-request audit.
Only observations linked to this job count as newly obtained prices. A stopped
request without a callback remains unknown; it is never labelled unattempted.
"""
from datetime import datetime
import re
from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_datetime
from .models import CatalogPriceObservation
from .validation import clean_price

DEFAULT_BATCH_SIZE = 10  # Existing empty-indices StorePriceJob contract.


def valid_currency(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Z]{3}', value, re.ASCII) is not None


def quote_values(item):
    """An observation timestamp alone is not a valid quoted amount/currency."""
    if not item.get('price_observed_at') or not valid_currency(item.get('currency')):
        return None, None
    try:
        low, high = clean_price(item.get('price_low')), clean_price(item.get('price_high'))
        return (low, high) if high >= low else (None, None)
    except (ValidationError, TypeError, ValueError):
        return None, None


def moment(value):
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else None
    if not isinstance(value, str) or len(value) > 50:
        return None
    try:
        parsed = parse_datetime(value)
        return parsed if parsed and parsed.tzinfo is not None else None
    except (ValueError, TypeError, OverflowError):
        return None


def _planned_indices(scan, job):
    if job is None:
        return [], True
    indices = job.indices or list(range(min(len(scan.products), DEFAULT_BATCH_SIZE)))
    good = (isinstance(indices, list) and len(indices) <= 100
            and all(type(i) is int and 0 <= i < len(scan.products) for i in indices)
            and len(set(indices)) == len(indices))
    return (indices if good else []), good


def build_catalog_coverage(scan, job=None):
    """Return display copies only; never save, enqueue, or read another scan."""
    if job is not None and job.discovery_id != scan.pk:
        raise ValueError('Price job must belong to the displayed directory.')
    indices, scope_known = _planned_indices(scan, job)
    planned_urls = {scan.products[i].get('url') for i in indices if isinstance(scan.products[i], dict)}
    # One bounded query for this job; no historical scans or private data involved.
    current = {}
    if job is not None and scope_known:
        for quote in CatalogPriceObservation.objects.filter(job_id=job.pk, discovery_id=scan.pk, url__in=planned_urls):
            item = dict(price_low=quote.price_low, price_high=quote.price_high,
                        currency=quote.currency, price_observed_at=quote.observed_at)
            if quote_values(item)[0] is not None:
                current[quote.url] = quote
    rows, seen = [], set()
    display_items = [dict(item) if isinstance(item, dict) else {} for item in scan.products]
    for index, original in enumerate(scan.products):
        if not isinstance(original, dict) or not isinstance(original.get('url'), str) or not original['url'] or original['url'] in seen:
            continue
        seen.add(original['url'])
        item = dict(original)
        quote = current.get(item['url'])
        # Independently saved observation wins over mutable directory metadata.
        if quote:
            item.update(price_low=quote.price_low, price_high=quote.price_high,
                        currency=quote.currency, price_observed_at=quote.observed_at.isoformat(),
                        availability=quote.availability, price_title=quote.title, price_error='')
        low, high = quote_values(item)
        quoted = low is not None
        attempted = moment(item.get('price_attempted_at'))
        in_window = bool(job and job.started_at and attempted and attempted >= job.started_at
                         and (job.finished_at is None or attempted <= job.finished_at))
        explicit_failure = bool(item['url'] in planned_urls and scope_known and in_window
                                and isinstance(item.get('price_error'), str) and item['price_error'])
        if quote:
            state, label = 'success', '本批新取得报价'
        elif not job:
            state, label = 'no_job', '本目录尚无报价任务'
        elif not scope_known:
            state, label = 'unknown', '任务范围无法核对'
        elif item['url'] not in planned_urls:
            state, label = 'not_scheduled', '未安排本批采集'
        elif explicit_failure:
            state, label = 'failed', '本批明确失败'
        elif job.status == 'queued':
            state, label = 'pending', '本批尚未开始'
        elif job.status == 'running':
            state, label = 'pending', '本批待处理或结果尚未记录'
        else:
            state, label = 'unknown', '本批未取得新报价，逐项结果未记录'
        item.update(catalog_index=index, coverage_state=state, coverage_label=label,
                    quote_origin='current' if quote else ('historical' if quoted else 'none'),
                    quote_origin_label='本批新报价' if quote else ('沿用已保存报价' if quoted else '无有效报价'),
                    quote_seen_at=moment(item.get('price_observed_at')), valid_quote=quoted)
        rows.append(item)
        display_items[index] = item
    new = sum(row['coverage_state'] == 'success' for row in rows)
    failed = sum(row['coverage_state'] == 'failed' for row in rows)
    unresolved = sum(row['coverage_state'] in ('pending', 'unknown') for row in rows)
    historical = sum(row['quote_origin'] == 'historical' for row in rows)
    quoted = new + historical
    not_scheduled = sum(row['coverage_state'] == 'not_scheduled' for row in rows)
    active = bool(job and job.status in ('queued', 'running'))
    if scan.status == 'failed':
        state, title = 'directory_failed', '公开目录获取失败'
    elif scan.status in ('queued', 'running'):
        state, title = 'discovering', '正在发现公开商品目录'
    elif not rows:
        state, title = 'empty', '没有可识别的公开商品链接'
    elif not job:
        state, title = 'directory_only', '已保存目录，尚无本目录报价任务'
    elif active:
        state, title = 'collecting', '目录已就绪，报价仍在采集'
    elif not new:
        state, title = 'no_new_quotes', '本批未取得新的有效报价'
    elif failed or unresolved:
        state, title = 'partial', '本批取得部分报价'
    else:
        state, title = 'completed', '本批报价已整理'
    return dict(state=state, title=title, items=display_items, catalog_only=not scan.analyze_prices and job is None,
                attribution=(dict(creator="Electronic Frontier Foundation", policy="https://www.eff.org/copyright", license="CC BY 4.0", license_url="https://creativecommons.org/licenses/by/4.0/") if scan.url.rstrip("/")=="https://shopeff.org" else None), total_count=len(rows),
                raw_link_count=len(scan.products), limited=scan.limited,
                directory_observed_at=scan.finished_at if scan.status == 'succeeded' else None,
                directory_created_at=scan.created_at, store_url=scan.url,
                job=job, active=active, scope_known=scope_known,
                planned_count=len({scan.products[i].get('url') for i in indices if isinstance(scan.products[i], dict) and scan.products[i].get('url')}) if scope_known else None,
                new_count=new, failed_count=failed, unresolved_count=unresolved,
                not_scheduled_count=not_scheduled, historical_count=historical,
                quoted_count=quoted, unquoted_count=len(rows)-quoted)


def coverage_message(coverage):
    return (f"已发现 {coverage['total_count']} 个商品链接；本批新报价 {coverage['new_count']}，"
            f"明确失败 {coverage['failed_count']}，待处理或逐项结果未记录 {coverage['unresolved_count']}。"
            f"沿用已保存报价 {coverage['historical_count']}；未安排本批 {coverage['not_scheduled_count']}。")
