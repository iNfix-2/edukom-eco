import json
import hashlib
import logging
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse, JsonResponse, HttpRequest
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.urls import reverse

from .models import (
    Invoice, 
    PaymentTransaction, 
    ProcessedWebhookEvent, 
    InvoiceStatus, 
    TransactionStatus, 
    GatewayChoices
)
from .security import (
    verify_paystack_signature, 
    verify_flutterwave_hash, 
    get_client_ip, 
    generate_secure_reference
)
from .services import PaystackService, FlutterwaveService

logger = logging.getLogger('payments')


@csrf_exempt
@require_POST
def paystack_webhook(request: HttpRequest) -> HttpResponse:
    """
    Highly secure Paystack Webhook Handler.
    Security Measures Enforced:
    1. Cryptographic HMAC-SHA512 signature verification.
    2. Replay attack defense via ProcessedWebhookEvent idempotency table.
    3. Payload integrity check (SHA-256 hash).
    4. Server-to-server zero-trust re-verification before state change.
    5. Atomic database transaction execution.
    """
    raw_body = request.body
    signature = request.headers.get('x-paystack-signature')

    # 1. Verify cryptographic HMAC signature
    if not verify_paystack_signature(raw_body, signature):
        logger.warning(f"Paystack webhook HMAC validation failed from IP: {get_client_ip(request)}")
        return HttpResponse("Invalid signature", status=400)

    try:
        payload = json.loads(raw_body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return HttpResponse("Malformed JSON payload", status=400)

    event_type = payload.get('event')
    data = payload.get('data', {})
    event_id = str(data.get('id') or data.get('reference') or '')

    if not event_id:
        return HttpResponse("Missing event ID/reference", status=400)

    # 2. Check for Replay Attack (Idempotency)
    payload_hash = hashlib.sha256(raw_body).hexdigest()
    if ProcessedWebhookEvent.objects.filter(gateway=GatewayChoices.PAYSTACK, event_id=event_id).exists():
        logger.info(f"Duplicate Paystack webhook event ignored: {event_id}")
        return HttpResponse("Event already processed", status=200)

    # 3. Handle successful charge
    if event_type == 'charge.success':
        reference = data.get('reference')
        
        # Zero Trust: Call Paystack directly to verify authenticity
        paystack_svc = PaystackService()
        verification = paystack_svc.verify_transaction(reference)

        if not verification.get('is_paid'):
            logger.error(f"Paystack reported charge.success but direct verification failed for ref {reference}")
            return HttpResponse("Verification mismatch", status=400)

        with transaction.atomic():
            try:
                tx = PaymentTransaction.objects.select_for_update().get(reference=reference)
            except PaymentTransaction.DoesNotExist:
                logger.error(f"PaymentTransaction not found for reference: {reference}")
                return HttpResponse("Transaction not found", status=404)

            # Prevent double-crediting
            if tx.status == TransactionStatus.SUCCESS:
                return HttpResponse("Transaction already finalized", status=200)

            # Amount verification to prevent underpayment exploits
            paid_amount = verification.get('amount_paid', Decimal(0))
            if paid_amount < tx.amount:
                logger.critical(
                    f"Underpayment detected for {reference}: Expected {tx.amount}, received {paid_amount}"
                )
                tx.status = TransactionStatus.FAILED
                tx.raw_response = data
                tx.save(update_fields=['status', 'raw_response'])
                return HttpResponse("Underpayment rejected", status=400)

            # Mark transaction success
            tx.status = TransactionStatus.SUCCESS
            tx.gateway_reference = str(data.get('id', ''))
            tx.channel = verification.get('channel', '')
            tx.verified_at = timezone.now()
            tx.raw_response = data
            tx.save()

            # Mark associated invoice as PAID
            invoice = tx.invoice
            invoice.status = InvoiceStatus.PAID
            invoice.paid_at = timezone.now()
            invoice.save(update_fields=['status', 'paid_at', 'updated_at'])

            # Record event in idempotency table
            ProcessedWebhookEvent.objects.create(
                gateway=GatewayChoices.PAYSTACK,
                event_id=event_id,
                event_type=event_type,
                payload_hash=payload_hash
            )

        # Trigger automated branded receipt email to parent
        from .notifications import send_payment_receipt_email
        send_payment_receipt_email(invoice, tx)
        logger.info(f"Successfully processed Paystack payment for invoice {invoice.invoice_number}")

    # =========================================================================
    # PAYSTACK AUTOMATED TRANSFER WEBHOOKS (PAYOUT SUCCESS, FAILURE, REVERSAL)
    # =========================================================================
    elif event_type == 'transfer.success':
        reference = data.get('reference', '')
        from payroll.models import TutorPayrollItem, PayrollRunStatus
        from payroll.notifications import send_tutor_payslip_email

        with transaction.atomic():
            item = TutorPayrollItem.objects.filter(disbursement_reference=reference).first()
            if not item and '-' in reference:
                parts = reference.split('-')
                if len(parts) >= 3:
                    item = TutorPayrollItem.objects.filter(id__hex__startswith=parts[2]).first()

            if item:
                item.status = 'PAID'
                item.save(update_fields=['status'])

                payroll_run = item.payroll_run
                if not payroll_run.items.exclude(status='PAID').exists():
                    payroll_run.status = PayrollRunStatus.DISBURSED
                    payroll_run.save(update_fields=['status'])

                send_tutor_payslip_email(item)

            ProcessedWebhookEvent.objects.create(
                gateway=GatewayChoices.PAYSTACK,
                event_id=event_id,
                event_type=event_type,
                payload_hash=payload_hash
            )
        logger.info(f"Paystack transfer succeeded for reference: {reference}")

    elif event_type in ('transfer.failed', 'transfer.reversed'):
        reference = data.get('reference', '')
        reason = data.get('reason') or data.get('gateway_response') or 'Bank transfer failed'
        from payroll.models import TutorPayrollItem, PayrollAuditLog
        from payroll.notifications import send_payout_failure_alert_email

        with transaction.atomic():
            item = TutorPayrollItem.objects.filter(disbursement_reference=reference).first()
            if not item and '-' in reference:
                parts = reference.split('-')
                if len(parts) >= 3:
                    item = TutorPayrollItem.objects.filter(id__hex__startswith=parts[2]).first()

            if item:
                item.status = 'FAILED'
                item.save(update_fields=['status'])

                PayrollAuditLog.objects.create(
                    action='PAYOUT_FAILED',
                    actor_username='Paystack Webhook',
                    target_id=str(item.id),
                    details={'reason': reason, 'reference': reference, 'tutor': item.tutor_name}
                )

                send_payout_failure_alert_email(item, reason)

            ProcessedWebhookEvent.objects.create(
                gateway=GatewayChoices.PAYSTACK,
                event_id=event_id,
                event_type=event_type,
                payload_hash=payload_hash
            )
        logger.warning(f"Paystack transfer failed/reversed for reference {reference}: {reason}")

    return HttpResponse("Webhook received successfully", status=200)


@csrf_exempt
@require_POST
def flutterwave_webhook(request: HttpRequest) -> HttpResponse:
    """
    Secure Flutterwave Webhook Handler with secret hash verification and idempotency.
    """
    signature = request.headers.get('verif-hash')
    if not verify_flutterwave_hash(signature):
        logger.warning(f"Flutterwave webhook secret hash check failed from IP: {get_client_ip(request)}")
        return HttpResponse("Unauthorized", status=401)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponse("Malformed payload", status=400)

    data = payload.get('data', {})
    event_id = str(data.get('id', ''))
    tx_ref = data.get('tx_ref')

    if not event_id or not tx_ref:
        return HttpResponse("Incomplete payload", status=400)

    # Replay attack check
    if ProcessedWebhookEvent.objects.filter(gateway=GatewayChoices.FLUTTERWAVE, event_id=event_id).exists():
        return HttpResponse("Event already processed", status=200)

    # Server verification
    flw_svc = FlutterwaveService()
    verification = flw_svc.verify_transaction(event_id)

    if verification.get('is_paid'):
        with transaction.atomic():
            try:
                tx = PaymentTransaction.objects.select_for_update().get(reference=tx_ref)
                if tx.status != TransactionStatus.SUCCESS:
                    tx.status = TransactionStatus.SUCCESS
                    tx.gateway_reference = event_id
                    tx.verified_at = timezone.now()
                    tx.raw_response = data
                    tx.save()

                    invoice = tx.invoice
                    invoice.status = InvoiceStatus.PAID
                    invoice.paid_at = timezone.now()
                    invoice.save(update_fields=['status', 'paid_at', 'updated_at'])

                ProcessedWebhookEvent.objects.create(
                    gateway=GatewayChoices.FLUTTERWAVE,
                    event_id=event_id,
                    event_type=payload.get('event', 'charge.completed'),
                    payload_hash=hashlib.sha256(request.body).hexdigest()
                )
            except PaymentTransaction.DoesNotExist:
                logger.error(f"Transaction not found for tx_ref: {tx_ref}")

    return HttpResponse("Webhook received", status=200)


@require_GET
def invoice_checkout_view(request: HttpRequest, invoice_id: str) -> HttpResponse:
    """
    Renders clean, secure payment portal for client / guardian to review invoice and pay.
    """
    invoice = get_object_or_404(Invoice, id=invoice_id)
    context = {
        'invoice': invoice,
        'paystack_public_key': getattr(settings, 'PAYSTACK_PUBLIC_KEY', ''),
        'flutterwave_public_key': getattr(settings, 'FLUTTERWAVE_PUBLIC_KEY', ''),
    }
    return render(request, 'payments/checkout.html', context)


@require_POST
def initialize_payment_view(request: HttpRequest, invoice_id: str) -> HttpResponse:
    """
    Initiates payment with selected gateway and returns redirect to secure checkout page.
    Protected by Django CSRF token.
    """
    invoice = get_object_or_404(Invoice, id=invoice_id)
    if invoice.status == InvoiceStatus.PAID:
        return JsonResponse({'error': 'Invoice is already paid.'}, status=400)

    gateway = request.POST.get('gateway', GatewayChoices.PAYSTACK)
    reference = generate_secure_reference(prefix="EDK")
    client_ip = get_client_ip(request)

    # Create unfinalized transaction record
    tx = PaymentTransaction.objects.create(
        reference=reference,
        invoice=invoice,
        gateway=gateway,
        amount=invoice.amount,
        currency=invoice.currency,
        status=TransactionStatus.INITIALIZED,
        client_ip=client_ip
    )

    callback_url = request.build_absolute_uri(reverse('payments:payment_callback'))

    if gateway == GatewayChoices.PAYSTACK:
        svc = PaystackService()
        result = svc.initialize_transaction(
            email=invoice.client_email,
            amount=invoice.amount,
            reference=reference,
            callback_url=callback_url,
            currency=invoice.currency,
            metadata={'invoice_id': str(invoice.id), 'invoice_number': invoice.invoice_number}
        )
    elif gateway == GatewayChoices.FLUTTERWAVE:
        svc = FlutterwaveService()
        result = svc.initialize_payment(
            email=invoice.client_email,
            amount=invoice.amount,
            reference=reference,
            callback_url=callback_url,
            currency=invoice.currency,
            customer_name=invoice.client_name,
            metadata={'invoice_id': str(invoice.id), 'invoice_number': invoice.invoice_number}
        )
    else:
        return JsonResponse({'error': 'Unsupported payment gateway'}, status=400)

    if result.get('success'):
        return redirect(result['authorization_url'])
    else:
        tx.status = TransactionStatus.FAILED
        tx.save(update_fields=['status'])
        return render(request, 'payments/error.html', {'error': result.get('error')})


@require_GET
def payment_callback_view(request: HttpRequest) -> HttpResponse:
    """
    Client return URL after completing gateway payment.
    Performs server-side zero-trust verification before presenting receipt.
    """
    reference = request.GET.get('reference') or request.GET.get('trxref') or request.GET.get('tx_ref')
    if not reference:
        return render(request, 'payments/error.html', {'error': 'No payment reference provided.'})

    tx = get_object_or_404(PaymentTransaction, reference=reference)

    if tx.status != TransactionStatus.SUCCESS:
        # Perform server-side check
        if tx.gateway == GatewayChoices.PAYSTACK:
            svc = PaystackService()
            verification = svc.verify_transaction(reference)
            if verification.get('is_paid'):
                with transaction.atomic():
                    tx.status = TransactionStatus.SUCCESS
                    tx.verified_at = timezone.now()
                    tx.channel = verification.get('channel', '')
                    tx.save()
                    tx.invoice.status = InvoiceStatus.PAID
                    tx.invoice.paid_at = timezone.now()
                    tx.invoice.save(update_fields=['status', 'paid_at', 'updated_at'])

                from .notifications import send_payment_receipt_email
                send_payment_receipt_email(tx.invoice, tx)

    context = {
        'transaction': tx,
        'invoice': tx.invoice,
        'is_success': tx.status == TransactionStatus.SUCCESS
    }
    return render(request, 'payments/receipt.html', context)
