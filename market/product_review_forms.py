from django import forms


class ReviewHistoryForm(forms.Form):
    batch=forms.TypedChoiceField(label='评论样本观测',coerce=int,required=False,
        empty_value=None,choices=[])

    def __init__(self,*args,batches=(),catalog_available=False,**kwargs):
        super().__init__(*args,**kwargs)
        from django.utils import timezone
        self.fields['batch'].choices=[('', '有评论的最近一次观测')]+[(row.pk,
            timezone.localtime(row.snapshot.observed_at).strftime('%Y-%m-%d %H:%M')+' · '+str(len(row.samples))+' 条样本') for row in batches]

        if catalog_available:
            self.fields['batch'].choices=list(self.fields['batch'].choices)+[(-1,'店铺目录已采集的评论样本')]
