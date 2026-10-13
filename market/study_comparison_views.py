from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.views.decorators.http import require_GET
from .study_comparison import choice_rows,selected_records,read_history,compare_histories
from .study_comparison_forms import StudyComparisonForm
from .profit_studies import report_link
from .models import Snapshot


@login_required
@require_GET
def comparison(request):
    rows=choice_rows(request.user)
    form=StudyComparisonForm(request.GET,rows=rows)
    result=None;histories=[];error='';status=200
    if form.is_valid():
        data=form.cleaned_data
        if data.get('left') and data.get('right'):
            try:
                records=selected_records(request.user,[int(data['left']),int(data['right'])])
                histories=[read_history(row) for row in records]
                for history in histories:
                    history['source_link']=report_link(request.user,history['scenario'])
                    history['source_label']=dict(Snapshot.Source.choices).get(history['source']['source'],'未知来源') if history['source'] else ''
                result=compare_histories(*histories)
            except ValidationError as problem:
                error=' '.join(problem.messages);histories=[];status=400
    else:status=400
    return render(request,'market/study_comparison.html',dict(form=form,choices=rows,result=result,histories=histories,error=error),status=status)
