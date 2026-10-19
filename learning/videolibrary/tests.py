from datetime import timedelta
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from classroom.models import Subject
from videolibrary.models import VideoCourse, VideoLesson, DRMKey, VideoSubscription, PlaybackSession
from videolibrary.services import DRMService

User = get_user_model()


class VideoDRMTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Users
        self.subscriber_user = User.objects.create_user(username='sub_alice', email='alice@edukom.ng', password='Pass123Password!')
        self.unsubscribed_user = User.objects.create_user(username='unsub_bob', email='bob@example.com', password='Pass123Password!')
        self.staff_user = User.objects.create_superuser(username='staff_dan', email='dan@edukom.ng', password='Pass123Password!')

        # Subject & Course
        self.subject = Subject.objects.create(name='Mathematics', category='STEM')
        self.course = VideoCourse.objects.create(
            title='IGCSE Mathematics Masterclass',
            description='Complete revision covering algebra, geometry, and calculus.',
            subject=self.subject,
            class_level='year 10',
            is_subscription_only=True
        )

        # Lesson
        self.lesson = VideoLesson.objects.create(
            course=self.course,
            title='Lesson 1: Quadratic Equations Demystified',
            description='In-depth breakdown of factoring and quadratic formula.',
            order=1,
            duration_seconds=3600,
            is_drm_protected=True
        )

        # Active Subscription for Alice (valid for next 30 days)
        self.subscription = VideoSubscription.objects.create(
            user=self.subscriber_user,
            course=self.course,
            is_active=True,
            starts_at=timezone.now() - timedelta(days=1),
            expires_at=timezone.now() + timedelta(days=30)
        )

    def test_drm_key_generation_and_storage(self):
        """
        Verify that 128-bit AES cryptographic keys and IVs are correctly provisioned.
        """
        key = DRMService.get_or_create_drm_key(self.lesson)
        self.assertIsNotNone(key.id)
        self.assertEqual(len(key.key_hex), 32)  # 16 bytes = 32 hex chars
        self.assertEqual(len(key.iv_hex), 32)

        # Raw key must be exactly 16 bytes (128-bit AES)
        raw_key = bytes.fromhex(key.key_hex)
        self.assertEqual(len(raw_key), 16)

    def test_playback_ticket_issued_to_subscribed_student(self):
        """
        Subscribed student successfully receives a short-lived playback ticket.
        """
        ok, session, reason = DRMService.create_playback_session(
            user=self.subscriber_user,
            lesson=self.lesson,
            client_ip='197.210.65.12'
        )
        self.assertTrue(ok)
        self.assertIsNotNone(session)
        self.assertFalse(session.is_expired)
        self.assertEqual(session.ip_address, '197.210.65.12')

    def test_playback_ticket_blocked_for_unsubscribed_user(self):
        """
        Unsubscribed user is denied streaming authorization.
        """
        ok, session, reason = DRMService.create_playback_session(
            user=self.unsubscribed_user,
            lesson=self.lesson,
            client_ip='102.89.23.44'
        )
        self.assertFalse(ok)
        self.assertIsNone(session)
        self.assertIn("subscription required", reason.lower())

    def test_drm_key_exchange_authorized(self):
        """
        Tokenized key request from authorized playback ticket releases 16-byte AES-128 key.
        """
        DRMService.get_or_create_drm_key(self.lesson)
        _, session, _ = DRMService.create_playback_session(
            user=self.subscriber_user,
            lesson=self.lesson,
            client_ip='127.0.0.1'
        )

        url = reverse('videolibrary:drm_key', kwargs={'token': session.token})
        response = self.client.get(url, REMOTE_ADDR='127.0.0.1')
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/octet-stream')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(len(response.content), 16)  # Exactly 16 bytes binary AES key

    def test_drm_key_exchange_unauthorized_token_rejected(self):
        """
        Tampered or bogus DRM key request is rejected with HTTP 403 Forbidden.
        """
        url = reverse('videolibrary:drm_key', kwargs={'token': 'bogus-tampered-token-12345'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_hls_manifest_generation(self):
        """
        HLS M3U8 playlist dynamically includes the AES-128 encryption key directive.
        """
        manifest = DRMService.generate_hls_manifest(self.lesson, "https://edukom.ng/video/drm-key/sample-token/")
        self.assertIn("#EXT-X-KEY:METHOD=AES-128", manifest)
        self.assertIn("sample-token", manifest)
        self.assertIn("#EXTINF:10.0", manifest)

    def test_player_view_renders_dynamic_watermark(self):
        """
        Player view contains user email, client IP, and anti-piracy listeners.
        """
        self.client.force_login(self.subscriber_user)
        url = reverse('videolibrary:watch_lesson', kwargs={'lesson_id': self.lesson.id})
        response = self.client.get(url, REMOTE_ADDR='197.210.45.10')

        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn("alice@edukom.ng", content)
        self.assertIn("197.210.45.10", content)
        self.assertIn("controlsList=\"nodownload noplaybackrate\"", content)
        self.assertIn("oncontextmenu=\"return false;\"", content)

    def test_concurrent_stream_guard_revocation(self):
        """
        Safeguard 1: Concurrent Stream Guard.
        When Alice opens a second stream, her first stream is immediately revoked.
        """
        # Session 1 on Laptop
        ok1, sess1, _ = DRMService.create_playback_session(self.subscriber_user, self.lesson, client_ip='197.210.1.1')
        self.assertTrue(ok1)
        self.assertTrue(sess1.is_active)

        # Session 2 on Mobile Tablet
        ok2, sess2, _ = DRMService.create_playback_session(self.subscriber_user, self.lesson, client_ip='197.210.1.2')
        self.assertTrue(ok2)
        self.assertTrue(sess2.is_active)

        # Session 1 must now be revoked!
        sess1.refresh_from_db()
        self.assertFalse(sess1.is_active)
        self.assertTrue(sess1.is_revoked)

        # Heartbeat from Session 1 is denied
        self.client.force_login(self.subscriber_user)
        url = reverse('videolibrary:heartbeat', kwargs={'lesson_id': self.lesson.id})
        resp = self.client.post(url, data={'token': sess1.token, 'current_time': 120})
        self.assertEqual(resp.status_code, 403)
        self.assertIn('active', resp.json())
        self.assertFalse(resp.json()['active'])

    def test_watch_progress_and_resume_engine(self):
        """
        Safeguard 4: Student Watch Progress & Resume.
        Heartbeat saves watch position and marks completion at 90% threshold.
        """
        self.client.force_login(self.subscriber_user)
        _, sess, _ = DRMService.create_playback_session(self.subscriber_user, self.lesson, client_ip='127.0.0.1')

        # 1. Send heartbeat at 500s
        url = reverse('videolibrary:heartbeat', kwargs={'lesson_id': self.lesson.id})
        resp = self.client.post(url, data={'token': sess.token, 'current_time': 500})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['active'])
        self.assertEqual(resp.json()['last_watched_seconds'], 500)

        # Query progress endpoint
        prog_url = reverse('videolibrary:watch_progress', kwargs={'lesson_id': self.lesson.id})
        prog_resp = self.client.get(prog_url)
        self.assertEqual(prog_resp.status_code, 200)
        self.assertTrue(prog_resp.json()['has_progress'])
        self.assertEqual(prog_resp.json()['last_watched_seconds'], 500)
        self.assertFalse(prog_resp.json()['is_completed'])

        # 2. Send heartbeat at 3300s (>= 90% of 3600s duration) -> should complete
        resp_complete = self.client.post(url, data={'token': sess.token, 'current_time': 3300})
        self.assertEqual(resp_complete.status_code, 200)
        self.assertTrue(resp_complete.json()['is_completed'])

    def test_live_recording_ingestion_with_ndpr_consent(self):
        """
        Safeguards 2 & 8: Live Recording Ingestion with NDPR Minor Consent.
        Ingests Daily.co recording into DRM library when consent is present.
        """
        from decimal import Decimal
        from homepage.models import Guardian
        from classroom.models import Student, TutorProfile, ClassBooking, ClassSession, SessionStatus

        # Setup student with guardian and consent
        guardian = Guardian.objects.create(
            first_name='Parent',
            last_name='Consent',
            email='guardian_consent@edukom.ng',
            phone='08011223344'
        )
        student_user = User.objects.create_user(username='consent_student', email='cstudent@edukom.ng', password='Pass123Password!')
        student = Student.objects.create(
            guardian=guardian,
            user=student_user,
            first_name='Kene',
            last_name='Consent',
            class_level='year 10'
        )
        tutor_user = User.objects.create_user(username='tutor_rec', email='trec@edukom.ng', password='Pass123Password!')
        tutor = TutorProfile.objects.create(
            user=tutor_user,
            display_name='Prof. Okonkwo',
            hourly_base_rate=Decimal('6000.00')
        )
        # Booking WITH consent
        booking = ClassBooking.objects.create(
            student=student,
            tutor=tutor,
            subject=self.subject,
            class_level='year 10',
            agreed_hourly_rate=Decimal('6000.00'),
            recording_consent_given=True
        )
        session = ClassSession.objects.create(
            booking=booking,
            title='Calculus Fundamentals',
            start_time=timezone.now() - timedelta(hours=2),
            end_time=timezone.now() - timedelta(hours=1),
            duration_minutes=60,
            status=SessionStatus.COMPLETED
        )

        # Ingestion succeeds
        ok, lesson, reason = DRMService.ingest_live_class_recording(
            session_id=str(session.id),
            recording_url='https://daily.co/recordings/edukom-rec-123.mp4',
            duration_seconds=3600
        )
        self.assertTrue(ok)
        self.assertIsNotNone(lesson)
        self.assertEqual(lesson.session, session)
        self.assertTrue(lesson.is_drm_protected)
        self.assertEqual(lesson.ingestion_status, 'READY')
        self.assertIsNotNone(lesson.drm_key)

    def test_live_recording_ingestion_rejected_without_ndpr_consent(self):
        """
        Safeguard 8: Minor Recording Consent Guard.
        Strictly rejects recording ingestion if guardian/student consent was not granted.
        """
        from decimal import Decimal
        from homepage.models import Guardian
        from classroom.models import Student, TutorProfile, ClassBooking, ClassSession, SessionStatus

        guardian = Guardian.objects.create(
            first_name='Parent',
            last_name='NoConsent',
            email='guardian_noconsent@edukom.ng',
            phone='08099887766'
        )
        student_user = User.objects.create_user(username='noconsent_student', email='noconsent@edukom.ng', password='Pass123Password!')
        student = Student.objects.create(
            guardian=guardian,
            user=student_user,
            first_name='Tobe',
            last_name='NoConsent',
            class_level='year 10'
        )
        tutor_user = User.objects.create_user(username='tutor_noconsent', email='tnoconsent@edukom.ng', password='Pass123Password!')
        tutor = TutorProfile.objects.create(
            user=tutor_user,
            display_name='Dr. Eze',
            hourly_base_rate=Decimal('6000.00')
        )
        # Booking WITHOUT consent (recording_consent_given=False)
        booking = ClassBooking.objects.create(
            student=student,
            tutor=tutor,
            subject=self.subject,
            class_level='year 10',
            agreed_hourly_rate=Decimal('6000.00'),
            recording_consent_given=False
        )
        session = ClassSession.objects.create(
            booking=booking,
            title='Unconsented Class Session',
            start_time=timezone.now() - timedelta(hours=2),
            end_time=timezone.now() - timedelta(hours=1),
            duration_minutes=60,
            status=SessionStatus.COMPLETED
        )

        ok, lesson, reason = DRMService.ingest_live_class_recording(
            session_id=str(session.id),
            recording_url='https://daily.co/recordings/unconsented.mp4',
            duration_seconds=3600
        )
        self.assertFalse(ok)
        self.assertIsNone(lesson)
        self.assertIn("NDPR Compliance Rejection", reason)

    def test_adaptive_bitrate_master_manifest(self):
        """
        Safeguard 7: Adaptive Bitrate Multi-Quality HLS Master Manifest.
        Verifies presence of 1080p, 720p, 480p, and 360p Data Saver variants.
        """
        _, sess, _ = DRMService.create_playback_session(self.subscriber_user, self.lesson, client_ip='127.0.0.1')

        # Master manifest
        url = reverse('videolibrary:hls_master', kwargs={'lesson_id': self.lesson.id, 'token': sess.token})
        resp = self.client.get(url, REMOTE_ADDR='127.0.0.1')
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')

        self.assertIn("#EXTM3U", content)
        self.assertIn("360p Data Saver", content)
        self.assertIn("BANDWIDTH=400000", content)
        self.assertIn("BANDWIDTH=1800000", content)
        self.assertIn("BANDWIDTH=3500000", content)

        # 360p Data Saver variant media playlist
        variant_url = reverse('videolibrary:hls_variant', kwargs={'lesson_id': self.lesson.id, 'token': sess.token}) + '?resolution=360p'
        v_resp = self.client.get(variant_url, REMOTE_ADDR='127.0.0.1')
        self.assertEqual(v_resp.status_code, 200)
        v_content = v_resp.content.decode('utf-8')
        self.assertIn("#EXT-X-KEY:METHOD=AES-128", v_content)
        self.assertIn("segment_360p_000.ts", v_content)

