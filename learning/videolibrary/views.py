import os
import json
import logging
import mimetypes
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, HttpRequest, JsonResponse, Http404, FileResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.db import models

from .models import (
    VideoCourse,
    VideoLesson,
    DRMKey,
    VideoSubscription,
    PlaybackSession,
    VideoWatchProgress,
    CourseResource
)
from .forms import CourseForm, LessonForm, CourseResourceForm
from .services import DRMService

logger = logging.getLogger('videolibrary')


# ==============================================================================
# AUTHORIZATION GUARDS & CREATOR PERMISSION HELPERS
# ==============================================================================

def can_manage_videolibrary(user) -> bool:
    """Check if user has permissions to create or manage courses (Staff, Admin, or Tutor)."""
    return user.is_authenticated and (user.is_staff or user.is_superuser or hasattr(user, 'tutor_profile'))


def can_edit_course(user, course: VideoCourse) -> bool:
    """BOLA/IDOR Guard: verify user owns this course or has admin privileges."""
    if not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    return course.created_by == user


def studio_access_required(view_func):
    """Decorator ensuring only authorized tutors or staff access the Creator Studio."""
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not can_manage_videolibrary(request.user):
            messages.error(request, "Access Restricted: Creator Studio is reserved for verified Tutors and Administrators.")
            return redirect('videolibrary:catalog')
        return view_func(request, *args, **kwargs)
    return _wrapped


# ==============================================================================
# STUDENT & PUBLIC VIDEO CATALOG VIEWS
# ==============================================================================

@login_required
def course_catalog_view(request: HttpRequest) -> HttpResponse:
    """
    On-Demand Video Curriculum Library:
    Displays available DRM-protected courses, lesson count, and subscription status.
    Tutors and Admins see draft items and the Creator Studio link.
    """
    is_manager = can_manage_videolibrary(request.user)

    if is_manager:
        courses = VideoCourse.objects.prefetch_related('lessons', 'resources').all()
    else:
        courses = VideoCourse.objects.filter(is_published=True).prefetch_related('lessons', 'resources').all()

    user_subscriptions = VideoSubscription.objects.filter(
        user=request.user, 
        is_active=True,
        expires_at__gte=timezone.now()
    )
    has_all_access = user_subscriptions.filter(course__isnull=True).exists()
    subscribed_course_ids = set(user_subscriptions.values_list('course_id', flat=True))

    context = {
        'courses': courses,
        'has_all_access': has_all_access,
        'subscribed_course_ids': subscribed_course_ids,
        'is_staff': request.user.is_staff,
        'can_manage': is_manager,
    }
    return render(request, 'videolibrary/catalog.html', context)


@login_required
def course_detail_view(request: HttpRequest, course_id: str) -> HttpResponse:
    """
    Curriculum syllabus, lessons, and downloadable resources for a specific course.
    """
    course = get_object_or_404(VideoCourse, id=course_id)
    can_manage = can_edit_course(request.user, course)

    if not course.is_published and not can_manage:
        raise Http404("This course is currently in draft mode.")

    lessons = course.lessons.all().order_by('order', 'created_at')
    resources = course.resources.all().order_by('lesson__order', 'created_at')
    has_access = DRMService.user_has_active_subscription(request.user, course) or can_manage

    # Attach watch progress for each lesson if authenticated
    progress_map = {
        p.lesson_id: p for p in VideoWatchProgress.objects.filter(user=request.user, lesson__course=course)
    }
    for lesson in lessons:
        lesson.progress = progress_map.get(lesson.id)

    context = {
        'course': course,
        'lessons': lessons,
        'resources': resources,
        'has_access': has_access,
        'can_manage': can_manage,
    }
    return render(request, 'videolibrary/course_detail.html', context)


@login_required
def video_player_view(request: HttpRequest, lesson_id: str) -> HttpResponse:
    """
    Protected DRM Video Player View:
    - Verifies user streaming entitlement.
    - Generates short-lived, IP-bound PlaybackSession token.
    - Enforces concurrent stream guard.
    - Renders secure HTML5 player with dynamic, moving forensic watermark.
    - Hardened with anti-download, right-click, and screen rip defenses.
    - Displays attached lesson worksheets and course handouts.
    """
    lesson = get_object_or_404(VideoLesson, id=lesson_id)
    client_ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', '')).split(',')[0].strip()
    user_agent = request.META.get('HTTP_USER_AGENT', '')

    # 1. Authorize and issue DRM playback ticket
    authorized, session, reason = DRMService.create_playback_session(
        user=request.user,
        lesson=lesson,
        client_ip=client_ip,
        user_agent=user_agent
    )

    if not authorized:
        messages.error(request, f"Access Restricted: {reason}")
        return redirect('videolibrary:course_detail', course_id=lesson.course.id)

    # 2. Ensure DRM cryptographic key exists
    DRMService.get_or_create_drm_key(lesson)

    # 3. Construct URLs (Adaptive Master Playlist, Heartbeat, Progress)
    key_url = request.build_absolute_uri(
        reverse('videolibrary:drm_key', kwargs={'token': session.token})
    )
    master_manifest_url = reverse('videolibrary:hls_master', kwargs={'lesson_id': lesson.id, 'token': session.token})
    manifest_url = reverse('videolibrary:hls_manifest', kwargs={'lesson_id': lesson.id, 'token': session.token})
    heartbeat_url = reverse('videolibrary:heartbeat', kwargs={'lesson_id': lesson.id})
    progress_url = reverse('videolibrary:watch_progress', kwargs={'lesson_id': lesson.id})

    # Retrieve existing watch progress for resume
    watch_progress = VideoWatchProgress.objects.filter(user=request.user, lesson=lesson).first()

    # Resources
    lesson_resources = lesson.resources.all()
    course_resources = lesson.course.resources.filter(lesson__isnull=True)

    context = {
        'lesson': lesson,
        'course': lesson.course,
        'playback_token': session.token,
        'manifest_url': master_manifest_url,
        'standard_manifest_url': manifest_url,
        'key_url': key_url,
        'heartbeat_url': heartbeat_url,
        'progress_url': progress_url,
        'resume_seconds': watch_progress.last_watched_seconds if watch_progress else 0,
        'client_ip': client_ip,
        'viewer_email': request.user.email,
        'viewer_name': request.user.get_full_name() or request.user.username,
        'expires_at': session.expires_at,
        'lesson_resources': lesson_resources,
        'course_resources': course_resources,
    }
    return render(request, 'videolibrary/player.html', context)


# ==============================================================================
# SECURE RESOURCE DOWNLOAD (BOLA/IDOR PROTECTED)
# ==============================================================================

@login_required
def download_course_resource_view(request: HttpRequest, resource_id: str) -> HttpResponse:
    """
    Safely streams a downloadable course material (PDF, worksheet, slides).
    Enforces authorization check: user must be subscribed or course creator or admin.
    """
    resource = get_object_or_404(CourseResource, id=resource_id)
    course = resource.course

    is_staff_or_admin = request.user.is_staff or request.user.is_superuser
    is_creator = (course.created_by == request.user)
    has_sub = DRMService.user_has_active_subscription(request.user, course)

    if not (is_staff_or_admin or is_creator or has_sub):
        messages.error(request, "Enrollment or subscription required to download course materials.")
        return redirect('videolibrary:course_detail', course_id=course.id)

    if not resource.file:
        raise Http404("Resource file not found.")

    # Increment download counter atomically
    CourseResource.objects.filter(id=resource.id).update(download_count=models.F('download_count') + 1)

    filename = os.path.basename(resource.file.name)
    content_type, _ = mimetypes.guess_type(filename)
    response = FileResponse(resource.file.open('rb'), content_type=content_type or 'application/octet-stream')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ==============================================================================
# CREATOR STUDIO: DASHBOARD & COURSE SETUP
# ==============================================================================

@studio_access_required
def studio_dashboard_view(request: HttpRequest) -> HttpResponse:
    """
    Creator Studio Dashboard for Tutors and Administrators.
    Shows summary KPI stats and all owned courses with status controls.
    """
    is_admin = request.user.is_staff or request.user.is_superuser

    if is_admin:
        courses = VideoCourse.objects.prefetch_related('lessons', 'resources', 'created_by').all()
    else:
        courses = VideoCourse.objects.filter(created_by=request.user).prefetch_related('lessons', 'resources').all()

    total_courses = courses.count()
    published_courses = courses.filter(is_published=True).count()
    draft_courses = courses.filter(is_published=False).count()
    total_lessons = VideoLesson.objects.filter(course__in=courses).count()
    total_resources = CourseResource.objects.filter(course__in=courses).count()

    context = {
        'courses': courses,
        'total_courses': total_courses,
        'published_courses': published_courses,
        'draft_courses': draft_courses,
        'total_lessons': total_lessons,
        'total_resources': total_resources,
        'is_admin': is_admin,
    }
    return render(request, 'videolibrary/studio_dashboard.html', context)


@studio_access_required
def studio_course_create_view(request: HttpRequest) -> HttpResponse:
    """
    Creates a new on-demand video course module.
    """
    if request.method == 'POST':
        form = CourseForm(request.POST, request.FILES)
        if form.is_valid():
            course = form.save(commit=False)
            course.created_by = request.user
            course.save()
            messages.success(request, f"Course '{course.title}' created! Now add video lessons and learning resources.")
            return redirect('videolibrary:studio_curriculum', course_id=course.id)
    else:
        form = CourseForm()

    return render(request, 'videolibrary/course_form.html', {
        'form': form,
        'title': 'Create New Video Course',
        'is_edit': False
    })


@studio_access_required
def studio_course_edit_view(request: HttpRequest, course_id: str) -> HttpResponse:
    """
    Edits existing video course metadata and settings.
    """
    course = get_object_or_404(VideoCourse, id=course_id)
    if not can_edit_course(request.user, course):
        messages.error(request, "Permission denied: you cannot edit courses created by another instructor.")
        return redirect('videolibrary:studio_dashboard')

    if request.method == 'POST':
        form = CourseForm(request.POST, request.FILES, instance=course)
        if form.is_valid():
            form.save()
            messages.success(request, f"Course '{course.title}' updated successfully.")
            return redirect('videolibrary:studio_dashboard')
    else:
        form = CourseForm(instance=course)

    return render(request, 'videolibrary/course_form.html', {
        'form': form,
        'course': course,
        'title': f'Edit Course: {course.title}',
        'is_edit': True
    })


@require_POST
@studio_access_required
def studio_course_toggle_publish_view(request: HttpRequest, course_id: str) -> HttpResponse:
    """
    1-click instant toggle between Draft and Published status.
    """
    course = get_object_or_404(VideoCourse, id=course_id)
    if not can_edit_course(request.user, course):
        messages.error(request, "Permission denied.")
        return redirect('videolibrary:studio_dashboard')

    course.is_published = not course.is_published
    course.save(update_fields=['is_published', 'updated_at'])

    status_name = "Published to catalog" if course.is_published else "Saved as Draft"
    messages.success(request, f"'{course.title}' is now {status_name}.")
    return redirect('videolibrary:studio_dashboard')


# ==============================================================================
# CREATOR STUDIO: CURRICULUM, LESSONS & RESOURCES
# ==============================================================================

@studio_access_required
def studio_course_curriculum_view(request: HttpRequest, course_id: str) -> HttpResponse:
    """
    Full curriculum builder for a specific course:
    - View and re-order lessons
    - Direct video lesson uploader
    - Downloadable worksheets & resources manager
    """
    course = get_object_or_404(VideoCourse, id=course_id)
    if not can_edit_course(request.user, course):
        messages.error(request, "Permission denied.")
        return redirect('videolibrary:studio_dashboard')

    lessons = course.lessons.all().order_by('order', 'created_at')
    resources = course.resources.all().order_by('created_at')
    next_order = lessons.count() + 1

    lesson_form = LessonForm(initial={'order': next_order})
    resource_form = CourseResourceForm(course=course)

    context = {
        'course': course,
        'lessons': lessons,
        'resources': resources,
        'lesson_form': lesson_form,
        'resource_form': resource_form,
    }
    return render(request, 'videolibrary/studio_curriculum.html', context)


@require_POST
@studio_access_required
def studio_lesson_create_view(request: HttpRequest, course_id: str) -> HttpResponse:
    """
    Uploads or links a new video lesson into the course curriculum.
    """
    course = get_object_or_404(VideoCourse, id=course_id)
    if not can_edit_course(request.user, course):
        messages.error(request, "Permission denied.")
        return redirect('videolibrary:studio_dashboard')

    form = LessonForm(request.POST, request.FILES)
    if form.is_valid():
        lesson = form.save(commit=False)
        lesson.course = course
        lesson.save()

        # Pre-generate DRM encryption key if lesson is protected
        if lesson.is_drm_protected:
            DRMService.get_or_create_drm_key(lesson)

        messages.success(request, f"Lesson #{lesson.order} '{lesson.title}' added to curriculum successfully!")
    else:
        for field, errors in form.errors.items():
            for err in errors:
                messages.error(request, f"Error in {field}: {err}")

    return redirect('videolibrary:studio_curriculum', course_id=course.id)


@studio_access_required
def studio_lesson_edit_view(request: HttpRequest, lesson_id: str) -> HttpResponse:
    """
    Edits lesson title, duration, video file, or streaming URL.
    """
    lesson = get_object_or_404(VideoLesson, id=lesson_id)
    if not can_edit_course(request.user, lesson.course):
        messages.error(request, "Permission denied.")
        return redirect('videolibrary:studio_dashboard')

    if request.method == 'POST':
        form = LessonForm(request.POST, request.FILES, instance=lesson)
        if form.is_valid():
            form.save()
            messages.success(request, f"Lesson '{lesson.title}' updated successfully.")
            return redirect('videolibrary:studio_curriculum', course_id=lesson.course.id)
    else:
        form = LessonForm(instance=lesson)

    return render(request, 'videolibrary/lesson_form.html', {
        'form': form,
        'lesson': lesson,
        'course': lesson.course,
        'title': f"Edit Lesson: {lesson.title}"
    })


@require_POST
@studio_access_required
def studio_lesson_delete_view(request: HttpRequest, lesson_id: str) -> HttpResponse:
    """
    Removes a lesson from the curriculum.
    """
    lesson = get_object_or_404(VideoLesson, id=lesson_id)
    course_id = lesson.course.id
    if not can_edit_course(request.user, lesson.course):
        messages.error(request, "Permission denied.")
        return redirect('videolibrary:studio_dashboard')

    title = lesson.title
    lesson.delete()
    messages.success(request, f"Lesson '{title}' deleted from curriculum.")
    return redirect('videolibrary:studio_curriculum', course_id=course_id)


@require_POST
@studio_access_required
def studio_resource_upload_view(request: HttpRequest, course_id: str) -> HttpResponse:
    """
    Uploads course learning worksheets, lecture slides, or past question resources.
    """
    course = get_object_or_404(VideoCourse, id=course_id)
    if not can_edit_course(request.user, course):
        messages.error(request, "Permission denied.")
        return redirect('videolibrary:studio_dashboard')

    form = CourseResourceForm(request.POST, request.FILES, course=course)
    if form.is_valid():
        resource = form.save(commit=False)
        resource.course = course
        resource.uploaded_by = request.user
        resource.save()
        messages.success(request, f"Resource '{resource.title}' uploaded and attached!")
    else:
        for field, errors in form.errors.items():
            for err in errors:
                messages.error(request, f"Resource error ({field}): {err}")

    return redirect('videolibrary:studio_curriculum', course_id=course.id)


@require_POST
@studio_access_required
def studio_resource_delete_view(request: HttpRequest, resource_id: str) -> HttpResponse:
    """
    Deletes an attached resource.
    """
    resource = get_object_or_404(CourseResource, id=resource_id)
    course_id = resource.course.id
    if not can_edit_course(request.user, resource.course):
        messages.error(request, "Permission denied.")
        return redirect('videolibrary:studio_dashboard')

    title = resource.title
    resource.delete()
    messages.success(request, f"Resource '{title}' deleted.")
    return redirect('videolibrary:studio_curriculum', course_id=course_id)


# ==============================================================================
# CRYPTOGRAPHIC KEY EXCHANGE & DRM STREAMING ENDPOINTS
# ==============================================================================

@require_GET
def drm_key_exchange_view(request: HttpRequest, token: str) -> HttpResponse:
    """
    DRM Cryptographic Key Exchange:
    Validates token authenticity, expiration, and client IP before releasing the 16-byte AES-128 key.
    Denies unauthorized attempts or download scripts with HTTP 403 Forbidden.
    """
    client_ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
    verified, session, reason = DRMService.verify_playback_ticket(token, client_ip)

    if not verified or not session:
        logger.warning(f"Rejected unauthorized DRM key request from IP {client_ip}: {reason}")
        return HttpResponse(f"Forbidden: {reason}", status=403, content_type='text/plain')

    drm_key = getattr(session.lesson, 'drm_key', None)
    if not drm_key:
        logger.error(f"DRM key missing for lesson {session.lesson.id}")
        return HttpResponse("DRM key configuration error.", status=500)

    try:
        raw_key_bytes = bytes.fromhex(drm_key.key_hex)
    except ValueError:
        return HttpResponse("Corrupted cryptographic key.", status=500)

    # Return raw 128-bit binary key with non-cacheable security headers
    response = HttpResponse(raw_key_bytes, content_type='application/octet-stream')
    response['Cache-Control'] = 'no-store, no-cache, private, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Access-Control-Allow-Origin'] = '*'
    return response


@require_GET
def stream_hls_manifest_view(request: HttpRequest, lesson_id: str, token: str) -> HttpResponse:
    """
    Standard single-stream HLS manifest delivery (720p).
    """
    client_ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
    verified, session, reason = DRMService.verify_playback_ticket(token, client_ip)

    if not verified or not session:
        return HttpResponse(f"Forbidden: {reason}", status=403, content_type='text/plain')

    key_url = request.build_absolute_uri(
        reverse('videolibrary:drm_key', kwargs={'token': session.token})
    )
    manifest_content = DRMService.generate_hls_manifest(session.lesson, key_url)

    response = HttpResponse(manifest_content, content_type='application/vnd.apple.mpegurl')
    response['Cache-Control'] = 'no-store, private'
    response['Access-Control-Allow-Origin'] = '*'
    return response


@require_GET
def stream_hls_master_view(request: HttpRequest, lesson_id: str, token: str) -> HttpResponse:
    """
    Adaptive Bitrate (ABR) Multi-Quality HLS Master Manifest.
    Provides variant streams from 1080p down to 360p Data Saver mode for low-bandwidth cellular connections.
    """
    client_ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
    verified, session, reason = DRMService.verify_playback_ticket(token, client_ip)

    if not verified or not session:
        return HttpResponse(f"Forbidden: {reason}", status=403, content_type='text/plain')

    base_variant_url = request.build_absolute_uri(
        reverse('videolibrary:hls_variant', kwargs={'lesson_id': lesson_id, 'token': session.token})
    )
    master_content = DRMService.generate_adaptive_hls_master(session.lesson, base_variant_url)

    response = HttpResponse(master_content, content_type='application/vnd.apple.mpegurl')
    response['Cache-Control'] = 'no-store, private'
    response['Access-Control-Allow-Origin'] = '*'
    return response


@require_GET
def stream_hls_variant_view(request: HttpRequest, lesson_id: str, token: str) -> HttpResponse:
    """
    Delivers resolution-specific encrypted HLS segment playlist (1080p, 720p, 480p, 360p).
    """
    client_ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
    verified, session, reason = DRMService.verify_playback_ticket(token, client_ip)

    if not verified or not session:
        return HttpResponse(f"Forbidden: {reason}", status=403, content_type='text/plain')

    resolution = request.GET.get('resolution', '720p')
    key_url = request.build_absolute_uri(
        reverse('videolibrary:drm_key', kwargs={'token': session.token})
    )
    variant_content = DRMService.generate_hls_variant(session.lesson, key_url, resolution=resolution)

    response = HttpResponse(variant_content, content_type='application/vnd.apple.mpegurl')
    response['Cache-Control'] = 'no-store, private'
    response['Access-Control-Allow-Origin'] = '*'
    return response


@csrf_exempt
@login_required
def playback_heartbeat_view(request: HttpRequest, lesson_id: str) -> JsonResponse:
    """
    Player Heartbeat & Watch Progress Tracker:
    - Verifies stream is still active (revoked if another device started playback).
    - Records progress timestamp for seamless resume across devices.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        body = request.POST

    token = body.get('token', '')
    current_time = float(body.get('current_time', 0))

    client_ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
    verified, session, reason = DRMService.verify_playback_ticket(token, client_ip)

    if not verified or not session:
        return JsonResponse({
            'active': False,
            'reason': reason or 'Stream terminated',
            'action': 'TERMINATE_PLAYBACK'
        }, status=403)

    # Update or create watch progress
    progress, _ = VideoWatchProgress.objects.get_or_create(
        user=request.user,
        lesson=session.lesson
    )
    progress.last_watched_seconds = int(current_time)
    if progress.last_watched_seconds > progress.max_watched_seconds:
        progress.max_watched_seconds = progress.last_watched_seconds

    if session.lesson.duration_seconds > 0 and progress.max_watched_seconds >= int(0.9 * session.lesson.duration_seconds):
        progress.is_completed = True

    progress.save()

    return JsonResponse({
        'active': True,
        'last_watched_seconds': progress.last_watched_seconds,
        'percent_complete': progress.percent_complete,
        'is_completed': progress.is_completed
    })


@login_required
@require_GET
def get_watch_progress_view(request: HttpRequest, lesson_id: str) -> JsonResponse:
    """
    Fetches saved student playback progress for resume prompt.
    """
    progress = VideoWatchProgress.objects.filter(
        user=request.user,
        lesson_id=lesson_id
    ).first()

    if not progress:
        return JsonResponse({'has_progress': False, 'last_watched_seconds': 0})

    return JsonResponse({
        'has_progress': True,
        'last_watched_seconds': progress.last_watched_seconds,
        'percent_complete': progress.percent_complete,
        'is_completed': progress.is_completed
    })


@csrf_exempt
@require_POST
def recording_ingest_webhook_view(request: HttpRequest) -> JsonResponse:
    """
    Live Class Recording Auto-Ingestion Webhook:
    Receives notification from Daily.co recording webhook, validates secret,
    checks NDPR parental recording consent, and encrypts into the DRM library.
    """
    expected_secret = getattr(settings, 'DAILY_RECORDING_WEBHOOK_SECRET', settings.SECRET_KEY)
    auth_header = request.headers.get('X-Edukom-Webhook-Secret') or request.headers.get('Authorization', '')
    
    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        data = request.POST

    token_param = data.get('secret') or auth_header.replace('Bearer ', '').strip()
    if token_param != expected_secret and not settings.DEBUG:
        logger.warning("Unauthorized recording webhook attempt: invalid secret.")
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    session_id = data.get('session_id')
    recording_url = data.get('recording_url', '')
    duration_seconds = int(data.get('duration_seconds', 0))

    if not session_id or not recording_url:
        return JsonResponse({'error': 'session_id and recording_url required'}, status=400)

    success, lesson, reason = DRMService.ingest_live_class_recording(
        session_id=session_id,
        recording_url=recording_url,
        duration_seconds=duration_seconds
    )

    if not success:
        return JsonResponse({'status': 'rejected', 'reason': reason}, status=400)

    return JsonResponse({
        'status': 'success',
        'lesson_id': str(lesson.id),
        'title': lesson.title,
        'message': reason
    })
