"""
Automated Notifications and Alerts for Edukom Classroom.
Handles:
1. Automated post-lesson progress reports sent to parents/guardians upon lesson completion.
2. Low QA rating alerts sent to academic coordination/support staff when a lesson gets <= 3 stars.
3. Cancellation & no-show notifications.
"""

import logging
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger('classroom')


def send_lesson_progress_report_to_parent(session) -> bool:
    """
    Dispatches automated progress report to guardian when tutor submits lesson notes.
    Fail-soft: logs any transport failure without interrupting the tutor's session flow.
    """
    try:
        student = session.booking.student
        guardian = getattr(student, 'guardian', None)
        parent_email = guardian.email if guardian else ''

        if not parent_email:
            logger.warning(f"No guardian email found for session {session.id} student {student.first_name}")
            return False

        subject = f"[Edukom LMS] Lesson Progress Report: {student.first_name} {student.last_name} - {session.booking.subject.name}"
        
        tutor_name = session.booking.tutor.display_name
        lesson_topic = session.lesson_topic or 'Regular Curriculum Coverage'
        lesson_notes = session.lesson_notes or 'Lesson completed successfully.'
        homework = session.homework_assigned or 'None assigned for this session.'
        duration = f"{session.duration_minutes} minutes"
        lesson_date = session.start_time.strftime('%A, %d %B %Y at %I:%M %p')

        context = {
            'student_name': f"{student.first_name} {student.last_name}",
            'guardian_name': f"{guardian.first_name} {guardian.last_name}" if guardian else "Parent/Guardian",
            'tutor_name': tutor_name,
            'subject_name': session.booking.subject.name,
            'class_level': session.booking.class_level,
            'lesson_topic': lesson_topic,
            'lesson_notes': lesson_notes,
            'homework_assigned': homework,
            'duration': duration,
            'lesson_date': lesson_date,
            'site_url': getattr(settings, 'SITE_URL', 'https://edukom.ng'),
        }

        message = (
            f"Dear {context['guardian_name']},\n\n"
            f"Your child {context['student_name']} has just completed a live lesson on Edukom LMS.\n\n"
            f"Lesson Summary:\n"
            f"- Subject: {context['subject_name']} ({context['class_level']})\n"
            f"- Tutor: {context['tutor_name']}\n"
            f"- Date & Time: {context['lesson_date']} ({context['duration']})\n"
            f"- Topic Covered: {context['lesson_topic']}\n\n"
            f"Tutor Remarks & Progress:\n{context['lesson_notes']}\n\n"
            f"Homework / Tasks Assigned:\n{context['homework_assigned']}\n\n"
            f"You can view complete attendance history and rate this lesson on your Guardian Portal.\n\n"
            f"Best regards,\nEdukom Learning Support Team\nsupport@edukom.ng"
        )

        from_email = getattr(settings, 'EMAIL_HOST_USER', 'support@edukom.ng')
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=[parent_email],
            fail_silently=False
        )
        logger.info(f"Progress report email sent to {parent_email} for session {session.id}")
        return True

    except Exception as exc:
        logger.error(f"Failed to send progress report email for session {session.id}: {str(exc)}", exc_info=True)
        return False


def send_qa_low_rating_alert(feedback) -> bool:
    """
    Sends an urgent email notification to academic coordinators if a parent or student
    rates a lesson 3 stars or below. Enables immediate quality assurance intervention.
    """
    try:
        session = feedback.session
        student = session.booking.student
        tutor = session.booking.tutor
        
        subject = f"[URGENT QA ALERT] Low Lesson Rating ({feedback.rating}/5) - {tutor.display_name} with {student.first_name}"
        
        admin_emails = getattr(settings, 'OFFICIAL_NOTIFICATION_EMAILS', ['support@edukom.ng'])
        from_email = getattr(settings, 'EMAIL_HOST_USER', 'support@edukom.ng')

        body = (
            f"URGENT QUALITY ASSURANCE INTERVENTION REQUIRED\n\n"
            f"A lesson received a low rating ({feedback.rating}/5 stars) on Edukom LMS.\n\n"
            f"Details:\n"
            f"- Session ID: {session.id}\n"
            f"- Subject: {session.booking.subject.name} ({session.booking.class_level})\n"
            f"- Tutor: {tutor.display_name} ({tutor.user.email})\n"
            f"- Student: {student.first_name} {student.last_name}\n"
            f"- Guardian: {student.guardian.first_name} {student.guardian.last_name} ({student.guardian.email}, {student.guardian.phone})\n"
            f"- Overall Rating: {feedback.rating} / 5\n"
            f"- Audio/Video Quality: {feedback.audio_video_quality} / 5\n"
            f"- Tutor Punctuality: {feedback.tutor_punctuality} / 5\n"
            f"- Student Engagement: {feedback.student_engagement} / 5\n"
            f"- Feedback Remarks: {feedback.comments or 'No remarks provided.'}\n\n"
            f"Please review the session logs and contact the guardian within 24 hours.\n\n"
            f"Edukom Automated QA Monitor"
        )

        send_mail(
            subject=subject,
            message=body,
            from_email=from_email,
            recipient_list=admin_emails,
            fail_silently=False
        )
        logger.info(f"QA low rating alert dispatched for session {session.id}")
        return True

    except Exception as exc:
        logger.error(f"Failed to dispatch QA low rating alert for session {feedback.session.id}: {str(exc)}", exc_info=True)
        return False
