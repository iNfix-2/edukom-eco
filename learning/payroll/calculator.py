from decimal import Decimal
from typing import Dict, List, Any, Optional, Tuple
from .models import TutorRateTier, TimezoneCategory


# Fallback base hourly rates in NGN if no specific tier is configured yet
DEFAULT_RATES_NGN = {
    'Reception Class': Decimal('4000.00'),
    'year 1': Decimal('4500.00'),
    'year 2': Decimal('4500.00'),
    'year 3': Decimal('5000.00'),
    'year 4': Decimal('5000.00'),
    'year 5': Decimal('5500.00'),
    'year 6': Decimal('5500.00'),
    'year 7': Decimal('6000.00'),
    'year 8': Decimal('6000.00'),
    'year 9': Decimal('6500.00'),
    'year 10': Decimal('7000.00'),
    'year 11': Decimal('7500.00'),
    'WAEC/GCSE CLASS': Decimal('8000.00'),
    'A levels': Decimal('9000.00'),
}


KEYWORD_LEVEL_MAP = [
    ('reception', 'Reception Class'),
    ('a level', 'A levels'),
    ('a-level', 'A levels'),
    ('alevel', 'A levels'),
    ('waec', 'WAEC/GCSE CLASS'),
    ('gcse', 'WAEC/GCSE CLASS'),
    ('igcse', 'WAEC/GCSE CLASS'),
    ('year 11', 'year 11'),
    ('year 10', 'year 10'),
    ('year 9', 'year 9'),
    ('year 8', 'year 8'),
    ('year 7', 'year 7'),
    ('year 6', 'year 6'),
    ('year 5', 'year 5'),
    ('year 4', 'year 4'),
    ('year 3', 'year 3'),
    ('year 2', 'year 2'),
    ('year 1', 'year 1'),
]


def normalize_class_level(raw_level: str) -> str:
    """
    Normalizes variations in class level naming from TutorCruncher/Zoho.
    Checks exact matches and standard educational keywords.
    """
    cleaned = raw_level.strip().lower()

    # 1. Exact match check
    for valid_level in DEFAULT_RATES_NGN.keys():
        if valid_level.lower() == cleaned:
            return valid_level

    # 2. Keyword matching in order of specificity
    for keyword, target_level in KEYWORD_LEVEL_MAP:
        if keyword in cleaned:
            return target_level

    return 'year 7'  # Safe default intermediate level


def normalize_timezone(raw_tz: str) -> str:
    """
    Maps client timezone string to standardized TimezoneCategory.
    """
    tz_clean = raw_tz.strip().upper()
    if any(k in tz_clean for k in ['WAT', 'LAGOS', 'NIGERIA', 'WEST AFRICA', 'GMT+1', 'UTC+1']):
        return TimezoneCategory.LOCAL_WAT
    elif any(k in tz_clean for k in ['GMT', 'BST', 'CET', 'LONDON', 'UK', 'ENGLAND', 'EUROPE', 'UTC+0', 'UTC+2']):
        return TimezoneCategory.UK_EUROPE
    elif any(k in tz_clean for k in ['EST', 'EDT', 'CST', 'CDT', 'PST', 'PDT', 'AMERICA', 'CANADA', 'US', 'USA', 'TEXAS', 'NEW YORK']):
        return TimezoneCategory.AMERICAS
    elif any(k in tz_clean for k in ['GST', 'SGT', 'DUBAI', 'UAE', 'SINGAPORE', 'AEST', 'AUSTRALIA']):
        return TimezoneCategory.MIDDLE_EAST_ASIA
    return TimezoneCategory.OTHER


def get_hourly_rate(
    class_level: str,
    delivery_mode: str = 'Online lessons',
    timezone_category: str = TimezoneCategory.LOCAL_WAT,
    currency: str = 'NGN'
) -> Decimal:
    """
    Queries active rate matrix for matching rate.
    Falls back gracefully to default table if not explicitly set.
    """
    norm_level = normalize_class_level(class_level)
    
    tier = TutorRateTier.objects.filter(
        class_level=norm_level,
        delivery_mode=delivery_mode,
        timezone_category=timezone_category,
        currency=currency,
        is_active=True
    ).first()

    if tier:
        return tier.hourly_rate

    # Fallback to local online rate for that level
    local_tier = TutorRateTier.objects.filter(
        class_level=norm_level,
        currency=currency,
        is_active=True
    ).first()

    if local_tier:
        return local_tier.hourly_rate

    # Fallback to coded baseline
    return DEFAULT_RATES_NGN.get(norm_level, Decimal('5000.00'))


def calculate_tutor_payroll(
    tutor_name: str,
    tutor_email: str,
    sessions: List[Dict[str, Any]],
    currency: str = 'NGN',
    deductions: Decimal = Decimal('0.00'),
    bonuses: Decimal = Decimal('0.00')
) -> Dict[str, Any]:
    """
    Computes total hours, itemized session pay, gross and net earnings for a tutor.
    """
    total_hours = Decimal('0.00')
    total_gross = Decimal('0.00')
    itemized_breakdown = []

    for s in sessions:
        hours = Decimal(str(s.get('duration_hours', 1.0)))
        class_level = s.get('class_level', 'year 7')
        delivery_mode = s.get('delivery_mode', 'Online lessons')
        tz_cat = normalize_timezone(s.get('timezone', 'WAT'))

        rate = get_hourly_rate(
            class_level=class_level,
            delivery_mode=delivery_mode,
            timezone_category=tz_cat,
            currency=currency
        )

        session_amount = hours * rate
        total_hours += hours
        total_gross += session_amount

        itemized_breakdown.append({
            'date': str(s.get('date', '')),
            'student_name': s.get('student_name', 'Student'),
            'class_level': class_level,
            'duration_hours': float(hours),
            'hourly_rate': float(rate),
            'amount': float(session_amount),
            'delivery_mode': delivery_mode,
            'timezone': tz_cat,
        })

    net_pay = total_gross - Decimal(str(deductions)) + Decimal(str(bonuses))
    if net_pay < Decimal('0.00'):
        net_pay = Decimal('0.00')

    return {
        'tutor_name': tutor_name,
        'tutor_email': tutor_email,
        'total_hours': total_hours,
        'gross_pay': total_gross,
        'deductions': Decimal(str(deductions)),
        'bonuses': Decimal(str(bonuses)),
        'net_pay': net_pay,
        'currency': currency,
        'breakdown': itemized_breakdown
    }


def calculate_lms_payroll(
    period_start,
    period_end,
    wht_percentage: Decimal = Decimal('5.0'),
    currency: str = 'NGN'
) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """
    Direct LMS-to-Payroll Bridge:
    Extracts all verified COMPLETED sessions from Edukom LMS within the specified period.
    Calculates hours, gross compensation using the 140-tier matrix, applies statutory
    withholding tax (WHT), and computes net disbursements with full audit breakdowns.
    Zero CSV handling required.
    """
    from classroom.models import ClassSession, SessionStatus
    from tutors.models import Tutor

    sessions_qs = ClassSession.objects.filter(
        status=SessionStatus.COMPLETED,
        start_time__date__gte=period_start,
        start_time__date__lte=period_end
    ).select_related(
        'booking', 
        'booking__tutor', 
        'booking__tutor__user', 
        'booking__tutor__tutor_record',
        'booking__student', 
        'booking__subject'
    ).order_by('booking__tutor', 'start_time')

    grouped_tutors: Dict[str, Dict[str, Any]] = {}
    warnings: List[str] = []

    if not sessions_qs.exists():
        warnings.append(f"No completed classroom sessions found between {period_start} and {period_end}.")
        return {}, warnings

    for s in sessions_qs:
        tutor_prof = s.booking.tutor
        tutor_user = tutor_prof.user
        tutor_email = tutor_user.email.strip().lower()
        tutor_name = tutor_prof.display_name or tutor_user.get_full_name() or tutor_user.username

        # Find or link corresponding Tutor model for payroll records
        tutor_record = tutor_prof.tutor_record
        if not tutor_record and tutor_email:
            tutor_record = Tutor.objects.filter(email__iexact=tutor_email).first()

        duration_hours = round(Decimal(str(s.duration_minutes)) / Decimal('60.0'), 2)
        class_level = s.booking.class_level
        delivery_mode = s.booking.delivery_mode
        tz_cat = normalize_timezone(s.booking.client_timezone)

        # Rate determination
        rate = get_hourly_rate(
            class_level=class_level,
            delivery_mode=delivery_mode,
            timezone_category=tz_cat,
            currency=currency
        )
        if rate <= Decimal('0.00') and s.booking.agreed_hourly_rate > Decimal('0.00'):
            rate = s.booking.agreed_hourly_rate

        session_amount = round(duration_hours * rate, 2)

        session_entry = {
            'session_id': str(s.id),
            'date': s.start_time.strftime('%Y-%m-%d %H:%M'),
            'student_name': f"{s.booking.student.first_name} {s.booking.student.last_name}",
            'subject': s.booking.subject.name,
            'class_level': class_level,
            'topic': s.lesson_topic or s.title,
            'duration_hours': float(duration_hours),
            'hourly_rate': float(rate),
            'amount': float(session_amount),
            'delivery_mode': delivery_mode,
            'timezone': tz_cat,
        }

        if tutor_email not in grouped_tutors:
            grouped_tutors[tutor_email] = {
                'tutor_obj': tutor_record,
                'tutor_name': tutor_name,
                'tutor_email': tutor_email,
                'sessions': [session_entry],
                'total_hours': duration_hours,
                'gross_pay': session_amount,
            }
        else:
            grouped_tutors[tutor_email]['sessions'].append(session_entry)
            grouped_tutors[tutor_email]['total_hours'] += duration_hours
            grouped_tutors[tutor_email]['gross_pay'] += session_amount

    # Apply Withholding Tax (WHT) and compute final Net
    for email, data in grouped_tutors.items():
        gross = data['gross_pay']
        wht_deduction = round((gross * Decimal(str(wht_percentage))) / Decimal('100.0'), 2)
        net = gross - wht_deduction
        if net < Decimal('0.00'):
            net = Decimal('0.00')

        data['deductions'] = wht_deduction
        data['bonuses'] = Decimal('0.00')
        data['net_pay'] = net
        data['wht_percentage'] = float(wht_percentage)

    return grouped_tutors, warnings

