from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from django.shortcuts import render
from django.core.paginator import Paginator
from .catalog_research import latest_catalogs, catalog_rows
from .sample_market import prepare_rows, filter_rows, summarize
from .sample_market_forms import SampleMarketForm


@login_required
@require_GET
def sample_market(request):
    scans=latest_catalogs()
    raw=catalog_rows(scans)
    all_rows=prepare_rows(raw)
    form=SampleMarketForm(request.GET,scans=scans,rows=all_rows)
    valid=form.is_valid()
    data=form.cleaned_data if valid else {}
    rows=filter_rows(all_rows,data) if valid else []
    params=request.GET.copy();params.pop('page',None)
    context={'form':form,'valid':valid,'sample_count':len(all_rows),'duplicate_count':len(raw)-len(all_rows),
             'store_count':len(scans),'limited_count':sum(scan.limited for scan in scans),
             'page':Paginator(rows,25).get_page(request.GET.get('page')),'query_string':params.urlencode()}
    if valid:
        context.update(summarize(rows,data,scans))
    return render(request,'market/sample_market.html',context,status=200 if valid else 400)
