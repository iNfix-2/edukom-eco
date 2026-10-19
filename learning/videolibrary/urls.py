from django.urls import path
from . import views

app_name = 'videolibrary'

urlpatterns = [
    # Catalog & Course Syllabus (Student & Public)
    path('', views.course_catalog_view, name='index'),
    path('catalog/', views.course_catalog_view, name='catalog'),
    path('course/<uuid:course_id>/', views.course_detail_view, name='course_detail'),
    path('resource/<uuid:resource_id>/download/', views.download_course_resource_view, name='download_resource'),

    # Creator Studio (Tutors & Admin Only)
    path('studio/', views.studio_dashboard_view, name='studio_dashboard'),
    path('studio/course/create/', views.studio_course_create_view, name='studio_course_create'),
    path('studio/course/<uuid:course_id>/edit/', views.studio_course_edit_view, name='studio_course_edit'),
    path('studio/course/<uuid:course_id>/toggle-publish/', views.studio_course_toggle_publish_view, name='studio_course_toggle_publish'),
    path('studio/course/<uuid:course_id>/curriculum/', views.studio_course_curriculum_view, name='studio_course_curriculum'),
    path('studio/course/<uuid:course_id>/builder/', views.studio_course_curriculum_view, name='studio_curriculum'),
    path('studio/course/<uuid:course_id>/lesson/create/', views.studio_lesson_create_view, name='studio_lesson_create'),
    path('studio/lesson/<uuid:lesson_id>/edit/', views.studio_lesson_edit_view, name='studio_lesson_edit'),
    path('studio/lesson/<uuid:lesson_id>/delete/', views.studio_lesson_delete_view, name='studio_lesson_delete'),
    path('studio/course/<uuid:course_id>/resource/upload/', views.studio_resource_upload_view, name='studio_resource_upload'),
    path('studio/resource/<uuid:resource_id>/delete/', views.studio_resource_delete_view, name='studio_resource_delete'),

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
