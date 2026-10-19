from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from .models import UserRole


def role_required(allowed_roles):
    """
    Decorator ensuring the authenticated user has one of the allowed roles.
    Admins / Superusers are always granted access to all roles.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect(f"/account/login/?next={request.path}")

            profile = getattr(request.user, 'profile', None)
            if not profile:
                # Fallback to create profile on-the-fly
                from .models import UserProfile
                initial_role = UserRole.ADMIN if request.user.is_superuser else (
                    UserRole.STAFF if request.user.is_staff else (
                        UserRole.TUTOR if hasattr(request.user, 'tutor_profile') else UserRole.STUDENT
                    )
                )
                profile = UserProfile.objects.create(user=request.user, role=initial_role)

            # Superusers always have universal access
            if request.user.is_superuser or profile.role == UserRole.ADMIN:
                return view_func(request, *args, **kwargs)

            if profile.role in allowed_roles:
                return view_func(request, *args, **kwargs)

            # Staff can access student, tutor, and guardian dashboards for coordination
            if profile.role == UserRole.STAFF and (UserRole.STUDENT in allowed_roles or UserRole.TUTOR in allowed_roles or UserRole.GUARDIAN in allowed_roles):
                return view_func(request, *args, **kwargs)

            messages.warning(
                request, 
                f"Access restricted. You do not have permission to access that dashboard."
            )
            return redirect(profile.get_dashboard_url())
        return _wrapped_view
    return decorator


def student_required(view_func):
    return role_required([UserRole.STUDENT])(view_func)


def guardian_required(view_func):
    return role_required([UserRole.GUARDIAN])(view_func)


def tutor_required(view_func):
    return role_required([UserRole.TUTOR])(view_func)


def staff_required(view_func):
    return role_required([UserRole.STAFF, UserRole.ADMIN])(view_func)


def admin_required(view_func):
    return role_required([UserRole.ADMIN])(view_func)

