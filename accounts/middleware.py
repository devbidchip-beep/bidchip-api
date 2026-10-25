"""
Middleware for MFA enforcement on staff and mfa_required users.
"""

from django.conf import settings
from django.shortcuts import redirect

# URL path prefixes/exact paths that are exempt from MFA enforcement
MFA_EXEMPT_PREFIXES = (
    "/mfa/",
    "/admin/login/",
    "/health/",
    "/api/v1/auth/",
)


class MFAEnforcementMiddleware:
    """
    For staff users and users with mfa_required=True:
    If authenticated and no verified OTP device in session → redirect to /mfa/setup/.
    Exempt: /mfa/, /admin/login/, /health/, /api/v1/auth/.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._should_enforce(request):
            return redirect("/mfa/setup/")
        return self.get_response(request)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_exempt(self, path: str) -> bool:
        return any(path.startswith(prefix) for prefix in MFA_EXEMPT_PREFIXES)

    def _requires_mfa(self, user) -> bool:
        """Return True if this user must have MFA verified."""
        if not user or not user.is_authenticated:
            return False
        return user.is_staff or getattr(user, "mfa_required", False)

    def _has_verified_otp(self, request) -> bool:
        """
        Return True if the user has a verified OTP device for this session.
        Uses django-otp's is_verified() helper.
        """
        try:
            from django_otp import user_is_verified  # noqa: PLC0415

            return user_is_verified(request.user)
        except ImportError:
            # If django-otp is not installed, skip the check
            return True

    def _should_enforce(self, request) -> bool:
        if self._is_exempt(request.path):
            return False

        user = getattr(request, "user", None)
        if not self._requires_mfa(user):
            return False

        return not self._has_verified_otp(request)
