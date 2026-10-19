from django.contrib import admin
from .models import TutorRateTier, TutorBankAccount, PayrollRun, TutorPayrollItem, PayrollAuditLog


@admin.register(TutorRateTier)
class TutorRateTierAdmin(admin.ModelAdmin):
    list_display = ('class_level', 'delivery_mode', 'timezone_category', 'hourly_rate', 'currency', 'is_active')
    list_filter = ('delivery_mode', 'timezone_category', 'currency', 'is_active')
    search_fields = ('class_level',)
    list_editable = ('hourly_rate', 'is_active')


@admin.register(TutorBankAccount)
class TutorBankAccountAdmin(admin.ModelAdmin):
    list_display = ('tutor', 'account_name', 'bank_name', 'masked_account_number', 'is_verified', 'recipient_code')
    list_filter = ('is_verified', 'bank_name')
    search_fields = ('tutor__first_name', 'tutor__last_name', 'account_name', 'account_number', 'recipient_code')
    readonly_fields = ('recipient_code', 'updated_at')


class TutorPayrollItemInline(admin.TabularInline):
    model = TutorPayrollItem
    extra = 0
    readonly_fields = ('tutor', 'tutor_name', 'tutor_email', 'total_hours', 'calculated_gross_pay', 'deductions', 'bonuses', 'net_pay', 'status')
    can_delete = False


@admin.register(PayrollRun)
class PayrollRunAdmin(admin.ModelAdmin):
    list_display = ('title', 'period_start', 'period_end', 'status', 'total_hours', 'total_net', 'currency', 'created_by', 'created_at')
    list_filter = ('status', 'currency', 'created_at')
    search_fields = ('title', 'source_filename')
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines = [TutorPayrollItemInline]


@admin.register(PayrollAuditLog)
class PayrollAuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'actor_username', 'action', 'ip_address', 'target_id')
    list_filter = ('action', 'created_at')
    search_fields = ('actor_username', 'action', 'target_id')
    readonly_fields = ('id', 'action', 'actor', 'actor_username', 'ip_address', 'target_id', 'details', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
