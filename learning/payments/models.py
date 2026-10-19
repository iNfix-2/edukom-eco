import uuid
from django.db import models
from django.utils import timezone
from homepage.models import Guardian


class CurrencyChoices(models.TextChoices):
    NGN = 'NGN', 'Nigerian Naira (NGN)'
    USD = 'USD', 'US Dollar (USD)'
    GBP = 'GBP', 'British Pound (GBP)'
    EUR = 'EUR', 'Euro (EUR)'
    CAD = 'CAD', 'Canadian Dollar (CAD)'


class InvoiceStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    PENDING = 'PENDING', 'Pending Payment'
    PAID = 'PAID', 'Paid'
    FAILED = 'FAILED', 'Failed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class GatewayChoices(models.TextChoices):
    PAYSTACK = 'PAYSTACK', 'Paystack'
    FLUTTERWAVE = 'FLUTTERWAVE', 'Flutterwave'


class TransactionStatus(models.TextChoices):
    INITIALIZED = 'INITIALIZED', 'Initialized'
    SUCCESS = 'SUCCESS', 'Success'
    FAILED = 'FAILED', 'Failed'
    ABANDONED = 'ABANDONED', 'Abandoned'


class Invoice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number = models.CharField(max_length=64, unique=True, db_index=True)
    guardian = models.ForeignKey(
        Guardian, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='invoices'
    )
    client_name = models.CharField(max_length=255)
    client_email = models.EmailField(db_index=True)
    client_phone = models.CharField(max_length=50, blank=True)
    
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(
        max_length=10, 
        choices=CurrencyChoices.choices, 
        default=CurrencyChoices.NGN
    )
    status = models.CharField(
        max_length=20, 
        choices=InvoiceStatus.choices, 
        default=InvoiceStatus.PENDING,
        db_index=True
    )
    description = models.TextField(blank=True, help_text="Tuition, registration, or lesson package details")
    due_date = models.DateField(default=timezone.now)
    paid_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.invoice_number} - {self.client_name} ({self.currency} {self.amount})"


class PaymentTransaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=128, unique=True, db_index=True)
    invoice = models.ForeignKey(
        Invoice, 
        on_delete=models.CASCADE, 
        related_name='transactions'
    )
    gateway = models.CharField(
        max_length=20, 
        choices=GatewayChoices.choices, 
        default=GatewayChoices.PAYSTACK
    )
    gateway_reference = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, choices=CurrencyChoices.choices)
    status = models.CharField(
        max_length=20, 
        choices=TransactionStatus.choices, 
        default=TransactionStatus.INITIALIZED,
        db_index=True
    )
    channel = models.CharField(max_length=50, blank=True, help_text="card, bank_transfer, ussd, apple_pay, etc.")
    client_ip = models.GenericIPAddressField(null=True, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.reference} - {self.gateway} - {self.status} ({self.currency} {self.amount})"


class ProcessedWebhookEvent(models.Model):
    """
    Prevents Webhook Replay Attacks and ensures idempotency.
    Every successfully validated webhook event ID is recorded here.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gateway = models.CharField(max_length=20, choices=GatewayChoices.choices, db_index=True)
    event_id = models.CharField(max_length=255, db_index=True)
    event_type = models.CharField(max_length=100)
    payload_hash = models.CharField(max_length=64, help_text="SHA-256 hash of raw webhook payload")
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('gateway', 'event_id')
        ordering = ['-processed_at']

    def __str__(self):
        return f"{self.gateway} Event {self.event_id} ({self.event_type})"
