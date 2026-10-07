"""商品身份与历史快照分开保存；价格变化不会覆盖旧记录。"""
from django.db import models
from django.db.models import Q


class Product(models.Model):
    title = models.CharField("商品名称", max_length=300)
    url = models.URLField("商品链接", unique=True, max_length=500)
    platform = models.CharField("平台", max_length=40, default="AliExpress")
    shop = models.CharField("店铺", max_length=200, blank=True)
    notes = models.TextField("备注", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return self.title


class Snapshot(models.Model):
    class Source(models.TextChoices):
        CSV = "csv", "CSV 导入"
        WEB = "web", "网页采集"
        DEMO = "demo", "演示数据"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="snapshots")
    price = models.DecimalField("价格", max_digits=12, decimal_places=2)
    currency = models.CharField("币种", max_length=3)
    sales = models.PositiveIntegerField("销量（来源提供时）", null=True, blank=True)
    observed_at = models.DateTimeField("观测时间")
    source = models.CharField(max_length=10, choices=Source.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-observed_at", "-pk"]
        constraints = [models.CheckConstraint(condition=Q(price__gte=0), name="snapshot_nonnegative_price"),
                       models.UniqueConstraint(fields=["product", "observed_at", "source"], name="unique_observation")]
        indexes = [models.Index(fields=["product", "observed_at"])]


class CollectionJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "等待采集"
        RUNNING = "running", "采集中"
        SUCCEEDED = "succeeded", "采集成功"
        FAILED = "failed", "采集失败"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="jobs")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED)
    message = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [models.UniqueConstraint(fields=["product"], condition=Q(status__in=["queued", "running"]),
                                               name="one_active_job_per_product")]
