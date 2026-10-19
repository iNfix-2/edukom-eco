import json
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core import mail
from django.utils import timezone

from payroll.security import sanitize_spreadsheet_value
from payroll.calculator import normalize_class_level, normalize_timezone, calculate_tutor_payroll
from payroll.models import TimezoneCategory, PayrollRun, TutorPayrollItem, PayrollRunStatus
from payroll.notifications import send_tutor_payslip_email, send_payout_failure_alert_email

User = get_user_model()


class PayrollSecurityAndMathTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username='payroll_admin',
            email='admin@edukom.ng',
            password='TestPassword123'
        )

    def test_formula_injection_defense(self):
        malicious_samples = [
            "=cmd|' /C calc'!A0",
            "+12345",
            "-5000",
            "@SUM(A1:A10)",
            "\tTabbedExploit",
            "\rCarriageReturnExploit"
        ]

        for sample in malicious_samples:
            sanitized = sanitize_spreadsheet_value(sample)
            self.assertTrue(sanitized.startswith("'"), f"Failed to neutralize: {sample}")

        benign_sample = "Ope Komolafe"
        self.assertEqual(sanitize_spreadsheet_value(benign_sample), "Ope Komolafe")

    def test_timezone_normalization(self):
        self.assertEqual(normalize_timezone("London, UK (GMT)"), TimezoneCategory.UK_EUROPE)
        self.assertEqual(normalize_timezone("Lagos, Nigeria (WAT)"), TimezoneCategory.LOCAL_WAT)
        self.assertEqual(normalize_timezone("New York (EST)"), TimezoneCategory.AMERICAS)
        self.assertEqual(normalize_timezone("Dubai (GST)"), TimezoneCategory.MIDDLE_EAST_ASIA)
        self.assertEqual(normalize_timezone("Unknown Location"), TimezoneCategory.OTHER)

    def test_class_level_normalization(self):
        self.assertEqual(normalize_class_level("year 10"), "year 10")
        self.assertEqual(normalize_class_level("A Levels Cambridge"), "A levels")
        self.assertEqual(normalize_class_level("WAEC Class"), "WAEC/GCSE CLASS")

    def test_tutor_payroll_math(self):
        sessions = [
            {
                'date': '2026-10-01',
                'student_name': 'David',
                'class_level': 'year 10',
                'duration_hours': Decimal('2.0'),
                'delivery_mode': 'Online lessons',
                'timezone': 'WAT'
            },
            {
                'date': '2026-10-03',
                'student_name': 'Sarah',
                'class_level': 'A levels',
                'duration_hours': Decimal('1.5'),
                'delivery_mode': 'Online lessons',
                'timezone': 'London (GMT)'
            }
        ]

        result = calculate_tutor_payroll(
            tutor_name="John Doe",
            tutor_email="john@example.com",
            sessions=sessions,
            currency='NGN',
            deductions=Decimal('1000.00'),
            bonuses=Decimal('2000.00')
        )

        self.assertEqual(result['total_hours'], Decimal('3.5'))
        self.assertGreater(result['gross_pay'], Decimal('0.00'))
        self.assertEqual(result['net_pay'], result['gross_pay'] - Decimal('1000.00') + Decimal('2000.00'))
        self.assertEqual(len(result['breakdown']), 2)

    def test_payslip_email_generation_and_sending(self):
        run = PayrollRun.objects.create(
            title='October Test Payroll Run',
            period_start=timezone.now().date(),
            period_end=timezone.now().date(),
            status=PayrollRunStatus.APPROVED
        )

        item = TutorPayrollItem.objects.create(
            payroll_run=run,
            tutor_name='Alex Teacher',
            tutor_email='alex@example.com',
            total_hours=Decimal('15.00'),
            calculated_gross_pay=Decimal('90000.00'),
            net_pay=Decimal('90000.00'),
            session_breakdown=[{
                'date': '2026-10-05',
                'student_name': 'Emeka',
                'class_level': 'year 11',
                'duration_hours': 2.0,
                'hourly_rate': 7500.0,
                'amount': 15000.0
            }]
        )

        success = send_tutor_payslip_email(item)
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Your Payslip', mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, ['alex@example.com'])
        self.assertIn('90,000.00', mail.outbox[0].body or mail.outbox[0].alternatives[0][0])

    def test_payout_failure_alert_email(self):
        run = PayrollRun.objects.create(
            title='November Test Payroll',
            period_start=timezone.now().date(),
            period_end=timezone.now().date()
        )

        item = TutorPayrollItem.objects.create(
            payroll_run=run,
            tutor_name='Failing Tutor',
            tutor_email='failing@example.com',
            total_hours=Decimal('2.00'),
            calculated_gross_pay=Decimal('10000.00'),
            net_pay=Decimal('10000.00')
        )

        success = send_payout_failure_alert_email(item, reason="Account blacklisted by NIBSS")
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Tutor Payout Failed", mail.outbox[0].subject)

    def test_resolve_nuban_api_validation(self):
        self.client.force_login(self.admin_user)
        url = reverse('payroll:api_resolve_account')
        
        # Test invalid account number (not 10 digits)
        res = self.client.post(
            url, 
            data=json.dumps({'account_number': '123', 'bank_code': '058'}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn('Nigerian NUBAN must be exactly 10 digits', res.json().get('error'))
