from django import forms
from .models import Post, Tag, Category


class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ['title', 'author', 'content', 'cover', 'category', 'tags', 'published']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'author': forms.TextInput(attrs={'class': 'form-control'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 10}),
            'cover': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'tags': forms.SelectMultiple(attrs={'class': 'form-select'}),
            'published': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Category name'}),
        }


class TagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tag name'}),
        }
