import uuid
from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from tutors.models import Tutor, cc as CLASS_CHOICES, lesson_choices as LESSON_CHOICES

User = get_user_model()


class TimezoneCategory(models.TextChoices):
    LOCAL_WAT = 'LOCAL_WAT', 'Local / West Africa (WAT)'
    UK_EUROPE = 'UK_EUROPE', 'UK / Europe (GMT/BST/CET)'
    AMERICAS = 'AMERICAS', 'Americas (EST/CST/PST)'
    MIDDLE_EAST_ASIA = 'MIDDLE_EAST_ASIA', 'Middle East / Asia (GST/SGT/AEST)'
    OTHER = 'OTHER', 'Other Global Regions'


class PayrollRunStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    CALCULATED = 'CALCULATED', 'Calculated'
    APPROVED = 'APPROVED', 'Approved by Management'
    DISBURSED = 'DISBURSED', 'Disbursed / Paid'
    CANCELLED = 'CANCELLED', 'Cancelled'


class TutorRateTier(models.Model):
    """
    Configurable dynamic rate matrix.
    Allows Edukom Operations to set hourly pay rates based on:
    - Class Level (Reception, Years 1-11, A-Levels, WAEC/GCSE)
    - Delivery Mode (Physical vs Online)
    - Client Timezone (WAT, GMT, EST, GST)
    """
    class_level = models.CharField(max_length=100, choices=CLASS_CHOICES, db_index=True)
    delivery_mode = models.CharField(max_length=100, choices=LESSON_CHOICES, default='Online lessons', db_index=True)
    timezone_category = models.CharField(
        max_length=30, 
        choices=TimezoneCategory.choices, 
        default=TimezoneCategory.LOCAL_WAT,
        db_index=True
    )
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    currency = models.CharField(max_length=10, default='NGN')
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('class_level', 'delivery_mode', 'timezone_category', 'currency')
        ordering = ['class_level', 'delivery_mode', 'timezone_category']

    def __str__(self):
        return f"{self.class_level} ({self.delivery_mode}, {self.get_timezone_category_display()}): {self.currency} {self.hourly_rate}/hr"


class TutorBankAccount(models.Model):
    """
    Secured banking details for automated tutor disbursements.
    Includes masking property to enforce NDPR/PCI privacy compliance.
    """
    tutor = models.OneToOneField(Tutor, on_delete=models.CASCADE, related_name='bank_account')
    bank_name = models.CharField(max_length=128)
    bank_code = models.CharField(max_length=10, help_text="CBN 3-digit bank code or Paystack bank code")
    account_number = models.CharField(max_length=10, db_index=True)
    account_name = models.CharField(max_length=255, help_text="Verified account name from bank lookup")
    recipient_code = models.CharField(max_length=100, blank=True, help_text="Paystack Transfer Recipient Code")
    is_verified = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def masked_account_number(self) -> str:
        """Masks account number to prevent sensitive data leakage in logs and UI."""
        if len(self.account_number) == 10:
            return f"******{self.account_number[-4:]}"
        return "******"

    def __str__(self):
        return f"{self.account_name} - {self.bank_name} ({self.masked_account_number})"


class PayrollRun(models.Model):
    """
    Represents a full payroll period run.
    Enforces dual-control authorization (maker-checker):
    Created by one Admin, approved by a separate Manager.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(
        max_length=20, 
        choices=PayrollRunStatus.choices, 
        default=PayrollRunStatus.DRAFT,
        db_index=True
    )
    total_hours = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_gross = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_net = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    currency = models.CharField(max_length=10, default='NGN')
    source_filename = models.CharField(max_length=255, blank=True)
    
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='created_payroll_runs'
    )
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='approved_payroll_runs'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.get_status_display()}) - {self.currency} {self.total_net}"


class TutorPayrollItem(models.Model):
    """
    Individual tutor compensation line item within a payroll run.
    Contains granular session audit breakdown for full transparency.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payroll_run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name='items')
    tutor = models.ForeignKey(Tutor, on_delete=models.SET_NULL, null=True, related_name='payroll_items')
    tutor_name = models.CharField(max_length=255)
    tutor_email = models.EmailField()
    
    total_hours = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))
    calculated_gross_pay = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    deductions = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    bonuses = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    net_pay = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    status = models.CharField(max_length=20, default='PENDING', db_index=True)
    disbursement_reference = models.CharField(max_length=128, blank=True)
    session_breakdown = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['tutor_name']

    def __str__(self):
        return f"{self.tutor_name} - Hours: {self.total_hours} - Net: {self.net_pay}"


class PayrollAuditLog(models.Model):
    """
    Immutable security audit trail for all payroll calculations, rate changes, and payouts.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action = models.CharField(max_length=64, db_index=True)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    actor_username = models.CharField(max_length=150)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    target_id = models.CharField(max_length=128, blank=True)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.created_at}] {self.actor_username} - {self.action}"
