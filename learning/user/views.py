import json
import logging
import hashlib
import hmac
from decimal import Decimal
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from django.utils import timezone
from django.db import models
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator

from homepage import models as home_models
from tutors import models as tmodels
from classroom.models import (
    Student, TutorProfile, ClassBooking, ClassSession, 
    LessonResource, ResourceType, LessonFeedback, LearningPathMilestone, 
    LearningMilestoneStatus, SessionStatus, BookingStatus, Subject,
    HomeworkSubmission, SubmissionStatus,
    Quiz, QuizAttempt, CourseCertificate
)
from payments.models import Invoice, PaymentTransaction
from payroll.models import PayrollRun, TutorBankAccount, TutorPayrollItem
from videolibrary.models import VideoWatchProgress, VideoLesson, VideoCourse
from edukom.health import run_health_checks

from .models import UserProfile, UserRole
from .decorators import student_required, guardian_required, tutor_required, staff_required, admin_required

User = get_user_model()
logger = logging.getLogger('edukom.security')


# ==============================================================================
# 1. SMART ROLE-BASED DASHBOARD DISPATCHER
# ==============================================================================
@login_required
def dashboard_dispatcher_view(request: HttpRequest) -> HttpResponse:
    """
    Intelligent routing hub: redirects the authenticated user directly
    to their dedicated role dashboard (Student, Tutor, Staff, or Admin).
    """
    profile = getattr(request.user, 'profile', None)
    if not profile:
        initial_role = UserRole.ADMIN if request.user.is_superuser else (
            UserRole.STAFF if request.user.is_staff else (
                UserRole.TUTOR if hasattr(request.user, 'tutor_profile') else UserRole.STUDENT
            )
        )
        profile, _ = UserProfile.objects.get_or_create(user=request.user, defaults={'role': initial_role})

    return redirect(profile.get_dashboard_url())


# ==============================================================================
# 2. STUDENT LMS DASHBOARD & LEARNING HISTORY PATH
# ==============================================================================
@login_required
@student_required
def student_dashboard_view(request: HttpRequest) -> HttpResponse:
    """
    Dedicated Student LMS Hub:
    Displays curriculum learning history path, milestone mastery, upcoming live WebRTC
    classrooms with Daily.co 1-click launcher, lesson notes, DRM video history, and billing.
    """
    user = request.user
    profile = user.profile
    now = timezone.now()

    # Find associated Student profiles
    students = Student.objects.filter(models.Q(user=user) | models.Q(guardian__email__iexact=user.email))
    primary_student = students.first()

    # If student profile does not exist yet, create a default learner profile
    if not primary_student:
        guardian, _ = home_models.Guardian.objects.get_or_create(
            email=user.email,
            defaults={
                'first_name': user.first_name or user.username,
                'last_name': user.last_name or 'Learner',
                'phone': profile.phone_number or '+2340000000000',
                'curriculum': profile.curriculum or 'British',
                'lesson_type': 'Online lessons',
            }
        )
        primary_student = Student.objects.create(
            user=user,
            guardian=guardian,
            first_name=user.first_name or user.username,
            last_name=user.last_name or 'Learner',
            class_level=profile.student_grade or 'year 10',
            curriculum=profile.curriculum or 'British',
            timezone=profile.timezone or 'Africa/Lagos'
        )
        students = Student.objects.filter(id=primary_student.id)

    # 1. Learning Path Milestones & Curriculum Mastery
    milestones = LearningPathMilestone.objects.filter(
        student__in=students
    ).select_related('subject').order_by('subject__name', 'order')

    # Seed sample curriculum milestones if new
    if not milestones.exists() and primary_student:
        default_subject, _ = Subject.objects.get_or_create(name='General Science', defaults={'category': 'STEM'})
        LearningPathMilestone.objects.bulk_create([
            LearningPathMilestone(
                student=primary_student,
                subject=default_subject,
                module_title='Module 1: Foundations & Scientific Inquiry',
                curriculum=primary_student.curriculum,
                order=1,
                status=LearningMilestoneStatus.COMPLETED,
                comprehension_score=Decimal('92.00'),
                tutor_feedback='Outstanding foundational understanding demonstrated in class discussions.',
                completed_at=now - timezone.timedelta(days=7)
            ),
            LearningPathMilestone(
                student=primary_student,
                subject=default_subject,
                module_title='Module 2: Core Analysis & Quantitative Problem Solving',
                curriculum=primary_student.curriculum,
                order=2,
                status=LearningMilestoneStatus.IN_PROGRESS,
                comprehension_score=Decimal('85.50'),
                tutor_feedback='Currently mastering practice worksheets and formula derivations.'
            ),
            LearningPathMilestone(
                student=primary_student,
                subject=default_subject,
                module_title='Module 3: Advanced Application & Exam Strategy',
                curriculum=primary_student.curriculum,
                order=3,
                status=LearningMilestoneStatus.NOT_STARTED
            ),
        ])
        milestones = LearningPathMilestone.objects.filter(student__in=students).select_related('subject')

    total_milestones = milestones.count()
    completed_milestones = milestones.filter(
        status__in=[LearningMilestoneStatus.COMPLETED, LearningMilestoneStatus.MASTERED]
    ).count()
    progress_percentage = int((completed_milestones / total_milestones * 100)) if total_milestones > 0 else 0

    # 2. Upcoming Live Classrooms
    upcoming_sessions = ClassSession.objects.filter(
        booking__student__in=students,
        end_time__gte=now,
        status__in=[SessionStatus.SCHEDULED, SessionStatus.IN_PROGRESS]
    ).select_related('booking', 'booking__tutor', 'booking__subject').order_by('start_time')[:5]

    # 3. Past Completed Sessions & Lesson Notes
    past_sessions = ClassSession.objects.filter(
        booking__student__in=students,
        status=SessionStatus.COMPLETED
    ).select_related('booking', 'booking__tutor', 'booking__subject').order_by('-start_time')[:5]

    # 4. Total Study Hours Logged
    total_completed_minutes = sum(s.duration_minutes for s in past_sessions)
    total_study_hours = round(total_completed_minutes / 60, 1)

    # 5. DRM Video Watch Progress History
    watch_history = VideoWatchProgress.objects.filter(
        user=user
    ).select_related('lesson', 'lesson__course').order_by('-updated_at')[:4]

    # 6. Available Worksheets & Resources
    resources = LessonResource.objects.filter(
        session__booking__student__in=students
    ).select_related('session').order_by('-created_at')[:5]

    # 7. Invoices & Billing
    invoices = Invoice.objects.filter(
        client_email__iexact=user.email
    ).order_by('-created_at')[:5]

    # 8. Interactive Quizzes & Assessments
    quiz_attempts = QuizAttempt.objects.filter(
        models.Q(user=user) | models.Q(student__in=students)
    ).select_related('quiz', 'quiz__subject').order_by('-completed_at')[:4]

    # 9. Verifiable Certificates
    certificates = CourseCertificate.objects.filter(
        student__in=students,
        is_revoked=False
    ).select_related('subject')

    # 10. Student Onboarding Telemetry & Guided Experience
    has_phone = bool(profile.phone_number and profile.phone_number.strip() and profile.phone_number != '+2340000000000')
    has_grade = bool(primary_student and primary_student.class_level and primary_student.class_level.strip())
    step_profile = has_phone and has_grade
    step_tech_check = bool(request.session.get('student_tech_check_passed') or past_sessions.exists())
    step_diagnostic = bool(milestones.filter(status__in=[LearningMilestoneStatus.COMPLETED, LearningMilestoneStatus.IN_PROGRESS]).exists() or upcoming_sessions.exists() or request.session.get('student_diagnostic_done'))
    step_calendar = bool(request.session.get('student_calendar_synced') or upcoming_sessions.exists())

    student_onboarding_steps = [
        {
            'id': 'profile',
            'title': 'Academic Profile & Target',
            'desc': 'Configure your class grade, curriculum (British/WAEC/IGCSE), and phone contact.',
            'is_completed': step_profile,
            'action_url': reverse('profile_settings'),
            'action_label': 'Edit Profile',
            'icon': 'fa-solid fa-user-pen',
            'badge': 'Essential'
        },
        {
            'id': 'tech_check',
            'title': 'Classroom Hardware Check',
            'desc': 'Verify your webcam, microphone, and browser audio for live interactive WebRTC classes.',
            'is_completed': step_tech_check,
            'action_onclick': "openModal('studentTechCheckModal'); initHardwareTest('student');",
            'action_label': 'Run Test',
            'icon': 'fa-solid fa-headset',
            'badge': 'Quick 30s'
        },
        {
            'id': 'goals',
            'title': 'Curriculum Milestone & Diagnostic',
            'desc': 'Review your assigned subject modules, learning targets, and diagnostic progress.',
            'is_completed': step_diagnostic,
            'action_url': '#curriculum-path',
            'action_label': 'View Roadmap',
            'icon': 'fa-solid fa-graduation-cap',
            'badge': 'Academic'
        },
        {
            'id': 'calendar',
            'title': 'Timetable & Calendar Sync',
            'desc': 'Download your personalized .ics calendar file for Google / Apple Calendar lesson reminders.',
            'is_completed': step_calendar,
            'action_url': reverse('classroom:calendar_sync'),
            'action_label': 'Sync .ics',
            'icon': 'fa-regular fa-calendar-check',
            'badge': 'Schedule'
        }
    ]
    completed_steps_count = sum(1 for s in student_onboarding_steps if s['is_completed'])
    student_onboarding_percent = int((completed_steps_count / len(student_onboarding_steps)) * 100)
    is_onboarding_finished = (student_onboarding_percent == 100)
    is_onboarding_dismissed = request.session.get('student_onboarding_dismissed', False)
    is_returning_student = bool(past_sessions.exists() or total_study_hours > 0 or (total_milestones > 3 and completed_milestones > 0))

    next_session = upcoming_sessions.first() if upcoming_sessions.exists() else None
    latest_graded_homework = HomeworkSubmission.objects.filter(
        student__in=students, 
        status=SubmissionStatus.GRADED
    ).order_by('-reviewed_at').first()
    resume_lesson = watch_history.first() if watch_history.exists() else None

    context = {
        'profile': profile,
        'student': primary_student,
        'milestones': milestones,
        'progress_percentage': progress_percentage,
        'completed_milestones': completed_milestones,
        'total_milestones': total_milestones,
        'total_study_hours': total_study_hours,
        'upcoming_sessions': upcoming_sessions,
        'past_sessions': past_sessions,
        'watch_history': watch_history,
        'resources': resources,
        'invoices': invoices,
        'quiz_attempts': quiz_attempts,
        'certificates': certificates,
        'student_onboarding_steps': student_onboarding_steps,
        'student_completed_count': completed_steps_count,
        'student_onboarding_percent': student_onboarding_percent,
        'is_onboarding_finished': is_onboarding_finished,
        'is_onboarding_dismissed': is_onboarding_dismissed,
        'is_returning_student': is_returning_student,
        'next_session': next_session,
        'latest_graded_homework': latest_graded_homework,
        'resume_lesson': resume_lesson,
        'now': now,
    }
    return render(request, 'account/dashboard_student.html', context)


# ==============================================================================
# 2B. PARENT / GUARDIAN PORTAL & MULTI-CHILD ACADEMIC OVERSIGHT
# ==============================================================================
@login_required
@guardian_required
def guardian_dashboard_view(request: HttpRequest) -> HttpResponse:
    """
    Dedicated Parent / Guardian Portal:
    Provides multi-child academic oversight switcher, attendance metrics,
    tutor lesson notes & feedback per session, upcoming live class timetable,
    homework submission reviews, quiz results, course certificates,
    and 1-click Paystack tuition invoice settlement.
    """
    user = request.user
    profile = user.profile
    now = timezone.now()

    # 1. Fetch or initialize Guardian lead/profile record
    guardian_record = home_models.Guardian.objects.filter(email__iexact=user.email).first()
    if not guardian_record:
        guardian_record, _ = home_models.Guardian.objects.get_or_create(
            email=user.email,
            defaults={
                'first_name': user.first_name or user.username,
                'last_name': user.last_name or 'Guardian',
                'phone': profile.phone_number or '+2340000000000',
                'curriculum': profile.curriculum or 'British',
                'lesson_type': 'Online lessons',
            }
        )

    # 2. Associated Children (Students)
    students = Student.objects.filter(
        models.Q(guardian__email__iexact=user.email) |
        models.Q(guardian=guardian_record)
    ).order_by('first_name', 'last_name')

    # Multi-Child Switcher with BOLA ID verification
    selected_child_id = request.GET.get('child_id')
    active_child = None
    if selected_child_id:
        active_child = students.filter(id=selected_child_id).first()

    if not active_child and students.exists():
        active_child = students.first()

    # Child-specific academic telemetry
    upcoming_sessions = []
    past_sessions = []
    milestones = []
    homework_submissions = []
    quiz_attempts = []
    certificates = []
    attendance_rate = 100.0
    total_study_hours = 0.0

    if active_child:
        # Upcoming sessions
        upcoming_sessions = ClassSession.objects.filter(
            booking__student=active_child,
            end_time__gte=now,
            status__in=[SessionStatus.SCHEDULED, SessionStatus.IN_PROGRESS]
        ).select_related('booking', 'booking__tutor', 'booking__subject').order_by('start_time')[:5]

        # Completed sessions with tutor lesson notes
        past_sessions_qs = ClassSession.objects.filter(
            booking__student=active_child,
            status=SessionStatus.COMPLETED
        ).select_related('booking', 'booking__tutor', 'booking__subject').order_by('-start_time')
        past_sessions = past_sessions_qs[:10]

        # Attendance calculation
        total_finished = ClassSession.objects.filter(booking__student=active_child).exclude(status=SessionStatus.SCHEDULED).count()
        attended = past_sessions_qs.count()
        if total_finished > 0:
            attendance_rate = round((attended / total_finished) * 100, 1)

        total_completed_minutes = sum(s.duration_minutes for s in past_sessions_qs)
        total_study_hours = round(total_completed_minutes / 60, 1)

        # Learning milestones
        milestones = LearningPathMilestone.objects.filter(student=active_child).select_related('subject')[:10]

        # Homework Submissions
        homework_submissions = HomeworkSubmission.objects.filter(student=active_child).select_related('session', 'reviewed_by').order_by('-submitted_at')[:5]

        # Interactive Quiz Attempts
        quiz_attempts = QuizAttempt.objects.filter(student=active_child).select_related('quiz', 'quiz__subject').order_by('-completed_at')[:5]

        # Verifiable Course Completion Certificates
        certificates = CourseCertificate.objects.filter(student=active_child, is_revoked=False).select_related('subject')

    # 3. Invoices & Tuition Billing (Parent-wide)
    invoices = Invoice.objects.filter(client_email__iexact=user.email).order_by('-created_at')
    unpaid_invoices = invoices.filter(status='PENDING')
    total_unpaid = sum(inv.amount for inv in unpaid_invoices)
    total_paid = sum(inv.amount for inv in invoices.filter(status='PAID'))

    # 4. Cryptographic Calendar Feed URL
    calendar_token = hmac.new(
        settings.SECRET_KEY.encode('utf-8'),
        f"calendar_sync:{user.id}:{user.username}".encode('utf-8'),
        hashlib.sha256
    ).hexdigest()[:32]
    calendar_subscribe_url = request.build_absolute_uri(f"/classroom/calendar/sync.ics?user_id={user.id}&token={calendar_token}")

    context = {
        'profile': profile,
        'guardian_record': guardian_record,
        'students': students,
        'active_child': active_child,
        'upcoming_sessions': upcoming_sessions,
        'past_sessions': past_sessions,
        'attendance_rate': attendance_rate,
        'total_study_hours': total_study_hours,
        'milestones': milestones,
        'homework_submissions': homework_submissions,
        'quiz_attempts': quiz_attempts,
        'certificates': certificates,
        'invoices': invoices[:6],
        'unpaid_invoices': unpaid_invoices,
        'total_unpaid': total_unpaid,
        'total_paid': total_paid,
        'calendar_subscribe_url': calendar_subscribe_url,
        'now': now,
    }
    return render(request, 'account/dashboard_guardian.html', context)


# ==============================================================================
# 3. TUTOR LMS DASHBOARD & TEACHING HUB
# ==============================================================================
@login_required
@tutor_required
def tutor_dashboard_view(request: HttpRequest) -> HttpResponse:
    """
    Dedicated Tutor LMS Hub:
    Manages assigned student rosters, upcoming WebRTC live classes with Daily.co launcher,
    attendance/lesson note logging, resource vault uploader, and calculated payroll earnings.
    """
    user = request.user
    profile = user.profile
    now = timezone.now()

    tutor_profile = getattr(user, 'tutor_profile', None)
    if not tutor_profile:
        from tutors.models import Tutor as LegacyTutor
        tutor_rec = None
        if user.email:
            tutor_rec = LegacyTutor.objects.filter(email__iexact=user.email).first()
            if not tutor_rec:
                tutor_rec = LegacyTutor.objects.create(
                    first_name=user.first_name or user.username,
                    last_name=user.last_name or 'Tutor',
                    email=user.email,
                    phone=profile.phone_number or '+2340000000000',
                    hear='Portal',
                    lesson_type='Online lessons',
                    curriculum='British'
                )
        tutor_profile, _ = TutorProfile.objects.get_or_create(
            user=user,
            defaults={
                'tutor_record': tutor_rec,
                'display_name': user.get_full_name() or user.username,
                'phone': profile.phone_number or '+2340000000000',
                'hourly_base_rate': Decimal('5000.00'),
                'currency': 'NGN',
                'is_verified': True
            }
        )
    elif not tutor_profile.tutor_record and user.email:
        from tutors.models import Tutor as LegacyTutor
        tutor_rec = LegacyTutor.objects.filter(email__iexact=user.email).first()
        if not tutor_rec:
            tutor_rec = LegacyTutor.objects.create(
                first_name=user.first_name or user.username,
                last_name=user.last_name or 'Tutor',
                email=user.email,
                phone=profile.phone_number or '+2340000000000',
                hear='Portal',
                lesson_type='Online lessons',
                curriculum='British'
            )
        tutor_profile.tutor_record = tutor_rec
        tutor_profile.save(update_fields=['tutor_record'])

    # 1. Upcoming & Scheduled Teaching Sessions
    upcoming_sessions = ClassSession.objects.filter(
        booking__tutor=tutor_profile,
        end_time__gte=now,
        status__in=[SessionStatus.SCHEDULED, SessionStatus.IN_PROGRESS]
    ).select_related('booking', 'booking__student', 'booking__subject').order_by('start_time')[:10]

    # 2. Past Completed Sessions
    past_sessions_qs = ClassSession.objects.filter(
        booking__tutor=tutor_profile,
        status=SessionStatus.COMPLETED
    ).select_related('booking', 'booking__student', 'booking__subject').order_by('-start_time')
    past_sessions = past_sessions_qs[:10]

    # 3. Active Enrolled Student Bookings
    active_bookings = ClassBooking.objects.filter(
        tutor=tutor_profile,
        status=BookingStatus.ACTIVE
    ).select_related('student', 'subject')

    # 4. Monthly Verified Teaching Hours & Accrued Earnings
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_completed_sessions = past_sessions_qs.filter(start_time__gte=current_month_start)
    monthly_hours = sum(s.duration_minutes for s in month_completed_sessions) / 60
    monthly_earnings = round(Decimal(str(monthly_hours)) * tutor_profile.hourly_base_rate, 2)

    # 5. Bank Account & Payroll Status
    payroll_account = TutorBankAccount.objects.filter(tutor__email__iexact=user.email).first()

    # 6. QA Rating & Student Feedback
    feedbacks = LessonFeedback.objects.filter(
        session__booking__tutor=tutor_profile
    ).select_related('session', 'submitted_by')[:5]
    avg_rating = round(sum(f.rating for f in feedbacks) / feedbacks.count(), 1) if feedbacks.exists() else 5.0

    # 7. Student Homework Submissions & Grading
    homework_submissions_qs = HomeworkSubmission.objects.filter(
        session__booking__tutor=tutor_profile
    ).select_related('student', 'session', 'session__booking__subject').order_by('-submitted_at')
    homework_submissions = homework_submissions_qs[:15]

    # 8. Tutor's Historical Payslips & Compensation Records
    tutor_payslips = TutorPayrollItem.objects.filter(
        models.Q(tutor_email__iexact=user.email) | models.Q(tutor__email__iexact=user.email)
    ).select_related('payroll_run').order_by('-payroll_run__created_at')[:6]

    # 9. All resources uploaded by or for this tutor
    resources = LessonResource.objects.filter(
        models.Q(booking__tutor=tutor_profile) | 
        models.Q(session__booking__tutor=tutor_profile) | 
        models.Q(uploaded_by=user)
    ).select_related('booking', 'session', 'booking__student', 'booking__subject').distinct().order_by('-created_at')

    # 10. Tutor Onboarding Telemetry & Guided Experience
    has_tutor_phone = bool(profile.phone_number and profile.phone_number.strip() and profile.phone_number != '+2340000000000')
    step_tutor_profile = bool(has_tutor_phone and profile.headline and (profile.bio or profile.avatar))
    step_tutor_bank = bool(payroll_account is not None)
    step_tutor_rates = bool(tutor_profile.hourly_base_rate and tutor_profile.hourly_base_rate > Decimal('0.00'))
    step_tutor_tech = bool(request.session.get('tutor_tech_check_passed') or past_sessions_qs.exists())
    step_tutor_verified = bool(tutor_profile.is_verified)

    tutor_onboarding_steps = [
        {
            'id': 'profile',
            'title': 'Educator Dossier & Headline',
            'desc': 'Add your teaching qualifications, headline, and bio for parents and students.',
            'is_completed': step_tutor_profile,
            'action_url': reverse('profile_settings'),
            'action_label': 'Update Dossier',
            'icon': 'fa-solid fa-chalkboard-user',
            'badge': 'Required'
        },
        {
            'id': 'bank',
            'title': 'Link Nigerian Bank Account',
            'desc': 'Connect your verified NUBAN bank account for automated bi-weekly payroll disbursements.',
            'is_completed': step_tutor_bank,
            'action_url': reverse('payroll:link_bank', args=[tutor_profile.tutor_record.id]) if (tutor_profile and tutor_profile.tutor_record) else reverse('profile_settings'),
            'action_label': 'Link Bank Account',
            'icon': 'fa-solid fa-building-columns',
            'badge': 'Payroll'
        },
        {
            'id': 'rates',
            'title': 'Base Rate & Compensation Tier',
            'desc': f'Teaching rate confirmed at {tutor_profile.currency} {tutor_profile.hourly_base_rate:.2f}/hr.',
            'is_completed': step_tutor_rates,
            'action_url': reverse('payroll:rate_matrix'),
            'action_label': 'Rate Matrix',
            'icon': 'fa-solid fa-coins',
            'badge': 'Earnings'
        },
        {
            'id': 'tech_check',
            'title': 'Virtual Classroom Hardware Test',
            'desc': 'Verify your microphone, webcam, and browser permissions before meeting students.',
            'is_completed': step_tutor_tech,
            'action_onclick': "openModal('tutorTechCheckModal'); initHardwareTest('tutor');",
            'action_label': 'Run Test',
            'icon': 'fa-solid fa-video',
            'badge': 'Teaching'
        },
        {
            'id': 'verified',
            'title': 'Faculty Background Verification',
            'desc': 'Verified Educator in good standing with the Edukom Academic Advisory Board.' if step_tutor_verified else 'Credential vetting & background check in progress by Edukom Coordinators.',
            'is_completed': step_tutor_verified,
            'action_url': '#',
            'action_label': 'Verified' if step_tutor_verified else 'In Review',
            'icon': 'fa-solid fa-shield-halved',
            'badge': 'Faculty'
        }
    ]
    tutor_completed_count = sum(1 for s in tutor_onboarding_steps if s['is_completed'])
    tutor_onboarding_percent = int((tutor_completed_count / len(tutor_onboarding_steps)) * 100)
    is_tutor_onboarding_finished = (tutor_onboarding_percent == 100)
    is_tutor_onboarding_dismissed = request.session.get('tutor_onboarding_dismissed', False)
    is_returning_tutor = bool(past_sessions_qs.exists() or monthly_hours > 0 or active_bookings.exists())

    unsubmitted_notes_count = past_sessions_qs.filter(lesson_notes='').count()
    ungraded_homework_count = homework_submissions_qs.filter(status=SubmissionStatus.SUBMITTED).count()
    next_tutor_session = upcoming_sessions.first() if upcoming_sessions.exists() else None

    context = {
        'profile': profile,
        'tutor': tutor_profile,
        'upcoming_sessions': upcoming_sessions,
        'past_sessions': past_sessions,
        'active_bookings': active_bookings,
        'monthly_hours': round(monthly_hours, 1),
        'monthly_earnings': monthly_earnings,
        'payroll_account': payroll_account,
        'avg_rating': avg_rating,
        'feedbacks': feedbacks,
        'homework_submissions': homework_submissions,
        'tutor_payslips': tutor_payslips,
        'resources': resources,
        'resource_types': ResourceType.choices,
        'tutor_onboarding_steps': tutor_onboarding_steps,
        'tutor_completed_count': tutor_completed_count,
        'tutor_onboarding_percent': tutor_onboarding_percent,
        'is_tutor_onboarding_finished': is_tutor_onboarding_finished,
        'is_tutor_onboarding_dismissed': is_tutor_onboarding_dismissed,
        'is_returning_tutor': is_returning_tutor,
        'unsubmitted_notes_count': unsubmitted_notes_count,
        'ungraded_homework_count': ungraded_homework_count,
        'next_tutor_session': next_tutor_session,
        'now': now,
    }
    return render(request, 'account/dashboard_tutor.html', context)


# ==============================================================================
# 4. STAFF / OPERATIONS COORDINATOR DASHBOARD
# ==============================================================================
@login_required
@staff_required
def staff_dashboard_view(request: HttpRequest) -> HttpResponse:
    """
    Operations & Academic Coordination Command Center:
    Schedule oversight across all tutors and students, double-booking monitoring,
    QA alert triage (< 3 stars), pending notes verification, and 1-click payroll dispatch.
    """
    profile = request.user.profile
    now = timezone.now()

    # 1. Platform Operational Metrics
    total_students = Student.objects.filter(is_active=True).count()
    total_tutors = TutorProfile.objects.filter(is_active=True).count()
    active_bookings = ClassBooking.objects.filter(status=BookingStatus.ACTIVE).count()
    
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_sessions = ClassSession.objects.filter(start_time__gte=today_start, start_time__lte=today_start + timezone.timedelta(days=1))
    today_sessions_count = today_sessions.count()

    # 2. Live & Upcoming Sessions Across All Tutors
    upcoming_sessions = ClassSession.objects.filter(
        end_time__gte=now,
        status__in=[SessionStatus.SCHEDULED, SessionStatus.IN_PROGRESS]
    ).select_related('booking', 'booking__student', 'booking__tutor', 'booking__subject').order_by('start_time')[:10]

    # 3. QA Alerts: Lessons rated 3 stars or lower requiring coordinator review
    qa_alerts = LessonFeedback.objects.filter(
        rating__lte=3
    ).select_related('session', 'session__booking__tutor', 'session__booking__student').order_by('-created_at')[:8]

    # 4. Unsubmitted Lesson Notes (> 2 hours post class completion)
    unsubmitted_notes = ClassSession.objects.filter(
        end_time__lt=now - timezone.timedelta(hours=2),
        status=SessionStatus.SCHEDULED,
        lesson_topic__exact=''
    ).select_related('booking__tutor', 'booking__student')[:8]

    # 5. Recent Guardian Applications / Lead Requests
    recent_guardians = home_models.Guardian.objects.all().order_by('-date_joined')[:6]

    context = {
        'profile': profile,
        'total_students': total_students,
        'total_tutors': total_tutors,
        'active_bookings': active_bookings,
        'today_sessions_count': today_sessions_count,
        'upcoming_sessions': upcoming_sessions,
        'qa_alerts': qa_alerts,
        'unsubmitted_notes': unsubmitted_notes,
        'recent_guardians': recent_guardians,
        'now': now,
    }
    return render(request, 'account/dashboard_staff.html', context)


# ==============================================================================
# 5. ADMIN / EXECUTIVE PLATFORM DASHBOARD
# ==============================================================================
@login_required
@admin_required
def admin_dashboard_view(request: HttpRequest) -> HttpResponse:
    """
    Executive LMS Governance & System Dashboard:
    Platform revenue & tuition receipts, payroll liability & disbursement runs,
    user role management, live infrastructure telemetry, and forensic security audit stream.
    """
    profile = request.user.profile
    now = timezone.now()

    # 1. Executive Platform KPIs
    total_users = User.objects.count()
    total_students = Student.objects.count()
    total_tutors = TutorProfile.objects.count()
    completed_sessions = ClassSession.objects.filter(status=SessionStatus.COMPLETED).count()

    # Revenue
    paid_invoices = Invoice.objects.filter(status='PAID')
    gross_revenue = sum(inv.amount for inv in paid_invoices)

    # 2. User Management (Paginated List with Role Badges)
    role_filter = request.GET.get('role', '')
    users_qs = User.objects.select_related('profile').order_by('-date_joined')
    if role_filter:
        users_qs = users_qs.filter(profile__role=role_filter)

    paginator = Paginator(users_qs, 10)
    page_number = request.GET.get('page')
    users_page = paginator.get_page(page_number)

    # 3. Live Infrastructure Health Telemetry (Database, Redis, Disk)
    telemetry = run_health_checks()

    # 4. Recent Forensic Security Events
    # Read last 8 lines from security log if available
    security_events = []
    from django.conf import settings
    sec_log_path = getattr(settings, 'BASE_DIR') / 'logs' / 'security.log'
    if sec_log_path.exists():
        try:
            with open(sec_log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                security_events = [line.strip() for line in lines[-8:] if line.strip()]
        except Exception:
            pass

    # 5. Recent Payroll Runs
    recent_payroll_runs = PayrollRun.objects.all().order_by('-created_at')[:4]

    context = {
        'profile': profile,
        'total_users': total_users,
        'total_students': total_students,
        'total_tutors': total_tutors,
        'completed_sessions': completed_sessions,
        'gross_revenue': gross_revenue,
        'users_page': users_page,
        'selected_role': role_filter,
        'telemetry': telemetry,
        'security_events': security_events,
        'recent_payroll_runs': recent_payroll_runs,
        'all_roles': UserRole.choices,
        'now': now,
    }
    return render(request, 'account/dashboard_admin.html', context)


# ==============================================================================
# 6. USER ROLE MANAGEMENT & PROFILE SETTINGS
# ==============================================================================
@login_required
@admin_required
@require_POST
def update_user_role_view(request: HttpRequest, user_id: int) -> HttpResponse:
    """
    Allows Admins to change a user's role directly from the dashboard.
    """
    target_user = get_object_or_404(User, id=user_id)
    new_role = request.POST.get('role')

    if new_role in dict(UserRole.choices):
        profile = target_user.profile
        profile.role = new_role
        profile.save()

        # Synchronize Django staff/superuser flags
        if new_role == UserRole.ADMIN:
            target_user.is_staff = True
            target_user.is_superuser = True
        elif new_role == UserRole.STAFF:
            target_user.is_staff = True
            target_user.is_superuser = False
        else:
            target_user.is_staff = False
            target_user.is_superuser = False
        target_user.save()

        logger.info(f"Admin {request.user.username} modified role of user {target_user.username} to {new_role}")
        messages.success(request, f"Updated {target_user.username}'s role to {dict(UserRole.choices)[new_role]}.")
    else:
        messages.error(request, "Invalid role specified.")

    return redirect('dashboard_admin')


@login_required
def profile_settings_view(request: HttpRequest) -> HttpResponse:
    """
    Allows any user to update their phone number, timezone, avatar, headline, bio,
    and role-specific academic grade and curriculum preferences.
    """
    profile = request.user.profile
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone = request.POST.get('phone_number', '').strip()
        headline = request.POST.get('headline', '').strip()
        bio = request.POST.get('bio', '').strip()
        user_timezone = request.POST.get('timezone', 'Africa/Lagos').strip()
        student_grade = request.POST.get('student_grade', '').strip()
        curriculum = request.POST.get('curriculum', '').strip()

        request.user.first_name = first_name
        request.user.last_name = last_name
        request.user.save()

        profile.phone_number = phone
        profile.headline = headline
        profile.bio = bio
        profile.timezone = user_timezone
        if student_grade:
            profile.student_grade = student_grade
        if curriculum:
            profile.curriculum = curriculum

        if 'avatar' in request.FILES:
            profile.avatar = request.FILES['avatar']
        profile.save()

        # Sync Student model records if user has student associations
        student_records = Student.objects.filter(models.Q(user=request.user) | models.Q(guardian__email__iexact=request.user.email))
        for sr in student_records:
            if student_grade:
                sr.class_level = student_grade
            if curriculum:
                sr.curriculum = curriculum
            sr.save()

        messages.success(request, "Profile information updated successfully.")
        return redirect(profile.get_dashboard_url())

    return render(request, 'account/profile_settings.html', {'profile': profile})


@login_required
@require_POST
def complete_onboarding_step_api(request: HttpRequest) -> HttpResponse:
    """
    AJAX endpoint to record onboarding progress, dismiss cards, or record tech-checks.
    """
    try:
        data = json.loads(request.body) if request.body else request.POST
    except Exception:
        data = request.POST

    step = data.get('step')
    role = data.get('role', 'student')
    dismiss = data.get('dismiss', False)

    if dismiss:
        if role == 'tutor':
            request.session['tutor_onboarding_dismissed'] = True
        else:
            request.session['student_onboarding_dismissed'] = True
        request.session.modified = True
        return JsonResponse({'status': 'dismissed'})

    if step == 'undismiss':
        if role == 'tutor':
            request.session['tutor_onboarding_dismissed'] = False
        else:
            request.session['student_onboarding_dismissed'] = False
        request.session.modified = True
        return JsonResponse({'status': 'restored'})

    if step == 'tech_check':
        if role == 'tutor':
            request.session['tutor_tech_check_passed'] = True
        else:
            request.session['student_tech_check_passed'] = True
        request.session.modified = True
        return JsonResponse({'status': 'success', 'step': 'tech_check'})

    if step == 'calendar':
        if role == 'tutor':
            request.session['tutor_calendar_synced'] = True
        else:
            request.session['student_calendar_synced'] = True
        request.session.modified = True
        return JsonResponse({'status': 'success', 'step': 'calendar'})

    if step == 'goals' or step == 'diagnostic':
        request.session['student_diagnostic_done'] = True
        request.session.modified = True
        return JsonResponse({'status': 'success', 'step': 'diagnostic'})

    return JsonResponse({'status': 'acknowledged'})


def register_view(request: HttpRequest) -> HttpResponse:
    """
    Public student/tutor registration view with role selection.
    """
    if request.user.is_authenticated:
        return redirect('dashboard_dispatcher')

    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        role = request.POST.get('role', UserRole.STUDENT)
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()

        if form.is_valid():
            user = form.save(commit=False)
            user.email = email
            user.first_name = first_name
            user.last_name = last_name
            user.save()

            # Set role on profile
            profile = user.profile
            if role in [UserRole.STUDENT, UserRole.TUTOR, UserRole.GUARDIAN]:
                profile.role = role
                profile.save()

            if role == UserRole.GUARDIAN:
                home_models.Guardian.objects.get_or_create(
                    email=user.email,
                    defaults={
                        'first_name': user.first_name or user.username,
                        'last_name': user.last_name or 'Guardian',
                        'phone': profile.phone_number or '+2340000000000',
                        'curriculum': 'British',
                        'lesson_type': 'Online lessons',
                    }
                )

            login(request, user)
            messages.success(request, f"Welcome to Edukom, {user.first_name or user.username}! Your academic portal is ready.")
            return redirect(profile.get_dashboard_url())
    else:
        form = UserCreationForm()

    return render(request, 'account/register.html', {'form': form})


# ==============================================================================
# 7. LEGACY VIEWS (PRESERVED FOR BACKWARD COMPATIBILITY)
# ==============================================================================
@login_required
def GuardianListView(request):
    order = request.GET.get('order', 'desc')
    if order == 'asc':
        guardian = home_models.Guardian.objects.all().order_by('date_joined')
        tutor = tmodels.Tutor.objects.all().order_by('date_joined')
    else:
        guardian = home_models.Guardian.objects.all().order_by('-date_joined')
        tutor = tmodels.Tutor.objects.all().order_by('-date_joined')
        
    context = {
        'guardian': guardian,
        'tutor': tutor,
        'current_order': order
    }
    return render(request, 'Request/list.html', context)


@login_required
def GuardianDetailView(request, uid):
    guardian = home_models.Guardian.objects.get(uid=uid)
    context = {
        'guardian': guardian
    }
    return render(request, 'Request/details.html', context)


@login_required
def TutorDetailView(request, uid):
    tutor = tmodels.Tutor.objects.get(uid=uid)
    context = {
        'tutor': tutor
    }
    return render(request, 'Request/tutordetail.html', context)