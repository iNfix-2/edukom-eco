from django.contrib import admin
from .import models

admin.site.register( models.AboutChild)
admin.site.register( models.Guardian)
admin.site.register( models.Location)
admin.site.register( models.Lesson)

@admin.register(models.Blog)
class BlogAdmin(admin.ModelAdmin):
    list_display = ('title', 'date_created')
    prepopulated_fields = {'slug': ('title',)}

admin.site.register(models.Testimonial)