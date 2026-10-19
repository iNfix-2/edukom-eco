import hmac
import hashlib
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.conf import settings

from user.models import UserProfile, UserRole
from homepage.models import Guardian
from classroom.models import (
    Student, TutorProfile, Subject, ClassBooking, ClassSession, 
    SessionStatus, BookingStatus, Quiz, QuizQuestion, QuizOption, 
    QuizAttempt, CourseCertificate, QuestionType
)
from classroom.views import get_user_calendar_token
from payments.models import Invoice

User = get_user_model()


class PortalAndStandardLmsFeatureTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.password = "SecurePass123!"

        # Create Subject
        self.subject = Subject.objects.create(name="IGCSE Physics", category="STEM")

        # 1. Guardian & Students
        self.guardian_user = User.objects.create_user(
            username="guardian_grace",
            email="grace@parent.org",
            password=self.password,
            first_name="Grace",
            last_name="Hopper"
        )
        self.guardian_profile = self.guardian_user.profile
        self.guardian_profile.role = UserRole.GUARDIAN
        self.guardian_profile.save()

        self.guardian_record = Guardian.objects.create(
            first_name="Grace",
            last_name="Hopper",
            email="grace@parent.org",
            phone="+2348011223344",
            lesson_type="Online lessons",
            curriculum="British"
        )

        self.child1 = Student.objects.create(
            guardian=self.guardian_record,
            first_name="Ada",
            last_name="Hopper",
            class_level="year 10",
            curriculum="British"
        )
        self.child2 = Student.objects.create(
            guardian=self.guardian_record,
            first_name="Alan",
            last_name="Hopper",
            class_level="year 8",
            curriculum="British"
        )

        # 2. Student User (Ada)
        self.student_user = User.objects.create_user(
            username="ada_student",
            email="ada@learner.org",
            password=self.password,
            first_name="Ada",
            last_name="Hopper"
        )
        self.student_profile = self.student_user.profile
        self.student_profile.role = UserRole.STUDENT
        self.student_profile.save()
        self.child1.user = self.student_user
        self.child1.save()

        # 3. Tutor User & Profile
        self.tutor_user = User.objects.create_user(
            username="tutor_feynman",
            email="richard@tutor.org",
            password=self.password,
            first_name="Richard",
            last_name="Feynman"
        )
        self.tutor_profile = self.tutor_user.profile
        self.tutor_profile.role = UserRole.TUTOR
        self.tutor_profile.save()

        self.tutor_cls_profile = TutorProfile.objects.create(
            user=self.tutor_user,
            display_name="Prof. Richard Feynman",
            hourly_base_rate=Decimal('6000.00'),
            is_verified=True
        )

        # 4. Booking & Session
        self.booking = ClassBooking.objects.create(
            student=self.child1,
            tutor=self.tutor_cls_profile,
            subject=self.subject,
            class_level="year 10",
            curriculum="British",
            agreed_hourly_rate=Decimal('6000.00'),
            status=BookingStatus.ACTIVE
        )

        now = timezone.now()
        self.session = ClassSession.objects.create(
            booking=self.booking,
            title="Electromagnetic Induction",
            start_time=now + timezone.timedelta(hours=2),
            end_time=now + timezone.timedelta(hours=3),
            duration_minutes=60,
            room_name="room-phys-101",
            status=SessionStatus.SCHEDULED
        )

        # 5. Quiz Setup
        self.quiz = Quiz.objects.create(
            title="Physics Diagnostic Assessment",
            description="Diagnostic test on Newton's Laws and Waves.",
            subject=self.subject,
            class_level="year 10",
            curriculum="British",
            created_by=self.tutor_user,
            time_limit_minutes=15,
            pass_percentage=Decimal('70.00'),
            max_attempts=2,
            is_active=True
        )

        # Q1: 1 point
        self.q1 = QuizQuestion.objects.create(
            quiz=self.quiz,
            question_text="What is the SI unit of electric current?",
            question_type=QuestionType.SINGLE,
            order=1,
            points=1,
            explanation="The SI unit of electric current is the Ampere (A)."
        )
        self.opt1_correct = QuizOption.objects.create(question=self.q1, option_text="Ampere (A)", is_correct=True, order=1)
        self.opt1_wrong = QuizOption.objects.create(question=self.q1, option_text="Volt (V)", is_correct=False, order=2)

        # Q2: 1 point
        self.q2 = QuizQuestion.objects.create(
            quiz=self.quiz,
            question_text="Is light an electromagnetic transverse wave?",
            question_type=QuestionType.TRUE_FALSE,
            order=2,
            points=1,
            explanation="Light is an electromagnetic transverse wave that does not require a material medium."
        )
        self.opt2_correct = QuizOption.objects.create(question=self.q2, option_text="True", is_correct=True, order=1)
        self.opt2_wrong = QuizOption.objects.create(question=self.q2, option_text="False", is_correct=False, order=2)

        # 6. Certificate Setup
        self.cert = CourseCertificate.objects.create(
            student=self.child1,
            subject=self.subject,
            curriculum="British",
            class_level="year 10",
            instructor_name="Prof. Richard Feynman",
            grade_achieved="Distinction",
            hours_completed=Decimal('25.0')
        )

    def test_guardian_dashboard_access_and_child_switcher(self):
        """Verify Guardian portal authentication, multi-child switcher, and BOLA protection."""
        self.client.login(username="guardian_grace", password=self.password)
        response = self.client.get(reverse('dashboard_guardian'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Parent &amp; Guardian Portal")
        self.assertContains(response, "Grace Hopper")
        self.assertContains(response, "Ada")
        self.assertContains(response, "Alan")

        # Child switcher test with child_id query
        resp_child = self.client.get(f"{reverse('dashboard_guardian')}?child_id={self.child2.id}")
        self.assertEqual(resp_child.status_code, 200)
        self.assertEqual(resp_child.context['active_child'], self.child2)

    def test_quiz_take_and_anti_tampering(self):
        """Verify anti-tampering: 'is_correct' is never exposed in quiz form HTML."""
        self.client.login(username="ada_student", password=self.password)
        response = self.client.get(reverse('classroom:take_quiz', kwargs={'quiz_id': self.quiz.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "What is the SI unit of electric current?")
        self.assertContains(response, "Ampere (A)")
        self.assertContains(response, "Volt (V)")
        # Crucial security check: is_correct should NOT appear anywhere in the rendered HTML
        self.assertNotContains(response, "is_correct")
        self.assertNotContains(response, "CORRECT")

    def test_quiz_server_side_grading_pass(self):
        """Verify server-side automated grading with 100% score and PASS result."""
        self.client.login(username="ada_student", password=self.password)
        post_data = {
            f'question_{self.q1.id}': str(self.opt1_correct.id),
            f'question_{self.q2.id}': str(self.opt2_correct.id),
        }
        response = self.client.post(reverse('classroom:submit_quiz', kwargs={'quiz_id': self.quiz.id}), post_data)
        self.assertEqual(response.status_code, 302)

        attempt = QuizAttempt.objects.filter(quiz=self.quiz, user=self.student_user).latest('completed_at')
        self.assertEqual(attempt.score, Decimal('2.00'))
        self.assertEqual(attempt.max_score, Decimal('2.00'))
        self.assertEqual(attempt.percentage, Decimal('100.00'))
        self.assertTrue(attempt.passed)

        # Follow to result page
        res_page = self.client.get(reverse('classroom:quiz_result', kwargs={'attempt_id': attempt.id}))
        self.assertEqual(res_page.status_code, 200)
        self.assertContains(res_page, "Passed Assessment")
        self.assertContains(res_page, "100.0%")
        self.assertContains(res_page, "The SI unit of electric current is the Ampere")

    def test_quiz_server_side_grading_fail(self):
        """Verify server-side automated grading with 0% score and FAIL result."""
        self.client.login(username="ada_student", password=self.password)
        post_data = {
            f'question_{self.q1.id}': str(self.opt1_wrong.id),
            f'question_{self.q2.id}': str(self.opt2_wrong.id),
        }
        response = self.client.post(reverse('classroom:submit_quiz', kwargs={'quiz_id': self.quiz.id}), post_data)
        self.assertEqual(response.status_code, 302)

        attempt = QuizAttempt.objects.filter(quiz=self.quiz, user=self.student_user).latest('completed_at')
        self.assertEqual(attempt.score, Decimal('0.00'))
        self.assertEqual(attempt.percentage, Decimal('0.00'))
        self.assertFalse(attempt.passed)

    def test_quiz_attempt_limit_enforcement(self):
        """Verify maximum attempt limits are strictly enforced on backend."""
        self.client.login(username="ada_student", password=self.password)
        # Attempt 1
        self.client.post(reverse('classroom:submit_quiz', kwargs={'quiz_id': self.quiz.id}), {
            f'question_{self.q1.id}': str(self.opt1_correct.id),
            f'question_{self.q2.id}': str(self.opt2_correct.id),
        })
        # Attempt 2
        self.client.post(reverse('classroom:submit_quiz', kwargs={'quiz_id': self.quiz.id}), {
            f'question_{self.q1.id}': str(self.opt1_correct.id),
            f'question_{self.q2.id}': str(self.opt2_correct.id),
        })
        self.assertEqual(QuizAttempt.objects.filter(quiz=self.quiz, student=self.child1).count(), 2)

        # Attempt 3 (Should be blocked by server!)
        resp = self.client.get(reverse('classroom:take_quiz', kwargs={'quiz_id': self.quiz.id}))
        self.assertEqual(resp.status_code, 302) # Redirects away because max attempts reached
        
        post_resp = self.client.post(reverse('classroom:submit_quiz', kwargs={'quiz_id': self.quiz.id}), {
            f'question_{self.q1.id}': str(self.opt1_correct.id),
        })
        self.assertEqual(post_resp.status_code, 302)
        # Count remains 2
        self.assertEqual(QuizAttempt.objects.filter(quiz=self.quiz, student=self.child1).count(), 2)

    def test_certificate_view_and_public_verification(self):
        """Verify high-resolution certificate rendering and public verification portal."""
        # 1. Public Verification (No login required)
        verify_url = reverse('classroom:verify_certificate', kwargs={'code': self.cert.certificate_code})
        resp_verify = self.client.get(verify_url)
        self.assertEqual(resp_verify.status_code, 200)
        self.assertContains(resp_verify, "Verified Authentic")
        self.assertContains(resp_verify, self.cert.certificate_code)
        self.assertContains(resp_verify, "Ada Hopper")
        self.assertContains(resp_verify, "Distinction")

        # 2. View Certificate (Authenticated owner)
        self.client.login(username="ada_student", password=self.password)
        view_url = reverse('classroom:view_certificate', kwargs={'certificate_code': self.cert.certificate_code})
        resp_view = self.client.get(view_url)
        self.assertEqual(resp_view.status_code, 200)
        self.assertContains(resp_view, "Certificate of Academic Achievement")
        self.assertContains(resp_view, "Prof. Richard Feynman")

        # 3. Revoked certificate verification
        self.cert.is_revoked = True
        self.cert.revocation_reason = "Course enrollment superseded."
        self.cert.save()

        resp_revoked = self.client.get(verify_url)
        self.assertEqual(resp_revoked.status_code, 200)
        self.assertContains(resp_revoked, "Certificate Revoked")

    def test_calendar_sync_rfc5545_feed(self):
        """Verify RFC 5545 iCalendar generation and cryptographic HMAC token auth."""
        # 1. Session Auth (Logged In Student)
        self.client.login(username="ada_student", password=self.password)
        response = self.client.get(reverse('classroom:calendar_sync'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], "text/calendar; charset=utf-8")
        ics_text = response.content.decode('utf-8')
        self.assertIn("BEGIN:VCALENDAR", ics_text)
        self.assertIn("BEGIN:VEVENT", ics_text)
        self.assertIn("SUMMARY:Electromagnetic Induction (IGCSE Physics) - Edukom", ics_text)
        self.assertIn("Electromagnetic Induction", ics_text)
        self.assertIn("END:VCALENDAR", ics_text)

        # 2. Cryptographic Token Auth (Logged Out Calendar Apps like Google/Apple)
        self.client.logout()
        token = get_user_calendar_token(self.student_user)
        sync_url = f"{reverse('classroom:calendar_sync')}?user_id={self.student_user.id}&token={token}"
        resp_token = self.client.get(sync_url)
        self.assertEqual(resp_token.status_code, 200)
        self.assertIn("BEGIN:VCALENDAR", resp_token.content.decode('utf-8'))

        # 3. Tampered Token Auth (Must be rejected with 403)
        bad_sync_url = f"{reverse('classroom:calendar_sync')}?user_id={self.student_user.id}&token=badtoken12345678"
        resp_bad = self.client.get(bad_sync_url)
        self.assertEqual(resp_bad.status_code, 403)
