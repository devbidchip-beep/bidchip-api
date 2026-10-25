"""
Imports companies and users from a WordPress/MariaDB CSV dump.
Usage: python manage.py etl_import_companies --file companies.csv

Expected CSV columns (flexible mapping):
  company_id, legal_name, display_name, country, tax_id, website,
  is_buyer, is_supplier, email, full_name, role, phone

Steps:
1. For each row: get_or_create Company by legal_name (normalized)
2. Create User (email, full_name, phone)
   - Set unusable password (user resets on first login)
   - is_active=True
3. Create CompanyMember(user, company, role='owner')
4. Set company.status = 'pending_review' (must re-verify)
5. Print progress every 100 rows
6. At end: print summary (created/skipped/failed)
"""

import csv
import time
import unicodedata

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

User = get_user_model()


def normalize_name(value: str) -> str:
    """Lowercase, strip whitespace, normalize unicode."""
    return unicodedata.normalize("NFKC", value or "").strip().lower()


class Command(BaseCommand):
    help = "Import companies and users from a CSV dump"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            required=True,
            help="Path to the companies CSV file",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Parse and validate without writing to the database",
        )

    def handle(self, *args, **options):
        from accounts.models import Company, CompanyMember  # noqa: PLC0415

        filepath = options["file"]
        dry_run = options["dry_run"]

        created_companies = 0
        skipped_companies = 0
        created_users = 0
        skipped_users = 0
        failed = 0
        row_number = 0

        start = time.time()

        try:
            csv_file = open(filepath, newline="", encoding="utf-8-sig")  # noqa: WPS515
        except OSError as exc:
            raise CommandError(f"Cannot open file: {exc}") from exc

        with csv_file:
            reader = csv.DictReader(csv_file)

            for row in reader:
                row_number += 1

                try:
                    with transaction.atomic():
                        legal_name = row.get("legal_name", "").strip()
                        if not legal_name:
                            self.stderr.write(f"Row {row_number}: missing legal_name — skipped")
                            failed += 1
                            continue

                        # 1. get_or_create Company by normalized legal_name
                        name_norm = normalize_name(legal_name)
                        company, company_created = Company.objects.get_or_create(
                            legal_name__iexact=legal_name,
                            defaults={
                                "legal_name": legal_name,
                                "display_name": row.get("display_name", "").strip() or legal_name,
                                "country": row.get("country", "").strip()[:2].upper(),
                                "tax_id": row.get("tax_id", "").strip(),
                                "website": row.get("website", "").strip(),
                                "is_buyer": row.get("is_buyer", "").strip().lower() in ("1", "true", "yes"),
                                "is_supplier": row.get("is_supplier", "").strip().lower() in ("1", "true", "yes"),
                                "status": "pending_review",
                            },
                        )

                        if company_created:
                            created_companies += 1
                        else:
                            # 4. Ensure status is pending_review on existing companies too
                            if company.status != "pending_review":
                                if not dry_run:
                                    company.status = "pending_review"
                                    company.save(update_fields=["status"])
                            skipped_companies += 1

                        # 2. Create User
                        email = row.get("email", "").strip().lower()
                        if not email:
                            self.stderr.write(f"Row {row_number}: missing email — skipping user creation")
                            failed += 1
                            continue

                        full_name = row.get("full_name", "").strip()
                        phone = row.get("phone", "").strip()
                        role = row.get("role", "owner").strip() or "owner"

                        user, user_created = User.objects.get_or_create(
                            email=email,
                            defaults={
                                "full_name": full_name,
                                "phone": phone,
                                "is_active": True,
                            },
                        )

                        if user_created:
                            # Set unusable password — user resets on first login
                            user.set_unusable_password()
                            if not dry_run:
                                user.save(update_fields=["password"])
                            created_users += 1
                        else:
                            skipped_users += 1

                        # 3. Create CompanyMember
                        if not dry_run:
                            CompanyMember.objects.get_or_create(
                                user=user,
                                company=company,
                                defaults={"role": role},
                            )

                        if dry_run:
                            # Roll back if dry run
                            raise transaction.TransactionManagementError("dry-run rollback")

                except transaction.TransactionManagementError:
                    pass  # expected during dry run
                except Exception as exc:  # noqa: BLE001
                    self.stderr.write(f"Row {row_number}: ERROR — {exc}")
                    failed += 1

                # 5. Progress every 100 rows
                if row_number % 100 == 0:
                    self.stdout.write(f"Processed {row_number} rows...")

        elapsed = time.time() - start

        # 6. Summary
        self.stdout.write(self.style.SUCCESS("\n=== etl_import_companies summary ==="))
        self.stdout.write(f"  Rows processed : {row_number}")
        self.stdout.write(f"  Companies created : {created_companies}")
        self.stdout.write(f"  Companies skipped : {skipped_companies}")
        self.stdout.write(f"  Users created  : {created_users}")
        self.stdout.write(f"  Users skipped  : {skipped_users}")
        self.stdout.write(f"  Failed rows    : {failed}")
        self.stdout.write(f"  Elapsed        : {elapsed:.1f}s")
        if dry_run:
            self.stdout.write(self.style.WARNING("  DRY RUN — no data written"))
