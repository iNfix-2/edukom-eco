import json
import hashlib
import hmac
from decimal import Decimal
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.core import mail
from django.utils import timezone

from payments.models import (
    Invoice, 
    PaymentTransaction, 
    ProcessedWebhookEvent, 
    InvoiceStatus, 
    TransactionStatus, 
    GatewayChoices
)
from payments.security import verify_paystack_signature, generate_secure_reference
from payments.notifications import send_payment_receipt_email
from payroll.models import PayrollRun, TutorPayrollItem, PayrollRunStatus


@override_settings(PAYSTACK_SECRET_KEY='sk_test_secret_test_key')
class PaymentSecurityTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.secret = 'sk_test_secret_test_key'
        self.invoice = Invoice.objects.create(
            invoice_number='INV-TEST-001',
            client_name='Test Parent',
            client_email='parent@example.com',
            amount=Decimal('50000.00'),
            currency='NGN',
            status=InvoiceStatus.PENDING
        )

    def test_secure_reference_generation(self):
        ref1 = generate_secure_reference()
        ref2 = generate_secure_reference()
        self.assertNotEqual(ref1, ref2)
        self.assertTrue(ref1.startswith('EDK-'))
        self.assertGreaterEqual(len(ref1), 20)

    def test_hmac_signature_validation(self):
        payload = b'{"event": "charge.success", "data": {"id": 12345}}'
        valid_signature = hmac.new(
            self.secret.encode('utf-8'),
            msg=payload,
            digestmod=hashlib.sha512
        ).hexdigest()

        self.assertTrue(verify_paystack_signature(payload, valid_signature))

        tampered_payload = b'{"event": "charge.success", "data": {"id": 99999}}'
        self.assertFalse(verify_paystack_signature(tampered_payload, valid_signature))
        self.assertFalse(verify_paystack_signature(payload, "invalid_sig_abc123"))

    def test_webhook_rejects_unauthorized_post(self):
        url = reverse('payments:paystack_webhook')
        response = self.client.post(url, data='{}', content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_replay_attack_idempotency_defense(self):
        ProcessedWebhookEvent.objects.create(
            gateway=GatewayChoices.PAYSTACK,
            event_id='EVT-REPLAY-99',
            event_type='charge.success',
            payload_hash='dummy_hash'
        )

        payload = json.dumps({'event': 'charge.success', 'data': {'id': 'EVT-REPLAY-99'}}).encode('utf-8')
        signature = hmac.new(
            self.secret.encode('utf-8'),
            msg=payload,
            digestmod=hashlib.sha512
        ).hexdigest()

        url = reverse('payments:paystack_webhook')
        response = self.client.post(
            url, 
            data=payload, 
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=signature
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Event already processed", response.content)

    def test_payment_receipt_email_sending(self):
        tx = PaymentTransaction.objects.create(
            reference='EDK-TEST-RECEIPT-REF',
            invoice=self.invoice,
            gateway=GatewayChoices.PAYSTACK,
            amount=Decimal('50000.00'),
            currency='NGN',
            status=TransactionStatus.SUCCESS
        )

        success = send_payment_receipt_email(self.invoice, tx)
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.invoice.invoice_number, mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, ['parent@example.com'])

    def test_transfer_success_webhook_updates_status(self):
        payroll_run = PayrollRun.objects.create(
            title='October Test Payroll',
            period_start=timezone.now().date(),
            period_end=timezone.now().date(),
            status=PayrollRunStatus.APPROVED
        )

        item = TutorPayrollItem.objects.create(
            payroll_run=payroll_run,
            tutor_name='Jane Tutor',
            tutor_email='jane@example.com',
            total_hours=Decimal('10.00'),
            calculated_gross_pay=Decimal('50000.00'),
            net_pay=Decimal('50000.00'),
            status='PENDING',
            disbursement_reference='PAY-TEST-JANE'
        )

        payload = json.dumps({
            'event': 'transfer.success',
            'data': {
                'id': 88888,
                'reference': 'PAY-TEST-JANE',
                'amount': 5000000
            }
        }).encode('utf-8')

        signature = hmac.new(
            self.secret.encode('utf-8'),
            msg=payload,
            digestmod=hashlib.sha512
        ).hexdigest()

        url = reverse('payments:paystack_webhook')
        response = self.client.post(
            url, 
            data=payload, 
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=signature
        )

        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.status, 'PAID')
        payroll_run.refresh_from_db()
        self.assertEqual(payroll_run.status, PayrollRunStatus.DISBURSED)

    def test_transfer_failed_webhook_marks_failed(self):
        payroll_run = PayrollRun.objects.create(
            title='October Test Payroll 2',
            period_start=timezone.now().date(),
            period_end=timezone.now().date(),
            status=PayrollRunStatus.APPROVED
        )

        item = TutorPayrollItem.objects.create(
            payroll_run=payroll_run,
            tutor_name='Bob Tutor',
            tutor_email='bob@example.com',
            total_hours=Decimal('5.00'),
            calculated_gross_pay=Decimal('25000.00'),
            net_pay=Decimal('25000.00'),
            status='PENDING',
            disbursement_reference='PAY-TEST-BOB'
        )

        payload = json.dumps({
            'event': 'transfer.failed',
            'data': {
                'id': 77777,
                'reference': 'PAY-TEST-BOB',
                'reason': 'Account number does not exist'
            }
        }).encode('utf-8')

        signature = hmac.new(
            self.secret.encode('utf-8'),
            msg=payload,
            digestmod=hashlib.sha512
        ).hexdigest()

        url = reverse('payments:paystack_webhook')
        response = self.client.post(
            url, 
            data=payload, 
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=signature
        )

        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.status, 'FAILED')
