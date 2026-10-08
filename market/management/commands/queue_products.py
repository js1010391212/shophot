from django.core.management.base import BaseCommand
from django.db.models import Q
from market.jobs import enqueue
from market.models import Product


class Command(BaseCommand):
    help = "为速卖通和 Shopify 商品加入采集任务，可用于定时更新"

    def handle(self, *args, **options):
        created = 0
        for product in Product.objects.filter(Q(platform__iexact="AliExpress") | Q(platform__iexact="Shopify")).iterator():
            _, added = enqueue(product)
            created += added
        self.stdout.write(f"新增 {created} 个任务（已有进行中的任务不会重复加入）。")
