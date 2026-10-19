import re

from django import forms
from . import models

INTERNATIONAL_PHONE_REGEX = re.compile(r'^\+[1-9]\d{7,14}$')

class GuardianForm(forms.ModelForm):
    curriculum= forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple, choices=models.Curriculums)
    class Meta:
        model = models.Guardian
        fields = ['first_name','last_name','email','phone','hear','lesson_type','curriculum']
        widgets = {
            'lesson_type':forms.RadioSelect,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'hear' in self.fields:
            self.fields['hear'].widget.attrs.update({'placeholder': 'e.g. Google, Social Media, Recommendation'})

class AboutChildForm(forms.ModelForm):
    subject =forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple, choices=models.subjects)
    class Meta:
        model = models.AboutChild
        fields = ('child_class','goal','subject','about')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'child_class' in self.fields:
            self.fields['child_class'].empty_label = "Select Child's Class / Grade Level"
        if 'goal' in self.fields:
            self.fields['goal'].empty_label = "Select Primary Learning Goal"
                                          
class LocationForm(forms.ModelForm):
    class Meta:
        model = models.Location
        fields = ('state','street_address')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'state' in self.fields:
            self.fields['state'].empty_label = "Select State / Province"

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
        widgets = {
            'phone_number': forms.TextInput(attrs={
                'type': 'tel',
            }),
        }

    def clean_phone_number(self):
        phone_number = self.cleaned_data.get('phone_number', '').strip()
        if not INTERNATIONAL_PHONE_REGEX.match(phone_number):
            raise forms.ValidationError(
                "Enter a valid international phone number starting with a country code (e.g. +2348012345678)."
            )
        return phone_number

class BlogForm(forms.ModelForm):
    class Meta:
        model = models.Blog
        fields = ('title', 'content', 'image', 'category', 'is_featured', 'cta_title', 'cta_url')
        widgets = {
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 10}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
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

class SubscriberForm(forms.ModelForm):
    class Meta:
        model = models.Subscriber
        fields = ('email',)
        widgets = {
            'email': forms.EmailInput(attrs={'placeholder': 'Your academic email address'}),
        }
