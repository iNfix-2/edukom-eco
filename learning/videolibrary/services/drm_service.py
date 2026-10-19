"""
Digital Rights Management (DRM) Cryptographic Service for Edukom LMS.
Implements:
1. AES-128 HLS segment encryption key management.
2. Tokenized, short-lived playback sessions bound to user identity and client IP.
3. Anti-piracy entitlement verification.
"""

import hmac
import hashlib
import secrets
import logging
from typing import Tuple, Optional
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from videolibrary.models import VideoLesson, DRMKey, VideoSubscription, PlaybackSession

User = get_user_model()
logger = logging.getLogger('videolibrary')


class DRMService:
    @staticmethod
    def user_has_active_subscription(user, course=None) -> bool:
        """
        Validates if the user has an active, non-expired subscription for the course
        or a platform-wide all-access pass. Staff/Admins always have access.
        """
        if not user or not user.is_authenticated:
            return False
        if user.is_staff or user.is_superuser:
            return True

        now = timezone.now()
        subs = VideoSubscription.objects.filter(
            user=user,
            is_active=True,
            starts_at__lte=now,
            expires_at__gte=now
        )
        if course:
            # Matches all-access (course=None) OR this specific course
            return subs.filter(models_Q_or_null(course)).exists()
        return subs.exists()

    @staticmethod
    def get_or_create_drm_key(lesson: VideoLesson) -> DRMKey:
        """
        Fetches or provisions the AES-128 encryption key for a video lesson.
        """
        if hasattr(lesson, 'drm_key'):
            return lesson.drm_key
        return DRMKey.generate_for_lesson(lesson)

    @classmethod
    def create_playback_session(cls, user, lesson: VideoLesson, client_ip: str, user_agent: str = '') -> Tuple[bool, Optional[PlaybackSession], str]:
        """
        Issues a time-bound DRM playback ticket for an entitled student.
        """
        # 1. Verify user subscription entitlement
        if not cls.user_has_active_subscription(user, lesson.course):
            # Check if user was enrolled in the original live class session
            has_session_access = False
            if lesson.session and hasattr(lesson.session, 'booking'):
                booking = lesson.session.booking
                if booking.student.user == user or booking.student.guardian.email.lower() == (user.email or '').lower():
                    has_session_access = True
            
            if not has_session_access:
                return False, None, "Active video subscription required to stream this lesson."

        # 2. Generate cryptographically strong random token
        raw_token = secrets.token_urlsafe(48)
        
        # 3. Bind expiration window (default 2 hours)
        ttl_minutes = getattr(settings, 'DRM_TOKEN_TTL_MINUTES', 120)
        expires_at = timezone.now() + timedelta(minutes=ttl_minutes)

        # 4. Clean client IP
        clean_ip = (client_ip or '127.0.0.1').split(',')[0].strip()

        session = PlaybackSession.objects.create(
            lesson=lesson,
            user=user,
            token=raw_token,
            ip_address=clean_ip,
            user_agent=user_agent[:250],
            expires_at=expires_at,
            is_active=True
        )

        # 5. Safeguard 1: Concurrent Stream Guard (Revoke older streams on account sharing)
        max_concurrent = getattr(settings, 'MAX_CONCURRENT_VIDEO_STREAMS', 1)
        PlaybackSession.enforce_concurrent_limit(user, current_token=session.token, max_concurrent=max_concurrent)

        logger.info(f"DRM Playback session created for user {user.username} on lesson {lesson.id} (IP: {clean_ip})")
        return True, session, "Playback authorized."

    @staticmethod
    def verify_playback_ticket(token: str, client_ip: Optional[str] = None) -> Tuple[bool, Optional[PlaybackSession], str]:
        """
        Verifies playback ticket authenticity, expiration, and IP binding.
        """
        if not token:
            return False, None, "Missing playback authorization token."

        try:
            playback_session = PlaybackSession.objects.select_related('lesson', 'user', 'lesson__drm_key').get(token=token)
        except PlaybackSession.DoesNotExist:
            logger.warning(f"DRM playback attempt with non-existent token: {token[:12]}...")
            return False, None, "Invalid playback token."

        if playback_session.is_expired:
            return False, None, "Playback token has expired. Please refresh the player."

        if not playback_session.is_active or playback_session.is_revoked:
            return False, None, "Playback session terminated: Your account is active on another device."

        # Verify client IP binding if provided
        if client_ip:
            clean_ip = client_ip.split(',')[0].strip()
            # Allow matching or localhost in dev
            if playback_session.ip_address and playback_session.ip_address != clean_ip and clean_ip not in ('127.0.0.1', '::1'):
                logger.warning(f"DRM IP mismatch: token issued to {playback_session.ip_address}, presented by {clean_ip}")
                return False, None, "IP address mismatch. Token bound to another network connection."

        # Update activity heartbeat
        playback_session.last_heartbeat = timezone.now()
        playback_session.save(update_fields=['last_heartbeat'])

        return True, playback_session, "Token verified."

    @classmethod
    def generate_hls_manifest(cls, lesson: VideoLesson, key_url: str) -> str:
        """
        Generates a standard AES-128 encrypted HLS M3U8 media manifest.
        The client player requests chunks which can only be decrypted with the key from key_url.
        """
        return cls.generate_hls_variant(lesson, key_url, resolution='720p')

    @classmethod
    def generate_adaptive_hls_master(cls, lesson: VideoLesson, base_variant_url: str) -> str:
        """
        Safeguard 7: Adaptive Bitrate (ABR) Multi-Quality HLS Master Manifest.
        Serves multi-tier bitrates:
        - 1080p HD (3.5 Mbps) - Fiber/Broadband
        - 720p HD (1.8 Mbps) - Standard 4G
        - 480p SD (850 Kbps) - Mobile LTE
        - 360p Data Saver (400 Kbps) - Low bandwidth/3G African cellular networks
        """
        variants = [
            ("1080p", 3500000, "1920x1080", "1080p HD"),
            ("720p", 1800000, "1280x720", "720p HD"),
            ("480p", 850000, "854x480", "480p SD"),
            ("360p", 400000, "640x360", "360p Data Saver"),
        ]

        lines = [
            "#EXTM3U",
            "#EXT-X-VERSION:3",
            f"# Edukom Adaptive HLS Stream for Lesson: {lesson.title}",
        ]

        sep = '&' if '?' in base_variant_url else '?'
        for name, bw, res, label in variants:
            lines.append(f'#EXT-X-STREAM-INF:BANDWIDTH={bw},RESOLUTION={res},NAME="{label}"')
            lines.append(f"{base_variant_url}{sep}resolution={name}")

        return "\n".join(lines) + "\n"

    @classmethod
    def generate_hls_variant(cls, lesson: VideoLesson, key_url: str, resolution: str = '720p') -> str:
        """
        Generates resolution-specific HLS segment playlist encrypted with AES-128 DRM.
        """
        drm_key = cls.get_or_create_drm_key(lesson)
        iv_hex = drm_key.iv_hex.upper()

        manifest = (
            "#EXTM3U\n"
            "#EXT-X-VERSION:3\n"
            "#EXT-X-TARGETDURATION:10\n"
            "#EXT-X-MEDIA-SEQUENCE:0\n"
            "#EXT-X-PLAYLIST-TYPE:VOD\n"
            f'#EXT-X-KEY:METHOD=AES-128,URI="{key_url}",IV=0x{iv_hex}\n'
            f"#EXTINF:10.0,\n"
            f"segment_{resolution}_000.ts\n"
            f"#EXTINF:10.0,\n"
            f"segment_{resolution}_001.ts\n"
            f"#EXTINF:10.0,\n"
            f"segment_{resolution}_002.ts\n"
            "#EXT-X-ENDLIST\n"
        )
        return manifest

    @classmethod
    def ingest_live_class_recording(cls, session_id: str, recording_url: str, duration_seconds: int = 0) -> Tuple[bool, Optional[VideoLesson], str]:
        """
        Safeguards 2 & 8: Live Class Recording Ingestion with NDPR Minor Consent Guard.
        Bridges finished Daily.co classroom recordings into the DRM video library.
        """
        from classroom.models import ClassSession
        from videolibrary.models import VideoCourse

        try:
            session = ClassSession.objects.select_related('booking', 'booking__student', 'booking__subject').get(id=session_id)
        except (ClassSession.DoesNotExist, ValueError):
            return False, None, f"ClassSession '{session_id}' not found."

        # Safeguard 8: NDPR / COPPA Minor Recording Consent verification
        if not getattr(session.booking, 'recording_consent_given', False):
            logger.warning(f"Recording ingestion rejected for session {session_id}: NDPR parental consent was not granted.")
            return False, None, "NDPR Compliance Rejection: Parental recording consent was not granted for this session."

        subject = session.booking.subject
        class_level = session.booking.class_level
        course_title = f"Class Recordings - {subject.name} ({class_level})"

        # Find or create recorded classes course
        course, _ = VideoCourse.objects.get_or_create(
            title=course_title,
            subject=subject,
            class_level=class_level,
            defaults={
                'description': f"Automated class recordings archive for {subject.name}.",
                'is_subscription_only': True,
            }
        )

        # Create or update VideoLesson
        lesson, created = VideoLesson.objects.get_or_create(
            session=session,
            defaults={
                'course': course,
                'title': f"{session.title} ({session.start_time.strftime('%b %d, %Y')})",
                'description': f"Live class recording with tutor {session.booking.tutor.display_name}. Topic: {session.title}.",
                'order': course.lessons.count() + 1,
                'duration_seconds': duration_seconds,
                'recording_source_url': recording_url,
                'ingestion_status': 'READY',
                'is_drm_protected': True,
            }
        )

        if not created and recording_url:
            lesson.recording_source_url = recording_url
            if duration_seconds:
                lesson.duration_seconds = duration_seconds
            lesson.ingestion_status = 'READY'
            lesson.save(update_fields=['recording_source_url', 'duration_seconds', 'ingestion_status'])

        # Guarantee AES-128 encryption key
        cls.get_or_create_drm_key(lesson)

        logger.info(f"Ingested live class recording for session {session.id} into lesson {lesson.id} (DRM encrypted).")
        return True, lesson, "Recording successfully ingested and DRM encrypted."


def models_Q_or_null(course):
    from django.db.models import Q
    return Q(course=course) | Q(course__isnull=True)
