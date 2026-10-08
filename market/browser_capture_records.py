"""私有观测的原子确认与完整条件分组，不请求外站。"""
import json
from collections import OrderedDict

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.utils.dateparse import parse_datetime

from .browser_capture import load_preview
from .models import Product, Snapshot
from .browser_capture_targets import identify_capture_target as identify_target


def home_summary(owner):
    """首页只展示当前账号最近保存的每件商品，不混入公共报价统计。"""
    owned = Snapshot.all_objects.filter(source=Snapshot.Source.BROWSER, owner=owner)
    latest = owned.filter(product_id=OuterRef('product_id')).values('pk')[:1]
    return {
        'count': owned.count(),
        'recent': owned.filter(pk=Subquery(latest)).select_related('product')[:3],
    }


def save_preview(token, *, owner, product_pk):
    with transaction.atomic():
        # 同账号不同商品的同一UUID也串行确认；唯一约束作为最终防线。
        get_user_model().objects.select_for_update().get(pk=owner.pk)
        product = Product.objects.select_for_update().get(pk=product_pk)
        platform, target = identify_target(product.url)
        if platform != product.platform:
            raise ValidationError('商品平台已变更，请核对资料并重新采集。')
        capture = load_preview(token, product.url, owner_id=owner.pk, product_pk=product.pk)
        if capture['platform'] != platform or capture['url'] != target:
            raise ValidationError('商品或规格已变更，请重新采集。')
        observation, created = Snapshot.all_objects.get_or_create(
            source=Snapshot.Source.BROWSER, owner=owner, capture_id=capture['capture_id'],
            defaults={
                'product': product, 'price': capture['price'], 'currency': capture['currency'],
                'observed_at': parse_datetime(capture['observed_at']), 'capture_data': capture,
                'context': ('浏览器主动观测；规格 ' + (capture['sku_id'] or '未知') + '；国家 '
                            + (capture['market_country'] or '未知') + '；'
                            + '；'.join(capture['conditions']))[:300],
            },
        )
        if not created and (observation.product_id != product.pk or observation.capture_data != capture):
            raise ValidationError('该观测编号已有不同内容或商品，未覆盖历史；请重新点击采集。')
        return observation, created


def private_groups(rows):
    """不使用截断摘要；未知条件只展示记录，不判断可比性。"""
    groups = OrderedDict()
    for row in rows:
        data = row.capture_data
        conditions = {
            'url': data.get('url'), 'sku_id': data.get('sku_id'),
            'market_country': data.get('market_country'), 'quote_type': data.get('quote_type'),
            'conditions': data.get('conditions', []),
        }
        key = (row.currency, json.dumps(conditions, ensure_ascii=True, sort_keys=True))
        group = groups.setdefault(key, {'currency': row.currency, **conditions, 'rows': []})
        group['rows'].append(row)
    return list(groups.values())
