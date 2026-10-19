from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', include('core.urls')),
    path('blog/', include('blog.urls')),
]

if settings.DEBUG:
    # Serve /static/ via staticfiles app
    urlpatterns += staticfiles_urlpatterns()
    # Serve legacy /img/... references used by the original HTML
    urlpatterns += static('/img/', document_root=settings.BASE_DIR / 'img')
    # Serve media uploads during development
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
