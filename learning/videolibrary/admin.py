from django.contrib import admin
from .models import (
    VideoCourse,
    VideoLesson,
    CourseResource,
    DRMKey,
    VideoSubscription,
    PlaybackSession,
    VideoWatchProgress
)


class VideoLessonInline(admin.TabularInline):
    model = VideoLesson
    extra = 1
    fields = ('order', 'title', 'duration_seconds', 'video_file', 'video_url', 'is_drm_protected', 'ingestion_status')
    ordering = ('order',)


class CourseResourceInline(admin.TabularInline):
    model = CourseResource
    extra = 1
    fields = ('title', 'resource_type', 'file', 'lesson', 'download_count')


@admin.register(VideoCourse)
class VideoCourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'subject', 'class_level', 'created_by', 'is_published', 'is_subscription_only', 'price', 'created_at')
    list_filter = ('class_level', 'is_published', 'is_subscription_only', 'subject')
    search_fields = ('title', 'description', 'created_by__username', 'created_by__email')
    inlines = [VideoLessonInline, CourseResourceInline]
    date_hierarchy = 'created_at'


@admin.register(VideoLesson)
class VideoLessonAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'order', 'duration_seconds', 'is_drm_protected', 'ingestion_status', 'created_at')
    list_filter = ('course', 'is_drm_protected', 'ingestion_status')
    search_fields = ('title', 'description', 'course__title')
    ordering = ('course', 'order')


@admin.register(CourseResource)
class CourseResourceAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'lesson', 'resource_type', 'file_size_formatted', 'download_count', 'uploaded_by', 'created_at')
    list_filter = ('resource_type', 'course')
    search_fields = ('title', 'course__title', 'description')


@admin.register(VideoSubscription)
class VideoSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'course', 'is_active', 'starts_at', 'expires_at', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('user__username', 'user__email', 'course__title')


@admin.register(DRMKey)
class DRMKeyAdmin(admin.ModelAdmin):
    list_display = ('lesson', 'created_at')
    search_fields = ('lesson__title', 'lesson__course__title')


@admin.register(PlaybackSession)
class PlaybackSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'lesson', 'ip_address', 'is_active', 'is_revoked', 'expires_at', 'created_at')
    list_filter = ('is_active', 'is_revoked')
    search_fields = ('user__username', 'user__email', 'lesson__title', 'ip_address', 'token')


@admin.register(VideoWatchProgress)
class VideoWatchProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'lesson', 'last_watched_seconds', 'max_watched_seconds', 'percent_complete', 'is_completed', 'updated_at')
    list_filter = ('is_completed',)
    search_fields = ('user__username', 'lesson__title')
