import os
from django import forms
from django.core.exceptions import ValidationError
from classroom.models import Subject
from homepage.models import cc as CLASS_CHOICES
from .models import VideoCourse, VideoLesson, CourseResource, ResourceType


ALLOWED_VIDEO_EXTENSIONS = ['.mp4', '.webm', '.mov', '.m4v', '.mkv']
MAX_VIDEO_FILE_SIZE = 500 * 1024 * 1024  # 500MB

ALLOWED_RESOURCE_EXTENSIONS = ['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt', '.zip', '.txt', '.png', '.jpg', '.jpeg']
MAX_RESOURCE_FILE_SIZE = 25 * 1024 * 1024  # 25MB


class CourseForm(forms.ModelForm):
    class Meta:
        model = VideoCourse
        fields = [
            'title',
            'subject',
            'class_level',
            'description',
            'thumbnail',
            'thumbnail_url',
            'price',
            'is_subscription_only',
            'is_published',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 bg-white border border-slate-300 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-slate-800 placeholder-slate-400',
                'placeholder': 'e.g. Complete Cambridge IGCSE Additional Mathematics'
            }),
            'subject': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 bg-white border border-slate-300 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-slate-800'
            }),
            'class_level': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 bg-white border border-slate-300 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-slate-800'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 bg-white border border-slate-300 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-slate-800 placeholder-slate-400',
                'rows': 4,
                'placeholder': 'Explain what topics are covered, target exams, learning outcomes, and prerequisites...'
            }),
            'thumbnail': forms.FileInput(attrs={
                'class': 'w-full text-xs text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-bold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 cursor-pointer',
                'accept': 'image/*'
            }),
            'thumbnail_url': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2.5 bg-white border border-slate-300 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-slate-800 placeholder-slate-400',
                'placeholder': 'https://example.com/cover-image.jpg (Optional alternative to direct upload)'
            }),
            'price': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 bg-white border border-slate-300 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-slate-800',
                'min': '0',
                'step': '100'
            }),
            'is_subscription_only': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-indigo-600 border-slate-300 rounded focus:ring-indigo-500'
            }),
            'is_published': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-indigo-600 border-slate-300 rounded focus:ring-indigo-500'
            }),
        }

    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price is not None and price < 0:
            raise ValidationError("Course price cannot be negative.")
        return price


class LessonForm(forms.ModelForm):
    duration_minutes = forms.IntegerField(
        required=False,
        min_value=0,
        label="Duration (Minutes)",
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-4 py-2.5 bg-white border border-slate-300 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-slate-800',
            'placeholder': 'e.g. 45'
        }),
        help_text="Lesson length in minutes"
    )

    class Meta:
        model = VideoLesson
        fields = [
            'title',
            'order',
            'description',
            'video_file',
            'video_url',
            'is_drm_protected',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 bg-white border border-slate-300 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-slate-800 placeholder-slate-400',
                'placeholder': 'e.g. Lesson 1: Introduction to Quadratic Functions & Graphs'
            }),
            'order': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 bg-white border border-slate-300 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-slate-800',
                'min': '1'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 bg-white border border-slate-300 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-slate-800 placeholder-slate-400',
                'rows': 3,
                'placeholder': 'Brief description of concepts explained in this video session...'
            }),
            'video_file': forms.FileInput(attrs={
                'class': 'w-full text-xs text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-bold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 cursor-pointer',
                'accept': 'video/mp4,video/webm,video/quicktime,video/x-matroska'
            }),
            'video_url': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2.5 bg-white border border-slate-300 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-slate-800 placeholder-slate-400',
                'placeholder': 'https://player.vimeo.com/... or S3 / CloudFront streaming link'
            }),
            'is_drm_protected': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-indigo-600 border-slate-300 rounded focus:ring-indigo-500'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.duration_seconds:
            self.fields['duration_minutes'].initial = self.instance.duration_seconds // 60

    def clean_video_file(self):
        f = self.cleaned_data.get('video_file')
        if f:
            ext = os.path.splitext(f.name)[1].lower()
            if ext not in ALLOWED_VIDEO_EXTENSIONS:
                raise ValidationError(f"Unsupported video file type ({ext}). Allowed: {', '.join(ALLOWED_VIDEO_EXTENSIONS)}")
            if f.size > MAX_VIDEO_FILE_SIZE:
                raise ValidationError(f"Video file exceeds maximum allowed upload size of 500MB ({f.size / (1024*1024):.1f}MB detected).")
        return f

    def save(self, commit=True):
        instance = super().save(commit=False)
        mins = self.cleaned_data.get('duration_minutes')
        if mins is not None:
            instance.duration_seconds = mins * 60
        if commit:
            instance.save()
        return instance


class CourseResourceForm(forms.ModelForm):
    class Meta:
        model = CourseResource
        fields = [
            'title',
            'resource_type',
            'lesson',
            'file',
            'description',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 bg-white border border-slate-300 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-slate-800 placeholder-slate-400',
                'placeholder': 'e.g. Chapter 4 Practice Exercises with Worked Solutions'
            }),
            'resource_type': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 bg-white border border-slate-300 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-slate-800'
            }),
            'lesson': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 bg-white border border-slate-300 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-slate-800'
            }),
            'file': forms.FileInput(attrs={
                'class': 'w-full text-xs text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-bold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 cursor-pointer',
                'accept': '.pdf,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.zip,.txt,image/*'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 bg-white border border-slate-300 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-slate-800 placeholder-slate-400',
                'rows': 2,
                'placeholder': 'Instructions for students on how to use this resource (optional)...'
            }),
        }

    def __init__(self, *args, course=None, **kwargs):
        super().__init__(*args, **kwargs)
        if course:
            self.fields['lesson'].queryset = course.lessons.all().order_by('order')
            self.fields['lesson'].empty_label = "Course-Wide Resource (Attached to Entire Course)"
            self.fields['lesson'].required = False
        else:
            self.fields['lesson'].queryset = VideoLesson.objects.none()

    def clean_file(self):
        f = self.cleaned_data.get('file')
        if f:
            ext = os.path.splitext(f.name)[1].lower()
            if ext not in ALLOWED_RESOURCE_EXTENSIONS:
                raise ValidationError(f"File extension '{ext}' is not permitted. Permitted: {', '.join(ALLOWED_RESOURCE_EXTENSIONS)}")
            if f.size > MAX_RESOURCE_FILE_SIZE:
                raise ValidationError(f"Resource file exceeds 25MB limit ({f.size / (1024*1024):.1f}MB detected).")
        return f

    def save(self, commit=True):
        instance = super().save(commit=False)
        f = self.cleaned_data.get('file')
        if f:
            instance.file_size = f.size
            instance.file_extension = os.path.splitext(f.name)[1].lower()
        if commit:
            instance.save()
        return instance
