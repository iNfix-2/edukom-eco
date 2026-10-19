from django import forms
from . import models



class TutorForm(forms.ModelForm):
    curriculum= forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple, choices=models.Curriculums)
    class Meta:
        model = models.Tutor
        fields = ['first_name','last_name','email','phone','hear','lesson_type','curriculum']
        widgets = {
            'lesson_type':forms.RadioSelect,
        }

class AboutTutorForm(forms.ModelForm):
    subject =forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple, choices=models.subjects)
    class Meta:
        model = models.AboutTutor
        fields = ('teacher_class','goal','subject','about')
                                          
class LocationForm(forms.ModelForm):
    class Meta:
        model = models.Location
        fields = ('state','street_address')

class LessonForm(forms.ModelForm):
    days =forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple, choices=models.days)
    class Meta:
        model = models.Lesson
        fields = ('days','weeks','hour_per_day','start_time') 
        widgets = {
            'start_time':forms.TimeInput(attrs={'type':'time'}),
            'hour_per_day':forms.NumberInput({'type':'number'}),
        }