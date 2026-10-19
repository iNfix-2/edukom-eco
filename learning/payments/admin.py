from django.contrib import admin
from .models import Invoice, PaymentTransaction, ProcessedWebhookEvent


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'client_name', 'client_email', 'currency', 'amount', 'status', 'due_date', 'paid_at')
    list_filter = ('status', 'currency', 'due_date', 'paid_at')
    search_fields = ('invoice_number', 'client_name', 'client_email', 'client_phone')
    readonly_fields = ('id', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('reference', 'invoice', 'gateway', 'currency', 'amount', 'status', 'channel', 'client_ip', 'created_at')
    list_filter = ('gateway', 'status', 'currency', 'channel', 'created_at')
    search_fields = ('reference', 'gateway_reference', 'invoice__invoice_number', 'client_ip')
    readonly_fields = ('id', 'reference', 'gateway', 'gateway_reference', 'amount', 'currency', 'client_ip', 'raw_response', 'verified_at', 'created_at')
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        # Prevent manual tampering with transaction logs
        return False


@admin.register(ProcessedWebhookEvent)
class ProcessedWebhookEventAdmin(admin.ModelAdmin):
    list_display = ('gateway', 'event_id', 'event_type', 'payload_hash', 'processed_at')
    list_filter = ('gateway', 'event_type', 'processed_at')
    search_fields = ('event_id', 'event_type', 'payload_hash')
    readonly_fields = ('gateway', 'event_id', 'event_type', 'payload_hash', 'processed_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
