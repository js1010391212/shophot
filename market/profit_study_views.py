from urllib.parse import urlencode
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render, redirect
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET, require_POST
from .models import ProfitStudyRecord, Snapshot
from .profit_study_forms import ProfitStudySaveForm, ProfitStudyFilterForm
from .profit_studies import save_study, owned_record, report_link, history_inputs


@login_required
@require_POST
def save(request):
    form=ProfitStudySaveForm(request.POST)
    if form.is_valid():
        try:
            record=save_study(request.user,form.cleaned_data['state'],form.cleaned_data['name'],form.cleaned_data['notes'])
            return redirect('profit_study_detail',pk=record.pk)
        except ValidationError as error:form.add_error(None,error)
    return render(request,'market/profit_study_save_error.html',{'form':form},status=400)


@login_required
@require_GET
def library(request):
    form=ProfitStudyFilterForm(request.GET)
    rows=ProfitStudyRecord.objects.filter(owner=request.user)
    query=''
    if form.is_valid():
        data=form.cleaned_data;rows=rows.filter(active=not data['archived'])
        if data['q']:rows=rows.filter(Q(name__icontains=data['q'])|Q(notes__icontains=data['q']))
        query=urlencode({key:value for key,value in data.items() if value})
    else:rows=rows.none()
    page=Paginator(rows,20).get_page(request.GET.get('page','')[:20])
    return render(request,'market/profit_study_list.html',{'form':form,'page':page,'filter_query':query})


@login_required
@require_GET
def detail(request,pk):
    record=owned_record(request.user,pk)
    source=record.snapshot['scenario']['source']
    return render(request,'market/profit_study_detail.html',{'record':record,
        'calculated_at':parse_datetime(record.snapshot['calculated_at']),
        'source_observed_at':parse_datetime(source['observed_at']) if source and source.get('observed_at') else None,
        'source_label':('目录公开页面历史观测' if source.get('kind')=='catalog' else dict(Snapshot.Source.choices).get(source['source'],'未知来源')) if source else '',
        'saved':record.snapshot['scenario'],'input_rows':history_inputs(record.snapshot['scenario']),'source_link':report_link(request.user,record.snapshot['scenario'])})


@login_required
@require_POST
def toggle(request,pk):
    record=owned_record(request.user,pk)
    active=request.POST.get('active')
    if active not in ('0','1'):
        return render(request,'market/profit_study_action_error.html',{'record':record},status=400)
    ProfitStudyRecord.objects.filter(pk=record.pk,owner=request.user).update(active=active=='1')
    return redirect('profit_study_detail',pk=record.pk)
