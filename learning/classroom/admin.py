from django.contrib import admin
from .models import Subject, Student, TutorProfile, ClassBooking, ClassSession, AttendanceRecord, HomeworkSubmission


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'category')
    list_filter = ('category',)
    search_fields = ('name',)


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'class_level', 'curriculum', 'timezone', 'guardian', 'is_active')
    list_filter = ('class_level', 'curriculum', 'timezone', 'is_active')
    search_fields = ('first_name', 'last_name', 'guardian__email')


@admin.register(TutorProfile)
class TutorProfileAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'user', 'phone', 'hourly_base_rate', 'currency', 'is_verified', 'is_active')
    list_filter = ('is_verified', 'is_active', 'currency')
    search_fields = ('display_name', 'user__email', 'phone')
    filter_horizontal = ('subjects',)


class ClassSessionInline(admin.TabularInline):
    model = ClassSession
    extra = 1
    fields = ('title', 'start_time', 'end_time', 'status', 'is_payroll_processed')


@admin.register(ClassBooking)
class ClassBookingAdmin(admin.ModelAdmin):
    list_display = ('student', 'tutor', 'subject', 'class_level', 'delivery_mode', 'agreed_hourly_rate', 'status', 'start_date')
    list_filter = ('status', 'delivery_mode', 'class_level', 'curriculum')
    search_fields = ('student__first_name', 'student__last_name', 'tutor__display_name', 'subject__name')
    inlines = [ClassSessionInline]


@admin.register(ClassSession)
class ClassSessionAdmin(admin.ModelAdmin):
    list_display = ('title', 'booking', 'start_time', 'end_time', 'status', 'room_name', 'is_payroll_processed')
    list_filter = ('status', 'is_payroll_processed', 'start_time')
    search_fields = ('title', 'room_name', 'booking__student__first_name', 'booking__tutor__display_name')
    readonly_fields = ('id', 'created_at', 'tutor_joined_at', 'student_joined_at', 'tutor_left_at', 'student_left_at')


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('session', 'user', 'role', 'joined_at', 'left_at', 'duration_seconds', 'ip_address')
    list_filter = ('role', 'joined_at')
    search_fields = ('user__username', 'session__title', 'ip_address')
    readonly_fields = ('id', 'session', 'user', 'role', 'joined_at', 'left_at', 'duration_seconds', 'ip_address', 'user_agent')

    def has_add_permission(self, request):
        return False


@admin.register(HomeworkSubmission)
class HomeworkSubmissionAdmin(admin.ModelAdmin):
    list_display = ('title', 'student', 'session', 'status', 'grade', 'submitted_at', 'reviewed_at')
    list_filter = ('status', 'submitted_at')
    search_fields = ('title', 'student__first_name', 'student__last_name', 'session__title', 'grade')
    readonly_fields = ('id', 'submitted_at', 'updated_at')

