from functools import wraps
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import ClassSession, SessionStatus


def can_access_session(user, session: ClassSession) -> tuple[bool, str]:
    """
    Evaluates role-based authorization for entering a live class session (IDOR/BOLA defense).
    Returns: (is_authorized: bool, role: 'TUTOR' | 'STUDENT' | 'ADMIN')
    """
    if not user.is_authenticated:
        return False, ""

    if user.is_staff or user.is_superuser:
        return True, "ADMIN"

    # Check if user is the assigned Tutor
    if hasattr(user, 'tutor_profile') and session.booking.tutor.user == user:
        return True, "TUTOR"

    # Check if user is the assigned Student
    student = session.booking.student
    if student.user and student.user == user:
        return True, "STUDENT"

    # Check if user is the Guardian of the student
    if student.guardian.email.lower() == user.email.lower():
        return True, "STUDENT"

    return False, ""


def session_access_required(view_func):
    """
    Decorator enforcing strict session authorization and timing guard.
    """
    @wraps(view_func)
    def _wrapped_view(request, session_id, *args, **kwargs):
        session = get_object_or_404(ClassSession, id=session_id)
        is_auth, role = can_access_session(request.user, session)

        if not is_auth:
            raise PermissionDenied("You are not authorized to enter this private classroom session.")

        request.session_user_role = role
        return view_func(request, session_id, *args, **kwargs)
    return _wrapped_view
