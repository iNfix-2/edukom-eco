import io
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from datetime import timedelta

from classroom.models import Subject, TutorProfile
from user.models import UserProfile, UserRole
from videolibrary.models import (
    VideoCourse,
    VideoLesson,
    CourseResource,
    ResourceType,
    VideoSubscription,
    DRMKey
)

User = get_user_model()


class CreatorStudioSecurityAndCRUDTests(TestCase):
    def setUp(self):
        self.client = Client()

        # 1. Admin user
        self.admin_user = User.objects.create_superuser(
            username='admin_boss',
            email='admin@edukom.ng',
            password='Password123!'
        )

        # 2. Tutor user A
        self.tutor_user = User.objects.create_user(
            username='tutor_dr_ade',
            email='ade@edukom.ng',
            password='Password123!'
        )
        self.tutor_user.profile.role = UserRole.TUTOR
        self.tutor_user.profile.save()
        self.tutor_profile = TutorProfile.objects.create(
            user=self.tutor_user,
            display_name='Dr. Ade Komolafe',
            is_verified=True
        )

        # 3. Tutor user B (Attacker / separate tutor)
        self.tutor_rival = User.objects.create_user(
            username='tutor_rival',
            email='rival@edukom.ng',
            password='Password123!'
        )
        self.tutor_rival.profile.role = UserRole.TUTOR
        self.tutor_rival.profile.save()
        self.tutor_rival_profile = TutorProfile.objects.create(
            user=self.tutor_rival,
            display_name='Rival Tutor',
            is_verified=True
        )

        # 4. Student user
        self.student_user = User.objects.create_user(
            username='student_tunde',
            email='tunde@edukom.ng',
            password='Password123!'
        )
        self.student_user.profile.role = UserRole.STUDENT
        self.student_user.profile.save()

        # Subject
        self.subject = Subject.objects.create(name='Mathematics')

        # Existing Course by Tutor A
        self.course = VideoCourse.objects.create(
            title='Advanced Calculus Masterclass',
            description='In-depth derivation and applications.',
            subject=self.subject,
            class_level='year 12',
            created_by=self.tutor_user,
            is_published=True,
            price=Decimal('15000.00')
        )

    def test_anonymous_redirected_from_studio(self):
        """Anonymous users must be redirected to login."""
        response = self.client.get(reverse('videolibrary:studio_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/account/login/', response.url)

    def test_student_denied_from_creator_studio(self):
        """Students cannot access Creator Studio and are redirected to catalog."""
        self.client.force_login(self.student_user)
        response = self.client.get(reverse('videolibrary:studio_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('videolibrary:catalog'), response.url)

    def test_tutor_and_admin_granted_studio_access(self):
        """Tutors and admins have 200 OK access to Creator Studio."""
        self.client.force_login(self.tutor_user)
        response = self.client.get(reverse('videolibrary:studio_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Creator Studio')
        self.assertContains(response, 'Advanced Calculus Masterclass')

        self.client.force_login(self.admin_user)
        response_admin = self.client.get(reverse('videolibrary:studio_dashboard'))
        self.assertEqual(response_admin.status_code, 200)

    def test_course_creation_flow(self):
        """Tutor can create a course with auto-assigned created_by ownership."""
        self.client.force_login(self.tutor_user)
        post_data = {
            'title': 'Organic Chemistry Simplified',
            'subject': self.subject.id,
            'class_level': 'year 11',
            'description': 'Mechanisms and reactions explained clearly.',
            'price': '8500.00',
            'is_subscription_only': 'on',
            'is_published': 'on'
        }
        response = self.client.post(reverse('videolibrary:studio_course_create'), post_data)
        self.assertEqual(response.status_code, 302)
        
        created = VideoCourse.objects.filter(title='Organic Chemistry Simplified').first()
        self.assertIsNotNone(created)
        self.assertEqual(created.created_by, self.tutor_user)
        self.assertEqual(created.class_level, 'year 11')
        self.assertTrue(created.is_published)

    def test_bola_idor_course_edit_protection(self):
        """Tutor B cannot edit Tutor A's course (BOLA/IDOR protection)."""
        self.client.force_login(self.tutor_rival)
        response = self.client.get(reverse('videolibrary:studio_course_edit', kwargs={'course_id': self.course.id}))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('videolibrary:studio_dashboard'), response.url)

        # Attacker POST attempt
        post_data = {
            'title': 'Hacked Course Title',
            'subject': self.subject.id,
            'class_level': 'year 12',
            'description': 'Tampered description',
            'price': '0.00'
        }
        tamper_response = self.client.post(
            reverse('videolibrary:studio_course_edit', kwargs={'course_id': self.course.id}),
            post_data
        )
        self.course.refresh_from_db()
        self.assertNotEqual(self.course.title, 'Hacked Course Title')

    def test_course_publish_toggle(self):
        """1-click toggle switches status between Published and Draft."""
        self.client.force_login(self.tutor_user)
        self.assertTrue(self.course.is_published)

        response = self.client.post(reverse('videolibrary:studio_course_toggle_publish', kwargs={'course_id': self.course.id}))
        self.assertEqual(response.status_code, 302)
        self.course.refresh_from_db()
        self.assertFalse(self.course.is_published)

        # Toggle back
        self.client.post(reverse('videolibrary:studio_course_toggle_publish', kwargs={'course_id': self.course.id}))
        self.course.refresh_from_db()
        self.assertTrue(self.course.is_published)

    def test_lesson_upload_and_drm_key_generation(self):
        """Adding a video lesson creates VideoLesson and generates DRMKey."""
        self.client.force_login(self.tutor_user)
        dummy_video = SimpleUploadedFile("intro_calculus.mp4", b"fake-mp4-video-stream-content", content_type="video/mp4")
        
        post_data = {
            'title': 'Lesson 1: Limits & Continuity',
            'order': 1,
            'duration_minutes': 45,
            'description': 'Mastering epsilon-delta proofs and standard limit laws.',
            'video_file': dummy_video,
            'is_drm_protected': 'on'
        }
        response = self.client.post(
            reverse('videolibrary:studio_lesson_create', kwargs={'course_id': self.course.id}),
            post_data
        )
        self.assertEqual(response.status_code, 302)

        lesson = VideoLesson.objects.filter(course=self.course, title='Lesson 1: Limits & Continuity').first()
        self.assertIsNotNone(lesson)
        self.assertEqual(lesson.duration_seconds, 45 * 60)
        self.assertTrue(lesson.is_drm_protected)

        # Verify DRM Key generated
        drm_key = getattr(lesson, 'drm_key', None)
        self.assertIsNotNone(drm_key)
        self.assertEqual(len(drm_key.key_hex), 32)

    def test_resource_upload_and_secure_download(self):
        """Uploading worksheets and enforcing subscription-backed download authorization."""
        self.client.force_login(self.tutor_user)
        dummy_pdf = SimpleUploadedFile("calculus_worksheet_1.pdf", b"%PDF-1.4 dummy pdf content for homework", content_type="application/pdf")

        # 1. Tutor uploads resource
        post_data = {
            'title': 'Calculus Homework Worksheet 1',
            'resource_type': ResourceType.WORKSHEET,
            'file': dummy_pdf,
            'description': 'Solve questions 1 through 15 before session 2.'
        }
        res_response = self.client.post(
            reverse('videolibrary:studio_resource_upload', kwargs={'course_id': self.course.id}),
            post_data
        )
        self.assertEqual(res_response.status_code, 302)

        resource = CourseResource.objects.filter(course=self.course, title='Calculus Homework Worksheet 1').first()
        self.assertIsNotNone(resource)
        self.assertEqual(resource.file_extension, '.pdf')
        self.assertGreater(resource.file_size, 0)

        # 2. Non-enrolled student tries to download -> Denied
        self.client.force_login(self.student_user)
        unauth_dl = self.client.get(reverse('videolibrary:download_resource', kwargs={'resource_id': resource.id}))
        self.assertEqual(unauth_dl.status_code, 302)

        # 3. Student subscribes -> Download granted
        VideoSubscription.objects.create(
            user=self.student_user,
            course=self.course,
            is_active=True,
            expires_at=timezone.now() + timedelta(days=30)
        )
        auth_dl = self.client.get(reverse('videolibrary:download_resource', kwargs={'resource_id': resource.id}))
        self.assertEqual(auth_dl.status_code, 200)
        self.assertIn('attachment;', auth_dl['Content-Disposition'])
        
        # Verify download count incremented
        resource.refresh_from_db()
        self.assertEqual(resource.download_count, 1)

    def test_file_extension_validation_defense(self):
        """Uploading dangerous executable files (.exe, .sh) is blocked."""
        self.client.force_login(self.tutor_user)
        malicious_file = SimpleUploadedFile("malware.exe", b"dangerous-binary", content_type="application/x-dosexec")

        post_data = {
            'title': 'Malicious payload',
            'resource_type': ResourceType.OTHER,
            'file': malicious_file
        }
        response = self.client.post(
            reverse('videolibrary:studio_resource_upload', kwargs={'course_id': self.course.id}),
            post_data
        )
        # Should stay on page with error message
        self.assertEqual(CourseResource.objects.filter(title='Malicious payload').count(), 0)
