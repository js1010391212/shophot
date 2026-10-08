"""报价历史模块，只读取独立成功观测，不启动采集。"""
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from django.shortcuts import get_object_or_404, render
from django.http import Http404
from .models import StoreDiscovery
from .price_history import observations_for_url, build_history
from .price_history_forms import HistoryFilterForm


@login_required
@require_GET
def catalog_history(request, pk, index):
    scan=get_object_or_404(StoreDiscovery,pk=pk,status='succeeded')
    if index >= len(scan.products):
        raise Http404('目录中没有此商品。')
    item=scan.products[index]
    observations=observations_for_url(item['url'])
    currencies=sorted(set(observations.values_list('currency',flat=True)))
    form=HistoryFilterForm(request.GET,currencies=currencies)
    context={'scan':scan,'item':item,'index':index,'title':item.get('price_title') or item.get('title'),'filter_form':form}
    if form.is_valid():
        latest=observations.first()
        currency=form.cleaned_data['currency'] or (latest.currency if latest else '')
        context.update(build_history(observations,currency,form.cleaned_data['days']))
        return render(request,'market/price_history.html',context)
    return render(request,'market/price_history.html',context,status=400)
