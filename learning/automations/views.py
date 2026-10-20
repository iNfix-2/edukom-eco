import json
import logging
from datetime import timedelta
from django.shortcuts import render, redirect
from django.http import HttpResponse, HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from classroom.models import ClassSession, Student, TutorProfile, SessionStatus
from homepage.models import Guardian
from automations.models import (
    NotificationPreference, 
    InboundMessage, 
    NotificationLog, 
    NotificationChannel, 
    NotificationStatus, 
    NotificationType
)
from automations.services.phone_formatter import normalize_to_e164
from automations.services.scheduler import ReminderScheduler
from automations.services.whatsapp import WhatsAppService

logger = logging.getLogger('automations')


# ==============================================================================
# 1. INBOUND WEBHOOK & TRIAGE
# ==============================================================================

@csrf_exempt
@require_POST
def whatsapp_inbound_webhook_view(request: HttpRequest) -> HttpResponse:
    """
    Safeguard 5: Two-Way WhatsApp Inbound Support Webhook.
    Receives incoming parent/student WhatsApp messages, correlates with enrolled sessions,
    performs keyword triage, and dispatches immediate alerts to academic operations.
    """
    # 1. Parse inbound parameters (supports standard form-encoded Twilio or JSON Meta payload)
    from_raw = request.POST.get('From', '')
    body = request.POST.get('Body', '').strip()
    message_sid = request.POST.get('MessageSid', '')

    if not body and request.body:
        try:
            json_data = json.loads(request.body.decode('utf-8'))
            from_raw = json_data.get('from', '') or json_data.get('From', '')
            body = (json_data.get('body', '') or json_data.get('Body', '') or '').strip()
            message_sid = json_data.get('message_sid', '') or json_data.get('id', '')
        except Exception:
            pass

    clean_phone = from_raw.replace('whatsapp:', '').strip()
    normalized_phone = normalize_to_e164(clean_phone)

    # 2. Correlate sender with Guardian, Student, or Tutor
    matched_user = None
    matched_session = None

    # Search Guardian
    last_9 = normalized_phone[-9:] if len(normalized_phone) >= 9 else normalized_phone
    guardian = Guardian.objects.filter(phone__icontains=last_9).first()
    if guardian:
        student = Student.objects.filter(guardian=guardian).select_related('user').first()
        if student and student.user:
            matched_user = student.user
    
    # If not guardian, search Tutor
    if not matched_user:
        tutor = TutorProfile.objects.filter(phone__icontains=last_9).select_related('user').first()
        if tutor:
            matched_user = tutor.user

    # 3. Find most recent or upcoming scheduled session
    if matched_user:
        matched_session = ClassSession.objects.filter(
            booking__student__user=matched_user,
            status__in=[SessionStatus.SCHEDULED, SessionStatus.IN_PROGRESS]
        ).order_by('start_time').first()

        if not matched_session:
            matched_session = ClassSession.objects.filter(
                booking__tutor__user=matched_user,
                status__in=[SessionStatus.SCHEDULED, SessionStatus.IN_PROGRESS]
            ).order_by('start_time').first()

    # 4. Save Inbound Message Log
    inbound_record = InboundMessage.objects.create(
        from_phone=normalized_phone,
        message_sid=message_sid,
        body=body,
        matched_user=matched_user,
        matched_session=matched_session,
        is_resolved=False
    )

    logger.info(f"Received WhatsApp inbound from {normalized_phone} (User: {matched_user}): {body[:50]}")

    # 5. Urgent Keyword Triage
    urgent_keywords = ['cancel', 'reschedule', 'urgent', 'help', 'emergency', 'late', 'link', 'cannot join', 'issue', 'complaint']
    is_urgent = any(kw in body.lower() for kw in urgent_keywords)

    if is_urgent:
        try:
            sender_name = matched_user.get_full_name() if matched_user else f"Parent at {normalized_phone}"
            session_info = f"Session #{matched_session.id} ({matched_session.title})" if matched_session else "No active session linked"
            
            send_mail(
                subject=f"[URGENT WHATSAPP SUPPORT] {sender_name}: '{body[:30]}...'",
                message=(
                    f"Urgent WhatsApp message received from {sender_name} ({normalized_phone}):\n\n"
                    f"Message: {body}\n"
                    f"Related Class: {session_info}\n\n"
                    f"Please respond to the client immediately."
                ),
                from_email=getattr(settings, 'EMAIL_HOST_USER', 'support@edukom.ng'),
                recipient_list=['support@edukom.ng'],
                fail_silently=True
            )
        except Exception as e:
            logger.error(f"Failed to send urgent ops alert for inbound WhatsApp: {e}")

    # Return standard TwiML or JSON acknowledgement
    twiml_response = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
    return HttpResponse(twiml_response, content_type='application/xml')


# ==============================================================================
# 2. PRIVACY & NOTIFICATION PREFERENCES
# ==============================================================================

@login_required
def notification_preferences_view(request: HttpRequest) -> HttpResponse:
    """
    Safeguard 3: NDPR/GDPR Privacy Compliance & Notification Preferences.
    Allows parents, students, and tutors to configure communication channels (WhatsApp, SMS, Email) and quiet hours.
    """
    pref, _ = NotificationPreference.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        if request.content_type == 'application/json':
            data = json.loads(request.body.decode('utf-8'))
        else:
            data = request.POST

        pref.whatsapp_enabled = 'whatsapp_enabled' in data and data['whatsapp_enabled'] in (True, 'true', 'on', '1')
        pref.email_enabled = 'email_enabled' in data and data['email_enabled'] in (True, 'true', 'on', '1')
        pref.sms_enabled = 'sms_enabled' in data and data['sms_enabled'] in (True, 'true', 'on', '1')
        pref.marketing_opt_in = 'marketing_opt_in' in data and data['marketing_opt_in'] in (True, 'true', 'on', '1')

        q_start = data.get('quiet_hours_start')
        q_end = data.get('quiet_hours_end')
        pref.quiet_hours_start = q_start if q_start else None
        pref.quiet_hours_end = q_end if q_end else None

        pref.save()
        messages.success(request, "Communication and privacy preferences updated successfully.")

        if request.content_type == 'application/json':
            return JsonResponse({'status': 'success', 'message': 'Preferences saved'})
        return redirect('automations:preferences')

    context = {
        'preferences': pref,
        'user': request.user
    }
    return render(request, 'automations/preferences.html', context)


# ==============================================================================
# 3. SECURE CRON TRIGGER ENDPOINT (FOR CLOUDFLARE / CRON-JOB / AWS / SCHEDULER)
# ==============================================================================

@csrf_exempt
def cron_run_reminders_view(request: HttpRequest) -> JsonResponse:
    """
    Hands-Free Automated Execution Trigger:
    Pings from external cron monitors (Cloudflare Worker, cron-job.org, AWS EventBridge, Linux crontab)
    run every 5-10 minutes.
    Requires matching AUTOMATIONS_CRON_SECRET token.
    """
    expected_secret = getattr(settings, 'AUTOMATIONS_CRON_SECRET', settings.SECRET_KEY)
    
    # Check token from query param, header, or bearer token
    token = request.GET.get('key') or request.GET.get('secret') or request.headers.get('X-Cron-Secret')
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.replace('Bearer ', '').strip()

    if token != expected_secret and not settings.DEBUG and not getattr(settings, 'TESTING', False):
        logger.warning("Unauthorized cron reminder trigger attempt: invalid secret.")
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=401)

    scheduler = ReminderScheduler()
    counts_sessions = scheduler.dispatch_all_due_reminders()
    counts_subs = scheduler.dispatch_subscription_expiry_alerts()

    return JsonResponse({
        'status': 'success',
        'timestamp': timezone.now().isoformat(),
        'session_reminders': counts_sessions,
        'subscription_alerts': counts_subs
    })


# ==============================================================================
# 4. ADMIN OPERATIONS COMMAND CENTER & LIVE AUDIT DASHBOARD
# ==============================================================================

def is_staff_or_admin(user) -> bool:
    return user.is_authenticated and (user.is_staff or user.is_superuser)


@login_required
@user_passes_test(is_staff_or_admin)
def automations_dashboard_view(request: HttpRequest) -> HttpResponse:
    """
    Admin Operations Command Center for Reminders & Multi-Channel Messaging:
    - View delivery stats (WhatsApp, SMS, Email)
    - Review upcoming 24h scheduled sessions
    - Inspect real-time NotificationLog entries
    - Trigger immediate on-demand reminder scan
    - Test send WhatsApp/SMS to any destination number
    """
    now = timezone.now()
    since_24h = now - timedelta(hours=24)

    logs_24h = NotificationLog.objects.filter(created_at__gte=since_24h)
    total_sent = logs_24h.filter(status=NotificationStatus.SENT).count()
    total_failed = logs_24h.filter(status=NotificationStatus.FAILED).count()
    total_logs = logs_24h.count()

    wa_count = logs_24h.filter(channel=NotificationChannel.WHATSAPP).count()
    sms_count = logs_24h.filter(channel=NotificationChannel.SMS).count()
    email_count = logs_24h.filter(channel=NotificationChannel.EMAIL).count()

    delivery_rate = int((total_sent / total_logs * 100)) if total_logs > 0 else 100

    # Upcoming sessions next 24h
    upcoming_sessions = ClassSession.objects.filter(
        status=SessionStatus.SCHEDULED,
        start_time__gte=now,
        start_time__lte=now + timedelta(hours=24)
    ).select_related('booking', 'booking__student', 'booking__tutor', 'booking__subject').order_by('start_time')[:15]

    # Recent 30 notification logs
    recent_logs = NotificationLog.objects.select_related('session').order_by('-created_at')[:30]

    context = {
        'total_sent': total_sent,
        'total_failed': total_failed,
        'total_logs': total_logs,
        'delivery_rate': delivery_rate,
        'wa_count': wa_count,
        'sms_count': sms_count,
        'email_count': email_count,
        'upcoming_sessions': upcoming_sessions,
        'recent_logs': recent_logs,
        'now': now,
    }
    return render(request, 'automations/dashboard.html', context)


@require_POST
@login_required
@user_passes_test(is_staff_or_admin)
def trigger_reminders_now_view(request: HttpRequest) -> HttpResponse:
    """
    1-Click Manual Execution trigger from the admin operations dashboard.
    """
    scheduler = ReminderScheduler()
    counts = scheduler.dispatch_all_due_reminders()
    sub_counts = scheduler.dispatch_subscription_expiry_alerts()

    messages.success(
        request, 
        f"Automated scan completed! Dispatched: 24h={counts['24h']}, 1h={counts['1h']}, 10m={counts['10m']}. "
        f"Skipped duplicate={counts['skipped']}. Subscription renewal warnings={sub_counts['3d'] + sub_counts['1d']}."
    )
    return redirect('automations:dashboard')


@require_POST
@login_required
@user_passes_test(is_staff_or_admin)
def test_send_message_view(request: HttpRequest) -> HttpResponse:
    """
    Interactive test tool: Admin enters a phone number and message body to test live WhatsApp or SMS.
    """
    phone = request.POST.get('phone', '').strip()
    body = request.POST.get('body', '').strip() or "Test notification from Edukom Learning Management System."
    channel = request.POST.get('channel', 'WHATSAPP').upper()

    if not phone:
        messages.error(request, "Recipient phone number is required.")
        return redirect('automations:dashboard')

    svc = WhatsAppService()
    if channel == 'SMS':
        res = svc.send_sms_message(phone, body)
    else:
        res = svc.send_whatsapp_message(phone, body)

    if res.get('success'):
        mock_note = " (Simulated Sandbox)" if res.get('is_mock') else " (Live Gateway)"
        messages.success(request, f"Successfully dispatched {channel} to {res.get('recipient', phone)}{mock_note}! SID: {res.get('sid', '')}")
    else:
        messages.error(request, f"Failed to send {channel} to {phone}: {res.get('error', 'Unknown error')}")

    return redirect('automations:dashboard')
