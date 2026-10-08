"""浏览器主动观测：只读桥接、签名预览、POST确认与账号私有报告。"""
from urllib.parse import parse_qsl

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import RequestDataTooBig, ValidationError
from django.db import transaction
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .browser_capture import parse_capture, sign_preview
from .browser_capture_records import private_groups, save_preview
from .models import Product, Snapshot
from .browser_capture_targets import identify_capture_target as identify_target

MAX_FORM_BYTES = 128 * 1024


@login_required
@require_GET
def download(request):
    from .browser_capture_package import extension_package
    try:
        archive = extension_package()
    except (FileNotFoundError, ValueError):
        return HttpResponse('浏览器扩展资源尚未准备完整，请更新本地 ShopHot 后重试。', status=503)
    return FileResponse(archive, as_attachment=True, filename='shophot-capture-0.1.0.zip',
                        content_type='application/zip')


def start_browser_research(request, url, platform):
    """由首页已校验的POST调用，创建明确入口，不触发HTTP采集。"""
    from urllib.parse import urlsplit
    product, _ = Product.objects.get_or_create(url=url, defaults={
        'platform': platform, 'title': '待识别竞品 · ' + urlsplit(url).path.rsplit('/', 1)[-1],
    })
    if product.platform != platform:
        messages.error(request, '已有商品的平台与链接不一致，请先核对商品资料。')
        return redirect('product_detail', pk=product.pk)
    messages.info(request, '已建立 eBay 研究入口。请在正常商品页选择规格，使用 ShopHot 扩展采集并核对保存。')
    return redirect('browser_report', pk=product.pk)


def _post_fields(request, required):
    if request.content_type != 'application/x-www-form-urlencoded':
        raise ValidationError('请使用普通表单提交观测，不接受该 Content-Type。')
    try:
        declared = int(request.META.get('CONTENT_LENGTH') or 0)
        if declared < 0 or declared > MAX_FORM_BYTES:
            raise ValidationError('表单正文过大，最大128KiB。')
        raw = request.body
        if len(raw) > MAX_FORM_BYTES:
            raise ValidationError('表单正文过大，最大128KiB。')
        pairs = parse_qsl(raw.decode('utf-8'), keep_blank_values=True, encoding='utf-8', errors='strict', max_num_fields=8)
    except (UnicodeError, ValueError, RequestDataTooBig):
        raise ValidationError('表单编码或字段数量无效，请重新采集。')
    fields = {}
    for key, value in pairs:
        if key in fields:
            raise ValidationError('表单包含重复参数，请重新采集。')
        fields[key] = value
    if set(fields) - (required | {'csrfmiddlewaretoken'}) or not required <= fields.keys():
        raise ValidationError('表单字段缺失或包含未允许的参数。')
    return fields


def _error(request, exc):
    return render(request, 'market/browser_capture.html', {'error': ' '.join(exc.messages)}, status=400)


@login_required
@require_http_methods(['GET', 'POST'])
def preview(request):
    if request.method == 'GET':
        return render(request, 'market/browser_capture.html', {'bridge_ready': True})
    try:
        fields = _post_fields(request, {'target_url', 'capture'})
        platform, target = identify_target(fields['target_url'])
        try:
            raw = fields['capture'].encode('utf-8')
        except UnicodeError:
            raise ValidationError('浏览器观测UTF-8编码无效。')
        capture = parse_capture(raw, target)
        with transaction.atomic():
            product, _ = Product.objects.get_or_create(url=target, defaults={
                'platform': platform, 'title': '待识别竞品 · ' + capture['product_id'],
            })
            product = Product.objects.select_for_update().get(pk=product.pk)
            if product.platform != platform:
                raise ValidationError('已有商品平台与链接不一致，请先核对商品资料。')
            token = sign_preview(raw, product.url, owner_id=request.user.pk, product_pk=product.pk)
        return render(request, 'market/browser_capture.html', {'product': product, 'capture': capture, 'preview': token})
    except ValidationError as exc:
        return _error(request, exc)


@login_required
@require_POST
def confirm(request, pk):
    get_object_or_404(Product, pk=pk)
    try:
        fields = _post_fields(request, {'preview'})
        observation, created = save_preview(fields['preview'], owner=request.user, product_pk=pk)
    except ValidationError as exc:
        return _error(request, exc)
    except Product.DoesNotExist:
        return _error(request, ValidationError('商品已删除，请重新采集。'))
    messages.success(request, '已保存到我的浏览器观测。' if created else '此观测已保存，未重复新增。')
    return redirect('browser_report', pk=observation.product_id)


@login_required
@require_GET
def report(request, pk):
    product = get_object_or_404(Product, pk=pk)
    rows = Snapshot.all_objects.filter(product=product, source=Snapshot.Source.BROWSER, owner=request.user)
    # 私有报告分页，不加载无界历史。
    from django.core.paginator import Paginator
    page = Paginator(rows, 50).get_page(request.GET.get('page'))
    return render(request, 'market/browser_report.html', {
        'product': product, 'groups': private_groups(page.object_list), 'page': page,
    })
