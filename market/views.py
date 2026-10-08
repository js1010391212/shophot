import csv
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Max, Min, OuterRef, Q, Subquery
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from .forms import AnalyzeForm, CompareForm, ImportForm, ObservationForm, ProductForm, ProfitForm, StoreDiscoveryForm
from .importing import COLUMNS, import_csv, safe_csv_cell
from .jobs import enqueue
from .models import CollectionJob, Product, Snapshot, StoreDiscovery, CatalogCandidate


def filtered_products(request):
    latest = Snapshot.objects.filter(product=OuterRef("pk"))
    products = Product.objects.annotate(
        latest_price=Subquery(latest.values("price")[:1]), latest_currency=Subquery(latest.values("currency")[:1]),
        latest_sales=Subquery(latest.values("sales")[:1]), latest_source=Subquery(latest.values("source")[:1]),
        latest_time=Subquery(latest.values("observed_at")[:1]))
    query = request.GET.get("q", "").strip()[:200]
    if query:
        products = products.filter(Q(title__icontains=query) | Q(shop__icontains=query) | Q(url__icontains=query))
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
    from .catalog_research import latest_catalogs
    recent_scans=list(StoreDiscovery.objects.filter(pk=Subquery(StoreDiscovery.objects.filter(url=OuterRef('url')).order_by('-created_at','-pk').values('pk')[:1]))[:6])
    for scan in recent_scans:
        scan.priced_count=sum(bool(p.get('price_observed_at')) for p in scan.products)
    return render(request, "market/dashboard.html", {
        'recent_scans':recent_scans,'catalog_count':sum(len(s.products) for s in latest_catalogs()),
        'candidate_count':CatalogCandidate.objects.filter(owner=request.user,active=True).count(),
        "page": page, "query_string": params.urlencode(), "analyze_form": AnalyzeForm(allow_store=True),
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
             "sources": [p.get_source_display() for p in points],
             "timezone": timezone.get_current_timezone_name()}
    change = None
    if len(points) >= 2 and points[0].price != 0:
        change = ((points[-1].price - points[0].price) / points[0].price * 100).quantize(Decimal("0.01"))
    stats = selected.aggregate(lowest=Min("price"), highest=Max("price"), count=Count("pk"))
    return render(request, "market/detail.html", {"analysis": stats, "product": product, "latest": latest, "currencies": currencies,
        "currency": currency, "chart": chart, "change": change, "chart_count": len(points),
        "snapshots": Paginator(selected, 20).get_page(request.GET.get("page")), "jobs": product.jobs.all()[:10],
        "has_active_job": product.jobs.filter(status__in=["queued", "running"]).exists()})


@login_required
@require_POST
def collect_product(request, pk):
    product = get_object_or_404(Product, pk=pk)
    validation = AnalyzeForm({'url': product.url, 'platform': product.platform})
    if not validation.is_valid():
        messages.error(request, "该商品不能自动采集：请在编辑页面确认平台与完整商品链接；其他平台请使用 CSV 或手动记录。")
        return redirect("product_detail", pk=pk)
    _, created = enqueue(product)
    messages.success(request, "已加入采集队列。请确认采集进程正在运行。" if created else "该商品已有等待或执行中的任务。")
    return redirect('product_analysis' if request.POST.get('workflow') == '1' else 'product_detail',pk=pk)


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
                         "" if item.sales is None else item.sales, item.observed_at.isoformat(), item.source,
                         "" if item.rating is None else item.rating,
                         "" if item.review_count is None else item.review_count, safe_csv_cell(item.context)])
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
    from .profit import calculate_profit
    from .shipping_forms import LogisticsProfitForm, ShippingEstimateForm
    initial = {}
    reference = None
    if request.method == 'GET' and request.GET.get('product', '').isdigit():
        reference = get_object_or_404(Product, pk=request.GET['product'])
        snapshot = reference.snapshots.first()
        if snapshot:
            initial = {'selling_price': snapshot.price, 'sale_currency': snapshot.currency}
        else:
            reference = None
    if request.method == 'GET' and request.GET.get('shipping_mode') == 'quote':
        initial.update({name: request.GET[name] for name in ShippingEstimateForm.base_fields if name in request.GET})
        initial['shipping_mode'] = 'quote'
    form = LogisticsProfitForm(request.POST if request.method == "POST" else None, initial=initial, user=request.user)
    result = calculate_profit(form.cleaned_data) if request.method == "POST" and form.is_valid() else None
    return render(request, "market/profit.html", {"form": form, "result": result, "reference": reference,
        "shipping_result": form.shipping_estimate, "quote_metadata": {key: q.metadata() for key, q in form.shipping_form.quotes.items()}})


@login_required
def observation_add(request, pk):
    import logging
    product = get_object_or_404(Product, pk=pk)
    form = ObservationForm(request.POST if request.method == "POST" else None,
                           initial={"observed_at": timezone.localtime(timezone.now()).replace(microsecond=0)})
    if request.method == "POST" and form.is_valid():
        _, created = Snapshot.objects.update_or_create(
            product=product, observed_at=form.cleaned_data["observed_at"], source=Snapshot.Source.MANUAL,
            defaults={key: value for key, value in form.cleaned_data.items() if key != "observed_at"})
        logging.getLogger(__name__).info("手动观测保存 product=%s created=%s", product.pk, created)
        messages.success(request, "公开页面观测已保存。" if created else "同一时间的手动观测已更新。")
        return redirect("product_detail", pk=pk)
    return render(request, "market/observation.html", {"form": form, "product": product})


@login_required
def compare(request):
    from datetime import timedelta
    form = CompareForm(request.GET if request.GET else None)
    rows = []
    chart = {"series": [], "timezone": timezone.get_current_timezone_name()}
    currency = None
    if form.is_bound and form.is_valid():
        currency = form.cleaned_data["currency"]
        days = form.cleaned_data["days"]
        cutoff = timezone.now() - timedelta(days=days) if days else None
        for product in form.cleaned_data["products"]:
            observations = product.snapshots.filter(currency=currency)
            if cutoff:
                observations = observations.filter(observed_at__gte=cutoff)
            # 限制每条曲线 500 点，但起点变化率使用整个筛选窗口的首条真实记录。
            latest = observations.first()
            earliest = observations.order_by("observed_at", "pk").first()
            points = list(observations[:500])[::-1]
            change = None
            if earliest and latest and earliest.pk != latest.pk and earliest.price != 0:
                change = ((latest.price - earliest.price) / earliest.price * 100).quantize(Decimal("0.01"))
            rows.append({"product": product, "latest": latest, "change": change})
            if points:
                chart["series"].append({"name": f"{product.title} · #{product.pk}", "product_id": product.pk, "points": [[p.observed_at.isoformat(), str(p.price)] for p in points]})
    return render(request, "market/compare.html", {"form": form, "rows": rows, "chart": chart, "currency": currency})


@login_required
@require_POST
def analyze_competitor(request):
    from urllib.parse import urlsplit
    form = AnalyzeForm(request.POST, allow_store=True)
    if form.is_valid():
        url = form.cleaned_data["url"]
        if form.cleaned_data['platform'] == 'AliExpress' and '?sku_id=' in url:
            product,_=Product.objects.get_or_create(url=url,defaults={'title':'待识别竞品 · '+urlsplit(url).path.rsplit('/',1)[-1],'platform':'AliExpress'})
            if product.platform != 'AliExpress':
                messages.error(request,'已有商品的平台与链接不一致，请先核对资料。')
                return redirect('product_detail',pk=product.pk)
            messages.info(request,'已保留速卖通规格编号，请导入已保存的商品页面；未创建自动采集任务。')
            return redirect('page_import',pk=product.pk)
        if form.cleaned_data['platform'] == 'OTTO':
            product,_=Product.objects.get_or_create(url=url,defaults={'title':'待识别竞品 · '+urlsplit(url).path.rsplit('/',2)[-2][:80],'platform':'OTTO'})
            if product.platform != 'OTTO':
                messages.error(request,'该链接已保存为其他平台，请先核对商品资料。')
                return redirect('product_detail',pk=product.pk)
            messages.info(request,'已建立 OTTO 研究入口。自动采集遇到安全验证，未创建任务；请导入正常保存的页面或手动记录。')
            return redirect('otto_import',pk=product.pk)
        if form.cleaned_data['platform'] == 'Shopify' and urlsplit(url).path in ('', '/'):
            from .workflows import start_store_analysis
            scan=start_store_analysis(url)
            if scan.status == 'succeeded':
                messages.info(request,'已打开保存的店铺报告；数据时间可在报告中查看，并可继续采集。')
            return redirect('store_analysis',pk=scan.pk)
        if form.cleaned_data['platform'] == 'Shopify':
            from .workflows import saved_catalog_product
            existing=saved_catalog_product(url)
            if existing:
                messages.info(request,'已打开保存的商品报告；可在报告中更新数据。')
                return redirect('catalog_detail',pk=existing[0],index=existing[1])
        product, created = Product.objects.get_or_create(url=url, defaults={
            "title": "待识别竞品 · " + urlsplit(url).path.rsplit("/", 1)[-1][:80], "platform": form.cleaned_data.get("platform") or "AliExpress",
            "shop": urlsplit(url).hostname if form.cleaned_data.get("platform") == "Shopify" else ""})
        selected_platform = form.cleaned_data.get("platform") or "AliExpress"
        if product.platform != selected_platform:
            product.platform = selected_platform
            if selected_platform == 'Shopify' and not product.shop:
                product.shop = urlsplit(url).hostname
            product.save(update_fields=['platform', 'shop'])
        _, queued = enqueue(product)
        messages.success(request, "已开始分析，正在等待公开数据采集。" if queued else "该竞品正在采集中，请等待结果。")
        return redirect("product_analysis", pk=product.pk)
    return render(request, "market/analyze.html", {"form": form}, status=400)


@login_required
def stores(request):
    """仅汇总已跟踪商品，不把样本当作店铺全部商品或销售额。"""
    from urllib.parse import urlsplit
    groups = {}
    query = request.GET.get('q', '').strip()[:200].lower()
    for product in filtered_products(request):
        domain = urlsplit(product.url).hostname or '未知域名'
        key = (product.platform, domain if product.platform.lower() == 'shopify' else (product.shop or domain))
        if query and query not in (key[1] + ' ' + domain).lower():
            continue
        row = groups.setdefault(key, {'name': key[1], 'domain': domain, 'platform': product.platform,
                                     'count': 0, 'observed': 0, 'latest': None, 'products': []})
        row['count'] += 1
        row['observed'] += int(product.latest_time is not None)
        if product.latest_time and (row['latest'] is None or product.latest_time > row['latest']):
            row['latest'] = product.latest_time
        if len(row['products']) < 4:
            row['products'].append(product)
    scans = list(StoreDiscovery.objects.filter(pk=Subquery(StoreDiscovery.objects.filter(url=OuterRef('url')).order_by('-created_at', '-pk').values('pk')[:1])).prefetch_related('price_jobs')[:8])
    for scan in scans:
        scan.recent_quotes = scan.price_observations.all()[:10]
        scan.priced_count = sum(bool(p.get('price_observed_at')) for p in scan.products)
        scan.pending_count = sum(not p.get('price_observed_at') and not p.get('price_attempted_at') for p in scan.products)
        scan.error_count = sum(bool(p.get('price_error')) for p in scan.products)
    return render(request, 'market/stores.html', {'stores': list(groups.values()), 'query': request.GET.get('q', ''),
                                                'store_count': len(groups), 'discovery_form': StoreDiscoveryForm(),
                                                'discoveries': scans})


@login_required
def collection_center(request):
    status = request.GET.get('status', '')
    jobs = CollectionJob.objects.select_related('product')
    if status in CollectionJob.Status.values:
        jobs = jobs.filter(status=status)
    counts = {value: CollectionJob.objects.filter(status=value).count() for value in CollectionJob.Status.values}
    return render(request, 'market/collections.html', {'jobs': Paginator(jobs, 20).get_page(request.GET.get('page')),
        'counts': counts, 'statuses': CollectionJob.Status.choices, 'status': status})


@login_required
@require_POST
def discover_store(request):
    form = StoreDiscoveryForm(request.POST)
    if form.is_valid():
        if request.POST.get('workflow') == '1':
            from .workflows import start_store_analysis
            return redirect('store_analysis',pk=start_store_analysis(form.cleaned_data['url'],refresh=True).pk)
        return queue_store_discovery(request, form.cleaned_data['url'])
    return render(request, 'market/store_discovery_form.html', {'form': form}, status=400)


def queue_store_discovery(request, url):
    from django.db import IntegrityError, transaction
    try:
        with transaction.atomic():
            StoreDiscovery.objects.create(url=url)
        messages.success(request, '已识别为店铺首页，公开商品目录发现已排队；请稍后刷新查看结果。')
    except IntegrityError:
        messages.info(request, '这个店铺正在发现中，请等待结果。')
    return redirect('stores')


@login_required
@require_POST
def collect_store_prices(request, pk):
    from .models import StorePriceJob
    from django.db import IntegrityError, transaction
    scan = get_object_or_404(StoreDiscovery, pk=pk, status='succeeded')
    if not scan.products:
        messages.error(request, '目录没有商品，无法采集价格。')
        return redirect('store_analysis',pk=pk) if request.POST.get('return_to') == 'report' else redirect('stores')
    mode = request.POST.get('mode', 'next')
    if mode not in ('next', 'remaining', 'refresh', 'retry'):
        return HttpResponse('无效的采集范围。', status=400)
    try:
        with transaction.atomic():
            scan = StoreDiscovery.objects.select_for_update().get(pk=scan.pk)
            if mode == 'refresh':
                indices = list(range(len(scan.products)))[:100]
            elif mode == 'retry':
                indices = [i for i, p in enumerate(scan.products) if p.get('price_error')][:100]
            else:
                indices = [i for i, p in enumerate(scan.products) if not p.get('price_observed_at') and not p.get('price_attempted_at')][:100]
                if mode == 'next':
                    indices = indices[:10]
            if not indices:
                messages.info(request, '此范围没有待采集商品；可选择重新观测已有价格。')
                return redirect('store_analysis',pk=pk) if request.POST.get('return_to') == 'report' else redirect('stores')
            StorePriceJob.objects.create(discovery=scan, indices=indices, total=len(indices))
        messages.success(request, f'{len(indices)} 件商品报价已排队，每批最多 10 件，请稍后刷新查看。')
    except IntegrityError:
        messages.info(request, '这个目录正在采集价格，请等待结果。')
    return redirect('store_analysis',pk=pk) if request.POST.get('return_to') == 'report' else redirect('stores')


@login_required
def keyword_research(request, pk=None):
    from .research import build_research
    from .forms import ResearchFilterForm
    scans = list(StoreDiscovery.objects.filter(status='succeeded').filter(
        pk=Subquery(StoreDiscovery.objects.filter(url=OuterRef('url'), status='succeeded').order_by('-created_at', '-pk').values('pk')[:1]))[:30])
    if pk is None:
        value = request.GET.get('store')
        if value:
            try:
                pk = int(value)
            except ValueError:
                return HttpResponse('无效的店铺编号。', status=400)
        elif scans:
            pk = next((scan.pk for scan in scans if any(p.get('price_observed_at') for p in scan.products)), scans[0].pk)
        else:
            return render(request, 'market/research.html', {'scans': []})
    scan = get_object_or_404(StoreDiscovery, pk=pk, status='succeeded')
    context = build_research(scan)
    form = ResearchFilterForm(request.GET, currencies=context['currencies'])
    if form.is_valid():
        context = build_research(scan, **form.cleaned_data)
    else:
        context.update(products=[], matched_count=0, distribution=[], matched_priced_count=0,
                       tree_data={'name': scan.url, 'children': []})
    params = request.GET.copy()
    params.pop('term', None)
    params.pop('store', None)
    return render(request, 'market/research.html', {**context, 'scan': scan, 'scans': scans,
        'filter_form': form, 'filter_query': params.urlencode(), 'report_job':scan.price_jobs.first(),
        'pending_count':sum(not p.get('price_observed_at') and not p.get('price_attempted_at') for p in scan.products),
        'price_job_active':scan.price_jobs.filter(status__in=['queued','running']).exists()})


@login_required
def catalog_detail(request, pk, index):
    from django.http import Http404
    from .research import title_terms
    from .review_analysis import analyze_reviews
    scan = get_object_or_404(StoreDiscovery, pk=pk, status='succeeded')
    if index >= len(scan.products):
        raise Http404('目录中没有此商品。')
    item = scan.products[index]
    from .candidates import candidate_url
    try:
        candidate=CatalogCandidate.objects.filter(owner=request.user,url=candidate_url(item['url']),active=True).first()
    except ValidationError:
        candidate=None
    job = next((job for job in scan.price_jobs.all()[:20]
                if index in (job.indices or list(range(min(len(scan.products), 10))))), None)
    context = {'scan': scan, 'item': item, 'index': index, 'job': job, 'candidate':candidate, 'review_analysis':analyze_reviews(item),
        'title': item.get('price_title') or item.get('title'),
        'terms': sorted(title_terms(item.get('price_title') or item.get('title') or '', scan.url)),
        'has_rating': item.get('rating') not in (None, ''),
        'has_review_count': item.get('review_count') is not None,
        'has_rating_count': item.get('rating_count') is not None,
        'quotes': scan.price_observations.filter(url=item['url'])[:20]}
    return render(request, 'market/catalog_detail.html', context)


@login_required
@require_POST
def refresh_catalog_product(request, pk, index):
    from django.db import IntegrityError, transaction
    from django.http import Http404
    from .models import StorePriceJob
    scan = get_object_or_404(StoreDiscovery, pk=pk, status='succeeded')
    try:
        with transaction.atomic():
            scan = StoreDiscovery.objects.select_for_update().get(pk=scan.pk)
            if index >= len(scan.products):
                raise Http404('目录中没有此商品。')
            StorePriceJob.objects.create(discovery=scan, indices=[index], total=1)
        messages.success(request, '当前商品已排队更新：报价、图片、描述、公开规格及可取得的商品评价。请稍后刷新页面。')
    except IntegrityError:
        messages.info(request, '这个店铺已有采集任务，请等它完成后再更新。')
    return redirect('catalog_detail', pk=pk, index=index)


@login_required
def catalog_market(request):
    from .catalog_research import latest_catalogs, catalog_rows
    from .research import price_distribution
    from .forms import ResearchFilterForm
    scans=latest_catalogs()
    all_rows=catalog_rows(scans)
    currencies=sorted({row['currency'] for row in all_rows if row['valid_quote'] and row.get('currency')})
    form=ResearchFilterForm(request.GET,currencies=currencies)
    rows=catalog_rows(scans,form.cleaned_data) if form.is_valid() else []
    from .candidates import candidate_url
    saved=set(CatalogCandidate.objects.filter(owner=request.user,active=True).values_list('url',flat=True))
    for row in rows:
        try: row['is_candidate']=candidate_url(row['url']) in saved
        except ValidationError: row['is_candidate']=False
    params=request.GET.copy();params.pop('page',None)
    return render(request,'market/catalog_market.html',{'filter_form':form,'page':Paginator(rows,50).get_page(request.GET.get('page')),
        'query_string':params.urlencode(),'store_count':len(scans),'total_count':len(all_rows),'matched_count':len(rows),
        'priced_count':sum(row['valid_quote'] for row in rows),'distribution':price_distribution(rows)})


@login_required
@require_POST
def candidate_add(request, pk, index):
    from .candidates import save_candidate
    scan=get_object_or_404(StoreDiscovery,pk=pk,status='succeeded')
    try:
        candidate, created=save_candidate(request.user,scan,index)
    except ValidationError as exc:
        return HttpResponse(' '.join(exc.messages),status=400)
    messages.success(request,'已加入候选清单。' if created else '商品已在候选清单中，原有备注已保留。')
    return redirect('candidates')


@login_required
def candidates(request):
    from .candidates import candidate_rows
    archived=request.GET.get('archived') == '1'
    query=request.GET.get('q','').strip()[:200]
    stage=request.GET.get('stage','')
    objects=CatalogCandidate.objects.filter(owner=request.user,active=not archived).select_related('discovery')
    if query:
        objects=objects.filter(Q(notes__icontains=query)|Q(url__icontains=query)|Q(saved_item__title__icontains=query)|Q(saved_item__price_title__icontains=query))
    if stage in CatalogCandidate.Stage.values:
        objects=objects.filter(stage=stage)
    elif stage:
        return HttpResponse('无效的研究状态。',status=400)
    page=Paginator(objects,30).get_page(request.GET.get('page'))
    params=request.GET.copy();params.pop('page',None)
    return render(request,'market/candidates.html',{'products':candidate_rows(page.object_list),'page':page,
        'archived':archived,'query':query,'stage':stage,'stages':CatalogCandidate.Stage.choices,'query_string':params.urlencode()})


@login_required
def candidate_edit(request, pk):
    from .forms import CandidateForm
    candidate=get_object_or_404(CatalogCandidate,pk=pk,owner=request.user)
    form=CandidateForm(request.POST if request.method == 'POST' else None,instance=candidate)
    if request.method == 'POST' and form.is_valid():
        form.save(commit=False).save(update_fields=['stage','notes','updated_at'])
        messages.success(request,'研究状态和备注已保存。')
        return redirect('candidates')
    return render(request,'market/candidate_edit.html',{'candidate':candidate,'form':form})


@login_required
@require_POST
def candidate_archive(request, pk):
    candidate=get_object_or_404(CatalogCandidate,pk=pk,owner=request.user)
    candidate.active=False
    candidate.save(update_fields=['active','updated_at'])
    messages.success(request,'已移出清单，可以在已移出商品中恢复。')
    return redirect('candidates')


@login_required
@require_POST
def candidate_restore(request, pk):
    candidate=get_object_or_404(CatalogCandidate,pk=pk,owner=request.user)
    candidate.active=True
    candidate.save(update_fields=['active','updated_at'])
    messages.success(request,'商品已恢复，原有备注和研究状态已保留。')
    return redirect('candidates')


@login_required
def candidate_compare(request):
    from .candidates import candidate_rows
    from .catalog_research import comparison_rows
    values=request.GET.getlist('items')
    if not 2 <= len(values) <= 8 or len(set(values)) != len(values) or any(not value.isascii() or not value.isdigit() or value.startswith('0') or len(value)>10 for value in values):
        return render(request,'market/catalog_compare.html',{'selection_error':'请选择 2–8 件不同候选商品。'},status=400)
    selected=CatalogCandidate.objects.filter(owner=request.user,active=True,pk__in=values).select_related('discovery')
    if len(selected) != len(values):
        return render(request,'market/catalog_compare.html',{'selection_error':'选择的候选商品不可用，请重新选择。'},status=400)
    resolved={str(row['candidate'].pk):row for row in candidate_rows(selected)}
    if any(not resolved[value]['from_latest'] for value in values):
        return render(request,'market/catalog_compare.html',{'selection_error':'部分候选商品不在最新目录中，请先更新店铺数据再对比。'},status=400)
    try:
        rows=comparison_rows([resolved[value]['selection_id'] for value in values])
    except ValidationError as exc:
        return render(request,'market/catalog_compare.html',{'selection_error':' '.join(exc.messages)},status=400)
    return render(request,'market/catalog_compare.html',{'products':rows,'currency':rows[0]['currency'],
        'chart_data':{'names':[row['display_title'] for row in rows],
                      'low':[str(row['_low']) for row in rows],'high':[str(row['_high']) for row in rows],'currency':rows[0]['currency']}})


@login_required
def catalog_export(request):
    from .catalog_research import latest_catalogs, catalog_rows
    from .forms import ResearchFilterForm
    scans=latest_catalogs()
    all_rows=catalog_rows(scans)
    currencies=sorted({row['currency'] for row in all_rows if row['valid_quote'] and row.get('currency')})
    form=ResearchFilterForm(request.GET,currencies=currencies)
    if not form.is_valid():
        return HttpResponse('筛选条件无效，请返回商品研究修正后再导出。',status=400)
    rows=catalog_rows(scans,form.cleaned_data)
    response=HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition']='attachment; filename="shophot-research.csv"'
    response['Cache-Control']='no-store'
    response.write('\ufeff')
    writer=csv.writer(response)
    writer.writerow(['商品标题','商品链接','店铺','最低公开报价','最高公开报价','币种','公开库存状态',
                     '商品评分（5分制）','公开评价数','有效评论样本数（最多10条）','报价观测时间','最近报价尝试时间',
                     '最近采集错误','目录编号','目录是否截取'])
    scans_by_pk={scan.pk:scan for scan in scans}
    for row in rows:
        writer.writerow([safe_csv_cell(value) for value in [row['display_title'],row['url'],row['store_name'],
            row['_low'] if row['valid_quote'] else '', row['_high'] if row['valid_quote'] else '',
            row.get('currency','') if row['valid_quote'] else '',row['inventory_label'],
            row['_rating'] if row['has_rating'] else '',row['_reviews'] if row['has_reviews'] else '',
            row['review_sample_count'],row.get('price_observed_at',''),row.get('price_attempted_at',''),
            row.get('price_error',''),row['scan_pk'],'是' if scans_by_pk[row['scan_pk']].limited else '否']])
    return response


@login_required
def catalog_compare(request):
    from .catalog_research import comparison_rows
    try:
        rows=comparison_rows(request.GET.getlist('items'))
    except ValidationError as exc:
        return render(request,'market/catalog_compare.html',{'selection_error':' '.join(exc.messages)},status=400)
    return render(request,'market/catalog_compare.html',{'products':rows,'currency':rows[0]['currency'],
        'chart_data':{'names':[row['display_title'] for row in rows],
                      'low':[str(row['_low']) for row in rows], 'high':[str(row['_high']) for row in rows],
                      'currency':rows[0]['currency']}})
