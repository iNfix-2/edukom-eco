"""
International E.164 Phone Number Formatter for Edukom Group.
Cleans raw phone numbers collected across 5+ global operating zones:
- Nigeria (+234)
- United Kingdom (+44)
- United States / Canada (+1)
- United Arab Emirates (+971)
- South Africa (+27)
"""

import re
from typing import Optional


def normalize_to_e164(raw_phone: Optional[str], default_country_code: str = '+234') -> str:
    """
    Standardizes international phone number strings to E.164 format.
    Examples:
    - '08012345678' -> '+2348012345678' (Nigeria local)
    - '2348012345678' -> '+2348012345678'
    - '+44 7123 456789' -> '+447123456789' (UK)
    - '07123456789' (if UK context) -> '+447123456789'
    - '1 (555) 123-4567' -> '+15551234567' (US)
    """
    if not raw_phone:
        return ''

    # Remove all non-digit characters except leading '+'
    cleaned = re.sub(r'[^\d+]', '', str(raw_phone).strip())

    if cleaned.startswith('+'):
        return cleaned

    # Already has Nigerian country code without '+'
    if cleaned.startswith('234') and len(cleaned) == 13:
        return f"+{cleaned}"

    # Already has UK country code without '+'
    if cleaned.startswith('44') and len(cleaned) in (12, 13):
        return f"+{cleaned}"

    # Already has US country code without '+'
    if cleaned.startswith('1') and len(cleaned) == 11:
        return f"+{cleaned}"

    # Already has UAE country code without '+'
    if cleaned.startswith('971') and len(cleaned) in (11, 12):
        return f"+{cleaned}"

    # Leading zero: Standard Nigerian local mobile (080, 081, 070, 090, 091)
    if cleaned.startswith(('080', '081', '090', '091', '070')) and len(cleaned) == 11:
        return f"+234{cleaned[1:]}"

    # Leading zero: UK local mobile (071-079)
    if cleaned.startswith('07') and len(cleaned) == 11:
        return f"+44{cleaned[1:]}"

    # Fallback with default country code
    clean_prefix = default_country_code if default_country_code.startswith('+') else f"+{default_country_code}"
    return f"{clean_prefix}{cleaned.lstrip('0')}"
