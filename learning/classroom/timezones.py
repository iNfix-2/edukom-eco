"""
Multi-Timezone Conversion and Formatting Utility for Edukom LMS.
Supports clients and tutors across 5+ global regions:
- West Africa Time (WAT) - Africa/Lagos (UTC+1)
- United Kingdom (GMT / BST) - Europe/London (UTC+0 / UTC+1 with Daylight Saving Time)
- North America Eastern (EST / EDT) - America/New_York (UTC-5 / UTC-4)
- North America Central (CST / CDT) - America/Chicago (UTC-6 / UTC-5)
- Gulf Standard Time (GST) - Asia/Dubai (UTC+4)
- South Africa Standard Time (SAST) - Africa/Johannesburg (UTC+2)
"""

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Optional
from django.utils import timezone

# Timezone alias mappings from common user input/shorthand to canonical IANA names
TIMEZONE_ALIASES = {
    'WAT': 'Africa/Lagos',
    'LAGOS': 'Africa/Lagos',
    'NIGERIA': 'Africa/Lagos',
    'GMT': 'Europe/London',
    'BST': 'Europe/London',
    'LONDON': 'Europe/London',
    'UK': 'Europe/London',
    'EST': 'America/New_York',
    'EDT': 'America/New_York',
    'NEW YORK': 'America/New_York',
    'US/EASTERN': 'America/New_York',
    'CST': 'America/Chicago',
    'CDT': 'America/Chicago',
    'CHICAGO': 'America/Chicago',
    'US/CENTRAL': 'America/Chicago',
    'PST': 'America/Los_Angeles',
    'PDT': 'America/Los_Angeles',
    'GST': 'Asia/Dubai',
    'DUBAI': 'Asia/Dubai',
    'UAE': 'Asia/Dubai',
    'SAST': 'Africa/Johannesburg',
    'SOUTH AFRICA': 'Africa/Johannesburg',
    'UTC': 'UTC',
}

# Friendly display names for zones
TIMEZONE_FRIENDLY_NAMES = {
    'Africa/Lagos': 'Lagos (WAT)',
    'Europe/London': 'London',
    'America/New_York': 'New York (ET)',
    'America/Chicago': 'Chicago (CT)',
    'Asia/Dubai': 'Dubai (GST)',
    'Africa/Johannesburg': 'Johannesburg (SAST)',
    'UTC': 'UTC',
}


def resolve_timezone(tz_str: Optional[str]) -> ZoneInfo:
    """
    Safely resolves a string or alias into a valid ZoneInfo instance.
    Defaults to Africa/Lagos (Edukom home base) on unresolvable input.
    """
    if not tz_str:
        return ZoneInfo('Africa/Lagos')

    cleaned = tz_str.strip()
    upper = cleaned.upper()

    # Check aliases first
    iana_name = TIMEZONE_ALIASES.get(upper)
    if not iana_name:
        iana_name = cleaned

    try:
        return ZoneInfo(iana_name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return ZoneInfo('Africa/Lagos')


def format_session_in_tz(dt: datetime, tz: ZoneInfo, friendly_city: str = '') -> str:
    """
    Converts aware datetime to target timezone and formats time with dynamic DST abbreviation.
    Example: '4:00 PM BST (London)' or '5:00 PM WAT (Lagos)'
    """
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.utc)

    localized = dt.astimezone(tz)
    # tzname returns dynamically 'BST' or 'GMT', 'EDT' or 'EST'
    tz_code = localized.tzname() or ''
    time_str = localized.strftime('%I:%M %p').lstrip('0')
    
    city_suffix = f" ({friendly_city})" if friendly_city else ""
    return f"{time_str} {tz_code}{city_suffix}".strip()


def format_dual_session_time(session) -> str:
    """
    Generates a dual-timezone display string for class cards, e.g.:
    '4:00 PM BST (London) / 5:00 PM WAT (Lagos) - Tuesday, 18 Nov'
    Prevents missed sessions during British Summer Time (BST) / US Daylight Saving Time (DST).
    """
    dt = session.start_time
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.utc)

    # 1. Determine student/client timezone
    client_raw = getattr(session.booking, 'client_timezone', '') or getattr(session.booking.student, 'timezone', '')
    client_tz = resolve_timezone(client_raw)
    client_iana = client_tz.key
    client_city = TIMEZONE_FRIENDLY_NAMES.get(client_iana, client_iana.split('/')[-1])

    # 2. Determine tutor/HQ timezone (Default Nigeria WAT)
    tutor_tz = ZoneInfo('Africa/Lagos')
    tutor_city = 'Lagos'

    # Localize
    client_str = format_session_in_tz(dt, client_tz, friendly_city=client_city)
    tutor_str = format_session_in_tz(dt, tutor_tz, friendly_city=tutor_city)

    # Date formatted in client timezone
    client_dt = dt.astimezone(client_tz)
    date_str = client_dt.strftime('%A, %d %b %Y')

    if client_iana == tutor_tz.key:
        return f"{client_str} - {date_str}"
    
    return f"{client_str} / {tutor_str} - {date_str}"
