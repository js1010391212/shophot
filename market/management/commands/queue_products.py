from django.core.management.base import BaseCommand
from market.jobs import enqueue
from market.models import Product


class Command(BaseCommand):
    help = "为速卖通商品加入采集任务，可用于定时更新"

    def handle(self, *args, **options):
        created = 0
        for product in Product.objects.filter(platform__iexact="AliExpress").iterator():
            _, added = enqueue(product)
            created += added
        self.stdout.write(f"新增 {created} 个任务（已有进行中的任务不会重复加入）。")
