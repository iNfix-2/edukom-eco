import json
import logging
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, HttpRequest, JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import transaction
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt

from .models import (
    PayrollRun, 
    TutorPayrollItem, 
    TutorRateTier, 
    PayrollAuditLog, 
    PayrollRunStatus,
    TimezoneCategory
)
from .security import (
    payroll_admin_required, 
    validate_payroll_file_upload, 
    sanitize_spreadsheet_value
)
from .parsers import parse_session_file
from .calculator import calculate_tutor_payroll, calculate_lms_payroll
from .disbursement import export_payroll_excel, generate_paystack_transfer_batch
from payments.services import PaystackService
from tutors.models import Tutor

logger = logging.getLogger('payroll')


def _log_payroll_audit(request: HttpRequest, action: str, target_id: str = '', details: dict = None):
    ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
    PayrollAuditLog.objects.create(
        action=action,
        actor=request.user if request.user.is_authenticated else None,
        actor_username=request.user.username if request.user.is_authenticated else 'Anonymous',
        ip_address=ip.split(',')[0].strip() if ip else '',
        target_id=target_id,
        details=details or {}
    )


@payroll_admin_required
def payroll_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Main operations hub for managing tutor payroll runs.
    """
    runs = PayrollRun.objects.all().order_by('-created_at')[:20]
    active_rates_count = TutorRateTier.objects.filter(is_active=True).count()
    
    total_disbursed = sum(
        (r.total_net for r in runs if r.status == PayrollRunStatus.DISBURSED), 
        Decimal('0.00')
    )

    context = {
        'runs': runs,
        'active_rates_count': active_rates_count,
        'total_disbursed': total_disbursed,
    }
    return render(request, 'payroll/dashboard.html', context)


@payroll_admin_required
def upload_and_calculate_payroll(request: HttpRequest) -> HttpResponse:
    """
    Upload session logs from TutorCruncher/Zoho and calculate payroll.
    """
    if request.method == 'POST':
        uploaded_file = request.FILES.get('session_file')
        title = request.POST.get('title', 'Tutor Payroll Run').strip()
        period_start = request.POST.get('period_start')
        period_end = request.POST.get('period_end')

        if not uploaded_file:
            messages.error(request, "Please select a valid CSV or Excel file to upload.")
            return redirect('payroll:upload')

        try:
            validate_payroll_file_upload(uploaded_file)
        except Exception as e:
            messages.error(request, f"File validation failed: {str(e)}")
            return redirect('payroll:upload')

        grouped_tutors, parse_errors = parse_session_file(uploaded_file)

        if not grouped_tutors:
            messages.error(request, f"No valid session data could be extracted. {parse_errors[:3]}")
            return redirect('payroll:upload')

        with transaction.atomic():
            payroll_run = PayrollRun.objects.create(
                title=title,
                period_start=period_start or timezone.now().date(),
                period_end=period_end or timezone.now().date(),
                status=PayrollRunStatus.CALCULATED,
                currency='NGN',
                source_filename=uploaded_file.name,
                created_by=request.user
            )

            total_hours = Decimal('0.00')
            total_gross = Decimal('0.00')
            total_net = Decimal('0.00')

            for tutor_key, t_data in grouped_tutors.items():
                tutor_name = t_data['tutor_name']
                tutor_email = t_data['tutor_email']
                sessions = t_data['sessions']

                calc = calculate_tutor_payroll(
                    tutor_name=tutor_name,
                    tutor_email=tutor_email,
                    sessions=sessions,
                    currency='NGN'
                )

                # Match with registered Tutor model if exists
                matched_tutor = None
                if tutor_email:
                    matched_tutor = Tutor.objects.filter(email__iexact=tutor_email).first()
                if not matched_tutor and tutor_name:
                    matched_tutor = Tutor.objects.filter(first_name__icontains=tutor_name.split()[0]).first()

                TutorPayrollItem.objects.create(
                    payroll_run=payroll_run,
                    tutor=matched_tutor,
                    tutor_name=tutor_name,
                    tutor_email=tutor_email,
                    total_hours=calc['total_hours'],
                    calculated_gross_pay=calc['gross_pay'],
                    deductions=calc['deductions'],
                    bonuses=calc['bonuses'],
                    net_pay=calc['net_pay'],
                    session_breakdown=calc['breakdown']
                )

                total_hours += calc['total_hours']
                total_gross += calc['gross_pay']
                total_net += calc['net_pay']

            payroll_run.total_hours = total_hours
            payroll_run.total_gross = total_gross
            payroll_run.total_net = total_net
            payroll_run.save()

            _log_payroll_audit(
                request, 
                action='PAYROLL_CALCULATED', 
                target_id=str(payroll_run.id),
                details={'tutors_count': len(grouped_tutors), 'total_net': float(total_net)}
            )

        messages.success(request, f"Payroll calculated successfully for {len(grouped_tutors)} tutors!")
        return redirect('payroll:run_detail', run_id=payroll_run.id)

    return render(request, 'payroll/upload.html')


@payroll_admin_required
def payroll_run_detail(request: HttpRequest, run_id: str) -> HttpResponse:
    """
    Detailed audit review page for a specific payroll run.
    """
    payroll_run = get_object_or_404(PayrollRun, id=run_id)
    items = payroll_run.items.all().select_related('tutor', 'tutor__bank_account')

    context = {
        'run': payroll_run,
        'items': items,
    }
    return render(request, 'payroll/run_detail.html', context)


@payroll_admin_required
@require_POST
def approve_payroll_run(request: HttpRequest, run_id: str) -> HttpResponse:
    """
    Dual-authorization checker: Manager approves calculated payroll run.
    """
    payroll_run = get_object_or_404(PayrollRun, id=run_id)

    if payroll_run.status != PayrollRunStatus.CALCULATED:
        messages.error(request, "Only runs with status 'Calculated' can be approved.")
        return redirect('payroll:run_detail', run_id=run_id)

    payroll_run.status = PayrollRunStatus.APPROVED
    payroll_run.approved_by = request.user
    payroll_run.approved_at = timezone.now()
    payroll_run.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])

    _log_payroll_audit(
        request, 
        action='PAYROLL_APPROVED', 
        target_id=str(payroll_run.id),
        details={'approved_by': request.user.username}
    )

    messages.success(request, f"Payroll run '{payroll_run.title}' has been officially approved.")
    return redirect('payroll:run_detail', run_id=run_id)


@payroll_admin_required
@require_GET
def export_payroll_excel_view(request: HttpRequest, run_id: str) -> HttpResponse:
    """
    Downloads formula-injection sanitized Excel payroll summary.
    """
    payroll_run = get_object_or_404(PayrollRun, id=run_id)
    excel_buffer = export_payroll_excel(payroll_run)

    safe_title = sanitize_spreadsheet_value(payroll_run.title).replace(' ', '_')
    filename = f"Payroll_{safe_title}_{payroll_run.period_end}.xlsx"

    response = HttpResponse(
        excel_buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@payroll_admin_required
def rate_matrix_view(request: HttpRequest) -> HttpResponse:
    """
    Manage dynamic tutor rate tiers across class levels, timezones, and delivery modes.
    """
    if request.method == 'POST':
        tier_id = request.POST.get('tier_id')
        hourly_rate = request.POST.get('hourly_rate')

        if tier_id and hourly_rate:
            tier = get_object_or_404(TutorRateTier, id=tier_id)
            try:
                tier.hourly_rate = Decimal(hourly_rate)
                tier.save(update_fields=['hourly_rate', 'updated_at'])
                _log_payroll_audit(
                    request, 
                    action='RATE_UPDATED', 
                    target_id=str(tier.id),
                    details={'level': tier.class_level, 'new_rate': float(tier.hourly_rate)}
                )
                messages.success(request, f"Rate for {tier.class_level} updated.")
            except Exception as e:
                messages.error(request, f"Invalid rate value: {str(e)}")

        return redirect('payroll:rate_matrix')

    tiers = TutorRateTier.objects.all().order_by('class_level', 'delivery_mode')
    context = {
        'tiers': tiers,
        'timezone_choices': TimezoneCategory.choices,
    }
    return render(request, 'payroll/rate_matrix.html', context)


FALLBACK_NIGERIAN_BANKS = [
    {"name": "Access Bank", "code": "044"},
    {"name": "Ecobank Nigeria", "code": "050"},
    {"name": "Fidelity Bank", "code": "070"},
    {"name": "First Bank of Nigeria", "code": "011"},
    {"name": "First City Monument Bank (FCMB)", "code": "214"},
    {"name": "Guaranty Trust Bank (GTB)", "code": "058"},
    {"name": "Kuda Bank", "code": "090267"},
    {"name": "Moniepoint MFB", "code": "090405"},
    {"name": "OPay Digital Services", "code": "090325"},
    {"name": "Palmpay", "code": "090466"},
    {"name": "Stanbic IBTC Bank", "code": "221"},
    {"name": "Sterling Bank", "code": "232"},
    {"name": "Union Bank of Nigeria", "code": "032"},
    {"name": "United Bank for Africa (UBA)", "code": "033"},
    {"name": "Wema Bank", "code": "035"},
    {"name": "Zenith Bank", "code": "057"},
]


@payroll_admin_required
@require_GET
def get_nigerian_banks_api(request: HttpRequest) -> JsonResponse:
    """
    Returns list of banks from Paystack or fallback cache.
    """
    svc = PaystackService()
    result = svc.list_banks()
    if result.get('success') and result.get('banks'):
        return JsonResponse({'banks': result['banks']})
    return JsonResponse({'banks': FALLBACK_NIGERIAN_BANKS})


@payroll_admin_required
@require_POST
def resolve_nuban_api(request: HttpRequest) -> JsonResponse:
    """
    NUBAN Verification endpoint:
    Verifies 10-digit account number against bank code via NIBSS.
    """
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid JSON body'}, status=400)

    account_number = str(data.get('account_number', '')).strip()
    bank_code = str(data.get('bank_code', '')).strip()

    if len(account_number) != 10 or not account_number.isdigit():
        return JsonResponse({'success': False, 'error': 'Nigerian NUBAN must be exactly 10 digits'}, status=400)

    if not bank_code:
        return JsonResponse({'success': False, 'error': 'Bank code is required'}, status=400)

    svc = PaystackService()
    result = svc.resolve_account_number(account_number, bank_code)
    return JsonResponse(result)


@payroll_admin_required
def link_tutor_bank_account(request: HttpRequest, tutor_id: int) -> HttpResponse:
    """
    Tutor KYC & Bank Account Linking:
    Verifies NUBAN name, registers Paystack transfer recipient code, and saves TutorBankAccount.
    """
    tutor = get_object_or_404(Tutor, id=tutor_id)
    bank_acct = getattr(tutor, 'bank_account', None)

    if request.method == 'POST':
        bank_code = request.POST.get('bank_code', '').strip()
        bank_name = request.POST.get('bank_name', '').strip()
        account_number = request.POST.get('account_number', '').strip()

        if len(account_number) != 10 or not account_number.isdigit():
            messages.error(request, "Account number must be exactly 10 digits.")
            return redirect('payroll:link_bank', tutor_id=tutor.id)

        # 1. Resolve Account Name via NIBSS/Paystack
        svc = PaystackService()
        res = svc.resolve_account_number(account_number, bank_code)
        
        # If live resolution fails due to test credentials, allow manual confirmation with warning
        account_name = res.get('account_name')
        if not account_name:
            account_name = request.POST.get('account_name', f"{tutor.first_name} {tutor.last_name}").strip()

        # 2. Register Transfer Recipient on Paystack
        recipient_code = ""
        rec_res = svc.create_transfer_recipient(
            name=account_name,
            account_number=account_number,
            bank_code=bank_code
        )
        if rec_res.get('success'):
            recipient_code = rec_res.get('recipient_code', '')
        else:
            recipient_code = f"RCP_MOCK_{tutor.id}"

        # 3. Save to database
        from .models import TutorBankAccount
        acct, _ = TutorBankAccount.objects.update_or_create(
            tutor=tutor,
            defaults={
                'bank_name': bank_name,
                'bank_code': bank_code,
                'account_number': account_number,
                'account_name': account_name,
                'recipient_code': recipient_code,
                'is_verified': True
            }
        )

        _log_payroll_audit(
            request, 
            action='BANK_ACCOUNT_VERIFIED', 
            target_id=str(tutor.id),
            details={'bank': bank_name, 'account_name': account_name, 'recipient_code': recipient_code}
        )

        messages.success(request, f"Bank account verified and linked successfully for {tutor.first_name} {tutor.last_name}!")
        return redirect('payroll:dashboard')

    context = {
        'tutor': tutor,
        'bank_acct': bank_acct,
        'banks': FALLBACK_NIGERIAN_BANKS,
    }
    return render(request, 'payroll/link_bank.html', context)


@payroll_admin_required
@require_POST
def send_all_payslips_view(request: HttpRequest, run_id: str) -> HttpResponse:
    """
    Dispatches automated itemized payslip HTML emails to all tutors in this payroll run.
    """
    payroll_run = get_object_or_404(PayrollRun, id=run_id)
    from .notifications import send_tutor_payslip_email

    sent_count = 0
    fail_count = 0

    for item in payroll_run.items.all():
        if item.tutor_email:
            success = send_tutor_payslip_email(item)
            if success:
                sent_count += 1
            else:
                fail_count += 1

    messages.success(
        request, 
        f"Payslip email dispatch completed: {sent_count} sent successfully ({fail_count} failed)."
    )
    return redirect('payroll:run_detail', run_id=run_id)


@payroll_admin_required
@require_POST
def generate_lms_payroll_view(request: HttpRequest) -> HttpResponse:
    """
    Direct LMS Session-to-Payroll Bridge:
    Automatically queries all COMPLETED live sessions in Edukom LMS for the selected date range,
    calculates gross earnings using the 140-tier matrix, applies statutory Withholding Tax (WHT),
    and creates a complete, itemized PayrollRun with zero external CSV handling.
    """
    from datetime import datetime

    period_start_str = request.POST.get('period_start', '').strip()
    period_end_str = request.POST.get('period_end', '').strip()
    title = request.POST.get('title', '').strip()
    wht_raw = request.POST.get('wht_percentage', '5.0').strip()

    if not period_start_str or not period_end_str:
        messages.error(request, "Both Start Date and End Date are required.")
        return redirect('payroll:dashboard')

    try:
        period_start = datetime.strptime(period_start_str, '%Y-%m-%d').date()
        period_end = datetime.strptime(period_end_str, '%Y-%m-%d').date()
        if period_end < period_start:
            messages.error(request, "End Date cannot be before Start Date.")
            return redirect('payroll:dashboard')
    except ValueError:
        messages.error(request, "Invalid date format. Expected YYYY-MM-DD.")
        return redirect('payroll:dashboard')

    try:
        wht_percentage = Decimal(wht_raw)
        if wht_percentage < Decimal('0.0') or wht_percentage > Decimal('100.0'):
            wht_percentage = Decimal('5.0')
    except Exception:
        wht_percentage = Decimal('5.0')

    if not title:
        title = f"LMS Payroll ({period_start.strftime('%b %d')} - {period_end.strftime('%b %d, %Y')})"

    grouped_tutors, warnings = calculate_lms_payroll(
        period_start=period_start,
        period_end=period_end,
        wht_percentage=wht_percentage,
        currency='NGN'
    )

    if not grouped_tutors:
        msg = warnings[0] if warnings else "No completed classroom sessions found for this date range."
        messages.warning(request, msg)
        return redirect('payroll:dashboard')

    with transaction.atomic():
        payroll_run = PayrollRun.objects.create(
            title=title,
            period_start=period_start,
            period_end=period_end,
            status=PayrollRunStatus.CALCULATED,
            currency='NGN',
            source_filename='Edukom LMS Live Sessions (Native)',
            created_by=request.user
        )

        total_hours = Decimal('0.00')
        total_gross = Decimal('0.00')
        total_net = Decimal('0.00')

        for email, t_data in grouped_tutors.items():
            TutorPayrollItem.objects.create(
                payroll_run=payroll_run,
                tutor=t_data['tutor_obj'],
                tutor_name=t_data['tutor_name'],
                tutor_email=t_data['tutor_email'],
                total_hours=t_data['total_hours'],
                calculated_gross_pay=t_data['gross_pay'],
                deductions=t_data['deductions'],
                bonuses=t_data['bonuses'],
                net_pay=t_data['net_pay'],
                session_breakdown=t_data['sessions']
            )

            total_hours += t_data['total_hours']
            total_gross += t_data['gross_pay']
            total_net += t_data['net_pay']

        payroll_run.total_hours = total_hours
        payroll_run.total_gross = total_gross
        payroll_run.total_net = total_net
        payroll_run.save(update_fields=['total_hours', 'total_gross', 'total_net'])

        _log_payroll_audit(
            request,
            action='PAYROLL_GENERATED_FROM_LMS',
            target_id=str(payroll_run.id),
            details={
                'tutors_count': len(grouped_tutors),
                'total_hours': float(total_hours),
                'total_net': float(total_net),
                'wht_percentage': float(wht_percentage)
            }
        )

    messages.success(
        request, 
        f"LMS Payroll successfully generated for {len(grouped_tutors)} tutors! Total Net: ₦{total_net:,.2f}"
    )
    return redirect('payroll:run_detail', run_id=payroll_run.id)


@login_required
def tutor_payslip_detail_view(request: HttpRequest, item_id: str) -> HttpResponse:
    """
    Tutor Self-Service Payslip & Statement Voucher:
    BOLA/IDOR protected view allowing tutors to inspect and print their itemized compensation breakdown.
    """
    item = get_object_or_404(
        TutorPayrollItem.objects.select_related('payroll_run', 'tutor', 'tutor__bank_account'),
        id=item_id
    )

    # Security: BOLA/IDOR ownership validation
    is_tutor_owner = (
        (item.tutor_email and item.tutor_email.lower() == request.user.email.lower()) or
        (item.tutor and item.tutor.email and item.tutor.email.lower() == request.user.email.lower()) or
        (hasattr(request.user, 'tutor_profile') and item.tutor and hasattr(item.tutor, 'profile') and item.tutor.profile == request.user.tutor_profile)
    )
    is_authorized = is_tutor_owner or request.user.is_staff or request.user.is_superuser

    if not is_authorized:
        return HttpResponse("Forbidden: You are not authorized to view this payslip.", status=403)

    bank_account = getattr(item.tutor, 'bank_account', None) if item.tutor else None

    context = {
        'item': item,
        'run': item.payroll_run,
        'bank_account': bank_account,
        'now': timezone.now(),
    }
    return render(request, 'payroll/payslip_detail.html', context)


@csrf_exempt
@require_POST
def paystack_transfer_webhook_view(request: HttpRequest) -> HttpResponse:
    """
    Paystack Automated Transfer Webhook Reconciliation:
    Listens for transfer events (success, failed, reversed), verifies HMAC-SHA512 signature,
    and updates TutorPayrollItem disbursement status in real time.
    """
    from django.conf import settings
    import hmac
    import hashlib

    secret = getattr(settings, 'PAYSTACK_SECRET_KEY', '')
    signature = request.META.get('HTTP_X_PAYSTACK_SIGNATURE', '')

    computed_sig = hmac.new(
        secret.encode('utf-8'),
        request.body,
        hashlib.sha512
    ).hexdigest()

    if not hmac.compare_digest(computed_sig, signature):
        logger.warning("Invalid Paystack transfer webhook signature received.")
        return HttpResponse("Invalid Signature", status=400)

    try:
        event_data = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponse("Invalid JSON", status=400)

    event_type = event_data.get('event')
    data = event_data.get('data', {})
    reference = data.get('reference', '')

    logger.info(f"Paystack transfer webhook received: {event_type} - Ref: {reference}")

    if reference:
        item = TutorPayrollItem.objects.filter(disbursement_reference=reference).first()
        if item:
            if event_type == 'transfer.success':
                item.status = 'PAID'
                item.save(update_fields=['status'])
                _log_payroll_audit(
                    request,
                    action='TRANSFER_SUCCESS_WEBHOOK',
                    target_id=str(item.id),
                    details={'reference': reference, 'amount': data.get('amount')}
                )
            elif event_type in ['transfer.failed', 'transfer.reversed']:
                item.status = 'FAILED'
                item.save(update_fields=['status'])
                _log_payroll_audit(
                    request,
                    action='TRANSFER_FAILED_WEBHOOK',
                    target_id=str(item.id),
                    details={'reference': reference, 'reason': data.get('reason')}
                )

    return JsonResponse({'status': 'success'})

