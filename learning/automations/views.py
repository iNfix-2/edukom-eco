import json
import logging
from django.shortcuts import render, redirect
from django.http import HttpResponse, HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from classroom.models import ClassSession, Student, TutorProfile, SessionStatus
from homepage.models import Guardian
from automations.models import NotificationPreference, InboundMessage
from automations.services.phone_formatter import normalize_to_e164

logger = logging.getLogger('automations')


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


@login_required
def notification_preferences_view(request: HttpRequest) -> HttpResponse:
    """
    Safeguard 3: NDPR/GDPR Privacy Compliance & Notification Preferences.
    Allows parents, students, and tutors to configure communication channels and quiet hours.
    """
    pref, _ = NotificationPreference.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        # Accept JSON or Form POST
        if request.content_type == 'application/json':
            data = json.loads(request.body.decode('utf-8'))
        else:
            data = request.POST

        pref.whatsapp_enabled = 'whatsapp_enabled' in data and data['whatsapp_enabled'] in (True, 'true', 'on', '1')
        pref.email_enabled = 'email_enabled' in data and data['email_enabled'] in (True, 'true', 'on', '1')
        pref.sms_enabled = 'sms_enabled' in data and data['sms_enabled'] in (True, 'true', 'on', '1')
        pref.marketing_opt_in = 'marketing_opt_in' in data and data['marketing_opt_in'] in (True, 'true', 'on', '1')

        # Quiet hours
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
