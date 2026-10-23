"""
Global DRF permission classes for the core app.
These supplement the per-app permissions in accounts/permissions.py.
"""

from rest_framework.permissions import BasePermission, IsAdminUser


class IsAdminOrReadOnly(BasePermission):
    """
    Allow full access to admin users; read-only access to authenticated users.
    """

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return bool(request.user and request.user.is_authenticated)
        return bool(request.user and request.user.is_staff)


class IsSuperUser(BasePermission):
    """
    Allow access only to Django superusers.
    """

    message = "Superuser access required."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser
        )


class HasVerifiedMFA(BasePermission):
    """
    Allow access only if the user has completed MFA verification in this
    session (django-otp is_verified()).
    """

    message = "Multi-factor authentication required."

    def has_permission(self, request, view):
        from django_otp import user_is_verified

        return bool(
            request.user
            and request.user.is_authenticated
            and user_is_verified(request.user)
        )


class MFARequiredForMFAUsers(BasePermission):
    """
    If a user has mfa_required=True, they MUST have completed MFA this session.
    Users without mfa_required pass through unchanged.
    """

    message = "This account requires multi-factor authentication."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if not getattr(user, "mfa_required", False):
            return True
        from django_otp import user_is_verified

        return user_is_verified(user)
