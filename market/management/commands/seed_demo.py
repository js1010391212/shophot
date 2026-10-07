"""可重复加载演示商品，与真实采集数据通过 source 字段区分。"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from django.core.management.base import BaseCommand
from market.models import Product, Snapshot


class Command(BaseCommand):
    help = "加载明确标记的虚构演示数据，不创建账号、不执行外网采集"

    def handle(self, *args, **options):
        for index, (name, shop, price) in enumerate([
            ("演示 · 无线降噪耳机", "演示数码店", "29.90"),
            ("演示 · 便携咖啡杯", "演示生活店", "12.50"),
            ("演示 · USB-C 充电线", "演示配件店", "4.80"),
        ], start=1):
            product, _ = Product.objects.get_or_create(url=f"https://example.com/demo/{index}", defaults={
                "title": name, "shop": shop, "platform": "Demo", "notes": "虚构数据，仅用于体验网站；不可用于市场判断。"})
            for day in range(7):
                Snapshot.objects.get_or_create(product=product, source=Snapshot.Source.DEMO,
                    observed_at=datetime(2026, 10, 1, tzinfo=timezone.utc) + timedelta(days=day),
                    defaults={"price": Decimal(price) + Decimal(6 - day) / 10,
                              "currency": "USD", "sales": index * 20 + day * 3})
        self.stdout.write(self.style.SUCCESS("演示数据已加载，重复执行不会增加重复记录。"))
