"""
Post-migration verification checks.
Usage: python manage.py etl_verify_migration

Checks:
1. Company count vs expected (~60)
2. User count vs expected (~60)
3. Part count vs expected (~6.6M, allow ±5%)
4. InventoryItem count vs expected (~590k, allow ±5%)
5. Rating count vs expected (~1086)
6. Manufacturer logo coverage (% of manufacturers with logos)
7. No User with a usable password (all should be set_unusable)
8. All Companies have status=pending_review
9. Print PASS/FAIL for each check
10. Exit code 1 if any check fails (for CI)
"""

import sys

from django.core.management.base import BaseCommand


EXPECTED_COMPANIES = 60
EXPECTED_USERS = 60
EXPECTED_PARTS = 6_600_000
EXPECTED_INVENTORY = 590_000
EXPECTED_RATINGS = 1_086
TOLERANCE = 0.05  # ±5%


def within_tolerance(actual: int, expected: int, tol: float = TOLERANCE) -> bool:
    if expected == 0:
        return actual == 0
    return abs(actual - expected) / expected <= tol


class Command(BaseCommand):
    help = "Run post-migration verification checks"

    def handle(self, *args, **options):
        from accounts.models import Company  # noqa: PLC0415
        from catalog.models import Manufacturer, Part  # noqa: PLC0415
        from listings.models import InventoryItem  # noqa: PLC0415
        from trust.models import Rating  # noqa: PLC0415

        try:
            from django.contrib.auth import get_user_model  # noqa: PLC0415
            User = get_user_model()
        except Exception:  # noqa: BLE001
            User = None

        results: list[tuple[str, bool, str]] = []  # (label, passed, detail)

        def check(label: str, passed: bool, detail: str = ""):
            results.append((label, passed, detail))

        # 1. Company count
        company_count = Company.objects.count()
        check(
            "Company count (~60)",
            within_tolerance(company_count, EXPECTED_COMPANIES),
            f"actual={company_count}, expected≈{EXPECTED_COMPANIES}",
        )

        # 2. User count
        if User:
            user_count = User.objects.count()
            check(
                "User count (~60)",
                within_tolerance(user_count, EXPECTED_USERS),
                f"actual={user_count}, expected≈{EXPECTED_USERS}",
            )
        else:
            check("User count (~60)", False, "Could not import User model")

        # 3. Part count
        part_count = Part.objects.count()
        check(
            "Part count (~6.6M, ±5%)",
            within_tolerance(part_count, EXPECTED_PARTS),
            f"actual={part_count:,}, expected≈{EXPECTED_PARTS:,}",
        )

        # 4. InventoryItem count
        inventory_count = InventoryItem.objects.count()
        check(
            "InventoryItem count (~590k, ±5%)",
            within_tolerance(inventory_count, EXPECTED_INVENTORY),
            f"actual={inventory_count:,}, expected≈{EXPECTED_INVENTORY:,}",
        )

        # 5. Rating count
        rating_count = Rating.objects.count()
        check(
            "Rating count (~1086)",
            rating_count >= EXPECTED_RATINGS,
            f"actual={rating_count}, expected≥{EXPECTED_RATINGS}",
        )

        # 6. Manufacturer logo coverage
        total_mfr = Manufacturer.objects.count()
        mfr_with_logo = Manufacturer.objects.exclude(logo="").exclude(logo__isnull=True).count()
        logo_pct = (mfr_with_logo / total_mfr * 100) if total_mfr else 0
        check(
            "Manufacturer logo coverage (>50%)",
            logo_pct >= 50.0,
            f"{mfr_with_logo}/{total_mfr} ({logo_pct:.1f}%)",
        )

        # 7. No User with usable password
        if User:
            users_with_password = 0
            for user in User.objects.all().iterator(chunk_size=1000):
                if user.has_usable_password():
                    users_with_password += 1
            check(
                "No users with usable passwords",
                users_with_password == 0,
                f"{users_with_password} users have usable passwords",
            )
        else:
            check("No users with usable passwords", False, "Could not import User model")

        # 8. All Companies have status=pending_review
        non_pending = Company.objects.exclude(status="pending_review").count()
        check(
            "All Companies are pending_review",
            non_pending == 0,
            f"{non_pending} companies with non-pending_review status",
        )

        # 9. Print results
        self.stdout.write("\n=== etl_verify_migration results ===")
        any_failed = False
        for label, passed, detail in results:
            tag = self.style.SUCCESS("PASS") if passed else self.style.ERROR("FAIL")
            line = f"  [{tag}] {label}"
            if detail:
                line += f"  — {detail}"
            self.stdout.write(line)
            if not passed:
                any_failed = True

        self.stdout.write("")
        if any_failed:
            self.stdout.write(self.style.ERROR("One or more checks FAILED."))
            # 10. Exit code 1
            sys.exit(1)
        else:
            self.stdout.write(self.style.SUCCESS("All checks PASSED."))
