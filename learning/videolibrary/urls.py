from django.urls import path
from . import views

app_name = 'videolibrary'

urlpatterns = [
    # Catalog & Course Syllabus
    path('', views.course_catalog_view, name='index'),
    path('catalog/', views.course_catalog_view, name='catalog'),
    path('course/<uuid:course_id>/', views.course_detail_view, name='course_detail'),

    # Secure DRM Video Player
    path('lesson/<uuid:lesson_id>/watch/', views.video_player_view, name='watch_lesson'),

    # Cryptographic Key Exchange & HLS Stream delivery
    path('drm-key/<str:token>/', views.drm_key_exchange_view, name='drm_key'),
    path('stream/<uuid:lesson_id>/<str:token>/manifest.m3u8', views.stream_hls_manifest_view, name='hls_manifest'),
    path('stream/<uuid:lesson_id>/<str:token>/master.m3u8', views.stream_hls_master_view, name='hls_master'),
    path('stream/<uuid:lesson_id>/<str:token>/variant.m3u8', views.stream_hls_variant_view, name='hls_variant'),

    # Safeguard 1 & 4: Heartbeat & Watch Progress
    path('lesson/<uuid:lesson_id>/heartbeat/', views.playback_heartbeat_view, name='heartbeat'),
    path('lesson/<uuid:lesson_id>/progress/', views.get_watch_progress_view, name='watch_progress'),

    # Safeguards 2 & 8: Live Recording Auto-Ingestion Webhook
    path('webhook/recording-ingest/', views.recording_ingest_webhook_view, name='recording_ingest_webhook'),
]
