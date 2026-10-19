import uuid
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from user.models import UserProfile, UserRole
from homepage.models import Guardian
from tutors.models import Tutor
from classroom.models import (
    Student, TutorProfile, Subject, ClassBooking, 
    ClassSession, LearningPathMilestone, LearningMilestoneStatus,
    SessionStatus, BookingStatus
)

User = get_user_model()


class UserRoleAccessTests(TestCase):
    def setUp(self):
        self.client = Client()

        # 1. Create Student User
        self.student_user = User.objects.create_user(
            username='student_sam',
            email='student_sam@example.com',
            password='Password123!',
            first_name='Sam',
            last_name='Student'
        )
        self.student_user.profile.role = UserRole.STUDENT
        self.student_user.profile.student_grade = 'year 10'
        self.student_user.profile.curriculum = 'British'
        self.student_user.profile.save()

        self.guardian = Guardian.objects.create(
            first_name='Grace',
            last_name='Student',
            email='grace.parent@example.com',
            phone='+2348011112222',
            lesson_type='Online lessons',
            curriculum='British'
        )
        self.student = Student.objects.create(
            user=self.student_user,
            guardian=self.guardian,
            first_name='Sam',
            last_name='Student',
            class_level='year 10',
            curriculum='British'
        )

        # 2. Create Tutor User
        self.tutor_user = User.objects.create_user(
            username='tutor_tara',
            email='tutor_tara@example.com',
            password='Password123!',
            first_name='Tara',
            last_name='Tutor'
        )
        self.tutor_user.profile.role = UserRole.TUTOR
        self.tutor_user.profile.save()

        self.tutor_profile = TutorProfile.objects.create(
            user=self.tutor_user,
            display_name='Tara Tutor',
            phone='+2348022223333',
            hourly_base_rate=Decimal('6000.00'),
            currency='NGN',
            is_verified=True
        )

        # 3. Create Staff User
        self.staff_user = User.objects.create_user(
            username='staff_steve',
            email='staff_steve@example.com',
            password='Password123!',
            is_staff=True,
            first_name='Steve',
            last_name='Staff'
        )
        self.staff_user.profile.role = UserRole.STAFF
        self.staff_user.profile.save()

        # 4. Create Admin User
        self.admin_user = User.objects.create_superuser(
            username='admin_alice',
            email='admin_alice@example.com',
            password='Password123!',
            first_name='Alice',
            last_name='Admin'
        )
        self.admin_user.profile.role = UserRole.ADMIN
        self.admin_user.profile.save()

        # Subject & Booking
        self.subject = Subject.objects.create(name='Chemistry', category='STEM')
        self.booking = ClassBooking.objects.create(
            student=self.student,
            tutor=self.tutor_profile,
            subject=self.subject,
            class_level='year 10',
            curriculum='British',
            agreed_hourly_rate=Decimal('6000.00'),
            currency='NGN',
            status=BookingStatus.ACTIVE
        )

    def test_user_profile_signal_and_roles(self):
        """Verify UserProfile is automatically created via signal and has correct role flags."""
        self.assertTrue(self.student_user.profile.is_student)
        self.assertFalse(self.student_user.profile.is_tutor)

        self.assertTrue(self.tutor_user.profile.is_tutor)
        self.assertFalse(self.tutor_user.profile.is_student)

        self.assertTrue(self.staff_user.profile.is_staff_member)
        self.assertTrue(self.admin_user.profile.is_admin)

    def test_dashboard_dispatcher_routing(self):
        """Verify dashboard dispatcher redirects each role to its dedicated LMS view."""
        # Student redirect
        self.client.force_login(self.student_user)
        res = self.client.get(reverse('dashboard_dispatcher'))
        self.assertRedirects(res, reverse('dashboard_student'))

        # Tutor redirect
        self.client.force_login(self.tutor_user)
        res = self.client.get(reverse('dashboard_dispatcher'))
        self.assertRedirects(res, reverse('dashboard_tutor'))

        # Staff redirect
        self.client.force_login(self.staff_user)
        res = self.client.get(reverse('dashboard_dispatcher'))
        self.assertRedirects(res, reverse('dashboard_staff'))

        # Admin redirect
        self.client.force_login(self.admin_user)
        res = self.client.get(reverse('dashboard_dispatcher'))
        self.assertRedirects(res, reverse('dashboard_admin'))

    def test_student_dashboard_learning_path_and_records(self):
        """Verify student dashboard displays learning path milestones and study records."""
        # Create curriculum milestone
        LearningPathMilestone.objects.create(
            student=self.student,
            subject=self.subject,
            module_title='Module 1: Atomic Structure',
            curriculum='British',
            order=1,
            status=LearningMilestoneStatus.COMPLETED,
            comprehension_score=Decimal('95.00')
        )

        self.client.force_login(self.student_user)
        res = self.client.get(reverse('dashboard_student'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'My Curriculum Learning Path &amp; Records')
        self.assertContains(res, 'Module 1: Atomic Structure')
        self.assertContains(res, '95.00%')

    def test_role_access_boundaries(self):
        """Verify students cannot access tutor, staff, or admin dashboards."""
        self.client.force_login(self.student_user)

        # Student trying to access Tutor Dashboard -> redirected to Student dashboard
        res = self.client.get(reverse('dashboard_tutor'))
        self.assertRedirects(res, reverse('dashboard_student'))

        # Student trying to access Admin Dashboard -> redirected to Student dashboard
        res = self.client.get(reverse('dashboard_admin'))
        self.assertRedirects(res, reverse('dashboard_student'))

    def test_tutor_dashboard_access_and_records(self):
        """Verify tutor dashboard renders active student bookings and sessions."""
        self.client.force_login(self.tutor_user)
        res = self.client.get(reverse('dashboard_tutor'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Upcoming Teaching Sessions')
        self.assertContains(res, 'My Enrolled Students')
        self.assertContains(res, 'Sam Student')

    def test_staff_dashboard_access(self):
        """Verify staff coordinator dashboard renders overview metrics."""
        self.client.force_login(self.staff_user)
        res = self.client.get(reverse('dashboard_staff'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Operations &amp; Academic Command Center')
        self.assertContains(res, 'Active Students')

    def test_admin_dashboard_and_role_update(self):
        """Verify admin can view executive KPIs and update user roles."""
        self.client.force_login(self.admin_user)
        res = self.client.get(reverse('dashboard_admin'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Platform Executive Dashboard')
        self.assertContains(res, 'Account &amp; Role Access Management')

        # Promote student_sam to TUTOR
        post_res = self.client.post(
            reverse('update_user_role', args=[self.student_user.id]),
            {'role': UserRole.TUTOR}
        )
        self.assertRedirects(post_res, reverse('dashboard_admin'))

        self.student_user.refresh_from_db()
        self.assertEqual(self.student_user.profile.role, UserRole.TUTOR)

    def test_profile_settings_update(self):
        """Verify user can update their profile information."""
        self.client.force_login(self.student_user)
        post_res = self.client.post(
            reverse('profile_settings'),
            {
                'first_name': 'Samuel',
                'last_name': 'Student',
                'phone_number': '+2348099998888',
                'headline': 'Aspiring Cambridge Scholar',
                'timezone': 'Europe/London',
                'bio': 'Passionate about chemistry and advanced mathematics.'
            }
        )
        self.assertRedirects(post_res, reverse('dashboard_student'))

        self.student_user.refresh_from_db()
        self.assertEqual(self.student_user.first_name, 'Samuel')
        self.assertEqual(self.student_user.profile.phone_number, '+2348099998888')
        self.assertEqual(self.student_user.profile.headline, 'Aspiring Cambridge Scholar')
        self.assertEqual(self.student_user.profile.timezone, 'Europe/London')
