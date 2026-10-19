from django import forms
from . import models

class GuardianForm(forms.ModelForm):
    curriculum= forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple, choices=models.Curriculums)
    class Meta:
        model = models.Guardian
        fields = ['first_name','last_name','email','phone','hear','lesson_type','curriculum']
        widgets = {
            'lesson_type':forms.RadioSelect,
        }

class AboutChildForm(forms.ModelForm):
    subject =forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple, choices=models.subjects)
    class Meta:
        model = models.AboutChild
        fields = ('child_class','goal','subject','about')
                                          
class LocationForm(forms.ModelForm):
    class Meta:
        model = models.Location
        fields = ('state','street_address')

class LessonForm(forms.ModelForm):
    days =forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple, choices=models.days)
    class Meta:
        model = models.Lesson
        fields = ('days','start','weeks','hour_per_day','start_time') 
        widgets = {
            'start':forms.DateInput(attrs={'type':'date'}),
            'start_time':forms.TimeInput(attrs={'type':'time'}),
            'hour_per_day':forms.NumberInput({'type':'number'}),
        }

class ContactForm(forms.ModelForm):
    class Meta:
        model = models.Contact
        fields = ('name','phone_number', 'email','message')

class BlogForm(forms.ModelForm):
    class Meta:
        model = models.Blog
        fields = ('title', 'content', 'image', 'cta_title', 'cta_url')
        widgets = {
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 10}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'cta_title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Register Now'}),
            'cta_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'e.g. https://edukom.ng/register'}),
        }

class CommentForm(forms.ModelForm):
    class Meta:
        model = models.Comment
        fields = ('name', 'email', 'content')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your Name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Your Email'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Write a comment...'}),
        }

class TestimonialForm(forms.ModelForm):
    class Meta:
        model = models.Testimonial
        fields = ('name', 'location', 'content', 'image')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Client Name'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Location (e.g. Abuja)'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Testimonial Content'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
        }
