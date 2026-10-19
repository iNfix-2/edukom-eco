import re
from functools import wraps
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest
from typing import Any

# Dangerous characters for CSV/Excel formula injection (CWE-1236)
DANGEROUS_FORMULA_PREFIXES = ('=', '+', '-', '@', '\t', '\r', '\n', '%')
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB limit


def sanitize_spreadsheet_value(val: Any) -> Any:
    """
    Prevents CSV / Formula Injection attacks (CWE-1236).
    Checks before and after whitespace stripping to ensure tab/newline bypasses are neutralized.
    If a cell starts with formula trigger characters, prepends an apostrophe (')
    so spreadsheet software treats it purely as text.
    """
    if val is None:
        return ""
    
    raw_str = str(val)
    # Check if raw string starts with dangerous characters (including tabs or CR)
    if raw_str.startswith(DANGEROUS_FORMULA_PREFIXES):
        return f"'{raw_str}"
    
    cleaned = raw_str.strip()
    if cleaned.startswith(DANGEROUS_FORMULA_PREFIXES):
        return f"'{cleaned}"
    
    return cleaned


def validate_payroll_file_upload(uploaded_file) -> None:
    """
    Validates uploaded session files against size and extension tampering.
    """
    if uploaded_file.size > MAX_UPLOAD_SIZE_BYTES:
        raise ValidationError("File size exceeds 10 MB limit.")

    valid_extensions = ('.csv', '.xlsx')
    file_name = uploaded_file.name.lower()

    if not any(file_name.endswith(ext) for ext in valid_extensions):
        raise ValidationError("Invalid file type. Only .csv and .xlsx files are permitted.")

    # Sanitize file name to prevent path traversal
    clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', uploaded_file.name)
    uploaded_file.name = clean_name


def payroll_admin_required(view_func):
    """
    Enforces Strict Role-Based Access Control (RBAC).
    Only authenticated Staff / Superusers can execute payroll actions.
    """
    @wraps(view_func)
    def _wrapped_view(request: HttpRequest, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required to access payroll operations.")
        if not request.user.is_staff:
            raise PermissionDenied("Administrative privileges required for payroll operations.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view
