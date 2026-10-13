from django import forms


class StudyComparisonForm(forms.Form):
    left=forms.ChoiceField(label='记录 A',required=False)
    right=forms.ChoiceField(label='记录 B',required=False)

    def __init__(self,*args,rows,**kwargs):
        super().__init__(*args,**kwargs)
        self.rows=rows
        choices=[('','选择自己的研究记录')]+[(str(row['pk']),row['name']) for row in rows]
        for name in ('left','right'):
            self.fields[name].choices=choices
            self.fields[name].error_messages['invalid_choice']='记录不可选择，请从自己的研究记录重新选择。'

    def clean(self):
        data=super().clean()
        if any(key not in ('left','right') for key in self.data):
            self.add_error(None,'仅支持选择两份记录，请移除额外参数。')
        for name in ('left','right'):
            values=self.data.getlist(name) if hasattr(self.data,'getlist') else ([self.data[name]] if name in self.data else [])
            if len(values)>1 or any(not isinstance(v,str) or len(v)>19 or (v and (not v.isascii() or not v.isdigit() or not 1<=int(v)<=9223372036854775807)) for v in values):
                self.add_error(name,'记录编号无效或重复，请重新选择。')
        if not self.errors and (data.get('left') or data.get('right')):
            if not data.get('left') or not data.get('right'):self.add_error(None,'请选择两份不同记录。')
            elif data['left']==data['right']:self.add_error(None,'请选两份不同记录，不能重复比较同一份。')
        return data
