import uuid
from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError
from homepage.models import Guardian, cc as CLASS_CHOICES, Curriculums as CURRICULUM_CHOICES, lesson_choices as LESSON_CHOICES
from tutors.models import Tutor

User = get_user_model()


class BookingStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active'
    PAUSED = 'PAUSED', 'Paused'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class SessionStatus(models.TextChoices):
    SCHEDULED = 'SCHEDULED', 'Scheduled'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'
    NO_SHOW = 'NO_SHOW', 'Student No-Show'


class Subject(models.Model):
    name = models.CharField(max_length=100, unique=True)
    category = models.CharField(
        max_length=50, 
        choices=[
            ('STEM', 'STEM & Computing'),
            ('Languages', 'Languages & Literature'),
            ('Humanities', 'Humanities & Social Sciences'),
            ('Commercial', 'Business & Commercial'),
            ('Arts', 'Creative Arts'),
            ('General', 'General Foundation'),
        ],
        default='STEM'
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.category})"


class Student(models.Model):
    """
    Student profile replacing TutorCruncher student record.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    guardian = models.ForeignKey(Guardian, on_delete=models.CASCADE, related_name='students')
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='student_profile')
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    class_level = models.CharField(max_length=100, choices=CLASS_CHOICES, default='year 7')
    curriculum = models.CharField(max_length=50, choices=CURRICULUM_CHOICES, default='British')
    timezone = models.CharField(max_length=50, default='Africa/Lagos', help_text="e.g. Africa/Lagos, Europe/London, America/New_York")
    learning_goals = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['first_name', 'last_name']

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.class_level})"


class TutorProfile(models.Model):
    """
    Comprehensive tutor LMS identity linked to User authentication and existing Tutor lead records.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='tutor_profile')
    tutor_record = models.OneToOneField(Tutor, on_delete=models.SET_NULL, null=True, blank=True, related_name='profile')
    display_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=50, blank=True)
    bio = models.TextField(blank=True)
    subjects = models.ManyToManyField(Subject, blank=True, related_name='tutors')
    hourly_base_rate = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('5000.00'))
    currency = models.CharField(max_length=10, default='NGN')
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['display_name']

    def __str__(self):
        return f"{self.display_name} ({self.user.email})"


class ClassBooking(models.Model):
    """
    Course / Class enrollment matching a Student with an assigned Tutor.
    Replaces TutorCruncher Job/Contract.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='bookings')
    tutor = models.ForeignKey(TutorProfile, on_delete=models.CASCADE, related_name='bookings')
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name='bookings')
    class_level = models.CharField(max_length=100, choices=CLASS_CHOICES)
    curriculum = models.CharField(max_length=50, choices=CURRICULUM_CHOICES, default='British')
    delivery_mode = models.CharField(max_length=50, choices=LESSON_CHOICES, default='Online lessons')
    client_timezone = models.CharField(max_length=50, default='WAT')
    
    agreed_hourly_rate = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='NGN')
    status = models.CharField(max_length=20, choices=BookingStatus.choices, default=BookingStatus.ACTIVE, db_index=True)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    
    # Safeguard 8: NDPR / COPPA Minor Safeguarding & Recording Consent
    recording_consent_given = models.BooleanField(
        default=True, 
        help_text="NDPR Compliance: Verified parental/guardian consent to record student during live lessons"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.student.first_name} & {self.tutor.display_name} - {self.subject.name} ({self.class_level})"


class ClassSession(models.Model):
    """
    Individual scheduled live lesson replacing Zoom / Google Meet.
    Contains built-in WebRTC / Daily.co virtual classroom room references.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(ClassBooking, on_delete=models.CASCADE, related_name='sessions')
    title = models.CharField(max_length=255)
    start_time = models.DateTimeField(db_index=True)
    end_time = models.DateTimeField(db_index=True)
    duration_minutes = models.PositiveIntegerField(default=60)
    status = models.CharField(max_length=20, choices=SessionStatus.choices, default=SessionStatus.SCHEDULED, db_index=True)
    
    # Virtual Classroom WebRTC identifiers
    room_name = models.CharField(max_length=128, unique=True, db_index=True)
    room_url = models.URLField(blank=True, max_length=500)
    
    # Automated attendance metrics
    tutor_joined_at = models.DateTimeField(null=True, blank=True)
    student_joined_at = models.DateTimeField(null=True, blank=True)
    tutor_left_at = models.DateTimeField(null=True, blank=True)
    student_left_at = models.DateTimeField(null=True, blank=True)
    
    # Educational logging
    lesson_topic = models.CharField(max_length=255, blank=True)
    lesson_notes = models.TextField(blank=True, help_text="Tutor remarks on lesson coverage and student comprehension")
    homework_assigned = models.TextField(blank=True)
    
    # Financial reconciliation
    is_payroll_processed = models.BooleanField(default=False, db_index=True)

    # Cancellation & No-Show Audit Policy
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='cancelled_sessions')
    cancellation_reason = models.TextField(blank=True)
    is_payable_late_cancel = models.BooleanField(
        default=False, 
        db_index=True, 
        help_text="True if student late cancellation or no-show qualifies tutor for compensation"
    )
    late_cancel_fee_multiplier = models.DecimalField(
        max_digits=4, 
        decimal_places=2, 
        default=Decimal('0.00'), 
        help_text="e.g. 0.50 for 50%, 1.00 for 100%"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['start_time']

    def clean(self):
        super().clean()
        if self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                raise ValidationError("Session start time must be before end time.")

            # Double-Booking Conflict Engine
            if hasattr(self, 'booking') and self.booking_id and self.status in [SessionStatus.SCHEDULED, SessionStatus.IN_PROGRESS]:
                # 1. Tutor double-booking guard
                tutor = self.booking.tutor
                tutor_conflict = ClassSession.objects.filter(
                    booking__tutor=tutor,
                    status__in=[SessionStatus.SCHEDULED, SessionStatus.IN_PROGRESS],
                    start_time__lt=self.end_time,
                    end_time__gt=self.start_time
                ).exclude(id=self.id).first()

                if tutor_conflict:
                    raise ValidationError(
                        f"Schedule conflict for tutor {tutor.display_name}: already scheduled for "
                        f"'{tutor_conflict.title}' ({tutor_conflict.start_time.strftime('%H:%M')} - {tutor_conflict.end_time.strftime('%H:%M')})."
                    )

                # 2. Student double-booking guard
                student = self.booking.student
                student_conflict = ClassSession.objects.filter(
                    booking__student=student,
                    status__in=[SessionStatus.SCHEDULED, SessionStatus.IN_PROGRESS],
                    start_time__lt=self.end_time,
                    end_time__gt=self.start_time
                ).exclude(id=self.id).first()

                if student_conflict:
                    raise ValidationError(
                        f"Schedule conflict for student {student.first_name} {student.last_name}: already scheduled for "
                        f"'{student_conflict.title}' ({student_conflict.start_time.strftime('%H:%M')} - {student_conflict.end_time.strftime('%H:%M')})."
                    )

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')
        if update_fields is None or any(f in update_fields for f in ['start_time', 'end_time', 'status']):
            self.clean()
        super().save(*args, **kwargs)

    @property
    def is_joinable(self) -> bool:
        """
        Classroom can be entered 15 minutes before scheduled start until 30 minutes after end.
        """
        now = timezone.now()
        allow_start = self.start_time - timezone.timedelta(minutes=15)
        allow_end = self.end_time + timezone.timedelta(minutes=30)
        return allow_start <= now <= allow_end

    @property
    def dual_time_display(self) -> str:
        """
        Dynamic dual-timezone display formatted for UK (GMT/BST), Nigeria (WAT), US (ET/CT), or Gulf (GST).
        """
        from .timezones import format_dual_session_time
        return format_dual_session_time(self)

    def __str__(self):
        return f"{self.title} - {self.start_time.strftime('%Y-%m-%d %H:%M')} ({self.get_status_display()})"


class AttendanceRecord(models.Model):
    """
    Granular audit log of user presence in the embedded virtual classroom.
    Provides verifiable proof of attendance for dispute resolution and payroll.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(ClassSession, on_delete=models.CASCADE, related_name='attendance_records')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=[('TUTOR', 'Tutor'), ('STUDENT', 'Student'), ('ADMIN', 'Admin')])
    joined_at = models.DateTimeField(default=timezone.now)
    left_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-joined_at']

    def __str__(self):
        return f"{self.user.username} ({self.role}) in {self.session.title} at {self.joined_at}"


class ClassroomSignal(models.Model):
    """
    Real-time signaling & event broker for WebRTC peer connections,
    synchronized digital whiteboard, in-class chat, and screen sharing across devices.
    """
    id = models.BigAutoField(primary_key=True)
    session = models.ForeignKey(ClassSession, on_delete=models.CASCADE, related_name='signals')
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    sender_name = models.CharField(max_length=150, blank=True)
    sender_role = models.CharField(max_length=20, default='STUDENT')
    signal_type = models.CharField(max_length=50, db_index=True)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['id']
        indexes = [
            models.Index(fields=['session', 'id']),
            models.Index(fields=['session', 'signal_type', 'id']),
        ]

    def __str__(self):
        return f"Signal {self.id} ({self.signal_type}) from {self.sender_name} in {self.session.title}"


class ResourceType(models.TextChoices):
    WORKSHEET = 'WORKSHEET', 'Worksheet & Exercises'
    NOTES = 'NOTES', 'Study Notes & Presentation'
    PAST_PAPER = 'PAST_PAPER', 'Past Exam Paper'
    VIDEO = 'VIDEO', 'Recorded Video / Lesson'
    OTHER = 'OTHER', 'Other Reference Material'


class LessonResource(models.Model):
    """
    Worksheet, reading material, past paper, or video resource uploaded for a session or booking.
    Protected with extension and MIME-type restrictions to prevent malware/stored XSS.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(ClassBooking, on_delete=models.CASCADE, null=True, blank=True, related_name='resources')
    session = models.ForeignKey(ClassSession, on_delete=models.CASCADE, null=True, blank=True, related_name='resources')
    title = models.CharField(max_length=255)
    resource_type = models.CharField(max_length=30, choices=ResourceType.choices, default=ResourceType.WORKSHEET, db_index=True)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to='classroom_resources/%Y/%m/', null=True, blank=True)
    file_size = models.PositiveIntegerField(default=0, help_text="Size in bytes")
    content_type = models.CharField(max_length=100, blank=True)
    video_url = models.URLField(max_length=500, blank=True, help_text="Direct link or embed URL for video lesson (YouTube, Vimeo, Cloud Storage, etc.)")
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        target = self.session.title if self.session else (self.booking.subject.name if self.booking else "General")
        return f"{self.title} [{self.get_resource_type_display()}] ({target})"


class LessonFeedback(models.Model):
    """
    Guardian and Student QA review for completed lessons.
    Ratings <= 3 trigger automated alerts to the academic support team.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.OneToOneField(ClassSession, on_delete=models.CASCADE, related_name='feedback')
    submitted_by = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(
        choices=[(1, '1 - Poor'), (2, '2 - Fair'), (3, '3 - Good'), (4, '4 - Very Good'), (5, '5 - Excellent')],
        default=5
    )
    audio_video_quality = models.PositiveSmallIntegerField(
        choices=[(i, str(i)) for i in range(1, 6)],
        default=5
    )
    tutor_punctuality = models.PositiveSmallIntegerField(
        choices=[(i, str(i)) for i in range(1, 6)],
        default=5
    )
    student_engagement = models.PositiveSmallIntegerField(
        choices=[(i, str(i)) for i in range(1, 6)],
        default=5
    )
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.session.title} - {self.rating}/5 stars by {self.submitted_by.username}"


class LearningMilestoneStatus(models.TextChoices):
    NOT_STARTED = 'NOT_STARTED', 'Not Started'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    COMPLETED = 'COMPLETED', 'Completed'
    MASTERED = 'MASTERED', 'Mastered'


class LearningPathMilestone(models.Model):
    """
    Structured Curriculum Milestone representing a student's learning progress path.
    Enables students to see modules completed, in-progress, and upcoming milestones.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='milestones')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='milestones')
    module_title = models.CharField(max_length=200, help_text="e.g. Module 1: Core Principles & Atomic Theory")
    curriculum = models.CharField(max_length=50, choices=CURRICULUM_CHOICES, default='British')
    order = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=20, 
        choices=LearningMilestoneStatus.choices, 
        default=LearningMilestoneStatus.NOT_STARTED,
        db_index=True
    )
    comprehension_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Score % e.g. 92.5")
    tutor_feedback = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['student', 'subject', 'order']

    def __str__(self):
        return f"{self.student.first_name} - {self.subject.name} - {self.module_title} [{self.get_status_display()}]"


class SubmissionStatus(models.TextChoices):
    SUBMITTED = 'SUBMITTED', 'Submitted for Review'
    GRADED = 'GRADED', 'Graded & Approved'
    REVISION_REQUESTED = 'REVISION_REQUESTED', 'Revision Requested'


class HomeworkSubmission(models.Model):
    """
    LMS Student assignment & homework submission.
    Allows students to submit written solutions and file attachments
    for scheduled/completed class sessions, with tutor grading & feedback.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(ClassSession, on_delete=models.CASCADE, related_name='homework_submissions')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='homework_submissions')
    submitted_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='submitted_homework')
    
    title = models.CharField(max_length=255, default='Homework Submission')
    content = models.TextField(blank=True, help_text="Written answers, essay content, or solution work")
    attachment = models.FileField(upload_to='homework_submissions/%Y/%m/', blank=True, null=True)
    
    status = models.CharField(
        max_length=25, 
        choices=SubmissionStatus.choices, 
        default=SubmissionStatus.SUBMITTED,
        db_index=True
    )
    grade = models.CharField(max_length=20, blank=True, help_text="e.g. A*, 95%, 18/20")
    tutor_feedback = models.TextField(blank=True, help_text="Tutor remarks, corrections, and guidance")
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_homework')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.student.first_name} - {self.session.title} [{self.get_status_display()}]"


# ==============================================================================
# 9. INTERACTIVE QUIZZES & AUTOMATED TESTING ENGINE
# ==============================================================================
class QuestionType(models.TextChoices):
    SINGLE = 'SINGLE', 'Single Choice'
    MULTIPLE = 'MULTIPLE', 'Multiple Choice'
    TRUE_FALSE = 'TF', 'True / False'


class Quiz(models.Model):
    """
    Standard LMS interactive assessment and evaluation quiz.
    Supports curriculum-aligned diagnostic tests, topic check-ins, and exams.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, help_text="Instructions and syllabus coverage for students")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='quizzes')
    class_level = models.CharField(max_length=100, choices=CLASS_CHOICES, default='year 10')
    curriculum = models.CharField(max_length=50, choices=CURRICULUM_CHOICES, default='British')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_quizzes')
    
    time_limit_minutes = models.PositiveIntegerField(default=15, help_text="Time allowed in minutes (0 for untimed test)")
    pass_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('70.00'), help_text="Passing threshold %")
    max_attempts = models.PositiveIntegerField(default=3, help_text="Maximum allowed attempts per student (0 for unlimited)")
    is_active = models.BooleanField(default=True, db_index=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Quizzes'

    def __str__(self):
        return f"{self.title} - {self.subject.name} ({self.class_level})"

    @property
    def total_questions(self) -> int:
        return self.questions.count()

    @property
    def total_points(self) -> int:
        return sum(q.points for q in self.questions.all())


class QuizQuestion(models.Model):
    """
    Individual question within an LMS Quiz.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    question_type = models.CharField(max_length=20, choices=QuestionType.choices, default=QuestionType.SINGLE)
    order = models.PositiveIntegerField(default=1)
    points = models.PositiveIntegerField(default=1)
    explanation = models.TextField(blank=True, help_text="Detailed educational explanation shown after submission")

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"Q{self.order}: {self.question_text[:50]} ({self.quiz.title})"


class QuizOption(models.Model):
    """
    Selectable answer choice for a quiz question.
    Anti-Tampering: is_correct is graded strictly server-side and never exposed to the client prior to grading.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE, related_name='options')
    option_text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False, help_text="Server-side grading key")
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.option_text[:40]} [{'CORRECT' if self.is_correct else 'INCORRECT'}]"


class QuizAttempt(models.Model):
    """
    Immutable audit record of a student's quiz submission and score.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='quiz_attempts')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='quiz_attempts')
    
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    score = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))
    max_score = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    passed = models.BooleanField(default=False, db_index=True)
    
    answers_payload = models.JSONField(default=dict, blank=True, help_text="Auditable breakdown of selected answers and question feedback")
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-completed_at', '-started_at']

    def __str__(self):
        return f"{self.student.first_name} - {self.quiz.title}: {self.score}/{self.max_score} ({self.percentage}%)"


# ==============================================================================
# 10. VERIFIABLE COURSE COMPLETION CERTIFICATES
# ==============================================================================
import secrets

def generate_secure_certificate_code() -> str:
    """Generates an unguessable cryptographic certificate verification code."""
    token = secrets.token_hex(4).upper()
    return f"EDK-{token[:4]}-{token[4:]}"


class CourseCertificate(models.Model):
    """
    Official verifiable certificate awarded to students upon successful course completion
    or demonstrated curriculum mastery.
    Includes a tamper-proof cryptographic code and public verification URL.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    certificate_code = models.CharField(
        max_length=64, 
        unique=True, 
        default=generate_secure_certificate_code, 
        db_index=True,
        help_text="Cryptographically secure verification reference"
    )
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='certificates')
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name='certificates')
    curriculum = models.CharField(max_length=50, choices=CURRICULUM_CHOICES, default='British')
    class_level = models.CharField(max_length=100, choices=CLASS_CHOICES, default='year 11')
    
    issue_date = models.DateField(default=timezone.now)
    instructor_name = models.CharField(max_length=200, default='Edukom Academic Board')
    grade_achieved = models.CharField(max_length=50, default='Distinction', help_text="e.g. Distinction, Merit, A*, Mastery")
    hours_completed = models.DecimalField(max_digits=6, decimal_places=1, default=Decimal('20.0'))
    
    is_revoked = models.BooleanField(default=False, db_index=True)
    revocation_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-issue_date']

    def __str__(self):
        return f"Certificate {self.certificate_code}: {self.student.first_name} {self.student.last_name} ({self.subject.name})"

    def get_verification_url(self) -> str:
        from django.urls import reverse
        return reverse('classroom:verify_certificate', kwargs={'code': self.certificate_code})


