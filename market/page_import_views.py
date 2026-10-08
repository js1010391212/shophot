from urllib.parse import urlsplit
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods
from .models import Product, Snapshot
from .page_import_forms import PageImportForm, PageImportTargetForm
from .page_import import parse_page, SUPPORTED_PLATFORMS

SALT='product-page-preview-v3'


@login_required
@require_http_methods(['GET','POST'])
def import_page(request,pk):
    product=get_object_or_404(Product,pk=pk,platform__in=SUPPORTED_PLATFORMS)
    confirm=request.method=='POST' and request.POST.get('action')=='confirm'
    form=PageImportForm(request.POST if request.method=='POST' and not confirm else None,request.FILES or None)
    context={'product':product,'form':form}
    if confirm:
        try:
            data=signing.loads(request.POST.get('preview',''),salt=SALT,max_age=1200)
            if data['owner']!=request.user.pk or data['product']!=product.pk or data['url']!=product.url or data['platform']!=product.platform:raise ValueError
        except (signing.BadSignature,KeyError,ValueError,TypeError):
            context['confirmation_error']='预览无效或已过期，请重新上传页面。'
            return render(request,'market/page_import.html',context,status=400)
        result=data['result']
        try:
            with transaction.atomic():
                locked=Product.objects.select_for_update().get(pk=product.pk)
                if locked.url!=data['url'] or locked.platform!=data['platform']:
                    context['confirmation_error']='商品资料已变更，请重新上传页面。'
                    return render(request,'market/page_import.html',context,status=400)
                quote,created=Snapshot.objects.get_or_create(product=product,observed_at=parse_datetime(data['observed_at']),source=Snapshot.Source.MANUAL,
                    defaults={'price':result['price'],'currency':result['currency'],'rating':result['rating'],'review_count':result['review_count'],
                              'sales':None,'context':(product.platform+' 页面文件导入；规格 '+result['specification']+'；文件 '+result['file_fingerprint']+'；'+data['context'])[:300]})
                if not created and any(str(getattr(quote,key))!=str(result[key]) for key in ('price','currency','rating','review_count')):
                    context['confirmation_error']='该时间已有不同观测，未覆盖历史；请核对观测时间与原页面。'
                    return render(request,'market/page_import.html',context,status=400)
                from .product_reviews import save_batch
                save_batch(quote,result,data['url'],created)
                if locked.title.startswith('待识别竞品 · '):
                    Product.objects.filter(pk=product.pk,title=locked.title).update(title=result['title'])
        except ValidationError as exc:
            context['confirmation_error']=' '.join(exc.messages)
            return render(request,'market/page_import.html',context,status=400)
        messages.success(request,'已保存页面文件中的公开报价，来源标记为手动记录；不是后台自动采集。' if created else '此观测已保存，未重复新增。')
        return redirect('product_detail',pk=product.pk)
    if request.method=='POST' and form.is_valid():
        try:
            result=parse_page(form.cleaned_data['file'].read(),product.url,product.platform)
            data={'owner':request.user.pk,'product':product.pk,'url':product.url,'platform':product.platform,'result':result,
                  'observed_at':form.cleaned_data['observed_at'].isoformat(),'context':form.cleaned_data['context']}
            context.update(result=result,observed_at=form.cleaned_data['observed_at'],preview=signing.dumps(data,salt=SALT),quote_context=data['context'])
        except ValidationError as exc:form.add_error('file',exc)
    return render(request,'market/page_import.html',context,status=400 if form.errors else 200)


@login_required
@require_http_methods(['GET','POST'])
def start_import(request):
    form=PageImportTargetForm(request.POST if request.method=='POST' else None)
    if request.method=='POST' and form.is_valid():
        product,_=Product.objects.get_or_create(url=form.cleaned_data['url'],defaults={
            'platform':form.platform,'title':'待识别竞品 · '+urlsplit(form.cleaned_data['url']).path.rstrip('/').rsplit('/',1)[-1][:80]})
        if product.platform!=form.platform:
            form.add_error('url','已有商品的平台与链接不一致，请先在商品报告编辑资料。')
        else:
            return redirect('page_import',pk=product.pk)
    return render(request,'market/page_import_start.html',{'form':form},status=400 if form.errors else 200)
