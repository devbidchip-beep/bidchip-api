"""
Accounts serializers.
"""

from rest_framework import serializers

from .models import Address, Company, CompanyMember, LoginEvent, StripeAccount, User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "full_name",
            "staff_role",
            "is_active",
            "mfa_required",
            "last_login_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "last_login_at"]


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "phone", "password"]
        read_only_fields = ["id"]

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = [
            "id",
            "legal_name",
            "display_name",
            "country",
            "website",
            "is_buyer",
            "is_supplier",
            "is_oem",
            "is_ems",
            "status",
            "integrity_score",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "integrity_score", "created_at", "updated_at"]


class CompanyMemberSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    company_name = serializers.CharField(source="company.display_name", read_only=True)

    class Meta:
        model = CompanyMember
        fields = [
            "id",
            "user",
            "user_email",
            "company",
            "company_name",
            "role",
            "can_release_payout",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            "id",
            "company",
            "user",
            "address_type",
            "line1",
            "line2",
            "city",
            "state",
            "postal_code",
            "country",
            "is_primary",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class LoginEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoginEvent
        fields = [
            "id",
            "email_attempted",
            "outcome",
            "ip_address",
            "mfa_used",
            "created_at",
        ]
        read_only_fields = fields
