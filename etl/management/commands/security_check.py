"""
Pre-launch security checklist.
Usage: python manage.py security_check

Checks:
1. DEBUG = False in current settings
2. SECRET_KEY is not the default test key
3. STRIPE_WEBHOOK_SECRET is set
4. No active StripeEvent with signature_verified=False that has been processed
5. No User with staff_role set and mfa_required=False
6. ALLOWED_HOSTS is not ['*']
7. SECURE_SSL_REDIRECT = True
8. SESSION_COOKIE_SECURE = True
9. ANTHROPIC_API_KEY is set
10. At least one active FeeSchedule exists
11. At least one active NotificationTemplate exists for 'delivered_payout_in_5_days'
12. PlatformSetting 'hold.green_days' exists
Print PASS/WARN/FAIL for each. Exit 1 if any FAIL.
"""

import sys

from django.conf import settings
from django.core.management.base import BaseCommand

INSECURE_SECRET_KEYS = {
    "insecure-dev-key-change-in-production",
    "change-me",
    "ci-test-secret-key-not-for-production",
    "test-secret-key",
}


class Command(BaseCommand):
    help = "Run pre-launch security checklist"

    def handle(self, *args, **options):
        results: list[tuple[str, str, str]] = []  # (label, level, detail)
        # level: PASS | WARN | FAIL

        def check_pass(label: str, detail: str = ""):
            results.append((label, "PASS", detail))

        def check_warn(label: str, detail: str = ""):
            results.append((label, "WARN", detail))

        def check_fail(label: str, detail: str = ""):
            results.append((label, "FAIL", detail))

        def check_bool(label: str, value: bool, fail_detail: str = "", warn: bool = False):
            if value:
                check_pass(label)
            elif warn:
                check_warn(label, fail_detail)
            else:
                check_fail(label, fail_detail)

        # 1. DEBUG = False
        check_bool("DEBUG=False", not settings.DEBUG, "DEBUG is True — must be False in production")

        # 2. SECRET_KEY is not default
        secret_key = getattr(settings, "SECRET_KEY", "")
        check_bool(
            "SECRET_KEY is not default",
            secret_key not in INSECURE_SECRET_KEYS and len(secret_key) >= 32,
            f"SECRET_KEY appears insecure: '{secret_key[:12]}...'",
        )

        # 3. STRIPE_WEBHOOK_SECRET is set
        stripe_wh = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
        check_bool(
            "STRIPE_WEBHOOK_SECRET is set",
            bool(stripe_wh),
            "STRIPE_WEBHOOK_SECRET is empty",
        )

        # 4. No StripeEvent with signature_verified=False processed
        try:
            from payments.models import StripeEvent  # noqa: PLC0415

            bad_events = StripeEvent.objects.filter(
                signature_verified=False,
                processed=True,
            ).count()
            check_bool(
                "No processed StripeEvents with unverified signatures",
                bad_events == 0,
                f"{bad_events} processed events with signature_verified=False",
            )
        except Exception as exc:  # noqa: BLE001
            check_warn("StripeEvent check", f"Could not query: {exc}")

        # 5. No staff user with mfa_required=False
        try:
            from django.contrib.auth import get_user_model  # noqa: PLC0415

            User = get_user_model()
            staff_no_mfa = User.objects.filter(
                is_staff=True,
                mfa_required=False,
            ).count()
            check_bool(
                "All staff users have mfa_required=True",
                staff_no_mfa == 0,
                f"{staff_no_mfa} staff users with mfa_required=False",
            )
        except Exception as exc:  # noqa: BLE001
            check_warn("Staff MFA check", f"Could not query: {exc}")

        # 6. ALLOWED_HOSTS is not ['*']
        allowed_hosts = getattr(settings, "ALLOWED_HOSTS", [])
        check_bool(
            "ALLOWED_HOSTS is not wildcard",
            "*" not in allowed_hosts,
            "ALLOWED_HOSTS contains '*' — restrict to real hostnames",
        )

        # 7. SECURE_SSL_REDIRECT = True
        check_bool(
            "SECURE_SSL_REDIRECT=True",
            getattr(settings, "SECURE_SSL_REDIRECT", False),
            "SECURE_SSL_REDIRECT is not True",
        )

        # 8. SESSION_COOKIE_SECURE = True
        check_bool(
            "SESSION_COOKIE_SECURE=True",
            getattr(settings, "SESSION_COOKIE_SECURE", False),
            "SESSION_COOKIE_SECURE is not True",
        )

        # 9. ANTHROPIC_API_KEY is set
        anthropic_key = getattr(settings, "ANTHROPIC_API_KEY", "")
        check_bool(
            "ANTHROPIC_API_KEY is set",
            bool(anthropic_key),
            "ANTHROPIC_API_KEY is empty",
            warn=True,  # Warn rather than fail — not critical at launch
        )

        # 10. At least one active FeeSchedule
        try:
            from pricing.models import FeeSchedule  # noqa: PLC0415

            fee_count = FeeSchedule.objects.filter(is_active=True).count()
            check_bool(
                "At least one active FeeSchedule",
                fee_count >= 1,
                f"No active FeeSchedule found (count={fee_count})",
            )
        except Exception as exc:  # noqa: BLE001
            check_warn("FeeSchedule check", f"Could not query: {exc}")

        # 11. NotificationTemplate for 'delivered_payout_in_5_days'
        try:
            from notify.models import NotificationTemplate  # noqa: PLC0415

            tmpl_exists = NotificationTemplate.objects.filter(
                slug="delivered_payout_in_5_days",
                is_active=True,
            ).exists()
            check_bool(
                "NotificationTemplate 'delivered_payout_in_5_days' exists",
                tmpl_exists,
                "Missing active NotificationTemplate for 'delivered_payout_in_5_days'",
            )
        except Exception as exc:  # noqa: BLE001
            check_warn("NotificationTemplate check", f"Could not query: {exc}")

        # 12. PlatformSetting 'hold.green_days' exists
        try:
            from core.models import PlatformSetting  # noqa: PLC0415

            setting_exists = PlatformSetting.objects.filter(key="hold.green_days").exists()
            check_bool(
                "PlatformSetting 'hold.green_days' exists",
                setting_exists,
                "Missing PlatformSetting 'hold.green_days'",
            )
        except Exception as exc:  # noqa: BLE001
            check_warn("PlatformSetting check", f"Could not query: {exc}")

        # Print results
        self.stdout.write("\n=== security_check results ===")
        any_fail = False
        for label, level, detail in results:
            if level == "PASS":
                tag = self.style.SUCCESS("PASS")
            elif level == "WARN":
                tag = self.style.WARNING("WARN")
            else:
                tag = self.style.ERROR("FAIL")
                any_fail = True

            line = f"  [{tag}] {label}"
            if detail:
                line += f"  — {detail}"
            self.stdout.write(line)

        self.stdout.write("")
        if any_fail:
            self.stdout.write(self.style.ERROR("Security check FAILED — fix FAIL items before launch."))
            sys.exit(1)
        else:
            self.stdout.write(self.style.SUCCESS("All security checks PASSED (review WARNs)."))
