from django.urls import path
from . import views

app_name = 'classroom'

urlpatterns = [
    # Virtual Classroom & WebRTC Entry
    path('session/<uuid:session_id>/', views.classroom_live_view, name='live_room'),
    path('session/<uuid:session_id>/notes/', views.submit_lesson_notes, name='submit_notes'),
    path('session/<uuid:session_id>/signal/send/', views.send_classroom_signal, name='send_signal'),
    path('session/<uuid:session_id>/signal/poll/', views.poll_classroom_signals, name='poll_signals'),

    # Portals
    path('tutor/portal/', views.tutor_portal_dashboard, name='tutor_portal'),
    path('student/portal/', views.student_portal_dashboard, name='student_portal'),

    # LMS to Payroll Direct Bridge
    path('dispatch-to-payroll/', views.dispatch_lms_sessions_to_payroll, name='dispatch_payroll'),

    # Live Session Scheduling & Instant Class Launcher
    path('schedule/new/', views.schedule_session_view, name='schedule_session'),
    path('instant/new/', views.instant_session_view, name='instant_session'),

    # Phase 2 Safeguards: Resources, Cancellations, and Feedback
    path('session/<uuid:session_id>/resources/upload/', views.upload_lesson_resource, name='upload_resource'),
    path('vault/upload/', views.upload_material_view, name='upload_material'),
    path('resource/<uuid:resource_id>/download/', views.download_lesson_resource, name='download_resource'),
    path('resource/<uuid:resource_id>/delete/', views.delete_resource_view, name='delete_resource'),
    path('session/<uuid:session_id>/cancel/', views.cancel_session_view, name='cancel_session'),
    path('session/<uuid:session_id>/feedback/', views.submit_lesson_feedback, name='submit_feedback'),

    # Student Homework & Assignment Submission Engine
    path('session/<uuid:session_id>/homework/submit/', views.submit_homework_view, name='submit_homework'),
    path('homework/<uuid:submission_id>/grade/', views.grade_homework_view, name='grade_homework'),
    path('homework/<uuid:submission_id>/download/', views.download_submission_file, name='download_homework'),

    # Interactive Quizzes & Automated Testing Engine
    path('quizzes/', views.quiz_list_view, name='quiz_list'),
    path('quizzes/<uuid:quiz_id>/', views.take_quiz_view, name='take_quiz'),
    path('quizzes/<uuid:quiz_id>/submit/', views.submit_quiz_view, name='submit_quiz'),
    path('quizzes/attempt/<uuid:attempt_id>/', views.quiz_result_view, name='quiz_result'),

    # Verifiable Course Completion Certificates
    path('certificates/verify/<str:code>/', views.verify_certificate_view, name='verify_certificate'),
    path('certificates/<str:certificate_code>/', views.view_certificate_view, name='view_certificate'),

    # Calendar Timetable Sync (.ics) Engine
    path('calendar/sync.ics', views.calendar_sync_ics_view, name='calendar_sync'),
]
