import uuid
import secrets
from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from classroom.models import Subject, ClassSession
from homepage.models import cc as CLASS_CHOICES

User = get_user_model()


class VideoCourse(models.Model):
    """
    Structured on-demand educational course module.
    Contains DRM-protected curriculum video lessons.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name='video_courses')
    class_level = models.CharField(max_length=100, choices=CLASS_CHOICES, default='year 10')
    thumbnail_url = models.URLField(blank=True, default='')
    is_subscription_only = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['title']

    def __str__(self):
        return f"{self.title} ({self.class_level})"


class VideoLesson(models.Model):
    """
    Individual video recording or on-demand lesson.
    Encrypted with AES-128 HLS DRM.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(VideoCourse, on_delete=models.CASCADE, related_name='lessons')
    session = models.ForeignKey(ClassSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='recorded_lessons')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=1)
    duration_seconds = models.PositiveIntegerField(default=0)
    
    # Encrypted HLS delivery references
    hls_manifest_path = models.CharField(max_length=500, blank=True, help_text="Path or CloudFront URL to master.m3u8")
    is_drm_protected = models.BooleanField(default=True)
    recording_source_url = models.URLField(blank=True, default='', max_length=500, help_text="Daily.co or S3 raw recording URI")
    ingestion_status = models.CharField(
        max_length=20,
        choices=[('PENDING', 'Pending Ingestion'), ('READY', 'Ready for Streaming'), ('FAILED', 'Failed Ingestion')],
        default='READY'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'created_at']

    @property
    def duration_formatted(self) -> str:
        mins = self.duration_seconds // 60
        secs = self.duration_seconds % 60
        return f"{mins}:{secs:02d}"

    def __str__(self):
        return f"{self.course.title} - #{self.order} {self.title}"


class DRMKey(models.Model):
    """
    AES-128 Cryptographic Key storage for HLS segment decryption.
    Keys are released ONLY via authenticated, tokenized DRM key-exchange endpoints.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lesson = models.OneToOneField(VideoLesson, on_delete=models.CASCADE, related_name='drm_key')
    key_hex = models.CharField(max_length=64, help_text="128-bit AES key in 32 hex chars")
    iv_hex = models.CharField(max_length=64, help_text="128-bit Initialization Vector in hex")
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def generate_for_lesson(cls, lesson: VideoLesson) -> 'DRMKey':
        key_bytes = secrets.token_bytes(16)  # 128-bit AES key
        iv_bytes = secrets.token_bytes(16)   # 128-bit IV
        return cls.objects.create(
            lesson=lesson,
            key_hex=key_bytes.hex(),
            iv_hex=iv_bytes.hex()
        )

    def __str__(self):
        return f"DRMKey for {self.lesson.title}"


class VideoSubscription(models.Model):
    """
    Student subscription access to video courses.
    Replaces unencrypted file downloads with time-bound streaming entitlements.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='video_subscriptions')
    course = models.ForeignKey(VideoCourse, on_delete=models.SET_NULL, null=True, blank=True, help_text="Null grant gives platform-wide all-course access")
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def is_valid(self) -> bool:
        now = timezone.now()
        return self.is_active and (self.starts_at <= now <= self.expires_at)

    def __str__(self):
        course_str = self.course.title if self.course else "All-Access Pass"
        return f"{self.user.username} - {course_str} (Valid until {self.expires_at.strftime('%Y-%m-%d')})"


class PlaybackSession(models.Model):
    """
    Short-lived, cryptographically signed DRM streaming authorization ticket.
    Binds playback to a specific authenticated user, client IP, and time window.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lesson = models.ForeignKey(VideoLesson, on_delete=models.CASCADE, related_name='playback_sessions')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='playback_sessions')
    token = models.CharField(max_length=128, unique=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    expires_at = models.DateTimeField(db_index=True)
    is_revoked = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, db_index=True)
    last_heartbeat = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at or self.is_revoked

    @classmethod
    def enforce_concurrent_limit(cls, user, current_token=None, max_concurrent=1):
        """
        Safeguard 1: Concurrent Stream Guard (Account Sharing Prevention).
        Revokes older active playback tickets for the user if they exceed max_concurrent streams.
        """
        active_sessions = cls.objects.filter(
            user=user,
            is_active=True,
            is_revoked=False,
            expires_at__gt=timezone.now()
        ).order_by('-created_at')

        if current_token:
            active_sessions = active_sessions.exclude(token=current_token)

        sessions_to_revoke = list(active_sessions[max_concurrent - 1:])
        for old_sess in sessions_to_revoke:
            old_sess.is_active = False
            old_sess.is_revoked = True
            old_sess.save(update_fields=['is_active', 'is_revoked'])

    def __str__(self):
        return f"PlaybackSession for {self.user.username} on {self.lesson.title}"


class VideoWatchProgress(models.Model):
    """
    Safeguard 4: Student Watch Progress & Resume Engine.
    Tracks last watched timestamp and completion status.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='watch_progress')
    lesson = models.ForeignKey(VideoLesson, on_delete=models.CASCADE, related_name='user_progress')
    last_watched_seconds = models.PositiveIntegerField(default=0)
    max_watched_seconds = models.PositiveIntegerField(default=0)
    is_completed = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'lesson')
        ordering = ['-updated_at']

    @property
    def percent_complete(self) -> int:
        if not self.lesson.duration_seconds:
            return 0
        return min(100, int((self.max_watched_seconds / self.lesson.duration_seconds) * 100))

    def __str__(self):
        return f"{self.user.username} - {self.lesson.title}: {self.last_watched_seconds}s ({self.percent_complete}%)"
