"""
Accounts API views.
"""

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Company, CompanyMember, User
from .permissions import IsCompanyMember, IsCompanyOwner, IsStaff
from .serializers import (
    AddressSerializer,
    CompanyMemberSerializer,
    CompanySerializer,
    LoginEventSerializer,
    UserCreateSerializer,
    UserSerializer,
)


class RegisterView(generics.CreateAPIView):
    """
    POST /api/v1/accounts/register/
    Create a new user account.
    """

    queryset = User.objects.all()
    serializer_class = UserCreateSerializer
    permission_classes = [permissions.AllowAny]


class MeView(generics.RetrieveUpdateAPIView):
    """
    GET/PATCH /api/v1/accounts/me/
    Retrieve or update the current user's profile.
    """

    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class CompanyListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/accounts/companies/   — list companies (staff only)
    POST /api/v1/accounts/companies/   — create a new company
    """

    serializer_class = CompanySerializer

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsStaff()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        if self.request.user.staff_role:
            return Company.objects.all()
        # Regular users only see companies they belong to
        return Company.objects.filter(
            members__user=self.request.user,
            members__status=CompanyMember.Status.ACTIVE,
        ).distinct()

    def perform_create(self, serializer):
        company = serializer.save()
        # Auto-create an Owner membership for the creating user
        CompanyMember.objects.create(
            user=self.request.user,
            company=company,
            role=CompanyMember.Role.OWNER,
            status=CompanyMember.Status.ACTIVE,
        )


class CompanyDetailView(generics.RetrieveUpdateAPIView):
    """
    GET/PATCH /api/v1/accounts/companies/<pk>/
    """

    serializer_class = CompanySerializer
    permission_classes = [IsCompanyMember]

    def get_queryset(self):
        return Company.objects.all()


class CompanyMemberListView(generics.ListCreateAPIView):
    """
    GET  /api/v1/accounts/companies/<company_pk>/members/
    POST /api/v1/accounts/companies/<company_pk>/members/
    """

    serializer_class = CompanyMemberSerializer
    permission_classes = [IsCompanyMember]

    def get_queryset(self):
        return CompanyMember.objects.filter(
            company_id=self.kwargs["company_pk"],
        ).select_related("user", "company")
