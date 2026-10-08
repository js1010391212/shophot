"""商品身份与历史快照分开保存；价格变化不会覆盖旧记录。"""
from django.db import models
from django.db.models import Q
from django.conf import settings


class ShippingRate(models.Model):
    """账号自己的物流报价；公开参考价在独立版本化目录中维护。"""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='shipping_rates')
    name = models.CharField('报价名称', max_length=120)
    carrier = models.CharField('承运商 / 货代', max_length=80)
    origin = models.CharField('始发国家 / 地区', max_length=2)
    destination = models.CharField('目的国家 / 地区', max_length=2)
    currency = models.CharField('报价币种', max_length=3)
    method = models.CharField('计费方式', max_length=12, choices=[('per_kg', '每公斤 + 每票'), ('first_step', '首重 + 续重')])
    min_weight = models.DecimalField('最低计费重（kg）', max_digits=8, decimal_places=3)
    max_weight = models.DecimalField('最高计费重（kg）', max_digits=8, decimal_places=3)
    step_weight = models.DecimalField('进位 / 续重单位（kg）', max_digits=8, decimal_places=3)
    per_kg = models.DecimalField('每公斤价格', max_digits=12, decimal_places=2, null=True, blank=True)
    first_weight = models.DecimalField('首重（kg）', max_digits=8, decimal_places=3, null=True, blank=True)
    first_price = models.DecimalField('首重价格', max_digits=12, decimal_places=2, null=True, blank=True)
    step_price = models.DecimalField('每续重单位价格', max_digits=12, decimal_places=2, null=True, blank=True)
    fixed_fee = models.DecimalField('每票固定费', max_digits=12, decimal_places=2)
    fuel_basis = models.CharField('燃油费计费基数', max_length=12, choices=[('freight', '仅运输运价'), ('subtotal', '运输运价 + 每票固定费')])
    volume_divisor = models.PositiveIntegerField('体积重系数（cm³/kg）', null=True, blank=True)
    effective_from = models.DateField('生效日期')
    effective_until = models.DateField('失效日期', null=True, blank=True)
    source_url = models.URLField('来源链接', max_length=1000, blank=True)
    notes = models.CharField('货物 / 地区条件与费用说明', max_length=500, blank=True)
    source = models.CharField(max_length=10, choices=[('manual', '手动报价'), ('import', '表格导入')])
    fingerprint = models.CharField(max_length=64)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [
            models.UniqueConstraint(fields=['owner', 'fingerprint'], name='unique_owner_shipping_rate'),
            models.CheckConstraint(condition=Q(min_weight__gt=0, max_weight__gte=models.F('min_weight'), step_weight__gt=0, fixed_fee__gte=0), name='shipping_valid_weights_fee'),
            models.CheckConstraint(condition=Q(method='per_kg', per_kg__gte=0, per_kg__isnull=False) | Q(method='first_step', first_weight__gt=0, first_weight__isnull=False, first_price__gte=0, first_price__isnull=False, step_price__gte=0, step_price__isnull=False), name='shipping_valid_rate_method'),
        ]

    def __str__(self):
        return self.name


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


class PublicSnapshotManager(models.Manager):
    """历史公共入口默认排除账号私有的浏览器观测。"""

    def get_queryset(self):
        return super().get_queryset().exclude(source="browser")


class Snapshot(models.Model):
    class Source(models.TextChoices):
        CSV = "csv", "CSV 导入"
        WEB = "web", "网页采集"
        DEMO = "demo", "演示数据"
        MANUAL = "manual", "手动记录公开页面"
        BROWSER = "browser", "浏览器主动观测"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="snapshots")
    price = models.DecimalField("价格", max_digits=12, decimal_places=2)
    currency = models.CharField("币种", max_length=3)
    sales = models.PositiveIntegerField("销量（来源提供时）", null=True, blank=True)
    rating = models.DecimalField("公开评分（5 分制）", max_digits=3, decimal_places=2, null=True, blank=True)
    review_count = models.PositiveIntegerField("公开评价数", null=True, blank=True)
    context = models.CharField("报价条件 / 规格", max_length=300, blank=True)
    observed_at = models.DateTimeField("观测时间")
    source = models.CharField(max_length=10, choices=Source.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    capture_id = models.UUIDField(null=True, blank=True)
    capture_data = models.JSONField(default=dict, blank=True)
    objects = PublicSnapshotManager()
    all_objects = models.Manager()

    class Meta:
        default_manager_name = "objects"
        base_manager_name = "all_objects"
        ordering = ["-observed_at", "-pk"]
        constraints = [models.CheckConstraint(condition=Q(price__gte=0), name="snapshot_nonnegative_price"),
                       models.CheckConstraint(condition=Q(rating__isnull=True) | Q(rating__gte=0, rating__lte=5), name="rating_zero_to_five"),
                       models.UniqueConstraint(fields=["product", "observed_at", "source"], condition=~Q(source="browser"), name="unique_observation"),
                       models.UniqueConstraint(fields=["owner", "capture_id"], condition=Q(source="browser"), name="unique_browser_capture"),
                       models.CheckConstraint(condition=(Q(source="browser", owner__isnull=False, capture_id__isnull=False) | (~Q(source="browser") & Q(owner__isnull=True, capture_id__isnull=True))), name="snapshot_capture_ownership")]
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


class StoreDiscovery(models.Model):
    analyze_prices = models.BooleanField(default=False)
    url = models.URLField('Shopify 店铺首页', max_length=500)
    status = models.CharField(max_length=12, choices=CollectionJob.Status.choices, default='queued')
    products = models.JSONField(default=list)
    limited = models.BooleanField(default=False)
    message = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [models.UniqueConstraint(fields=['url'], condition=Q(status__in=['queued', 'running']), name='one_active_store_discovery')]


class StorePriceJob(models.Model):
    indices = models.JSONField(default=list)
    discovery = models.ForeignKey(StoreDiscovery, on_delete=models.CASCADE, related_name='price_jobs')
    status = models.CharField(max_length=12, choices=CollectionJob.Status.choices, default='queued')
    processed = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    message = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [models.UniqueConstraint(fields=['discovery'], condition=Q(status__in=['queued', 'running']),
                                               name='one_active_catalog_price_job')]


class CatalogPriceObservation(models.Model):
    quote_scope = models.JSONField(default=dict, blank=True)
    discovery = models.ForeignKey(StoreDiscovery, on_delete=models.CASCADE, related_name='price_observations')
    job = models.ForeignKey(StorePriceJob, on_delete=models.CASCADE, related_name='observations')
    url = models.URLField(max_length=500)
    title = models.CharField(max_length=300)
    price_low = models.DecimalField(max_digits=12, decimal_places=2)
    price_high = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    availability = models.CharField(max_length=40, blank=True)
    observed_at = models.DateTimeField()

    class Meta:
        ordering = ['-observed_at', '-pk']
        constraints = [models.UniqueConstraint(fields=['job', 'url'], name='one_catalog_quote_per_job'),
            models.CheckConstraint(condition=Q(price_low__gte=0) & Q(price_high__gte=models.F('price_low')), name='catalog_quote_valid_range')]
        indexes = [models.Index(fields=['discovery', 'url', 'observed_at'])]


class CatalogCandidate(models.Model):
    class Stage(models.TextChoices):
        RESEARCH = 'research', '研究中'
        PRIORITY = 'priority', '重点关注'
        PAUSED = 'paused', '暂不考虑'

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='catalog_candidates')
    url = models.URLField(max_length=500)
    store_url = models.URLField(max_length=500)
    saved_item = models.JSONField(default=dict)
    discovery = models.ForeignKey(StoreDiscovery, null=True, on_delete=models.SET_NULL)
    notes = models.TextField('选品备注', blank=True, max_length=2000)
    stage = models.CharField('研究状态', max_length=12, choices=Stage.choices, default=Stage.RESEARCH)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-pk']
        constraints = [models.UniqueConstraint(fields=['owner', 'url'], name='one_candidate_per_owner_url')]


class PriceMonitor(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    url = models.URLField(max_length=500)
    store_url = models.URLField(max_length=500)
    title = models.CharField(max_length=300)
    interval_hours = models.PositiveSmallIntegerField(default=24, choices=[(6, '每 6 小时'), (12, '每 12 小时'), (24, '每天一次')])
    active = models.BooleanField(default=True)
    next_run_at = models.DateTimeField()
    pending_job = models.ForeignKey(StorePriceJob, null=True, blank=True, on_delete=models.SET_NULL)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=12, blank=True)
    message = models.CharField(max_length=500, blank=True)
    failures = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [models.UniqueConstraint(fields=['owner', 'url'], name='one_monitor_per_owner_url'),
                       models.CheckConstraint(condition=Q(interval_hours__in=[6, 12, 24]), name='monitor_safe_interval')]
        indexes = [models.Index(fields=['active', 'next_run_at'])]


class ProductReviewBatch(models.Model):
    """一份公开页面观测中的评论样本，价格与来源通过快照追溯。"""
    snapshot = models.OneToOneField(Snapshot, on_delete=models.CASCADE, related_name='review_batch')
    source_url = models.URLField(max_length=500)
    file_fingerprint = models.CharField(max_length=16)
    samples = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-snapshot__observed_at', '-pk']
