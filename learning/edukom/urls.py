"""edukom URL Configuration
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from .health import health_check_view

urlpatterns = [
    # Infrastructure Health & Monitoring Probes
    path('healthz/', health_check_view, name='health_check'),
    path('readyz/', health_check_view, name='readiness_check'),

    path('admin/', admin.site.urls),
    path('', include('homepage.urls')),
    path('Tutor/', include('tutors.urls')),
    path('account/', include('user.urls')),
    path('payments/', include('payments.urls')),
    path('payroll/', include('payroll.urls')),
    path('classroom/', include('classroom.urls')),
    path('video/', include('videolibrary.urls')),
    path('automations/', include('automations.urls')),
]

admin.site.site_title = "EDUKOM Admin"
admin.site.site_header = "Edukom Learning Admin Dashboard"
admin.site.index_title = "Operations & Management"

urlpatterns += static(settings.STATIC_URL, document_root=settings.BASE_DIR / 'public/Assets')
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
