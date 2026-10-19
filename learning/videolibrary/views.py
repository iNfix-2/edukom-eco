import os
import json
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, HttpRequest, JsonResponse, Http404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from .models import VideoCourse, VideoLesson, DRMKey, VideoSubscription, PlaybackSession, VideoWatchProgress
from .services import DRMService

logger = logging.getLogger('videolibrary')


@login_required
def course_catalog_view(request: HttpRequest) -> HttpResponse:
    """
    On-Demand Video Curriculum Library:
    Displays available DRM-protected courses, lesson count, and subscription status.
    """
    courses = VideoCourse.objects.prefetch_related('lessons').all()
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
    }
    return render(request, 'videolibrary/catalog.html', context)


@login_required
def course_detail_view(request: HttpRequest, course_id: str) -> HttpResponse:
    """
    Curriculum syllabus & lessons for a specific course.
    """
    course = get_object_or_404(VideoCourse, id=course_id)
    lessons = course.lessons.all().order_by('order')
    has_access = DRMService.user_has_active_subscription(request.user, course)

    # Attach watch progress for each lesson if authenticated
    progress_map = {
        p.lesson_id: p for p in VideoWatchProgress.objects.filter(user=request.user, lesson__course=course)
    }
    for lesson in lessons:
        lesson.progress = progress_map.get(lesson.id)

    context = {
        'course': course,
        'lessons': lessons,
        'has_access': has_access,
    }
    return render(request, 'videolibrary/course_detail.html', context)


@login_required
def video_player_view(request: HttpRequest, lesson_id: str) -> HttpResponse:
    """
    Protected DRM Video Player View:
    - Verifies user streaming entitlement.
    - Generates short-lived, IP-bound PlaybackSession token.
    - Enforces concurrent stream guard (Safeguard 1).
    - Renders secure HTML5 player with dynamic, moving forensic watermark.
    - Hardened with anti-download, right-click, and screen rip defenses.
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
    }
    return render(request, 'videolibrary/player.html', context)


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
    response['Access-Control-Allow-Origin'] = '*'  # Allow HLS video player fetch
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
    Safeguard 7: Adaptive Bitrate (ABR) Multi-Quality HLS Master Manifest.
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
    Safeguard 1 & 4: Player Heartbeat & Watch Progress Tracker.
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

    # Update or create watch progress (Safeguard 4)
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
    Safeguard 4: Fetches saved student playback progress for resume prompt.
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
    Safeguards 2 & 8: Live Class Recording Auto-Ingestion Webhook.
    Receives notification from Daily.co recording webhook, validates secret,
    checks NDPR parental recording consent, and encrypts into the DRM library.
    """
    # 1. Validate Webhook Secret
    expected_secret = getattr(settings, 'DAILY_RECORDING_WEBHOOK_SECRET', settings.SECRET_KEY)
    auth_header = request.headers.get('X-Edukom-Webhook-Secret') or request.headers.get('Authorization', '')
    
    # Try header or payload token
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

    # 2. Ingest and DRM encrypt recording
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

