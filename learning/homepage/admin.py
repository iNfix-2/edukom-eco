from django.contrib import admin
from .import models

admin.site.register( models.AboutChild)

@admin.register(models.Guardian)
class GuardianAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'email', 'phone', 'date_joined')
    list_filter = ('date_joined', 'lesson_type')
    search_fields = ('first_name', 'last_name', 'email', 'phone')
    ordering = ('-date_joined',)

admin.site.register( models.Location)
admin.site.register( models.Lesson)

@admin.register(models.Blog)
class BlogAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'is_featured', 'date_created')
    list_filter = ('category', 'is_featured')
    prepopulated_fields = {'slug': ('title',)}

admin.site.register(models.Testimonial)

@admin.register(models.Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone_number', 'date')
    readonly_fields = ('date',)

@admin.register(models.Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
    list_display = ('email', 'date_subscribed')
    readonly_fields = ('date_subscribed',)