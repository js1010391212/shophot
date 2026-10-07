"""CSV 全量校验后再写入，任何一行错误都会回滚，重复导入不会新增快照。"""
import csv
import io
import logging
from datetime import timezone as datetime_timezone
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from .models import Product, Snapshot
from .validation import clean_count, clean_currency, clean_price, clean_rating, clean_url

logger = logging.getLogger(__name__)
COLUMNS = ["title", "url", "platform", "shop", "price", "currency", "sales", "observed_at", "source", "rating", "review_count", "context"]
REQUIRED = {"title", "url", "price", "currency", "observed_at"}


def import_csv(content):
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValidationError("请使用 UTF-8 编码的 CSV 文件。")
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    # DictReader 首次读取 fieldnames 才解析表头，因此这里也必须捕获 CSV 错误。
    try:
        headers = reader.fieldnames or []
    except csv.Error as exc:
        raise ValidationError("CSV 格式错误，请检查表头字段的引号与长度。") from exc
    if len(headers) != len(set(headers)) or any(not header.strip() for header in headers):
        raise ValidationError("CSV 表头不能有重复或空白字段，请使用下载的模板。")
    missing = REQUIRED - set(headers)
    if missing:
        raise ValidationError("缺少字段：" + ", ".join(sorted(missing)))
    rows = []
    try:
        for line, raw in enumerate(reader, start=2):
            if len(rows) >= 5000:
                raise ValidationError("一次最多导入 5000 行。")
            try:
                if None in raw:
                    raise ValidationError("列数超过表头，请检查引号和分隔符。")
                row = {key: (value or "").strip() for key, value in raw.items()}
                title = row["title"]
                if not title or len(title) > 300:
                    raise ValidationError("商品名称不能为空且不能超过 300 字。")
                platform, shop = row.get("platform") or "AliExpress", row.get("shop", "")
                if len(platform) > 40 or len(shop) > 200:
                    raise ValidationError("平台或店铺名称过长。")
                date = parse_datetime(row["observed_at"])
                if not date:
                    raise ValidationError("观测时间须为 ISO 8601，例如 2026-10-01T10:00:00+08:00。")
                if timezone.is_naive(date):
                    date = timezone.make_aware(date)
                # 提前验证 UTC 可表示范围，防止极端时区使日期在数据库写入时溢出。
                try:
                    date = date.astimezone(datetime_timezone.utc)
                except (OverflowError, ValueError) as exc:
                    raise ValidationError("观测时间超出可保存范围，请检查日期和时区。") from exc
                sales = clean_count(row.get("sales", ""), "销量")
                source = row.get("source") or Snapshot.Source.CSV
                if source not in Snapshot.Source.values:
                    raise ValidationError("source 须为 csv、web、demo 或 manual。")
                context = row.get("context", "")
                if len(context) > 300:
                    raise ValidationError("报价条件不能超过 300 字。")
                rows.append({"title": title, "url": clean_url(row["url"]), "platform": platform, "shop": shop,
                             "price": clean_price(row["price"]), "currency": clean_currency(row["currency"]),
                             "observed_at": date, "sales": sales, "source": source,
                             "rating": clean_rating(row.get("rating", "")),
                             "review_count": clean_count(row.get("review_count", "")), "context": context})
            except (ValidationError, ValueError, OverflowError) as exc:
                message = "; ".join(exc.messages) if isinstance(exc, ValidationError) else "字段格式错误。"
                raise ValidationError(f"第 {line} 行：{message}") from exc
    except csv.Error as exc:
        raise ValidationError("CSV 格式错误，请检查字段引号。") from exc
    if not rows:
        raise ValidationError("CSV 没有数据行。")
    created = updated = 0
    with transaction.atomic():
        for row in rows:
            product, _ = Product.objects.update_or_create(url=row["url"], defaults={
                "title": row["title"], "platform": row["platform"], "shop": row["shop"]})
            _, is_new = Snapshot.objects.update_or_create(
                product=product, observed_at=row["observed_at"], source=row["source"],
                defaults={"price": row["price"], "currency": row["currency"], "sales": row["sales"],
                          "rating": row["rating"], "review_count": row["review_count"], "context": row["context"]})
            created += is_new
            updated += not is_new
    logger.info("CSV 导入完成 rows=%s created=%s updated=%s", len(rows), created, updated)
    return created, updated


def safe_csv_cell(value):
    # 防止标题等用户输入在 Excel 中被当作公式执行。
    value = str(value)
    if value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value
