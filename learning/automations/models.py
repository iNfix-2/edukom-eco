import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from classroom.models import ClassSession

User = get_user_model()


class NotificationChannel(models.TextChoices):
    WHATSAPP = 'WHATSAPP', 'WhatsApp'
    EMAIL = 'EMAIL', 'Email'
    SMS = 'SMS', 'SMS'


class NotificationType(models.TextChoices):
    REMINDER_24H = 'REMINDER_24H', '24-Hour Reminder'
    REMINDER_1H = 'REMINDER_1H', '1-Hour Reminder'
    REMINDER_10M = 'REMINDER_10M', '10-Minute Imminent Start Alert'
    POST_CLASS_SUMMARY = 'POST_CLASS_SUMMARY', 'Post-Class Summary & Homework'
    SUBSCRIPTION_EXPIRY_3D = 'SUBSCRIPTION_EXPIRY_3D', '3-Day Subscription Expiry Alert'
    SUBSCRIPTION_EXPIRY_1D = 'SUBSCRIPTION_EXPIRY_1D', '1-Day Subscription Expiry Alert'


class NotificationStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    SENT = 'SENT', 'Sent'
    FAILED = 'FAILED', 'Failed'
    SKIPPED_DUPLICATE = 'SKIPPED_DUPLICATE', 'Skipped Duplicate'


class NotificationLog(models.Model):
    """
    Idempotent audit record of all automated reminders and messages.
    Prevents message storming, duplicate WhatsApp spam, and ensures full delivery accountability.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(ClassSession, on_delete=models.CASCADE, null=True, blank=True, related_name='automation_logs')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    recipient_name = models.CharField(max_length=200)
    recipient_phone = models.CharField(max_length=50, blank=True)
    recipient_email = models.EmailField(blank=True)
    channel = models.CharField(max_length=20, choices=NotificationChannel.choices, default=NotificationChannel.WHATSAPP)
    notification_type = models.CharField(max_length=50, choices=NotificationType.choices)
    
    # Idempotency Key: Unique constraint preventing repeat triggers for the same class reminder
    idempotency_key = models.CharField(max_length=160, unique=True, db_index=True)
    
    message_body = models.TextField()
    message_sid = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=NotificationStatus.choices, default=NotificationStatus.PENDING, db_index=True)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.channel} {self.notification_type} -> {self.recipient_phone or self.recipient_email} ({self.status})"


class NotificationPreference(models.Model):
    """
    Safeguard 3: NDPR/GDPR Privacy Compliance & Notification Preferences.
    Empowers parents and tutors to customize preferred communication channels and quiet hours.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='notification_preferences')
    whatsapp_enabled = models.BooleanField(default=True, help_text="Allow class reminders via WhatsApp")
    email_enabled = models.BooleanField(default=True, help_text="Allow class receipts and progress reports via Email")
    sms_enabled = models.BooleanField(default=False, help_text="Allow emergency SMS fallback alerts")
    marketing_opt_in = models.BooleanField(default=False, help_text="Opt in to promotional masterclasses")
    quiet_hours_start = models.TimeField(null=True, blank=True, help_text="Do not message before this time (e.g. 08:00)")
    quiet_hours_end = models.TimeField(null=True, blank=True, help_text="Do not message after this time (e.g. 21:00)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_channel_allowed(self, channel: str) -> bool:
        if channel == NotificationChannel.WHATSAPP:
            return self.whatsapp_enabled
        if channel == NotificationChannel.EMAIL:
            return self.email_enabled
        if channel == NotificationChannel.SMS:
            return self.sms_enabled
        return True

    def __str__(self):
        return f"Preferences for {self.user.username} (WA: {self.whatsapp_enabled}, Email: {self.email_enabled})"


class InboundMessage(models.Model):
    """
    Safeguard 5: Two-Way WhatsApp Inbound Support Webhook.
    Logs incoming messages from parents/students, correlates them with scheduled sessions,
    and alerts academic operations coordinators.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    from_phone = models.CharField(max_length=50, db_index=True)
    message_sid = models.CharField(max_length=100, blank=True)
    body = models.TextField()
    matched_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='inbound_messages')
    matched_session = models.ForeignKey(ClassSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='inbound_messages')
    is_resolved = models.BooleanField(default=False, db_index=True)
    admin_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Inbound from {self.from_phone}: {self.body[:40]}..."
