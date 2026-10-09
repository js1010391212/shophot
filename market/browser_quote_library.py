"""Account-owned, read-only quote library; never aggregates currencies or conditions."""
from django.db.models import Q
from .models import Snapshot


def owned_quotes(owner):
    return Snapshot.all_objects.filter(source=Snapshot.Source.BROWSER, owner=owner)


def filter_options(owner):
    rows = owned_quotes(owner)
    platforms = list(rows.order_by('product__platform').values_list('product__platform', flat=True).distinct())
    currencies = list(rows.filter(currency__regex=r'^[A-Z]{3}$').order_by('currency').values_list('currency', flat=True).distinct())
    return platforms, currencies


def filtered_quotes(owner, filters):
    rows = owned_quotes(owner)
    if filters.get('q'):
        # Search the original observed title; product metadata may have changed later.
        missing_title = Q(capture_data__title__isnull=True) | Q(capture_data__title=None) | Q(capture_data__title='')
        rows = rows.filter(Q(capture_data__title__icontains=filters['q']) |
                           (missing_title & Q(product__title__icontains=filters['q'])))
    if filters.get('platform'):
        rows = rows.filter(product__platform=filters['platform'])
    if filters.get('currency'):
        rows = rows.filter(currency=filters['currency'])
    return rows.select_related('product').order_by('-observed_at', '-pk')
