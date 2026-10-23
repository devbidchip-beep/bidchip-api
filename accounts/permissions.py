"""
Role-based DRF permission classes for the accounts app.
"""

from rest_framework.permissions import BasePermission


class IsStaff(BasePermission):
    """
    Allow access only to users who have any staff_role set (i.e., internal
    BidChip employees).
    """

    message = "Staff access required."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.staff_role is not None
        )


class IsTrusty(BasePermission):
    """
    Allow access only to Trusty staff members.
    Trusties perform final listing approvals and dispute resolutions.
    """

    message = "Trusty staff role required."

    def has_permission(self, request, view):
        from accounts.models import User

        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.staff_role == User.StaffRole.TRUSTY
        )


class IsWarehouse(BasePermission):
    """
    Allow access only to Warehouse staff members.
    """

    message = "Warehouse staff role required."

    def has_permission(self, request, view):
        from accounts.models import User

        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.staff_role == User.StaffRole.WAREHOUSE
        )


class IsLab(BasePermission):
    """
    Allow access only to Lab staff members (component testing / grading).
    """

    message = "Lab staff role required."

    def has_permission(self, request, view):
        from accounts.models import User

        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.staff_role == User.StaffRole.LAB
        )


class IsCompanyOwner(BasePermission):
    """
    Allow access only if the authenticated user is an Owner of the company
    referenced in the request.

    Views using this permission should set `self.company` or pass the company
    PK in the URL kwargs as `company_pk` / `pk`.

    Object-level permission checks whether the user is an owner of the specific
    company object.
    """

    message = "Company owner access required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        from accounts.models import Company, CompanyMember

        # `obj` may be a Company or a related model with a .company attribute
        company = obj if isinstance(obj, Company) else getattr(obj, "company", None)
        if company is None:
            return False
        return CompanyMember.objects.filter(
            user=request.user,
            company=company,
            role=CompanyMember.Role.OWNER,
            status=CompanyMember.Status.ACTIVE,
        ).exists()


class IsCompanyMember(BasePermission):
    """
    Allow access only if the authenticated user is an active member of the
    company referenced in the request (any role).
    """

    message = "Active company membership required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        from accounts.models import Company, CompanyMember

        company = obj if isinstance(obj, Company) else getattr(obj, "company", None)
        if company is None:
            return False
        return CompanyMember.objects.filter(
            user=request.user,
            company=company,
            status=CompanyMember.Status.ACTIVE,
        ).exists()
