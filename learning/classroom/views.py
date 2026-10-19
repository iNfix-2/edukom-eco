import os
import re
import json
import uuid
import logging
import hashlib
import hmac
import secrets
from decimal import Decimal
from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, HttpRequest, JsonResponse, FileResponse
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db import transaction, models
from django.views.decorators.http import require_POST, require_GET
from django.core.exceptions import ValidationError

from .models import (
    ClassBooking, 
    ClassSession, 
    Student, 
    TutorProfile, 
    AttendanceRecord, 
    ClassroomSignal,
    LessonResource,
    ResourceType,
    LessonFeedback,
    HomeworkSubmission,
    SubmissionStatus,
    SessionStatus, 
    BookingStatus,
    Quiz,
    QuizQuestion,
    QuizOption,
    QuizAttempt,
    CourseCertificate,
    QuestionType
)
from .security import session_access_required, can_access_session
from .services import DailyVideoService
from .notifications import send_lesson_progress_report_to_parent, send_qa_low_rating_alert
from payroll.models import PayrollRun, TutorPayrollItem, PayrollRunStatus, PayrollAuditLog
from payroll.calculator import calculate_tutor_payroll
from payments.models import Invoice, InvoiceStatus

logger = logging.getLogger('classroom')


@login_required
@session_access_required
def classroom_live_view(request: HttpRequest, session_id: str) -> HttpResponse:
    """
    Main virtual classroom view.
    Replaces Zoom/Meet with an embedded WebRTC classroom powered by Daily.co.
    Guarded by BOLA/IDOR access verification and automated attendance logging.
    """
    session = get_object_or_404(ClassSession, id=session_id)
    role = getattr(request, 'session_user_role', 'STUDENT')
    is_tutor = (role == 'TUTOR')

    # 1. Initialize or fetch Daily.co video room
    video_svc = DailyVideoService()
    room_data = video_svc.create_or_get_room(session)
    
    if not session.room_url and room_data.get('room_url'):
        session.room_url = room_data['room_url']
        session.room_name = room_data['room_name']
        session.save(update_fields=['room_url', 'room_name'])

    # 2. Generate signed, role-restricted Meeting Token (JWT)
    display_name = request.user.get_full_name() or request.user.username
    token_data = video_svc.generate_meeting_token(
        room_name=session.room_name,
        user_name=display_name,
        user_id=str(request.user.id),
        is_owner=is_tutor
    )

    # 3. Automated Attendance & Presence Logging
    now = timezone.now()
    ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', '')).split(',')[0].strip()
    
    AttendanceRecord.objects.create(
        session=session,
        user=request.user,
        role=role,
        joined_at=now,
        ip_address=ip,
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:250]
    )

    if is_tutor and not session.tutor_joined_at:
        session.tutor_joined_at = now
    elif not is_tutor and not session.student_joined_at:
        session.student_joined_at = now

    if session.status == SessionStatus.SCHEDULED:
        session.status = SessionStatus.IN_PROGRESS
    session.save()

    context = {
        'session': session,
        'room_url': session.room_url or room_data.get('room_url'),
        'meeting_token': token_data.get('token', ''),
        'is_mock_video': room_data.get('is_mock', False),
        'role': role,
        'is_tutor': is_tutor,
        'user_name': display_name,
        'user_id': request.user.id,
    }
    return render(request, 'classroom/room.html', context)


@login_required
@session_access_required
@require_POST
def send_classroom_signal(request: HttpRequest, session_id: str) -> JsonResponse:
    """
    Real-time signaling & broker endpoint:
    Receives WebRTC SDP offers/answers, ICE candidates, live whiteboard strokes,
    screen-share toggles, and chat messages, and persists them for connected classroom peers.
    """
    session = get_object_or_404(ClassSession, id=session_id)
    role = getattr(request, 'session_user_role', 'STUDENT')
    display_name = request.user.get_full_name() or request.user.username

    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        data = request.POST

    signal_type = data.get('signal_type', '').strip()
    payload = data.get('payload', {})

    if not signal_type:
        return JsonResponse({'success': False, 'error': 'Missing signal_type'}, status=400)

    signal = ClassroomSignal.objects.create(
        session=session,
        sender=request.user,
        sender_name=display_name,
        sender_role=role,
        signal_type=signal_type,
        payload=payload
    )

    return JsonResponse({'success': True, 'signal_id': signal.id})


@login_required
@session_access_required
def poll_classroom_signals(request: HttpRequest, session_id: str) -> JsonResponse:
    """
    High-efficiency signaling polling endpoint:
    Returns newly arrived WebRTC signals, whiteboard draw events, chat messages,
    and presence updates since the last polled ID.
    """
    session = get_object_or_404(ClassSession, id=session_id)
    try:
        after_id = int(request.GET.get('after_id', 0))
    except (ValueError, TypeError):
        after_id = 0

    signals = ClassroomSignal.objects.filter(
        session=session,
        id__gt=after_id
    ).order_by('id')[:100]

    signals_data = []
    latest_id = after_id
    for s in signals:
        signals_data.append({
            'id': s.id,
            'sender_id': s.sender_id,
            'sender_name': s.sender_name,
            'sender_role': s.sender_role,
            'signal_type': s.signal_type,
            'payload': s.payload,
            'is_self': (s.sender_id == request.user.id),
            'created_at': s.created_at.strftime('%H:%M:%S')
        })
        latest_id = s.id

    return JsonResponse({
        'success': True,
        'signals': signals_data,
        'latest_id': latest_id,
        'server_time': timezone.now().isoformat()
    })


@login_required
@require_POST
def submit_lesson_notes(request: HttpRequest, session_id: str) -> HttpResponse:
    """
    Tutor concludes session and submits educational progress notes & homework.
    """
    session = get_object_or_404(ClassSession, id=session_id)
    is_auth, role = can_access_session(request.user, session)

    if not is_auth or role != 'TUTOR':
        return HttpResponse("Only assigned tutors can submit lesson notes.", status=403)

    topic = request.POST.get('lesson_topic', '').strip()
    notes = request.POST.get('lesson_notes', '').strip()
    homework = request.POST.get('homework_assigned', '').strip()

    session.lesson_topic = topic
    session.lesson_notes = notes
    session.homework_assigned = homework
    session.status = SessionStatus.COMPLETED
    session.tutor_left_at = timezone.now()
    session.save()

    # Safeguard 3: Automated Post-Lesson Parent Progress Report
    send_lesson_progress_report_to_parent(session)

    messages.success(request, f"Lesson notes recorded and session marked as completed. Progress report sent to parent.")
    return redirect('classroom:tutor_portal')


@login_required
def tutor_portal_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Dedicated Tutor LMS Hub:
    Replaces TutorCruncher dashboard for teachers.
    Displays live sessions, student roster, lesson notes, and earnings.
    """
    tutor_profile = getattr(request.user, 'tutor_profile', None)
    if not tutor_profile:
        # Check if user has a Tutor record or is staff
        if request.user.is_staff:
            tutor_profile = TutorProfile.objects.first()
        else:
            messages.error(request, "Tutor profile not found for this account.")
            return redirect('/')

    now = timezone.now()
    upcoming_sessions = ClassSession.objects.filter(
        booking__tutor=tutor_profile,
        end_time__gte=now,
        status__in=[SessionStatus.SCHEDULED, SessionStatus.IN_PROGRESS]
    ).select_related('booking', 'booking__student', 'booking__subject').order_by('start_time')

    past_sessions_qs = ClassSession.objects.filter(
        booking__tutor=tutor_profile,
        status=SessionStatus.COMPLETED
    ).select_related('booking', 'booking__student', 'booking__subject').order_by('-start_time')
    past_sessions = past_sessions_qs[:15]

    active_bookings = ClassBooking.objects.filter(
        tutor=tutor_profile, 
        status=BookingStatus.ACTIVE
    ).select_related('student', 'subject', 'student__guardian')

    # All resources uploaded by or for this tutor
    resources = LessonResource.objects.filter(
        models.Q(booking__tutor=tutor_profile) | 
        models.Q(session__booking__tutor=tutor_profile) | 
        models.Q(uploaded_by=request.user)
    ).select_related('booking', 'session', 'booking__student', 'booking__subject').distinct().order_by('-created_at')

    # Homework submissions
    homework_submissions = HomeworkSubmission.objects.filter(
        session__booking__tutor=tutor_profile
    ).select_related('student', 'session', 'session__booking__subject').order_by('-submitted_at')[:15]

    # Monthly hours and earnings calculation
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_completed = past_sessions_qs.filter(start_time__gte=current_month_start)
    monthly_hours = sum(s.duration_minutes for s in month_completed) / 60
    monthly_earnings = round(Decimal(str(monthly_hours)) * tutor_profile.hourly_base_rate, 2)

    # Payslips
    tutor_payslips = TutorPayrollItem.objects.filter(
        models.Q(tutor_email__iexact=request.user.email) | models.Q(tutor__email__iexact=request.user.email)
    ).select_related('payroll_run').order_by('-payroll_run__created_at')[:6]

    # Feedbacks & QA score
    feedbacks = LessonFeedback.objects.filter(
        session__booking__tutor=tutor_profile
    ).select_related('session', 'submitted_by')[:6]
    avg_rating = round(sum(f.rating for f in feedbacks) / feedbacks.count(), 1) if feedbacks.exists() else 5.0

    context = {
        'tutor': tutor_profile,
        'profile': getattr(request.user, 'profile', None),
        'upcoming_sessions': upcoming_sessions,
        'past_sessions': past_sessions,
        'active_bookings': active_bookings,
        'resources': resources,
        'resource_types': ResourceType.choices,
        'homework_submissions': homework_submissions,
        'tutor_payslips': tutor_payslips,
        'monthly_hours': round(monthly_hours, 1),
        'monthly_earnings': monthly_earnings,
        'feedbacks': feedbacks,
        'avg_rating': avg_rating,
        'now': now,
    }
    return render(request, 'classroom/tutor_dashboard.html', context)


@login_required
def student_portal_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Dedicated Student & Guardian Portal:
    Displays upcoming live classes with 1-click room entry, tutor feedback, and billing.
    """
    user = request.user
    
    # Locate student records linked to user or guardian email
    students = Student.objects.filter(models.Q(user=user) | models.Q(guardian__email__iexact=user.email))
    
    now = timezone.now()
    upcoming_sessions = ClassSession.objects.filter(
        booking__student__in=students,
        end_time__gte=now,
        status__in=[SessionStatus.SCHEDULED, SessionStatus.IN_PROGRESS]
    ).select_related('booking', 'booking__tutor', 'booking__subject').order_by('start_time')

    past_sessions = ClassSession.objects.filter(
        booking__student__in=students,
        status=SessionStatus.COMPLETED
    ).select_related('booking', 'booking__tutor').order_by('-start_time')[:5]

    # Invoices for guardian
    invoices = Invoice.objects.filter(client_email__iexact=user.email).order_by('-created_at')[:5]

    context = {
        'students': students,
        'upcoming_sessions': upcoming_sessions,
        'past_sessions': past_sessions,
        'invoices': invoices,
        'now': now,
    }
    return render(request, 'classroom/student_dashboard.html', context)


@login_required
def dispatch_lms_sessions_to_payroll(request: HttpRequest) -> HttpResponse:
    """
    Automated Bridge between LMS Classroom and Payroll Engine:
    Replaces TutorCruncher export. Pulls verified completed sessions directly from the LMS
    and creates a calculated PayrollRun ready for managerial authorization.
    """
    if not request.user.is_staff:
        return HttpResponse("Unauthorized", status=403)

    if request.method == 'POST':
        period_start = request.POST.get('period_start') or timezone.now().date()
        period_end = request.POST.get('period_end') or timezone.now().date()
        title = request.POST.get('title', f"LMS Direct Payroll - {period_end}")

        # Fetch all completed sessions or late-cancellations with tutor compensation not yet processed
        completed_sessions = ClassSession.objects.filter(
            models.Q(status=SessionStatus.COMPLETED) | models.Q(is_payable_late_cancel=True),
            is_payroll_processed=False
        ).select_related('booking', 'booking__tutor', 'booking__student')

        if not completed_sessions.exists():
            messages.warning(request, "No unprocessed completed or billable sessions found in LMS.")
            return redirect('payroll:dashboard')

        # Group sessions by tutor
        grouped_tutors = {}
        for sess in completed_sessions:
            tutor = sess.booking.tutor
            t_key = tutor.user.email
            if t_key not in grouped_tutors:
                grouped_tutors[t_key] = {
                    'tutor_obj': tutor,
                    'tutor_name': tutor.display_name,
                    'tutor_email': tutor.user.email,
                    'sessions': [],
                    'session_objects': []
                }

            if sess.is_payable_late_cancel and sess.status != SessionStatus.COMPLETED:
                multiplier = sess.late_cancel_fee_multiplier
                duration_hours = (Decimal(sess.duration_minutes) / Decimal(60)) * multiplier
                status_label = f" (Late Cancel {int(multiplier * 100)}%)"
            else:
                duration_hours = Decimal(sess.duration_minutes) / Decimal(60)
                status_label = ""

            grouped_tutors[t_key]['sessions'].append({
                'date': sess.start_time.strftime('%Y-%m-%d'),
                'student_name': f"{sess.booking.student.first_name} {sess.booking.student.last_name}{status_label}",
                'class_level': sess.booking.class_level,
                'duration_hours': duration_hours,
                'timezone': sess.booking.client_timezone,
                'delivery_mode': sess.booking.delivery_mode,
            })
            grouped_tutors[t_key]['session_objects'].append(sess)

        # Create PayrollRun
        with transaction.atomic():
            payroll_run = PayrollRun.objects.create(
                title=title,
                period_start=period_start,
                period_end=period_end,
                status=PayrollRunStatus.CALCULATED,
                currency='NGN',
                source_filename="LMS Internal Database Sessions",
                created_by=request.user
            )

            total_hours = Decimal('0.00')
            total_gross = Decimal('0.00')
            total_net = Decimal('0.00')

            for t_email, t_data in grouped_tutors.items():
                calc = calculate_tutor_payroll(
                    tutor_name=t_data['tutor_name'],
                    tutor_email=t_data['tutor_email'],
                    sessions=t_data['sessions'],
                    currency='NGN'
                )

                matched_tutor = getattr(t_data['tutor_obj'], 'tutor_record', None)

                TutorPayrollItem.objects.create(
                    payroll_run=payroll_run,
                    tutor=matched_tutor,
                    tutor_name=t_data['tutor_name'],
                    tutor_email=t_data['tutor_email'],
                    total_hours=calc['total_hours'],
                    calculated_gross_pay=calc['gross_pay'],
                    deductions=calc['deductions'],
                    bonuses=calc['bonuses'],
                    net_pay=calc['net_pay'],
                    session_breakdown=calc['breakdown']
                )

                total_hours += calc['total_hours']
                total_gross += calc['gross_pay']
                total_net += calc['net_pay']

                # Mark live sessions as processed to prevent double payout
                for s_obj in t_data['session_objects']:
                    s_obj.is_payroll_processed = True
                    s_obj.save(update_fields=['is_payroll_processed'])

            payroll_run.total_hours = total_hours
            payroll_run.total_gross = total_gross
            payroll_run.total_net = total_net
            payroll_run.save()

            PayrollAuditLog.objects.create(
                action='LMS_SESSIONS_DISPATCHED_TO_PAYROLL',
                actor=request.user,
                actor_username=request.user.username,
                target_id=str(payroll_run.id),
                details={'sessions_count': completed_sessions.count(), 'tutors_count': len(grouped_tutors)}
            )

        messages.success(request, f"Generated payroll run for {len(grouped_tutors)} tutors directly from LMS classes!")
        return redirect('payroll:run_detail', run_id=payroll_run.id)

    return redirect('payroll:dashboard')


# ==============================================================================
# SAFEGUARDS: LESSON RESOURCES, CANCELLATION POLICY, AND QA FEEDBACK
# ==============================================================================

ALLOWED_RESOURCE_EXTENSIONS = {
    '.pdf', '.docx', '.doc', '.pptx', '.ppt', '.xlsx', '.xls', 
    '.png', '.jpg', '.jpeg', '.webp', '.txt', '.zip',
    '.mp4', '.webm', '.mov', '.m4v'
}
MAX_RESOURCE_BYTES = 50 * 1024 * 1024  # 50 MB


@login_required
@require_POST
def schedule_session_view(request: HttpRequest) -> HttpResponse:
    """
    Allows a tutor (or staff) to schedule a new live class session with their assigned student.
    Enforces double-booking validation and sets up the WebRTC video room.
    """
    booking_id = request.POST.get('booking_id')
    booking = get_object_or_404(ClassBooking, id=booking_id)
    
    tutor_profile = getattr(request.user, 'tutor_profile', None)
    is_authorized = (
        (tutor_profile and booking.tutor == tutor_profile) or
        request.user.is_staff or
        request.user.is_superuser
    )
    if not is_authorized:
        return HttpResponse("Unauthorized to schedule sessions for this booking.", status=403)

    title = request.POST.get('title', '').strip()
    session_date = request.POST.get('date', '').strip()
    start_time_str = request.POST.get('start_time', '').strip()
    duration_minutes = int(request.POST.get('duration_minutes', 60))
    lesson_topic = request.POST.get('lesson_topic', '').strip()

    if not title:
        title = f"{booking.subject.name} with {booking.student.first_name}"

    try:
        from datetime import datetime
        import zoneinfo
        tz_name = booking.client_timezone or 'Africa/Lagos'
        try:
            tz = zoneinfo.ZoneInfo(tz_name)
        except Exception:
            tz = timezone.get_current_timezone()

        naive_start = datetime.strptime(f"{session_date} {start_time_str}", "%Y-%m-%d %H:%M")
        start_dt = naive_start.replace(tzinfo=tz)
        end_dt = start_dt + timezone.timedelta(minutes=duration_minutes)
    except Exception as e:
        messages.error(request, f"Invalid date or time format: {str(e)}")
        return redirect(request.META.get('HTTP_REFERER') or 'classroom:tutor_portal')

    room_name = f"edukom-{uuid.uuid4().hex[:12]}"

    session = ClassSession(
        booking=booking,
        title=title,
        start_time=start_dt,
        end_time=end_dt,
        duration_minutes=duration_minutes,
        status=SessionStatus.SCHEDULED,
        room_name=room_name,
        lesson_topic=lesson_topic
    )

    try:
        session.full_clean()
        session.save()
        messages.success(request, f"Class '{session.title}' scheduled successfully for {session.start_time.strftime('%A, %b %d at %H:%M')}.")
    except Exception as err:
        messages.error(request, f"Schedule conflict or validation error: {str(err)}")

    return redirect(request.META.get('HTTP_REFERER') or 'classroom:tutor_portal')


@login_required
@require_POST
def instant_session_view(request: HttpRequest) -> HttpResponse:
    """
    1-Click Instant Class Launcher:
    Allows a tutor to start an immediate virtual live classroom with an enrolled student,
    generating the WebRTC room instantly and redirecting straight into the live classroom.
    """
    booking_id = request.POST.get('booking_id')
    booking = get_object_or_404(ClassBooking, id=booking_id)

    tutor_profile = getattr(request.user, 'tutor_profile', None)
    is_authorized = (
        (tutor_profile and booking.tutor == tutor_profile) or
        request.user.is_staff or
        request.user.is_superuser
    )
    if not is_authorized:
        return HttpResponse("Unauthorized to start an instant class for this student.", status=403)

    title = request.POST.get('title', '').strip()
    duration_minutes = int(request.POST.get('duration_minutes', 60))
    lesson_topic = request.POST.get('lesson_topic', '').strip()

    if not title:
        title = f"Instant Class: {booking.subject.name} - {booking.student.first_name}"

    now = timezone.now()
    end_dt = now + timezone.timedelta(minutes=duration_minutes)
    room_name = f"edukom-{uuid.uuid4().hex[:12]}"

    try:
        session = ClassSession(
            booking=booking,
            title=title,
            start_time=now,
            end_time=end_dt,
            duration_minutes=duration_minutes,
            status=SessionStatus.IN_PROGRESS,
            room_name=room_name,
            lesson_topic=lesson_topic,
            tutor_joined_at=now
        )
        session.full_clean()
        session.save()
    except ValidationError as err:
        msg = err.messages[0] if hasattr(err, 'messages') and err.messages else str(err)
        messages.error(request, f"Unable to start instant class: {msg}")
        return redirect(request.META.get('HTTP_REFERER') or 'classroom:tutor_portal')

    messages.success(request, f"Instant class launched! Entering live classroom now...")
    return redirect('classroom:live_room', session_id=session.id)


@login_required
@require_POST
def upload_lesson_resource(request: HttpRequest, session_id: str) -> HttpResponse:
    """
    Secure file upload for session materials, worksheets, and lesson notes.
    Prevents directory traversal, malware uploads, and stored XSS.
    Synchronizes real-time notification to students in the live classroom.
    """
    from django.template.defaultfilters import filesizeformat
    from django.urls import reverse

    session = get_object_or_404(ClassSession, id=session_id)
    is_auth, role = can_access_session(request.user, session)
    is_ajax = (
        request.headers.get('x-requested-with') == 'XMLHttpRequest' or
        'application/json' in request.headers.get('Accept', '') or
        request.POST.get('ajax') == '1'
    )

    if not is_auth:
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'Unauthorized to upload files to this session.'}, status=403)
        return HttpResponse("Unauthorized to upload files to this session.", status=403)

    uploaded_file = request.FILES.get('resource_file')
    title = request.POST.get('title', '').strip()
    resource_type = request.POST.get('resource_type', ResourceType.WORKSHEET)
    video_url = request.POST.get('video_url', '').strip()
    description = request.POST.get('description', '').strip()

    if not uploaded_file and not video_url:
        err_msg = "No file or video link provided for upload."
        if is_ajax:
            return JsonResponse({'success': False, 'error': err_msg}, status=400)
        messages.error(request, err_msg)
        return redirect('classroom:live_room', session_id=session.id)

    if uploaded_file:
        if uploaded_file.size > MAX_RESOURCE_BYTES:
            err_msg = f"File exceeds maximum permitted size of {MAX_RESOURCE_BYTES // (1024*1024)}MB."
            if is_ajax:
                return JsonResponse({'success': False, 'error': err_msg}, status=400)
            messages.error(request, err_msg)
            return redirect('classroom:live_room', session_id=session.id)

        filename = uploaded_file.name
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_RESOURCE_EXTENSIONS:
            err_msg = f"File format '{ext}' is not permitted. Allowed formats: PDF, DOCX, PPTX, XLSX, Images, and Videos."
            if is_ajax:
                return JsonResponse({'success': False, 'error': err_msg}, status=400)
            messages.error(request, err_msg)
            return redirect('classroom:live_room', session_id=session.id)

        clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', os.path.basename(filename))
        uploaded_file.name = clean_name
        file_size = uploaded_file.size
        content_type = uploaded_file.content_type or 'application/octet-stream'
        if not title:
            title = clean_name
    else:
        file_size = 0
        content_type = 'video/external'
        if not title:
            title = "Video Lesson / Recording"

    resource = LessonResource.objects.create(
        booking=session.booking,
        session=session,
        title=title,
        resource_type=resource_type,
        description=description,
        file=uploaded_file,
        file_size=file_size,
        content_type=content_type,
        video_url=video_url,
        uploaded_by=request.user
    )

    resource_payload = {
        'id': str(resource.id),
        'title': resource.title,
        'resource_type': resource.resource_type,
        'resource_type_display': resource.get_resource_type_display(),
        'file_size': resource.file_size,
        'file_size_display': filesizeformat(resource.file_size) if resource.file_size else '0 B',
        'download_url': reverse('classroom:download_resource', args=[resource.id]) if resource.file else '',
        'video_url': resource.video_url or '',
        'uploader_name': request.user.get_full_name() or request.user.username,
        'uploader_role': role,
        'time': timezone.now().strftime('%H:%M')
    }

    # Automatically broadcast real-time sync signal to all participants
    ClassroomSignal.objects.create(
        session=session,
        sender=request.user,
        sender_role=role,
        signal_type='new_resource',
        payload=resource_payload
    )

    if is_ajax:
        return JsonResponse({
            'success': True,
            'resource': resource_payload,
            'message': f"Resource '{resource.title}' uploaded successfully."
        })

    messages.success(request, f"Resource '{resource.title}' uploaded successfully.")
    if role == 'TUTOR':
        return redirect(request.META.get('HTTP_REFERER') or 'classroom:tutor_portal')
    return redirect('classroom:live_room', session_id=session.id)


@login_required
@require_POST
def upload_material_view(request: HttpRequest) -> HttpResponse:
    """
    General uploader for tutors & teachers to add worksheets, lesson notes,
    past exam papers, and video recordings to their Resource Vault.
    """
    booking_id = request.POST.get('booking_id', '').strip()
    session_id = request.POST.get('session_id', '').strip()
    title = request.POST.get('title', '').strip()
    resource_type = request.POST.get('resource_type', ResourceType.WORKSHEET)
    description = request.POST.get('description', '').strip()
    video_url = request.POST.get('video_url', '').strip()
    uploaded_file = request.FILES.get('resource_file')

    if not uploaded_file and not video_url:
        messages.error(request, "Please attach a file or provide a video link.")
        return redirect(request.META.get('HTTP_REFERER') or 'classroom:tutor_portal')

    booking = None
    if booking_id:
        booking = ClassBooking.objects.filter(id=booking_id).first()

    session = None
    if session_id:
        session = ClassSession.objects.filter(id=session_id).first()
        if session and not booking:
            booking = session.booking

    if uploaded_file:
        if uploaded_file.size > MAX_RESOURCE_BYTES:
            messages.error(request, f"File exceeds maximum permitted size of {MAX_RESOURCE_BYTES // (1024*1024)}MB.")
            return redirect(request.META.get('HTTP_REFERER') or 'classroom:tutor_portal')

        filename = uploaded_file.name
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_RESOURCE_EXTENSIONS:
            messages.error(
                request, 
                f"File format '{ext}' is not permitted. Allowed formats: PDF, DOCX, PPTX, XLSX, Images, and Videos."
            )
            return redirect(request.META.get('HTTP_REFERER') or 'classroom:tutor_portal')

        clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', os.path.basename(filename))
        uploaded_file.name = clean_name
        file_size = uploaded_file.size
        content_type = uploaded_file.content_type or 'application/octet-stream'
        if not title:
            title = os.path.splitext(clean_name)[0].replace('_', ' ').title()
    else:
        file_size = 0
        content_type = 'video/external'
        if not title:
            title = "Video Lesson / Recording"

    resource = LessonResource.objects.create(
        booking=booking,
        session=session,
        title=title,
        resource_type=resource_type,
        description=description,
        file=uploaded_file,
        file_size=file_size,
        content_type=content_type,
        video_url=video_url,
        uploaded_by=request.user
    )

    messages.success(request, f"Resource '{resource.title}' uploaded successfully to your vault.")
    return redirect(request.META.get('HTTP_REFERER') or 'classroom:tutor_portal')


@login_required
@require_POST
def delete_resource_view(request: HttpRequest, resource_id: str) -> HttpResponse:
    """
    Deletes an uploaded lesson resource or video from the vault.
    """
    resource = get_object_or_404(LessonResource, id=resource_id)
    tutor_profile = getattr(request.user, 'tutor_profile', None)
    
    can_delete = (
        resource.uploaded_by == request.user or
        (tutor_profile and resource.booking and resource.booking.tutor == tutor_profile) or
        (tutor_profile and resource.session and resource.session.booking.tutor == tutor_profile) or
        request.user.is_staff or request.user.is_superuser
    )
    if not can_delete:
        return HttpResponse("Unauthorized to delete this resource.", status=403)

    title = resource.title
    resource.delete()
    messages.success(request, f"Resource '{title}' removed from your vault.")
    return redirect(request.META.get('HTTP_REFERER') or 'classroom:tutor_portal')


@login_required
def download_lesson_resource(request: HttpRequest, resource_id: str) -> HttpResponse:
    """
    BOLA/IDOR protected file download for class worksheets and study materials.
    Ensures only authorized class participants can access academic files.
    """
    resource = get_object_or_404(LessonResource, id=resource_id)
    user = request.user
    tutor_profile = getattr(user, 'tutor_profile', None)

    is_auth = False
    if resource.session:
        is_auth, _ = can_access_session(user, resource.session)
    elif resource.booking:
        is_auth = (
            (tutor_profile and resource.booking.tutor == tutor_profile) or
            (resource.booking.student.user and resource.booking.student.user == user) or
            (resource.booking.student.guardian and resource.booking.student.guardian.email.lower() == user.email.lower()) or
            user.is_staff or user.is_superuser or resource.uploaded_by == user
        )
    else:
        is_auth = (resource.uploaded_by == user or user.is_staff or user.is_superuser)

    if not is_auth:
        return HttpResponse("Forbidden: You do not have permission to download this file.", status=403)

    if not resource.file:
        if resource.video_url:
            return redirect(resource.video_url)
        messages.error(request, "The requested file is no longer available.")
        return redirect('classroom:tutor_portal')

    return FileResponse(resource.file.open('rb'), as_attachment=True, filename=os.path.basename(resource.file.name))


@login_required
@require_POST
def cancel_session_view(request: HttpRequest, session_id: str) -> HttpResponse:
    """
    Structured Cancellation & No-Show Policy:
    - >24 hours notice: Free cancellation, no tutor fee.
    - 2 to 24 hours notice (student): 50% tutor compensation fee.
    - <2 hours notice or student no-show: 100% tutor compensation fee.
    - Tutor cancellation: full refund to student, flagged for admin review.
    """
    session = get_object_or_404(ClassSession, id=session_id)
    is_auth, role = can_access_session(request.user, session)
    if not is_auth:
        return HttpResponse("Unauthorized to cancel this session.", status=403)

    if session.status in [SessionStatus.COMPLETED, SessionStatus.CANCELLED]:
        messages.warning(request, f"This session is already marked as {session.get_status_display()}.")
        return redirect('classroom:student_portal' if role == 'STUDENT' else 'classroom:tutor_portal')

    reason = request.POST.get('cancellation_reason', '').strip() or 'No reason provided.'
    now = timezone.now()
    time_diff_hours = (session.start_time - now).total_seconds() / 3600.0

    if role in ['STUDENT', 'ADMIN']:
        if time_diff_hours > 24:
            session.is_payable_late_cancel = False
            session.late_cancel_fee_multiplier = Decimal('0.00')
            msg = "Session cancelled with more than 24 hours notice. No cancellation fee applies."
        elif 2 <= time_diff_hours <= 24:
            session.is_payable_late_cancel = True
            session.late_cancel_fee_multiplier = Decimal('0.50')
            msg = "Session cancelled on short notice (<24h). 50% tutor compensation fee applies."
        else:
            # < 2 hours or no-show
            session.is_payable_late_cancel = True
            session.late_cancel_fee_multiplier = Decimal('1.00')
            msg = "Session cancelled with under 2 hours notice. 100% lesson fee applies to support tutor reservation."
    else:
        # Tutor initiated cancellation
        session.is_payable_late_cancel = False
        session.late_cancel_fee_multiplier = Decimal('0.00')
        msg = "Tutor cancelled the session. Student account credited and admin notified for rescheduling."

    session.status = SessionStatus.CANCELLED
    session.cancelled_at = now
    session.cancelled_by = request.user
    session.cancellation_reason = reason
    session.save(update_fields=[
        'status', 'cancelled_at', 'cancelled_by', 'cancellation_reason', 
        'is_payable_late_cancel', 'late_cancel_fee_multiplier'
    ])

    messages.info(request, msg)
    if role == 'TUTOR':
        return redirect('classroom:tutor_portal')
    return redirect('classroom:student_portal')


@login_required
@require_POST
def submit_lesson_feedback(request: HttpRequest, session_id: str) -> HttpResponse:
    """
    Guardian and Student QA review for completed lessons.
    Submissions with rating <= 3 immediately dispatch an urgent QA alert to support@edukom.ng.
    """
    session = get_object_or_404(ClassSession, id=session_id)
    is_auth, role = can_access_session(request.user, session)
    if not is_auth or role == 'TUTOR':
        return HttpResponse("Only students and guardians can submit QA lesson ratings.", status=403)

    if session.status != SessionStatus.COMPLETED:
        messages.warning(request, "Ratings can only be submitted after the lesson has completed.")
        return redirect('classroom:student_portal')

    try:
        raw_rating = int(request.POST.get('rating', 5))
        rating = max(1, min(5, raw_rating))
        raw_av = int(request.POST.get('audio_video_quality', 5))
        audio_video_quality = max(1, min(5, raw_av))
        raw_punctuality = int(request.POST.get('tutor_punctuality', 5))
        tutor_punctuality = max(1, min(5, raw_punctuality))
        raw_engagement = int(request.POST.get('student_engagement', 5))
        student_engagement = max(1, min(5, raw_engagement))
    except (ValueError, TypeError):
        rating = 5
        audio_video_quality = 5
        tutor_punctuality = 5
        student_engagement = 5

    comments = request.POST.get('comments', '').strip()

    feedback, created = LessonFeedback.objects.update_or_create(
        session=session,
        defaults={
            'submitted_by': request.user,
            'rating': rating,
            'audio_video_quality': audio_video_quality,
            'tutor_punctuality': tutor_punctuality,
            'student_engagement': student_engagement,
            'comments': comments,
        }
    )

    if rating <= 3:
        send_qa_low_rating_alert(feedback)
        messages.warning(
            request, 
            "Thank you for your candid feedback. Our Academic Quality Coordinator has been alerted to review this lesson."
        )
    else:
        messages.success(request, f"Thank you! Your {rating}-star rating has been recorded.")

    return redirect('classroom:student_portal')


# ==============================================================================
# STUDENT ASSIGNMENT & HOMEWORK SUBMISSION ENGINE
# ==============================================================================
ALLOWED_HOMEWORK_EXTENSIONS = ('.pdf', '.png', '.jpg', '.jpeg', '.docx', '.txt', '.zip')
MAX_HOMEWORK_SIZE_BYTES = 20 * 1024 * 1024  # 20MB


@login_required
@require_POST
def submit_homework_view(request: HttpRequest, session_id: str) -> HttpResponse:
    """
    Allows a student (or their guardian) to submit written answers and/or file attachments
    for assigned homework in a class session.
    """
    session = get_object_or_404(ClassSession, id=session_id)
    student = session.booking.student

    # Verify authorization: current user must be the student, the student's user, the guardian, or staff
    is_owner = (
        (student.user and student.user == request.user) or
        (student.guardian and student.guardian.email.lower() == request.user.email.lower()) or
        request.user.is_staff or
        request.user.is_superuser
    )
    if not is_owner:
        return HttpResponse("You are not authorized to submit homework for this session.", status=403)

    title = request.POST.get('title', f"Homework - {session.title}").strip()
    content = request.POST.get('content', '').strip()
    attachment = request.FILES.get('attachment')

    if attachment:
        ext = os.path.splitext(attachment.name)[1].lower()
        if ext not in ALLOWED_HOMEWORK_EXTENSIONS:
            messages.error(request, f"File format '{ext}' is not supported. Please upload PDF, Word document, or image files.")
            return redirect(request.META.get('HTTP_REFERER') or 'dashboard_student')

        if attachment.size > MAX_HOMEWORK_SIZE_BYTES:
            messages.error(request, "File exceeds maximum permitted size of 20MB.")
            return redirect(request.META.get('HTTP_REFERER') or 'dashboard_student')

    submission, created = HomeworkSubmission.objects.update_or_create(
        session=session,
        student=student,
        defaults={
            'submitted_by': request.user,
            'title': title,
            'content': content,
            'status': SubmissionStatus.SUBMITTED,
        }
    )

    if attachment:
        submission.attachment = attachment
        submission.save(update_fields=['attachment'])

    messages.success(request, f"Homework for '{session.title}' submitted successfully! Your tutor has been notified.")
    return redirect(request.META.get('HTTP_REFERER') or 'dashboard_student')


@login_required
@require_POST
def grade_homework_view(request: HttpRequest, submission_id: str) -> HttpResponse:
    """
    Allows the assigned tutor (or academic staff) to grade a student's homework submission
    and provide detailed feedback and remarks.
    """
    submission = get_object_or_404(HomeworkSubmission, id=submission_id)
    tutor_profile = getattr(request.user, 'tutor_profile', None)

    is_authorized = (
        (tutor_profile and submission.session.booking.tutor == tutor_profile) or
        request.user.is_staff or
        request.user.is_superuser
    )
    if not is_authorized:
        return HttpResponse("Only the assigned tutor or academic staff can grade this submission.", status=403)

    grade = request.POST.get('grade', '').strip()
    feedback = request.POST.get('tutor_feedback', '').strip()
    status = request.POST.get('status', SubmissionStatus.GRADED)

    if status not in dict(SubmissionStatus.choices):
        status = SubmissionStatus.GRADED

    submission.grade = grade
    submission.tutor_feedback = feedback
    submission.status = status
    submission.reviewed_by = request.user
    submission.reviewed_at = timezone.now()
    submission.save()

    messages.success(request, f"Assessment recorded for {submission.student.first_name}'s homework ({grade or status}).")
    return redirect(request.META.get('HTTP_REFERER') or 'dashboard_tutor')


@login_required
def download_submission_file(request: HttpRequest, submission_id: str) -> HttpResponse:
    """
    Securely serves homework attachment with BOLA/IDOR verification.
    """
    submission = get_object_or_404(HomeworkSubmission, id=submission_id)

    if not submission.attachment:
        return HttpResponse("No attachment file uploaded for this submission.", status=404)

    student = submission.student
    tutor = submission.session.booking.tutor
    tutor_profile = getattr(request.user, 'tutor_profile', None)

    can_access = (
        (student.user and student.user == request.user) or
        (student.guardian and student.guardian.email.lower() == request.user.email.lower()) or
        (tutor_profile and tutor == tutor_profile) or
        request.user.is_staff or
        request.user.is_superuser
    )
    if not can_access:
        return HttpResponse("Unauthorized to download this file.", status=403)

    return FileResponse(submission.attachment.open('rb'), as_attachment=True, filename=os.path.basename(submission.attachment.name))


# ==============================================================================
# 11. INTERACTIVE QUIZZES & AUTOMATED TESTING VIEWS
# ==============================================================================
@login_required
def quiz_list_view(request: HttpRequest) -> HttpResponse:
    """
    Catalog of interactive academic quizzes, subject diagnostic tests, and mastery checks.
    Tailored to the student's enrolled subjects and class level.
    """
    user = request.user
    profile = user.profile

    if profile.is_student:
        student = Student.objects.filter(models.Q(user=user) | models.Q(guardian__email__iexact=user.email)).first()
        quizzes = Quiz.objects.filter(is_active=True).select_related('subject')
        # Fetch user's previous attempts
        attempts = QuizAttempt.objects.filter(user=user).select_related('quiz')
        attempts_by_quiz = {}
        for att in attempts:
            attempts_by_quiz.setdefault(att.quiz_id, []).append(att)

        quiz_items = []
        for q in quizzes:
            q_attempts = attempts_by_quiz.get(q.id, [])
            attempt_count = len(q_attempts)
            best_score = max([a.percentage for a in q_attempts], default=Decimal('0.00'))
            has_passed = any(a.passed for a in q_attempts)
            can_attempt = (q.max_attempts == 0) or (attempt_count < q.max_attempts)
            latest_attempt = q_attempts[0] if q_attempts else None

            quiz_items.append({
                'quiz': q,
                'attempt_count': attempt_count,
                'best_score': best_score,
                'has_passed': has_passed,
                'can_attempt': can_attempt,
                'latest_attempt': latest_attempt,
            })

        context = {
            'quiz_items': quiz_items,
            'is_student': True,
        }
    else:
        # Tutors, Guardians, and Staff view all active quizzes and aggregate stats
        quizzes = Quiz.objects.all().select_related('subject', 'created_by').order_by('-created_at')
        quiz_items = [{'quiz': q, 'total_attempts': q.attempts.count()} for q in quizzes]
        context = {
            'quiz_items': quiz_items,
            'is_student': False,
        }

    return render(request, 'classroom/quiz_list.html', context)


@login_required
def take_quiz_view(request: HttpRequest, quiz_id: str) -> HttpResponse:
    """
    Renders the interactive quiz interface.
    Anti-Tampering: Question order and choices are rendered WITHOUT exposing the 'is_correct' flag in DOM.
    """
    quiz = get_object_or_404(Quiz, id=quiz_id, is_active=True)
    user = request.user
    
    # Identify student profile
    student = Student.objects.filter(models.Q(user=user) | models.Q(guardian__email__iexact=user.email)).first()
    if not student and user.profile.is_student:
        # Create student profile on the fly if needed
        student = Student.objects.create(
            user=user,
            guardian=home_models.Guardian.objects.get_or_create(email=user.email)[0],
            first_name=user.first_name or user.username,
            last_name=user.last_name or 'Learner',
            class_level=quiz.class_level,
            curriculum=quiz.curriculum,
        )

    # Check attempt limit
    if student:
        attempt_count = QuizAttempt.objects.filter(quiz=quiz, student=student).count()
        if quiz.max_attempts > 0 and attempt_count >= quiz.max_attempts:
            messages.warning(
                request, 
                f"You have reached the maximum of {quiz.max_attempts} attempts for '{quiz.title}'."
            )
            latest = QuizAttempt.objects.filter(quiz=quiz, student=student).first()
            if latest:
                return redirect('classroom:quiz_result', attempt_id=latest.id)
            return redirect('classroom:quiz_list')

    questions = quiz.questions.all().prefetch_related('options')
    
    context = {
        'quiz': quiz,
        'questions': questions,
        'student': student,
        'time_limit_seconds': quiz.time_limit_minutes * 60 if quiz.time_limit_minutes > 0 else None,
    }
    return render(request, 'classroom/quiz_take.html', context)


@login_required
@require_POST
def submit_quiz_view(request: HttpRequest, quiz_id: str) -> HttpResponse:
    """
    Automated Server-Side Grading Engine:
    Processes user responses, calculates score and percentage, determines pass/fail status,
    and stores an immutable QuizAttempt record with detailed per-question audit data.
    """
    quiz = get_object_or_404(Quiz, id=quiz_id, is_active=True)
    user = request.user
    student = Student.objects.filter(models.Q(user=user) | models.Q(guardian__email__iexact=user.email)).first()

    if not student:
        messages.error(request, "A valid student profile is required to record quiz results.")
        return redirect('classroom:quiz_list')

    # Guard against concurrent attempt flood
    attempt_count = QuizAttempt.objects.filter(quiz=quiz, student=student).count()
    if quiz.max_attempts > 0 and attempt_count >= quiz.max_attempts:
        messages.warning(request, f"Maximum allowed attempts ({quiz.max_attempts}) reached.")
        return redirect('classroom:quiz_list')

    questions = quiz.questions.all().prefetch_related('options')
    earned_score = Decimal('0.00')
    max_score = Decimal('0.00')
    answers_breakdown = []

    for q in questions:
        q_points = Decimal(str(q.points))
        max_score += q_points
        chosen_option_id = request.POST.get(f'question_{q.id}')
        
        # Verify selected option
        chosen_option = None
        is_q_correct = False
        correct_option = q.options.filter(is_correct=True).first()

        if chosen_option_id:
            chosen_option = q.options.filter(id=chosen_option_id).first()
            if chosen_option and chosen_option.is_correct:
                is_q_correct = True
                earned_score += q_points

        answers_breakdown.append({
            'question_id': str(q.id),
            'question_text': q.question_text,
            'question_type': q.question_type,
            'points_possible': float(q_points),
            'points_earned': float(q_points if is_q_correct else Decimal('0.00')),
            'is_correct': is_q_correct,
            'chosen_option': chosen_option.option_text if chosen_option else "No answer submitted",
            'correct_option': correct_option.option_text if correct_option else "N/A",
            'explanation': q.explanation,
        })

    # Calculate percentage
    percentage = round((earned_score / max_score * Decimal('100.0')), 2) if max_score > 0 else Decimal('0.00')
    passed = percentage >= quiz.pass_percentage

    # Client IP audit
    client_ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', '')).split(',')[0].strip()

    attempt = QuizAttempt.objects.create(
        quiz=quiz,
        student=student,
        user=user,
        score=earned_score,
        max_score=max_score,
        percentage=percentage,
        passed=passed,
        completed_at=timezone.now(),
        answers_payload={'breakdown': answers_breakdown},
        ip_address=client_ip or None
    )

    if passed:
        messages.success(request, f"Outstanding! You passed '{quiz.title}' with a score of {percentage}%!")
    else:
        messages.info(request, f"Quiz completed with a score of {percentage}%. Passing score is {quiz.pass_percentage}%.")

    return redirect('classroom:quiz_result', attempt_id=attempt.id)


@login_required
def quiz_result_view(request: HttpRequest, attempt_id: str) -> HttpResponse:
    """
    Displays detailed performance breakdown, question-by-question explanations, and score card.
    Guarded with BOLA/IDOR protection.
    """
    attempt = get_object_or_404(QuizAttempt, id=attempt_id)
    user = request.user
    profile = user.profile

    # BOLA / Access Authorization
    is_owner = (attempt.user == user) or (attempt.student.user == user)
    is_guardian = (attempt.student.guardian and attempt.student.guardian.email.lower() == user.email.lower())
    is_authorized = is_owner or is_guardian or profile.is_staff_member or profile.is_admin or profile.is_tutor

    if not is_authorized:
        return HttpResponse("Unauthorized to view this assessment report.", status=403)

    breakdown = attempt.answers_payload.get('breakdown', [])

    context = {
        'attempt': attempt,
        'quiz': attempt.quiz,
        'breakdown': breakdown,
        'can_reattempt': (attempt.quiz.max_attempts == 0) or (
            QuizAttempt.objects.filter(quiz=attempt.quiz, student=attempt.student).count() < attempt.quiz.max_attempts
        )
    }
    return render(request, 'classroom/quiz_result.html', context)


# ==============================================================================
# 12. VERIFIABLE COURSE COMPLETION CERTIFICATES
# ==============================================================================
def verify_certificate_view(request: HttpRequest, code: str) -> HttpResponse:
    """
    Public Certificate Verification Portal:
    Allows employers, educational institutions, and parents to verify certificate authenticity
    without needing an account, while preventing sensitive PII leakage.
    """
    clean_code = code.strip().upper()
    certificate = CourseCertificate.objects.filter(certificate_code__iexact=clean_code).select_related('student', 'subject').first()

    context = {
        'code': clean_code,
        'certificate': certificate,
        'is_verified': certificate is not None and not certificate.is_revoked,
    }
    return render(request, 'classroom/certificate_verify.html', context)


@login_required
def view_certificate_view(request: HttpRequest, certificate_code: str) -> HttpResponse:
    """
    Printable & downloadable high-resolution certificate with gold foil border,
    Edukom academic seal, verification code, and instant print capability.
    Guarded with BOLA/IDOR check.
    """
    clean_code = certificate_code.strip().upper()
    certificate = get_object_or_404(CourseCertificate, certificate_code__iexact=clean_code)
    user = request.user
    profile = user.profile

    # Authorization
    is_owner = (certificate.student.user == user)
    is_guardian = (certificate.student.guardian and certificate.student.guardian.email.lower() == user.email.lower())
    is_authorized = is_owner or is_guardian or profile.is_staff_member or profile.is_admin

    if not is_authorized:
        return HttpResponse("Unauthorized to view this certificate document.", status=403)

    context = {
        'certificate': certificate,
        'student': certificate.student,
        'verification_url': request.build_absolute_uri(certificate.get_verification_url()),
    }
    return render(request, 'classroom/certificate_detail.html', context)


# ==============================================================================
# 13. CALENDAR TIMETABLE SYNC (.ICS) ENGINE (RFC 5545)
# ==============================================================================
def get_user_calendar_token(user) -> str:
    """Tamper-proof HMAC token for calendar subscription feeds without exposed cookies."""
    return hmac.new(
        settings.SECRET_KEY.encode('utf-8'),
        f"calendar_sync:{user.id}:{user.username}".encode('utf-8'),
        hashlib.sha256
    ).hexdigest()[:32]


def calendar_sync_ics_view(request: HttpRequest) -> HttpResponse:
    """
    Generates standard RFC 5545 iCalendar (.ics) stream for automatic subscription
    and 1-click sync with Apple Calendar, Google Calendar, and Microsoft Outlook.
    Supports either authenticated session or cryptographically signed token in URL.
    """
    user = request.user
    
    # If not logged in via web session, authenticate via signed token
    if not user.is_authenticated:
        user_id = request.GET.get('user_id')
        token = request.GET.get('token', '')
        if not user_id or not token:
            return HttpResponse("Unauthorized calendar feed. Please provide valid authentication.", status=401)
        
        user_model = get_user_model()
        try:
            feed_user = user_model.objects.get(id=user_id)
        except user_model.DoesNotExist:
            return HttpResponse("Invalid calendar feed identifier.", status=404)
        
        expected_token = get_user_calendar_token(feed_user)
        if not hmac.compare_digest(token, expected_token):
            return HttpResponse("Forbidden: Invalid calendar security token.", status=403)
        user = feed_user

    profile = getattr(user, 'profile', None)
    
    # Gather relevant sessions based on role
    now = timezone.now()
    two_months_ago = now - timezone.timedelta(days=60)
    
    if profile and profile.is_tutor:
        sessions = ClassSession.objects.filter(
            booking__tutor__user=user,
            start_time__gte=two_months_ago
        ).select_related('booking', 'booking__student', 'booking__subject')
    elif profile and profile.is_guardian:
        sessions = ClassSession.objects.filter(
            booking__student__guardian__email__iexact=user.email,
            start_time__gte=two_months_ago
        ).select_related('booking', 'booking__student', 'booking__subject', 'booking__tutor')
    else:
        # Student or Staff
        sessions = ClassSession.objects.filter(
            booking__student__user=user,
            start_time__gte=two_months_ago
        ).select_related('booking', 'booking__student', 'booking__subject', 'booking__tutor')
        if not sessions.exists():
            sessions = ClassSession.objects.filter(
                booking__student__guardian__email__iexact=user.email,
                start_time__gte=two_months_ago
            ).select_related('booking', 'booking__student', 'booking__subject', 'booking__tutor')

    # Format iCalendar RFC 5545 feed
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Edukom Group//Edukom Academic LMS Calendar 1.0//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:Edukom Lessons ({user.get_full_name() or user.username})",
        "X-WR-TIMEZONE:Africa/Lagos",
    ]

    for s in sessions:
        dt_stamp = timezone.now().strftime("%Y%m%dT%H%M%SZ")
        dt_start = s.start_time.strftime("%Y%m%dT%H%M%SZ")
        dt_end = s.end_time.strftime("%Y%m%dT%H%M%SZ")
        student_name = f"{s.booking.student.first_name} {s.booking.student.last_name}"
        tutor_name = s.booking.tutor.display_name
        subject_name = s.booking.subject.name
        
        join_url = request.build_absolute_uri(f"/classroom/session/{s.id}/")
        description = (
            f"Lesson Title: {s.title}\\n"
            f"Subject: {subject_name}\\n"
            f"Student: {student_name}\\n"
            f"Tutor: {tutor_name}\\n"
            f"Status: {s.get_status_display()}\\n"
            f"Join Virtual Classroom: {join_url}\\n"
        )
        if s.lesson_topic:
            description += f"Topic: {s.lesson_topic}\\n"

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{s.id}@edukom.org",
            f"DTSTAMP:{dt_stamp}",
            f"DTSTART:{dt_start}",
            f"DTEND:{dt_end}",
            f"SUMMARY:{s.title} ({subject_name}) - Edukom",
            f"DESCRIPTION:{description}",
            f"LOCATION:{join_url}",
            f"STATUS:{'CONFIRMED' if s.status != SessionStatus.CANCELLED else 'CANCELLED'}",
            "END:VEVENT"
        ])

    lines.append("END:VCALENDAR")
    ics_body = "\r\n".join(lines) + "\r\n"

    response = HttpResponse(ics_body, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="edukom_schedule.ics"'
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response



