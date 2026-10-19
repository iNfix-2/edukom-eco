from django.contrib import admin
from .models import *

# Register your models here.
admin.site.register(AboutTutor)
admin.site.register(Location)

@admin.register(Tutor)
class TutorAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'email', 'phone', 'date_joined')
    list_filter = ('date_joined', 'lesson_type')
    search_fields = ('first_name', 'last_name', 'email', 'phone')
    ordering = ('-date_joined',)

admin.site.register(Lesson)
admin.site.register(TutorEmail)