"""保留旧 OTTO URL，使用统一的预览与保存流程。"""
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from .models import Product
from .page_import_views import import_page as unified_import_page


@login_required
@require_http_methods(['GET','POST'])
def import_page(request, pk):
    # 不让兼容入口接受其他平台的商品。
    get_object_or_404(Product, pk=pk, platform='OTTO')
    return unified_import_page(request, pk)
