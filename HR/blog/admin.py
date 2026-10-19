from django.contrib import admin
from .models import Post, Category, Tag


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'published', 'created_at')
    list_filter = ('published', 'created_at')
    search_fields = ('title', 'content', 'author')
    prepopulated_fields = {"slug": ("title",)}


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    prepopulated_fields = {"slug": ("name",)}
