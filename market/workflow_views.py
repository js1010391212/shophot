"""分析进度与报告路由，和目录/商品研究页面解耦。"""
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.views.decorators.http import require_GET
from .models import StoreDiscovery, Product
from .catalog_coverage import build_catalog_coverage, coverage_message


def progress_response(request, data):
    if request.GET.get('format') == 'json':
        response=JsonResponse(data)
    elif data['redirect_url']:
        response=redirect(data['redirect_url'])
    else:
        response=render(request,'market/workflow.html',data)
    response['Cache-Control']='no-store'
    return response


@login_required
@require_GET
def store_analysis(request, pk):
    scan=get_object_or_404(StoreDiscovery,pk=pk)
    job=scan.price_jobs.first()
    status=scan.status
    coverage=build_catalog_coverage(scan,job)
    title='正在发现店铺商品'
    message=('读取公开目录，完成后自动采集首批最多 10 件商品。' if scan.analyze_prices else '读取公开商品目录，完成后直接生成目录分析报告；本次不请求商品详情或报价。')
    if status == 'succeeded':
        status=job.status if job else 'succeeded'
        title=coverage['title']
        message=coverage_message(coverage)
    failed=status == 'failed'
    active=status in ('queued','running')
    redirect_url=reverse('store_research',args=[pk]) if scan.status == 'succeeded' and not active and coverage['total_count'] else ''
    if scan.status == 'failed':
        title='暂时无法完成分析'
        message=scan.message or '公开目录获取失败，请稍后重试。'
    elif scan.status == 'succeeded' and not coverage['total_count']:
        title='没有发现可分析的公开商品'
        message='没有可识别的公开商品链接；不代表店铺没有商品，可以重新分析或换一个店铺链接。'
        active=False
    elif failed and job:
        message += ' '+(job.message or '本批报价任务失败，已保存报价仍保留。')
    previous_report = StoreDiscovery.objects.filter(url=scan.url,status='succeeded').exclude(pk=scan.pk).first() if scan.status=='failed' else None
    data={'title':title,'message':message,'active':active,'redirect_url':redirect_url,
          'coverage':{key:coverage[key] for key in ('state','total_count','new_count','failed_count','unresolved_count','not_scheduled_count','historical_count','quoted_count','limited')}}
    if request.GET.get('format') != 'json':
        data.update(url=scan.url,store=scan,failed=failed,previous_report=previous_report,poll_url=reverse('store_analysis',args=[pk])+'?format=json',
                    report_coverage=coverage if scan.status == 'succeeded' else None,
                    step='prices' if scan.status == 'succeeded' else 'directory')
    return progress_response(request,data)


@login_required
@require_GET
def product_analysis(request, pk):
    product=get_object_or_404(Product,pk=pk)
    job=product.jobs.first()
    active=bool(job and job.status in ('queued','running'))
    success=bool(job and job.status == 'succeeded')
    data={'title':'正在分析商品' if active else '暂时无法完成分析',
          'message':'正在读取公开价格与商品数据，完成后自动打开报告。' if active else (job.message if job else '当前没有采集任务。'),
          'active':active,'redirect_url':reverse('product_detail',args=[pk]) if success else ''}
    if request.GET.get('format') != 'json':
        data.update(url=product.url,product=product,failed=not active and not success,step='prices',
                    poll_url=reverse('product_analysis',args=[pk])+'?format=json')
    return progress_response(request,data)
