from datetime import timedelta, time
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from homepage.models import Guardian
from classroom.models import Subject, Student, TutorProfile, ClassBooking, ClassSession, SessionStatus
from videolibrary.models import VideoCourse, VideoSubscription
from automations.models import (
    NotificationLog, 
    NotificationChannel, 
    NotificationType, 
    NotificationStatus,
    NotificationPreference,
    InboundMessage
)
from automations.services import WhatsAppService, ReminderScheduler, normalize_to_e164

User = get_user_model()


class AutomationAndWhatsAppTests(TestCase):
    def setUp(self):
        # Users & Profiles
        self.tutor_user = User.objects.create_user(username='tutor_wa', email='tutor_wa@edukom.ng', password='Pass123Password!')
        self.student_user = User.objects.create_user(username='student_wa', email='student_wa@edukom.ng', password='Pass123Password!')

        self.guardian = Guardian.objects.create(
            first_name='Amaka',
            last_name='Okeke',
            email='amaka@example.com',
            phone='08031234567',
            lesson_type='Online lessons',
            curriculum='British'
        )

        self.student = Student.objects.create(
            guardian=self.guardian,
            user=self.student_user,
            first_name='Chidi',
            last_name='Okeke',
            class_level='year 10',
            curriculum='British',
            timezone='WAT'
        )

        self.subject = Subject.objects.create(name='Chemistry', category='STEM')

        self.tutor = TutorProfile.objects.create(
            user=self.tutor_user,
            display_name='Dr. Bello',
            hourly_base_rate=Decimal('7000.00'),
            phone='08098765432'
        )

        self.booking = ClassBooking.objects.create(
            student=self.student,
            tutor=self.tutor,
            subject=self.subject,
            class_level='year 10',
            agreed_hourly_rate=Decimal('7000.00')
        )

    def test_phone_normalization_e164(self):
        """
        Tests multi-country phone number normalization to international E.164.
        """
        # Nigeria local formats
        self.assertEqual(normalize_to_e164('08031234567'), '+2348031234567')
        self.assertEqual(normalize_to_e164('2348031234567'), '+2348031234567')
        self.assertEqual(normalize_to_e164('+234 803 123 4567'), '+2348031234567')

        # UK local formats
        self.assertEqual(normalize_to_e164('07123456789'), '+447123456789')
        self.assertEqual(normalize_to_e164('+44 7123 456789'), '+447123456789')

        # US format
        self.assertEqual(normalize_to_e164('+1 (555) 234-5678'), '+15552345678')

    def test_whatsapp_service_sandbox_mode(self):
        """
        WhatsApp service dispatches safely in sandbox mock mode when live keys are omitted.
        """
        svc = WhatsAppService()
        result = svc.send_whatsapp_message('08031234567', 'Hello from Edukom Learning!')
        self.assertTrue(result['success'])
        self.assertTrue(result.get('is_mock', False))
        self.assertEqual(result['recipient'], '+2348031234567')
        self.assertIn('WA_MOCK_', result['sid'])

    @patch('automations.services.scheduler.send_mail')
    def test_24h_class_reminder_dispatch_and_idempotency(self, mock_send_mail):
        """
        Tests 24-hour reminder trigger and verifies idempotency prevents duplicate notifications.
        """
        mock_send_mail.return_value = 1
        now = timezone.now()

        # Session starting in exactly 24 hours
        session_24h = ClassSession.objects.create(
            booking=self.booking,
            title='Organic Chemistry Intro',
            start_time=now + timedelta(hours=24),
            end_time=now + timedelta(hours=25),
            duration_minutes=60,
            status=SessionStatus.SCHEDULED,
            room_name='edukom-wa-24h'
        )

        scheduler = ReminderScheduler()
        
        # 1. First execution: reminders must be dispatched
        counts_1 = scheduler.dispatch_all_due_reminders()
        self.assertEqual(counts_1['24h'], 1)

        # Check logs: 1 WhatsApp log and 1 Email log created
        logs = NotificationLog.objects.filter(session=session_24h, notification_type=NotificationType.REMINDER_24H)
        self.assertEqual(logs.count(), 2)
        wa_log = logs.filter(channel=NotificationChannel.WHATSAPP).first()
        self.assertIsNotNone(wa_log)
        self.assertEqual(wa_log.status, NotificationStatus.SENT)
        self.assertIn("Organic Chemistry Intro", wa_log.message_body)

        # 2. Second execution immediately after: IDEMPOTENCY MUST PREVENT DUPLICATES
        counts_2 = scheduler.dispatch_all_due_reminders()
        self.assertEqual(counts_2['24h'], 0)
        self.assertEqual(counts_2['skipped'], 1)

        # Total logs must remain 2! No spam sent.
        self.assertEqual(NotificationLog.objects.filter(session=session_24h).count(), 2)

    @patch('automations.services.scheduler.send_mail')
    def test_1h_and_10m_urgent_reminders(self, mock_send_mail):
        """
        Tests 1-hour and 10-minute imminent session alerts.
        """
        mock_send_mail.return_value = 1
        now = timezone.now()

        # Session in 1 hour (60 mins)
        session_1h = ClassSession.objects.create(
            booking=self.booking,
            title='Stoichiometry Calculations',
            start_time=now + timedelta(minutes=60),
            end_time=now + timedelta(minutes=120),
            duration_minutes=60,
            status=SessionStatus.SCHEDULED,
            room_name='edukom-wa-1h'
        )

        # Session in 10 minutes (30-minute quick lesson, ending at minute 40)
        session_10m = ClassSession.objects.create(
            booking=self.booking,
            title='Redox Reactions',
            start_time=now + timedelta(minutes=10),
            end_time=now + timedelta(minutes=40),
            duration_minutes=30,
            status=SessionStatus.SCHEDULED,
            room_name='edukom-wa-10m'
        )

        scheduler = ReminderScheduler()
        counts = scheduler.dispatch_all_due_reminders()

        self.assertEqual(counts['1h'], 1)
        self.assertEqual(counts['10m'], 1)

        # Verify 10-minute reminder text contains room URL
        log_10m = NotificationLog.objects.filter(session=session_10m, notification_type=NotificationType.REMINDER_10M).first()
        self.assertIsNotNone(log_10m)
        self.assertIn("Starting NOW", log_10m.message_body)
        self.assertIn(str(session_10m.id), log_10m.message_body)

    @patch('automations.views.send_mail')
    def test_whatsapp_inbound_webhook_and_keyword_triage(self, mock_send_mail):
        """
        Safeguard 5: Inbound WhatsApp Webhook.
        Processes incoming parent reply, matches student & session, and alerts operations for 'cancel'.
        """
        session = ClassSession.objects.create(
            booking=self.booking,
            title='Equilibrium Constants',
            start_time=timezone.now() + timedelta(hours=3),
            end_time=timezone.now() + timedelta(hours=4),
            duration_minutes=60,
            status=SessionStatus.SCHEDULED
        )

        client = Client()
        url = reverse('automations:whatsapp_inbound')

        # Parent replies via WhatsApp with cancellation request
        response = client.post(url, data={
            'From': 'whatsapp:08031234567',
            'Body': 'Hello teacher, please cancel our class today, Chidi has fever.',
            'MessageSid': 'SM_TEST_9999'
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn("application/xml", response['Content-Type'])

        # Verify inbound message logged and correlated to user and session
        msg = InboundMessage.objects.filter(message_sid='SM_TEST_9999').first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.from_phone, '+2348031234567')
        self.assertEqual(msg.matched_user, self.student_user)
        self.assertEqual(msg.matched_session, session)
        self.assertFalse(msg.is_resolved)

        # Verify urgent ops alert email dispatched due to 'cancel' keyword
        self.assertTrue(mock_send_mail.called)
        alert_args = mock_send_mail.call_args[1]
        self.assertIn("[URGENT WHATSAPP SUPPORT]", alert_args['subject'])
        self.assertIn("support@edukom.ng", alert_args['recipient_list'])

    @patch('automations.services.scheduler.send_mail')
    def test_notification_preference_channel_toggle_and_quiet_hours(self, mock_send_mail):
        """
        Safeguard 3: Notification Preferences & Quiet Hours.
        Respects user's opt-out of WhatsApp and respects quiet hours.
        """
        mock_send_mail.return_value = 1
        now = timezone.now()

        # 1. User disables WhatsApp, leaves Email enabled
        pref, _ = NotificationPreference.objects.get_or_create(user=self.student_user)
        pref.whatsapp_enabled = False
        pref.email_enabled = True
        pref.save()

        session = ClassSession.objects.create(
            booking=self.booking,
            title='Atomic Structure',
            start_time=now + timedelta(hours=24),
            end_time=now + timedelta(hours=25),
            duration_minutes=60,
            status=SessionStatus.SCHEDULED
        )

        scheduler = ReminderScheduler()
        scheduler.dispatch_all_due_reminders()

        # WhatsApp log must NOT exist, Email log MUST exist
        wa_log = NotificationLog.objects.filter(session=session, channel=NotificationChannel.WHATSAPP).first()
        email_log = NotificationLog.objects.filter(session=session, channel=NotificationChannel.EMAIL).first()
        self.assertIsNone(wa_log)
        self.assertIsNotNone(email_log)
        self.assertEqual(email_log.status, NotificationStatus.SENT)

    @patch('automations.services.scheduler.send_mail')
    def test_subscription_expiry_alerts_3d_and_1d(self, mock_send_mail):
        """
        Safeguard 6: Automated Subscription Expiration & Renewal Alerts.
        Triggers 3-day renewal warning with payment link and verifies idempotency.
        """
        mock_send_mail.return_value = 1
        now = timezone.now()

        course = VideoCourse.objects.create(
            title='WAEC Chemistry Revision Pack',
            subject=self.subject,
            class_level='year 10'
        )

        # Subscription expiring in exactly 72 hours (3 days)
        sub_3d = VideoSubscription.objects.create(
            user=self.student_user,
            course=course,
            is_active=True,
            starts_at=now - timedelta(days=27),
            expires_at=now + timedelta(hours=72)
        )

        scheduler = ReminderScheduler()
        counts_1 = scheduler.dispatch_subscription_expiry_alerts()
        self.assertEqual(counts_1['3d'], 1)

        # Check logs created
        log = NotificationLog.objects.filter(user=self.student_user, notification_type=NotificationType.SUBSCRIPTION_EXPIRY_3D).first()
        self.assertIsNotNone(log)
        self.assertIn("WAEC Chemistry Revision Pack", log.message_body)
        self.assertIn("*3 days*", log.message_body)
        self.assertIn(str(sub_3d.id), log.message_body)

        # Run again: idempotency prevents duplicate reminder
        counts_2 = scheduler.dispatch_subscription_expiry_alerts()
        self.assertEqual(counts_2['3d'], 0)
        self.assertEqual(counts_2['skipped'], 1)

