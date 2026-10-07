import csv
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import OuterRef, Q, Subquery
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from .forms import ImportForm, ProductForm, ProfitForm
from .importing import COLUMNS, import_csv, safe_csv_cell
from .jobs import enqueue
from .models import CollectionJob, Product, Snapshot


def filtered_products(request):
    latest = Snapshot.objects.filter(product=OuterRef("pk"))
    products = Product.objects.annotate(
        latest_price=Subquery(latest.values("price")[:1]), latest_currency=Subquery(latest.values("currency")[:1]),
        latest_sales=Subquery(latest.values("sales")[:1]), latest_source=Subquery(latest.values("source")[:1]),
        latest_time=Subquery(latest.values("observed_at")[:1]))
    query = request.GET.get("q", "").strip()[:200]
    if query:
        products = products.filter(Q(title__icontains=query) | Q(shop__icontains=query))
    platform = request.GET.get("platform", "")
    currency = request.GET.get("currency", "")
    if platform:
        products = products.filter(platform=platform)
    if currency:
        products = products.filter(latest_currency=currency)
    return products


@login_required
def dashboard(request):
    products = filtered_products(request)
    page = Paginator(products, 20).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "market/dashboard.html", {
        "page": page, "query_string": params.urlencode(),
        "total": Product.objects.count(), "snapshot_count": Snapshot.objects.count(),
        "active_jobs": CollectionJob.objects.filter(status__in=["queued", "running"]).count(),
        "failed_jobs": CollectionJob.objects.filter(status="failed").count(),
        "platforms": Product.objects.order_by("platform").values_list("platform", flat=True).distinct(),
        "currencies": Snapshot.objects.order_by("currency").values_list("currency", flat=True).distinct(),
    })


@login_required
def product_edit(request, pk=None):
    product = get_object_or_404(Product, pk=pk) if pk else None
    form = ProductForm(request.POST if request.method == "POST" else None, instance=product)
    if request.method == "POST" and form.is_valid():
        product = form.save()
        messages.success(request, "商品已保存。")
        return redirect("product_detail", pk=product.pk)
    return render(request, "market/form.html", {"form": form, "heading": "编辑商品" if product else "添加商品"})


@login_required
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    currencies = list(product.snapshots.order_by("currency").values_list("currency", flat=True).distinct())
    latest = product.snapshots.first()
    currency = request.GET.get("currency")
    if currency not in currencies:
        currency = latest.currency if latest else None
    selected = product.snapshots.filter(currency=currency)
    # 图表限制最近 500 点；保留全部数据库历史，导出不受此限制。
    points = list(selected[:500])[::-1]
    chart = {"dates": [p.observed_at.isoformat() for p in points], "prices": [str(p.price) for p in points],
             "sources": [p.get_source_display() for p in points]}
    change = None
    if len(points) >= 2 and points[0].price != 0:
        change = ((points[-1].price - points[0].price) / points[0].price * 100).quantize(Decimal("0.01"))
    return render(request, "market/detail.html", {"product": product, "latest": latest, "currencies": currencies,
        "currency": currency, "chart": chart, "change": change, "chart_count": len(points),
        "snapshots": Paginator(selected, 20).get_page(request.GET.get("page")), "jobs": product.jobs.all()[:10],
        "has_active_job": product.jobs.filter(status__in=["queued", "running"]).exists()})


@login_required
@require_POST
def collect_product(request, pk):
    product = get_object_or_404(Product, pk=pk)
    _, created = enqueue(product)
    messages.success(request, "已加入采集队列。请确认采集进程正在运行。" if created else "该商品已有等待或执行中的任务。")
    return redirect("product_detail", pk=pk)


@login_required
def job_status(request, pk):
    product = get_object_or_404(Product, pk=pk)
    return JsonResponse({"active": product.jobs.filter(status__in=["queued", "running"]).exists()})


@login_required
def csv_import(request):
    form = ImportForm(request.POST if request.method == "POST" else None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            created, updated = import_csv(form.cleaned_data["file"].read())
        except ValidationError as exc:
            form.add_error("file", exc)
        else:
            messages.success(request, f"导入完成：新增 {created} 条快照，更新 {updated} 条已有快照。")
            return redirect("dashboard")
    return render(request, "market/import.html", {"form": form})


@login_required
def csv_export(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="shophot-snapshots.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(COLUMNS)
    rows = Snapshot.objects.filter(product__in=filtered_products(request).values("pk")).select_related("product")
    for item in rows.iterator():
        writer.writerow([safe_csv_cell(item.product.title), item.product.url, safe_csv_cell(item.product.platform),
                         safe_csv_cell(item.product.shop), item.price, item.currency,
                         "" if item.sales is None else item.sales, item.observed_at.isoformat(), item.source])
    return response


@login_required
def csv_template(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="shophot-template.csv"'
    response.write("\ufeff")
    csv.writer(response).writerow(COLUMNS)
    return response


@login_required
def profit(request):
    form = ProfitForm(request.POST if request.method == "POST" else None)
    result = None
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        revenue = data["selling_price"] * data["exchange_rate"]
        fee = revenue * data["fee_rate"] / 100
        net = revenue - fee - data["cost"] - data["shipping"] - data["other_cost"]
        result = {"revenue": revenue.quantize(Decimal("0.01")), "fee": fee.quantize(Decimal("0.01")),
                  "net": net.quantize(Decimal("0.01")),
                  "margin": (net / revenue * 100).quantize(Decimal("0.01")) if revenue else None}
    return render(request, "market/profit.html", {"form": form, "result": result})
