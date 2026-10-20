"""
Automated Scheduling & Class Reminder Engine for Edukom LMS.
Triggers:
- 24-Hour Reminder (Confirmation & Syllabus prep)
- 1-Hour Reminder (Imminent class alert & room entry)
- 10-Minute Reminder (Starting now link)
- Multi-Channel: WhatsApp + SMS + Email
- Multi-Stakeholder: Guardian / Parent + Student + Tutor
- Strictly Idempotent: Prevents spam with unique database idempotency keys
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from django.core.mail import send_mail
from classroom.models import ClassSession, SessionStatus
from videolibrary.models import VideoSubscription
from automations.models import (
    NotificationLog, 
    NotificationChannel, 
    NotificationType, 
    NotificationStatus,
    NotificationPreference
)
from .whatsapp import WhatsAppService, MessagingService

logger = logging.getLogger('automations')


class ReminderScheduler:
    def __init__(self):
        self.wa_service = WhatsAppService()

    def dispatch_all_due_reminders(self) -> Dict[str, int]:
        """
        Scans upcoming scheduled sessions and triggers 24h, 1h, and 10m reminders.
        Can be run repeatedly (e.g. every 5 minutes by cron/celery) safely due to idempotency.
        """
        now = timezone.now()
        counts = {'24h': 0, '1h': 0, '10m': 0, 'skipped': 0}

        # 1. 24-Hour Reminder Window: 23 hours to 25 hours ahead
        t24_start = now + timedelta(hours=23)
        t24_end = now + timedelta(hours=25)
        sessions_24h = ClassSession.objects.filter(
            status=SessionStatus.SCHEDULED,
            start_time__gte=t24_start,
            start_time__lte=t24_end
        ).select_related('booking', 'booking__student', 'booking__tutor', 'booking__subject')

        for sess in sessions_24h:
            sent = self.send_reminder_for_session(sess, NotificationType.REMINDER_24H)
            if sent:
                counts['24h'] += 1
            else:
                counts['skipped'] += 1

        # 2. 1-Hour Reminder Window: 45 minutes to 75 minutes ahead
        t1_start = now + timedelta(minutes=45)
        t1_end = now + timedelta(minutes=75)
        sessions_1h = ClassSession.objects.filter(
            status=SessionStatus.SCHEDULED,
            start_time__gte=t1_start,
            start_time__lte=t1_end
        ).select_related('booking', 'booking__student', 'booking__tutor', 'booking__subject')

        for sess in sessions_1h:
            sent = self.send_reminder_for_session(sess, NotificationType.REMINDER_1H)
            if sent:
                counts['1h'] += 1
            else:
                counts['skipped'] += 1

        # 3. 10-Minute Reminder Window: 3 minutes to 15 minutes ahead
        t10_start = now + timedelta(minutes=3)
        t10_end = now + timedelta(minutes=15)
        sessions_10m = ClassSession.objects.filter(
            status=SessionStatus.SCHEDULED,
            start_time__gte=t10_start,
            start_time__lte=t10_end
        ).select_related('booking', 'booking__student', 'booking__tutor', 'booking__subject')

        for sess in sessions_10m:
            sent = self.send_reminder_for_session(sess, NotificationType.REMINDER_10M)
            if sent:
                counts['10m'] += 1
            else:
                counts['skipped'] += 1

        logger.info(f"Reminders dispatched: 24h={counts['24h']}, 1h={counts['1h']}, 10m={counts['10m']}, skipped={counts['skipped']}")
        return counts

    def send_reminder_for_session(
        self, 
        session: ClassSession, 
        reminder_type: str,
        notify_guardian: bool = True,
        notify_student: bool = True,
        notify_tutor: bool = True
    ) -> bool:
        """
        Dispatches multi-channel (WhatsApp, SMS, Email) reminders across all 3 key stakeholders:
        1. Guardian / Parent: Child progress, lesson overview, and monitoring link.
        2. Student: Direct 1-click classroom join link and preparation prompt.
        3. Tutor: Teaching schedule reminder and tutor launch link.
        
        Enforces NDPR quiet hours and individual user channel preferences.
        Returns True if at least one new notification was delivered.
        """
        student = session.booking.student
        guardian = getattr(student, 'guardian', None)
        tutor = session.booking.tutor

        student_name = f"{student.first_name} {student.last_name}"
        tutor_name = tutor.display_name
        subject_name = session.booking.subject.name
        class_level = session.booking.class_level
        time_display = session.dual_time_display
        site_url = getattr(settings, 'SITE_URL', 'https://edukom.ng').rstrip('/')
        room_url = f"{site_url}/classroom/session/{session.id}/"

        any_sent = False

        # ======================================================================
        # 1. GUARDIAN / PARENT REMINDER DISPATCH
        # ======================================================================
        if notify_guardian and guardian:
            parent_phone = guardian.phone or ''
            parent_email = guardian.email or ''
            parent_name = f"{guardian.first_name} {guardian.last_name}".strip() or "Parent"

            # Check guardian preference if user profile exists
            guardian_pref = None
            if student.user:
                guardian_pref = NotificationPreference.objects.filter(user=student.user).first()

            # Check quiet hours (24h/1h)
            is_quiet = self._is_quiet_hours(guardian_pref, reminder_type)
            if not is_quiet:
                allow_wa = guardian_pref.is_channel_allowed(NotificationChannel.WHATSAPP) if guardian_pref else True
                allow_sms = guardian_pref.is_channel_allowed(NotificationChannel.SMS) if guardian_pref else False
                allow_email = guardian_pref.is_channel_allowed(NotificationChannel.EMAIL) if guardian_pref else True

                # Message copy
                if reminder_type == NotificationType.REMINDER_24H:
                    msg_title = "Edukom Class Reminder: 24 Hours Away"
                    wa_body = (
                        f"*Edukom Learning Reminder*\n\n"
                        f"Hello {guardian.first_name or 'Parent'},\n"
                        f"Your child *{student_name}* has a scheduled lesson tomorrow:\n"
                        f"- *Topic / Lesson:* {session.title}\n"
                        f"- *Subject:* {subject_name} ({class_level})\n"
                        f"- *Tutor:* {tutor_name}\n"
                        f"- *Time:* {time_display}\n\n"
                        f"Please ensure worksheets and notebooks are ready.\n"
                        f"Join Classroom: {room_url}"
                    )
                    sms_body = f"Edukom Reminder: {student_name}'s {subject_name} class with {tutor_name} is tomorrow at {time_display}. Room: {room_url}"
                elif reminder_type == NotificationType.REMINDER_1H:
                    msg_title = "Edukom Class Starting in 1 Hour"
                    wa_body = (
                        f"*Edukom Class Starting in 1 Hour!*\n\n"
                        f"Student: *{student_name}*\n"
                        f"Subject: *{subject_name}* with {tutor_name}\n"
                        f"Time: *{time_display}*\n\n"
                        f"Please test your audio & video connection now.\n"
                        f"Click here to enter room: {room_url}"
                    )
                    sms_body = f"Edukom Alert: {student_name}'s {subject_name} lesson starts in 1 hour ({time_display}). Test audio & join: {room_url}"
                else: # 10 minutes
                    msg_title = "Edukom Class Starting in 10 Minutes"
                    wa_body = (
                        f"*Edukom Class Starting NOW (10 Mins)*\n\n"
                        f"Your live WebRTC classroom is open for *{student_name}* with {tutor_name}.\n"
                        f"Click to join immediately: {room_url}"
                    )
                    sms_body = f"Edukom: {student_name}'s class is starting NOW (10 mins)! Click to join room: {room_url}"

                # 1A. WhatsApp to Guardian
                if parent_phone and allow_wa:
                    wa_key = f"{session.id}_{parent_phone}_{reminder_type}_WHATSAPP"
                    if not NotificationLog.objects.filter(idempotency_key=wa_key).exists():
                        wa_resp = self.wa_service.send_whatsapp_message(parent_phone, wa_body)
                        NotificationLog.objects.create(
                            session=session,
                            user=student.user,
                            recipient_name=parent_name,
                            recipient_phone=parent_phone,
                            recipient_email=parent_email,
                            channel=NotificationChannel.WHATSAPP,
                            notification_type=reminder_type,
                            idempotency_key=wa_key,
                            message_body=wa_body,
                            message_sid=wa_resp.get('sid', ''),
                            status=NotificationStatus.SENT if wa_resp['success'] else NotificationStatus.FAILED,
                            error_message=wa_resp.get('error', ''),
                            sent_at=timezone.now() if wa_resp['success'] else None
                        )
                        any_sent = True

                # 1B. SMS to Guardian (if enabled in preferences or fallback)
                if parent_phone and allow_sms:
                    sms_key = f"{session.id}_{parent_phone}_{reminder_type}_SMS"
                    if not NotificationLog.objects.filter(idempotency_key=sms_key).exists():
                        sms_resp = self.wa_service.send_sms_message(parent_phone, sms_body)
                        NotificationLog.objects.create(
                            session=session,
                            user=student.user,
                            recipient_name=parent_name,
                            recipient_phone=parent_phone,
                            recipient_email=parent_email,
                            channel=NotificationChannel.SMS,
                            notification_type=reminder_type,
                            idempotency_key=sms_key,
                            message_body=sms_body,
                            message_sid=sms_resp.get('sid', ''),
                            status=NotificationStatus.SENT if sms_resp['success'] else NotificationStatus.FAILED,
                            error_message=sms_resp.get('error', ''),
                            sent_at=timezone.now() if sms_resp['success'] else None
                        )
                        any_sent = True

                # 1C. Email to Guardian
                if parent_email and allow_email:
                    email_key = f"{session.id}_{parent_email}_{reminder_type}_EMAIL"
                    if not NotificationLog.objects.filter(idempotency_key=email_key).exists():
                        try:
                            send_mail(
                                subject=f"[{msg_title}] {student_name} - {subject_name}",
                                message=wa_body,
                                from_email=getattr(settings, 'EMAIL_HOST_USER', 'support@edukom.ng'),
                                recipient_list=[parent_email],
                                fail_silently=False
                            )
                            email_status = NotificationStatus.SENT
                            err = ''
                        except Exception as exc:
                            logger.error(f"Email reminder failed to {parent_email}: {str(exc)}")
                            email_status = NotificationStatus.FAILED
                            err = str(exc)

                        NotificationLog.objects.create(
                            session=session,
                            user=student.user,
                            recipient_name=parent_name,
                            recipient_phone=parent_phone,
                            recipient_email=parent_email,
                            channel=NotificationChannel.EMAIL,
                            notification_type=reminder_type,
                            idempotency_key=email_key,
                            message_body=wa_body,
                            status=email_status,
                            error_message=err,
                            sent_at=timezone.now() if email_status == NotificationStatus.SENT else None
                        )
                        any_sent = True

        # ======================================================================
        # 2. STUDENT DIRECT REMINDER DISPATCH (If student phone on file)
        # ======================================================================
        student_user = student.user
        student_phone = ''
        if student_user and hasattr(student_user, 'profile'):
            student_phone = getattr(student_user.profile, 'phone_number', '') or ''

        if notify_student and student_phone:
            student_pref = NotificationPreference.objects.filter(user=student_user).first() if student_user else None
            if not self._is_quiet_hours(student_pref, reminder_type):
                allow_stu_wa = student_pref.is_channel_allowed(NotificationChannel.WHATSAPP) if student_pref else True
                allow_stu_sms = student_pref.is_channel_allowed(NotificationChannel.SMS) if student_pref else False

                if reminder_type == NotificationType.REMINDER_24H:
                    stu_wa = (
                        f"*Edukom Student Reminder*\n\n"
                        f"Hi {student.first_name},\n"
                        f"You have a scheduled *{subject_name}* lesson tomorrow with *{tutor_name}* at *{time_display}*.\n"
                        f"Prepare your notes and worksheets.\n"
                        f"Classroom Link: {room_url}"
                    )
                    stu_sms = f"Hi {student.first_name}, your Edukom {subject_name} class with {tutor_name} is tomorrow at {time_display}. Room: {room_url}"
                elif reminder_type == NotificationType.REMINDER_1H:
                    stu_wa = (
                        f"*Edukom Class in 1 Hour!*\n\n"
                        f"Hi {student.first_name}, your *{subject_name}* lesson with {tutor_name} begins in 1 hour.\n"
                        f"Join room: {room_url}"
                    )
                    stu_sms = f"Hi {student.first_name}, your {subject_name} class starts in 1 hour! Join: {room_url}"
                else: # 10m
                    stu_wa = (
                        f"*Edukom Class Starting NOW!*\n\n"
                        f"Hi {student.first_name}, your live classroom is open! Join now: {room_url}"
                    )
                    stu_sms = f"Hi {student.first_name}, class is starting NOW (10 mins)! Join your classroom: {room_url}"

                if allow_stu_wa:
                    stu_wa_key = f"{session.id}_student_{student_phone}_{reminder_type}_WHATSAPP"
                    if not NotificationLog.objects.filter(idempotency_key=stu_wa_key).exists():
                        wa_resp = self.wa_service.send_whatsapp_message(student_phone, stu_wa)
                        NotificationLog.objects.create(
                            session=session,
                            user=student_user,
                            recipient_name=student_name,
                            recipient_phone=student_phone,
                            recipient_email=student_user.email if student_user else '',
                            channel=NotificationChannel.WHATSAPP,
                            notification_type=reminder_type,
                            idempotency_key=stu_wa_key,
                            message_body=stu_wa,
                            message_sid=wa_resp.get('sid', ''),
                            status=NotificationStatus.SENT if wa_resp['success'] else NotificationStatus.FAILED,
                            error_message=wa_resp.get('error', ''),
                            sent_at=timezone.now() if wa_resp['success'] else None
                        )
                        any_sent = True

                if allow_stu_sms:
                    stu_sms_key = f"{session.id}_student_{student_phone}_{reminder_type}_SMS"
                    if not NotificationLog.objects.filter(idempotency_key=stu_sms_key).exists():
                        sms_resp = self.wa_service.send_sms_message(student_phone, stu_sms)
                        NotificationLog.objects.create(
                            session=session,
                            user=student_user,
                            recipient_name=student_name,
                            recipient_phone=student_phone,
                            recipient_email=student_user.email if student_user else '',
                            channel=NotificationChannel.SMS,
                            notification_type=reminder_type,
                            idempotency_key=stu_sms_key,
                            message_body=stu_sms,
                            message_sid=sms_resp.get('sid', ''),
                            status=NotificationStatus.SENT if sms_resp['success'] else NotificationStatus.FAILED,
                            error_message=sms_resp.get('error', ''),
                            sent_at=timezone.now() if sms_resp['success'] else None
                        )
                        any_sent = True

        # ======================================================================
        # 3. TUTOR REMINDER DISPATCH (WhatsApp & SMS to Tutor)
        # ======================================================================
        tutor_user = tutor.user
        tutor_phone = tutor.phone
        if not tutor_phone and tutor_user and hasattr(tutor_user, 'profile'):
            tutor_phone = tutor_user.profile.phone_number

        # Check if tutor notifications are enabled (default True)
        allow_tutor_notifications = getattr(settings, 'AUTOMATIONS_NOTIFY_TUTOR', True)
        if notify_tutor and tutor_phone and allow_tutor_notifications:
            tutor_pref = NotificationPreference.objects.filter(user=tutor_user).first() if tutor_user else None
            if not self._is_quiet_hours(tutor_pref, reminder_type):
                allow_tutor_wa = tutor_pref.is_channel_allowed(NotificationChannel.WHATSAPP) if tutor_pref else True
                allow_tutor_sms = tutor_pref.is_channel_allowed(NotificationChannel.SMS) if tutor_pref else False

                if reminder_type == NotificationType.REMINDER_24H:
                    tutor_wa = (
                        f"*Edukom Tutor Reminder*\n\n"
                        f"Hello {tutor_name},\n"
                        f"You have a scheduled lesson tomorrow with *{student_name}*:\n"
                        f"- *Subject:* {subject_name} ({class_level})\n"
                        f"- *Lesson Title:* {session.title}\n"
                        f"- *Time:* {time_display}\n\n"
                        f"Launch Tutor Room: {room_url}"
                    )
                    tutor_sms = f"Edukom Tutor: You have a scheduled class with {student_name} ({subject_name}) tomorrow at {time_display}. Launch: {room_url}"
                elif reminder_type == NotificationType.REMINDER_1H:
                    tutor_wa = (
                        f"*Edukom Tutor Reminder: Class in 1 Hour*\n\n"
                        f"Hello {tutor_name},\n"
                        f"Your lesson with *{student_name}* starts in 1 hour ({time_display}).\n"
                        f"Please launch your tutor room 5 minutes early:\n"
                        f"Room Link: {room_url}"
                    )
                    tutor_sms = f"Edukom Tutor: Class with {student_name} starts in 1 hour ({time_display}). Room: {room_url}"
                else: # 10m
                    tutor_wa = (
                        f"*Edukom Tutor Alert: Class Starting in 10 Mins!*\n\n"
                        f"Hello {tutor_name},\n"
                        f"Your student *{student_name}* is preparing to join.\n"
                        f"Click to launch your live classroom now: {room_url}"
                    )
                    tutor_sms = f"Edukom Tutor Alert: Class with {student_name} starts in 10 mins! Enter room: {room_url}"

                # WhatsApp to Tutor
                if allow_tutor_wa:
                    tutor_wa_key = f"{session.id}_tutor_{tutor_phone}_{reminder_type}_WHATSAPP"
                    if not NotificationLog.objects.filter(idempotency_key=tutor_wa_key).exists():
                        wa_resp = self.wa_service.send_whatsapp_message(tutor_phone, tutor_wa)
                        NotificationLog.objects.create(
                            session=session,
                            user=tutor_user,
                            recipient_name=tutor_name,
                            recipient_phone=tutor_phone,
                            recipient_email=tutor_user.email if tutor_user else '',
                            channel=NotificationChannel.WHATSAPP,
                            notification_type=reminder_type,
                            idempotency_key=tutor_wa_key,
                            message_body=tutor_wa,
                            message_sid=wa_resp.get('sid', ''),
                            status=NotificationStatus.SENT if wa_resp['success'] else NotificationStatus.FAILED,
                            error_message=wa_resp.get('error', ''),
                            sent_at=timezone.now() if wa_resp['success'] else None
                        )
                        any_sent = True

                # SMS to Tutor
                if allow_tutor_sms:
                    tutor_sms_key = f"{session.id}_tutor_{tutor_phone}_{reminder_type}_SMS"
                    if not NotificationLog.objects.filter(idempotency_key=tutor_sms_key).exists():
                        sms_resp = self.wa_service.send_sms_message(tutor_phone, tutor_sms)
                        NotificationLog.objects.create(
                            session=session,
                            user=tutor_user,
                            recipient_name=tutor_name,
                            recipient_phone=tutor_phone,
                            recipient_email=tutor_user.email if tutor_user else '',
                            channel=NotificationChannel.SMS,
                            notification_type=reminder_type,
                            idempotency_key=tutor_sms_key,
                            message_body=tutor_sms,
                            message_sid=sms_resp.get('sid', ''),
                            status=NotificationStatus.SENT if sms_resp['success'] else NotificationStatus.FAILED,
                            error_message=sms_resp.get('error', ''),
                            sent_at=timezone.now() if sms_resp['success'] else None
                        )
                        any_sent = True

        return any_sent

    def _is_quiet_hours(self, pref: Optional[NotificationPreference], reminder_type: str) -> bool:
        """Helper checking if current time falls within recipient quiet hours."""
        if not pref:
            return False
        if reminder_type in (NotificationType.REMINDER_24H, NotificationType.REMINDER_1H):
            if pref.quiet_hours_start and pref.quiet_hours_end:
                current_t = timezone.localtime().time()
                if pref.quiet_hours_start <= current_t <= pref.quiet_hours_end:
                    return True
        return False

    def dispatch_subscription_expiry_alerts(self) -> Dict[str, int]:
        """
        Automated Subscription Expiration & Renewal Alerts.
        Scans VideoSubscriptions expiring in 3 days and 1 day, and triggers renewal prompts.
        """
        now = timezone.now()
        counts = {'3d': 0, '1d': 0, 'skipped': 0}

        # 3-Day Window: 70h to 74h
        w3_start = now + timedelta(hours=70)
        w3_end = now + timedelta(hours=74)
        subs_3d = VideoSubscription.objects.filter(
            is_active=True,
            expires_at__gte=w3_start,
            expires_at__lte=w3_end
        ).select_related('user', 'course')

        for sub in subs_3d:
            sent = self.send_subscription_expiry_alert(sub, days_remaining=3)
            if sent:
                counts['3d'] += 1
            else:
                counts['skipped'] += 1

        # 1-Day Window: 22h to 26h
        w1_start = now + timedelta(hours=22)
        w1_end = now + timedelta(hours=26)
        subs_1d = VideoSubscription.objects.filter(
            is_active=True,
            expires_at__gte=w1_start,
            expires_at__lte=w1_end
        ).select_related('user', 'course')

        for sub in subs_1d:
            sent = self.send_subscription_expiry_alert(sub, days_remaining=1)
            if sent:
                counts['1d'] += 1
            else:
                counts['skipped'] += 1

        logger.info(f"Subscription renewal alerts: 3d={counts['3d']}, 1d={counts['1d']}, skipped={counts['skipped']}")
        return counts

    def send_subscription_expiry_alert(self, subscription: VideoSubscription, days_remaining: int) -> bool:
        """
        Dispatches subscription renewal alert via WhatsApp, SMS, and Email.
        """
        user = subscription.user
        pref = NotificationPreference.objects.filter(user=user).first()
        
        course_name = subscription.course.title if subscription.course else "All-Access Master Pass"
        expiry_date_str = subscription.expires_at.strftime('%A, %b %d, %Y')
        site_url = getattr(settings, 'SITE_URL', 'https://edukom.ng').rstrip('/')
        renewal_url = f"{site_url}/payments/initiate/?renew={subscription.id}"

        ntype = NotificationType.SUBSCRIPTION_EXPIRY_3D if days_remaining == 3 else NotificationType.SUBSCRIPTION_EXPIRY_1D
        msg_title = f"Action Required: Edukom Subscription Expires in {days_remaining} Day{'s' if days_remaining > 1 else ''}"
        wa_text = (
            f"*Edukom Subscription Expiry Notice*\n\n"
            f"Hello {user.first_name or user.username},\n"
            f"Your access to *{course_name}* expires in *{days_remaining} day{'s' if days_remaining > 1 else ''}* on {expiry_date_str}.\n\n"
            f"To avoid disruption to your curriculum lessons and recorded sessions, renew today:\n"
            f"Renewal Link: {renewal_url}\n\n"
            f"Need assistance? Contact support@edukom.ng"
        )
        sms_text = f"Edukom Notice: Your access to {course_name} expires in {days_remaining}d ({expiry_date_str}). Renew at: {renewal_url}"

        phone = ''
        if hasattr(user, 'student_profile') and getattr(user.student_profile, 'guardian', None):
            phone = user.student_profile.guardian.phone or ''
        elif hasattr(user, 'profile') and user.profile.phone_number:
            phone = user.profile.phone_number
        email = user.email or ''

        allow_wa = pref.is_channel_allowed(NotificationChannel.WHATSAPP) if pref else True
        allow_sms = pref.is_channel_allowed(NotificationChannel.SMS) if pref else False
        allow_email = pref.is_channel_allowed(NotificationChannel.EMAIL) if pref else True

        any_sent = False

        # 1. WhatsApp
        if phone and allow_wa:
            wa_key = f"sub_expiry_{subscription.id}_{days_remaining}d_WHATSAPP"
            if not NotificationLog.objects.filter(idempotency_key=wa_key).exists():
                wa_resp = self.wa_service.send_whatsapp_message(phone, wa_text)
                NotificationLog.objects.create(
                    session=None,
                    user=user,
                    recipient_name=user.get_full_name() or user.username,
                    recipient_phone=phone,
                    recipient_email=email,
                    channel=NotificationChannel.WHATSAPP,
                    notification_type=ntype,
                    idempotency_key=wa_key,
                    message_body=wa_text,
                    message_sid=wa_resp.get('sid', ''),
                    status=NotificationStatus.SENT if wa_resp['success'] else NotificationStatus.FAILED,
                    error_message=wa_resp.get('error', ''),
                    sent_at=timezone.now() if wa_resp['success'] else None
                )
                any_sent = True

        # 2. SMS (if enabled)
        if phone and allow_sms:
            sms_key = f"sub_expiry_{subscription.id}_{days_remaining}d_SMS"
            if not NotificationLog.objects.filter(idempotency_key=sms_key).exists():
                sms_resp = self.wa_service.send_sms_message(phone, sms_text)
                NotificationLog.objects.create(
                    session=None,
                    user=user,
                    recipient_name=user.get_full_name() or user.username,
                    recipient_phone=phone,
                    recipient_email=email,
                    channel=NotificationChannel.SMS,
                    notification_type=ntype,
                    idempotency_key=sms_key,
                    message_body=sms_text,
                    message_sid=sms_resp.get('sid', ''),
                    status=NotificationStatus.SENT if sms_resp['success'] else NotificationStatus.FAILED,
                    error_message=sms_resp.get('error', ''),
                    sent_at=timezone.now() if sms_resp['success'] else None
                )
                any_sent = True

        # 3. Email
        if email and allow_email:
            email_key = f"sub_expiry_{subscription.id}_{days_remaining}d_EMAIL"
            if not NotificationLog.objects.filter(idempotency_key=email_key).exists():
                try:
                    send_mail(
                        subject=f"[{msg_title}] - {course_name}",
                        message=wa_text,
                        from_email=getattr(settings, 'EMAIL_HOST_USER', 'support@edukom.ng'),
                        recipient_list=[email],
                        fail_silently=False
                    )
                    email_status = NotificationStatus.SENT
                    err = ''
                except Exception as exc:
                    logger.error(f"Subscription alert email failed to {email}: {str(exc)}")
                    email_status = NotificationStatus.FAILED
                    err = str(exc)

                NotificationLog.objects.create(
                    session=None,
                    user=user,
                    recipient_name=user.get_full_name() or user.username,
                    recipient_phone=phone,
                    recipient_email=email,
                    channel=NotificationChannel.EMAIL,
                    notification_type=ntype,
                    idempotency_key=email_key,
                    message_body=wa_text,
                    status=email_status,
                    error_message=err,
                    sent_at=timezone.now() if email_status == NotificationStatus.SENT else None
                )
                any_sent = True

        return any_sent
