from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError

from homepage.models import Guardian
from classroom.models import (
    Subject, 
    Student, 
    TutorProfile, 
    ClassBooking, 
    ClassSession, 
    SessionStatus, 
    BookingStatus, 
    AttendanceRecord,
    LessonResource,
    LessonFeedback,
    ClassroomSignal
)
from classroom.services import DailyVideoService
from classroom.timezones import format_dual_session_time, resolve_timezone
from payroll.models import PayrollRun, PayrollRunStatus

User = get_user_model()


class ClassroomSecurityAndLMSTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Users
        self.tutor_user = User.objects.create_user(username='tutor_sam', email='sam@edukom.ng', password='Pass123Password!')
        self.student_user = User.objects.create_user(username='student_leo', email='leo@edukom.ng', password='Pass123Password!')
        self.intruder_user = User.objects.create_user(username='intruder', email='intruder@example.com', password='Pass123Password!')
        self.admin_user = User.objects.create_superuser(username='lms_admin', email='admin@edukom.ng', password='Pass123Password!')

        # Profiles
        self.guardian = Guardian.objects.create(
            first_name='Parent',
            last_name='Leo',
            email='leo@edukom.ng',
            phone='08012345678',
            lesson_type='Online lessons',
            curriculum='British'
        )

        self.student = Student.objects.create(
            guardian=self.guardian,
            user=self.student_user,
            first_name='Leo',
            last_name='Student',
            class_level='year 10',
            curriculum='British',
            timezone='WAT'
        )

        self.subject = Subject.objects.create(name='Mathematics', category='STEM')

        self.tutor = TutorProfile.objects.create(
            user=self.tutor_user,
            display_name='Samuel Tutor',
            hourly_base_rate=Decimal('6000.00'),
            is_verified=True
        )

        # Booking
        self.booking = ClassBooking.objects.create(
            student=self.student,
            tutor=self.tutor,
            subject=self.subject,
            class_level='year 10',
            curriculum='British',
            delivery_mode='Online lessons',
            client_timezone='WAT',
            agreed_hourly_rate=Decimal('6000.00'),
            status=BookingStatus.ACTIVE
        )

        # Scheduled Session
        self.session = ClassSession.objects.create(
            booking=self.booking,
            title='Algebra & Functions',
            start_time=timezone.now(),
            end_time=timezone.now() + timezone.timedelta(hours=1),
            duration_minutes=60,
            status=SessionStatus.SCHEDULED,
            room_name='edukom-test-room-01'
        )

    def test_daily_video_service_mock_mode(self):
        svc = DailyVideoService()
        room = svc.create_or_get_room(self.session)
        self.assertTrue(room['success'])
        self.assertIn('edukom-', room['room_name'])

        token = svc.generate_meeting_token(
            room_name=room['room_name'],
            user_name='Samuel Tutor',
            user_id=str(self.tutor_user.id),
            is_owner=True
        )
        self.assertTrue(token['success'])

    def test_authorized_tutor_can_enter_classroom(self):
        self.client.force_login(self.tutor_user)
        url = reverse('classroom:live_room', kwargs={'session_id': self.session.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Algebra", response.content.decode('utf-8'))

        # Attendance record must be logged automatically
        self.assertEqual(AttendanceRecord.objects.filter(session=self.session, user=self.tutor_user).count(), 1)
        self.session.refresh_from_db()
        self.assertIsNotNone(self.session.tutor_joined_at)

    def test_authorized_student_can_enter_classroom(self):
        self.client.force_login(self.student_user)
        url = reverse('classroom:live_room', kwargs={'session_id': self.session.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Attendance record must be logged automatically
        self.assertEqual(AttendanceRecord.objects.filter(session=self.session, user=self.student_user).count(), 1)
        self.session.refresh_from_db()
        self.assertIsNotNone(self.session.student_joined_at)

    def test_unauthorized_user_blocked_from_classroom(self):
        """
        BOLA / IDOR Defense Check:
        Ensure random authenticated user cannot eavesdrop or room-bomb another person's lesson.
        """
        self.client.force_login(self.intruder_user)
        url = reverse('classroom:live_room', kwargs={'session_id': self.session.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_submit_lesson_notes_marks_completed(self):
        self.client.force_login(self.tutor_user)
        url = reverse('classroom:submit_notes', kwargs={'session_id': self.session.id})
        data = {
            'lesson_topic': 'Factoring Polynomials',
            'lesson_notes': 'Leo understood the factoring method quickly.',
            'homework_assigned': 'Ex 4B Q1-10'
        }
        response = self.client.post(url, data=data)
        self.assertEqual(response.status_code, 302)

        self.session.refresh_from_db()
        self.assertEqual(self.session.status, SessionStatus.COMPLETED)
        self.assertEqual(self.session.lesson_topic, 'Factoring Polynomials')
        self.assertIsNotNone(self.session.tutor_left_at)

    def test_direct_lms_payroll_dispatch(self):
        """
        Tests the direct bridge from LMS completed classes to Payroll engine.
        Eliminates the need for manual TutorCruncher exports!
        """
        # Mark session completed
        self.session.status = SessionStatus.COMPLETED
        self.session.save()

        self.client.force_login(self.admin_user)
        url = reverse('classroom:dispatch_payroll')
        response = self.client.post(url, data={
            'title': 'Automated November Payroll',
            'period_start': timezone.now().date(),
            'period_end': timezone.now().date(),
        })

        self.assertEqual(response.status_code, 302)

        # Verify PayrollRun created
        payroll_run = PayrollRun.objects.filter(title='Automated November Payroll').first()
        self.assertIsNotNone(payroll_run)
        self.assertEqual(payroll_run.status, PayrollRunStatus.CALCULATED)
        self.assertGreater(payroll_run.total_gross, Decimal('0.00'))

        # Verify session marked as processed so it cannot be double-paid
        self.session.refresh_from_db()
        self.assertTrue(self.session.is_payroll_processed)

    def test_double_booking_tutor_conflict_prevented(self):
        """
        Safeguard 1: Double-Booking Conflict Engine
        Ensures a tutor cannot be scheduled for two overlapping classes simultaneously.
        """
        conflict_session = ClassSession(
            booking=self.booking,
            title='Conflicting Geometry Lesson',
            start_time=self.session.start_time + timezone.timedelta(minutes=15),
            end_time=self.session.end_time + timezone.timedelta(minutes=15),
            duration_minutes=60,
            status=SessionStatus.SCHEDULED,
            room_name='edukom-conflict-room'
        )
        with self.assertRaises(ValidationError) as ctx:
            conflict_session.save()
        self.assertIn("Schedule conflict for tutor", str(ctx.exception))

    def test_double_booking_student_conflict_prevented(self):
        """
        Safeguard 1: Double-Booking Conflict Engine
        Ensures a student cannot be scheduled for two classes simultaneously across different tutors.
        """
        # Create second tutor
        second_tutor_user = User.objects.create_user(username='tutor_ada', email='ada@edukom.ng', password='Pass123Password!')
        second_tutor = TutorProfile.objects.create(
            user=second_tutor_user,
            display_name='Ada Physics',
            hourly_base_rate=Decimal('6500.00'),
            is_verified=True
        )
        second_booking = ClassBooking.objects.create(
            student=self.student,
            tutor=second_tutor,
            subject=self.subject,
            class_level='year 10',
            agreed_hourly_rate=Decimal('6500.00'),
            status=BookingStatus.ACTIVE
        )

        student_conflict_session = ClassSession(
            booking=second_booking,
            title='Overlapping Physics Session',
            start_time=self.session.start_time + timezone.timedelta(minutes=10),
            end_time=self.session.end_time + timezone.timedelta(minutes=10),
            duration_minutes=60,
            status=SessionStatus.SCHEDULED,
            room_name='edukom-conflict-student'
        )
        with self.assertRaises(ValidationError) as ctx:
            student_conflict_session.save()
        self.assertIn("Schedule conflict for student", str(ctx.exception))

    def test_non_overlapping_session_scheduled_successfully(self):
        """
        Ensure valid non-overlapping sessions save without conflict.
        """
        future_session = ClassSession.objects.create(
            booking=self.booking,
            title='Advanced Trigonometry',
            start_time=self.session.end_time + timezone.timedelta(hours=2),
            end_time=self.session.end_time + timezone.timedelta(hours=3),
            duration_minutes=60,
            status=SessionStatus.SCHEDULED,
            room_name='edukom-future-room'
        )
        self.assertIsNotNone(future_session.id)

    def test_multi_timezone_dual_display(self):
        """
        Safeguard 2: Multi-Timezone Dual-Display & DST Guard
        Tests conversion and dual-timestamp rendering across UK (GMT/BST) and Nigeria (WAT).
        """
        # Set client to London
        self.booking.client_timezone = 'Europe/London'
        self.booking.save()

        dual_display = self.session.dual_time_display
        self.assertIn("Lagos", dual_display)
        self.assertIn("London", dual_display)

    @patch('classroom.notifications.send_mail')
    def test_submit_notes_triggers_parent_progress_report(self, mock_send_mail):
        """
        Safeguard 3: Automated Post-Lesson Parent Progress Report
        Submitting lesson notes marks session completed and sends progress email to parent.
        """
        mock_send_mail.return_value = 1
        self.client.force_login(self.tutor_user)
        url = reverse('classroom:submit_notes', kwargs={'session_id': self.session.id})
        
        response = self.client.post(url, data={
            'lesson_topic': 'Quadratic Formula Mastery',
            'lesson_notes': 'Leo solved all standard equations without assistance.',
            'homework_assigned': 'Complete worksheet chapter 5.'
        })
        self.assertEqual(response.status_code, 302)

        # Check email sent
        mock_send_mail.assert_called_once()
        args, kwargs = mock_send_mail.call_args
        self.assertIn(self.guardian.email, kwargs.get('recipient_list', []))
        self.assertIn("Quadratic Formula Mastery", kwargs.get('message', ''))

    def test_lesson_resource_upload_and_bola_download(self):
        """
        Safeguard 4: Lesson Resource & Worksheet Sharing
        Validates secure upload and BOLA-protected download.
        """
        self.client.force_login(self.tutor_user)
        upload_url = reverse('classroom:upload_resource', kwargs={'session_id': self.session.id})

        # 1. Valid PDF upload
        test_file = SimpleUploadedFile("algebra_worksheet.pdf", b"%PDF-1.4 sample pdf content", content_type="application/pdf")
        response = self.client.post(upload_url, {
            'title': 'Week 3 Worksheet',
            'resource_file': test_file
        })
        self.assertEqual(response.status_code, 302)

        resource = LessonResource.objects.filter(session=self.session, title='Week 3 Worksheet').first()
        self.assertIsNotNone(resource)
        self.assertEqual(resource.uploaded_by, self.tutor_user)

        # 2. Block dangerous executable upload (.exe / .sh)
        malicious_file = SimpleUploadedFile("malware.exe", b"executable payload", content_type="application/octet-stream")
        bad_response = self.client.post(upload_url, {
            'title': 'Trojan Lesson',
            'resource_file': malicious_file
        })
        self.assertFalse(LessonResource.objects.filter(title='Trojan Lesson').exists())

        # 3. BOLA/IDOR Download Defense: Intruder blocked from downloading resource
        self.client.force_login(self.intruder_user)
        download_url = reverse('classroom:download_resource', kwargs={'resource_id': resource.id})
        download_response = self.client.get(download_url)
        self.assertEqual(download_response.status_code, 403)

        # 4. Authorized student CAN download
        self.client.force_login(self.student_user)
        auth_download = self.client.get(download_url)
        self.assertEqual(auth_download.status_code, 200)

    def test_lesson_resource_ajax_upload_and_live_sync_signal(self):
        """
        Live Worksheet Sync:
        Validates async AJAX upload without page reload, JSON response,
        and automatic real-time ClassroomSignal dispatch for student synchronization.
        """
        self.client.force_login(self.tutor_user)
        upload_url = reverse('classroom:upload_resource', kwargs={'session_id': self.session.id})

        test_pdf = SimpleUploadedFile("live_quadratics.pdf", b"%PDF-1.4 worksheet content", content_type="application/pdf")
        response = self.client.post(
            upload_url,
            {
                'title': 'Live Quadratic Equations Worksheet',
                'resource_type': 'WORKSHEET',
                'resource_file': test_pdf
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['resource']['title'], 'Live Quadratic Equations Worksheet')
        self.assertIn('download_url', data['resource'])
        self.assertTrue(len(data['resource']['download_url']) > 0)

        # Verify LessonResource was saved
        resource = LessonResource.objects.filter(session=self.session, title='Live Quadratic Equations Worksheet').first()
        self.assertIsNotNone(resource)
        self.assertEqual(resource.uploaded_by, self.tutor_user)

        # Verify ClassroomSignal was automatically created for live peer sync
        signal = ClassroomSignal.objects.filter(session=self.session, signal_type='new_resource').first()
        self.assertIsNotNone(signal)
        self.assertEqual(signal.sender, self.tutor_user)
        self.assertEqual(signal.payload['id'], str(resource.id))
        self.assertEqual(signal.payload['title'], 'Live Quadratic Equations Worksheet')

        # Verify student receives the signal when polling
        self.client.force_login(self.student_user)
        signals_url = reverse('classroom:poll_signals', kwargs={'session_id': self.session.id})
        poll_resp = self.client.get(signals_url + '?after_id=0')
        self.assertEqual(poll_resp.status_code, 200)
        poll_data = poll_resp.json()
        self.assertTrue(any(s['signal_type'] == 'new_resource' for s in poll_data['signals']))


    def test_cancellation_policy_advance_notice(self):
        """
        Safeguard 5: Structured Cancellation Policy (>24 hours notice)
        No penalty or tutor compensation fee charged.
        """
        far_future_session = ClassSession.objects.create(
            booking=self.booking,
            title='Far Future Class',
            start_time=timezone.now() + timezone.timedelta(days=3),
            end_time=timezone.now() + timezone.timedelta(days=3, hours=1),
            duration_minutes=60,
            status=SessionStatus.SCHEDULED,
            room_name='edukom-far-future'
        )

        self.client.force_login(self.student_user)
        cancel_url = reverse('classroom:cancel_session', kwargs={'session_id': far_future_session.id})
        response = self.client.post(cancel_url, {'cancellation_reason': 'Family travel'})
        self.assertEqual(response.status_code, 302)

        far_future_session.refresh_from_db()
        self.assertEqual(far_future_session.status, SessionStatus.CANCELLED)
        self.assertFalse(far_future_session.is_payable_late_cancel)
        self.assertEqual(far_future_session.late_cancel_fee_multiplier, Decimal('0.00'))

    def test_cancellation_policy_short_notice_compensates_tutor_in_payroll(self):
        """
        Safeguard 5: Structured Cancellation Policy (<24h notice)
        Tutor is compensated 50% for short notice cancellation and it flows directly into payroll.
        """
        near_future_session = ClassSession.objects.create(
            booking=self.booking,
            title='Short Notice Session',
            start_time=timezone.now() + timezone.timedelta(hours=6),
            end_time=timezone.now() + timezone.timedelta(hours=7),
            duration_minutes=60,
            status=SessionStatus.SCHEDULED,
            room_name='edukom-short-notice'
        )

        self.client.force_login(self.student_user)
        cancel_url = reverse('classroom:cancel_session', kwargs={'session_id': near_future_session.id})
        response = self.client.post(cancel_url, {'cancellation_reason': 'Student fell ill'})
        self.assertEqual(response.status_code, 302)

        near_future_session.refresh_from_db()
        self.assertEqual(near_future_session.status, SessionStatus.CANCELLED)
        self.assertTrue(near_future_session.is_payable_late_cancel)
        self.assertEqual(near_future_session.late_cancel_fee_multiplier, Decimal('0.50'))

        # Verify it dispatches into payroll as 0.50 hours payout
        self.client.force_login(self.admin_user)
        dispatch_url = reverse('classroom:dispatch_payroll')
        disp_resp = self.client.post(dispatch_url, {
            'title': 'December Late Cancel Payroll',
            'period_start': timezone.now().date(),
            'period_end': timezone.now().date(),
        })
        self.assertEqual(disp_resp.status_code, 302)

        near_future_session.refresh_from_db()
        self.assertTrue(near_future_session.is_payroll_processed)

        payroll_run = PayrollRun.objects.filter(title='December Late Cancel Payroll').first()
        self.assertIsNotNone(payroll_run)
        # 60 mins * 0.50 multiplier = 0.5 hours
        tutor_item = payroll_run.items.first()
        self.assertEqual(tutor_item.total_hours, Decimal('0.50'))
        self.assertEqual(tutor_item.calculated_gross_pay, Decimal('3500.00'))  # 0.5 * 7000 year 10 tier rate

    @patch('classroom.notifications.send_mail')
    def test_qa_feedback_and_low_rating_alert(self, mock_send_mail):
        """
        Safeguard 6: Parent Lesson Rating & QA Feedback
        Submitting <= 3 stars triggers an urgent alert to support@edukom.ng.
        """
        self.session.status = SessionStatus.COMPLETED
        self.session.save()

        self.client.force_login(self.student_user)
        feedback_url = reverse('classroom:submit_feedback', kwargs={'session_id': self.session.id})
        
        response = self.client.post(feedback_url, {
            'rating': 2,
            'audio_video_quality': 2,
            'tutor_punctuality': 3,
            'student_engagement': 2,
            'comments': 'Audio cut out frequently and tutor was late.'
        })
        self.assertEqual(response.status_code, 302)

        feedback = LessonFeedback.objects.filter(session=self.session).first()
        self.assertIsNotNone(feedback)
        self.assertEqual(feedback.rating, 2)

        # Urgent QA alert must have been emailed
        mock_send_mail.assert_called_once()
        args, kwargs = mock_send_mail.call_args
        self.assertIn("[URGENT QA ALERT]", kwargs.get('subject', ''))
        self.assertIn("Audio cut out frequently", kwargs.get('message', ''))

    def test_instant_session_launch(self):
        """
        Tutor launches an immediate virtual live classroom.
        """
        self.session.status = SessionStatus.COMPLETED
        self.session.save()

        self.client.force_login(self.tutor_user)
        url = reverse('classroom:instant_session')
        response = self.client.post(url, {
            'booking_id': str(self.booking.id),
            'title': 'Instant Algebra Support',
            'duration_minutes': 60,
            'lesson_topic': 'Factoring Quadratics'
        })
        self.assertEqual(response.status_code, 302)

        instant_sess = ClassSession.objects.filter(booking=self.booking, title='Instant Algebra Support').first()
        self.assertIsNotNone(instant_sess)
        self.assertEqual(instant_sess.status, SessionStatus.IN_PROGRESS)
        self.assertIsNotNone(instant_sess.tutor_joined_at)
        self.assertIn(str(instant_sess.id), response.url)

    def test_schedule_session_flow(self):
        """
        Tutor schedules a class session for an active booking.
        """
        self.client.force_login(self.tutor_user)
        url = reverse('classroom:schedule_session')
        tomorrow = timezone.now().date() + timezone.timedelta(days=2)
        response = self.client.post(url, {
            'booking_id': str(self.booking.id),
            'title': 'Trigonometry & Pythagoras',
            'date': tomorrow.strftime('%Y-%m-%d'),
            'start_time': '16:00',
            'duration_minutes': 60,
            'lesson_topic': 'Sine and Cosine Rules'
        })
        self.assertEqual(response.status_code, 302)

        scheduled_sess = ClassSession.objects.filter(title='Trigonometry & Pythagoras').first()
        self.assertIsNotNone(scheduled_sess)
        self.assertEqual(scheduled_sess.duration_minutes, 60)
        self.assertEqual(scheduled_sess.status, SessionStatus.SCHEDULED)

    def test_resource_and_video_upload_vault(self):
        """
        Tutor uploads a study material and an educational video link to the vault.
        """
        self.client.force_login(self.tutor_user)
        upload_url = reverse('classroom:upload_material')

        # 1. Upload worksheet file
        sample_pdf = SimpleUploadedFile("exercises_ch4.pdf", b"%PDF-1.4 dummy pdf content", content_type="application/pdf")
        resp1 = self.client.post(upload_url, {
            'booking_id': str(self.booking.id),
            'title': 'Chapter 4 Exercises PDF',
            'resource_type': 'WORKSHEET',
            'description': 'Practice sheet for homework',
            'resource_file': sample_pdf
        })
        self.assertEqual(resp1.status_code, 302)
        res_file = LessonResource.objects.filter(title='Chapter 4 Exercises PDF').first()
        self.assertIsNotNone(res_file)
        self.assertEqual(res_file.resource_type, 'WORKSHEET')

        # 2. Upload video URL
        resp2 = self.client.post(upload_url, {
            'booking_id': str(self.booking.id),
            'title': 'Vectors and Transformations Video Lesson',
            'resource_type': 'VIDEO',
            'video_url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            'description': 'Introductory recorded lesson'
        })
        self.assertEqual(resp2.status_code, 302)
        res_video = LessonResource.objects.filter(title='Vectors and Transformations Video Lesson').first()
        self.assertIsNotNone(res_video)
        self.assertEqual(res_video.resource_type, 'VIDEO')
        self.assertEqual(res_video.video_url, 'https://www.youtube.com/watch?v=dQw4w9WgXcQ')

    def test_delete_resource_security(self):
        """
        Only the resource uploader/tutor can delete materials from the vault.
        """
        res = LessonResource.objects.create(
            booking=self.booking,
            title='Delete Me Notes',
            resource_type='NOTES',
            uploaded_by=self.tutor_user
        )
        delete_url = reverse('classroom:delete_resource', kwargs={'resource_id': res.id})

        # Intruder attempts to delete -> 403 Forbidden
        self.client.force_login(self.intruder_user)
        bad_resp = self.client.post(delete_url)
        self.assertEqual(bad_resp.status_code, 403)
        self.assertTrue(LessonResource.objects.filter(id=res.id).exists())

        # Legitimate tutor deletes -> 302 Success
        self.client.force_login(self.tutor_user)
        good_resp = self.client.post(delete_url)
        self.assertEqual(good_resp.status_code, 302)
        self.assertFalse(LessonResource.objects.filter(id=res.id).exists())

    def test_signaling_send_and_poll_sync(self):
        """
        Tests multi-device real-time WebRTC, whiteboard, and chat signaling synchronization.
        """
        import json
        send_url = reverse('classroom:send_signal', kwargs={'session_id': self.session.id})
        poll_url = reverse('classroom:poll_signals', kwargs={'session_id': self.session.id})

        # 1. Intruder is denied signaling access
        self.client.force_login(self.intruder_user)
        bad_send = self.client.post(send_url, json.dumps({'signal_type': 'chat', 'payload': {'text': 'hacked'}}), content_type='application/json')
        self.assertEqual(bad_send.status_code, 403)

        # 2. Tutor sends an offer signal
        self.client.force_login(self.tutor_user)
        tutor_resp = self.client.post(
            send_url,
            json.dumps({'signal_type': 'offer', 'payload': {'type': 'offer', 'sdp': 'dummy_sdp_offer'}}),
            content_type='application/json'
        )
        self.assertEqual(tutor_resp.status_code, 200)
        t_json = tutor_resp.json()
        self.assertTrue(t_json['success'])
        offer_sig_id = t_json['signal_id']

        # 3. Student polls signals and receives the tutor's offer
        self.client.force_login(self.student_user)
        poll_resp = self.client.get(f"{poll_url}?after_id=0")
        self.assertEqual(poll_resp.status_code, 200)
        p_json = poll_resp.json()
        self.assertTrue(p_json['success'])
        self.assertGreaterEqual(len(p_json['signals']), 1)
        offer_sig = next(s for s in p_json['signals'] if s['signal_type'] == 'offer')
        self.assertEqual(offer_sig['payload']['sdp'], 'dummy_sdp_offer')
        self.assertFalse(offer_sig['is_self'])
        self.assertEqual(offer_sig['sender_role'], 'TUTOR')

        # 4. Student sends whiteboard stroke
        student_draw_resp = self.client.post(
            send_url,
            json.dumps({'signal_type': 'whiteboard', 'payload': {'action': 'stroke', 'tool': 'pen', 'color': '#ffffff', 'points': [[0.1, 0.2], [0.3, 0.4]]}}),
            content_type='application/json'
        )
        self.assertEqual(student_draw_resp.status_code, 200)

        # 5. Tutor polls signals after offer_sig_id and receives the student's whiteboard draw
        self.client.force_login(self.tutor_user)
        tutor_poll = self.client.get(f"{poll_url}?after_id={offer_sig_id}")
        self.assertEqual(tutor_poll.status_code, 200)
        tp_json = tutor_poll.json()
        wb_sig = next(s for s in tp_json['signals'] if s['signal_type'] == 'whiteboard')
        self.assertEqual(wb_sig['payload']['tool'], 'pen')
        self.assertFalse(wb_sig['is_self'])
        self.assertEqual(wb_sig['sender_role'], 'STUDENT')



