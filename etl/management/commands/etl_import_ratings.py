"""
Imports 1,086 legacy ratings.
Usage: python manage.py etl_import_ratings --file ratings.csv

CSV columns: rater_company_id, ratee_company_id, direction,
             quality, communication, shipping, documentation, comment, created_at

Steps:
1. Map company IDs to Company UUIDs
2. Create Rating(supplier_order=None, legacy_ref=f'legacy-{row_id}', ...)
3. Skip rows with invalid scores (not 1-5) — log them
4. Summary
"""

import csv
import time
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone


VALID_SCORES = {1, 2, 3, 4, 5}
SCORE_FIELDS = ("quality", "communication", "shipping", "documentation")


class Command(BaseCommand):
    help = "Import legacy ratings from a CSV dump"

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to ratings CSV file")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Validate without writing to DB",
        )

    def handle(self, *args, **options):
        from accounts.models import Company  # noqa: PLC0415
        from trust.models import Rating  # noqa: PLC0415

        filepath = options["file"]
        dry_run = options["dry_run"]
        start = time.time()

        # 1. Build company map: legacy_id → Company
        self.stdout.write("Building company map...")
        company_map: dict[str, object] = {}
        for company in Company.objects.all():
            legacy_id = getattr(company, "legacy_id", None)
            if legacy_id:
                company_map[str(legacy_id)] = company
            company_map[str(company.id)] = company
        self.stdout.write(f"  {len(company_map)} company entries cached.")

        try:
            csv_file = open(filepath, newline="", encoding="utf-8-sig")  # noqa: WPS515
        except OSError as exc:
            raise CommandError(f"Cannot open file: {exc}") from exc

        created = 0
        skipped_invalid = 0
        skipped_company = 0
        failed = 0
        row_number = 0

        with csv_file:
            reader = csv.DictReader(csv_file)

            for row in reader:
                row_number += 1

                rater_id = row.get("rater_company_id", "").strip()
                ratee_id = row.get("ratee_company_id", "").strip()

                rater = company_map.get(rater_id)
                ratee = company_map.get(ratee_id)

                if not rater or not ratee:
                    skipped_company += 1
                    self.stderr.write(
                        f"Row {row_number}: unknown company — rater='{rater_id}' ratee='{ratee_id}' — skipped"
                    )
                    continue

                # 3. Validate scores
                scores: dict[str, int] = {}
                score_invalid = False
                for field in SCORE_FIELDS:
                    raw = row.get(field, "").strip()
                    try:
                        val = int(raw)
                    except (ValueError, TypeError):
                        val = 0
                    if val not in VALID_SCORES:
                        self.stderr.write(
                            f"Row {row_number}: invalid {field}='{raw}' (must be 1-5) — skipped"
                        )
                        score_invalid = True
                        break
                    scores[field] = val

                if score_invalid:
                    skipped_invalid += 1
                    continue

                # Parse created_at
                created_at_raw = row.get("created_at", "").strip()
                created_at = timezone.now()
                if created_at_raw:
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                        try:
                            created_at = timezone.make_aware(
                                datetime.strptime(created_at_raw, fmt)
                            )
                            break
                        except ValueError:
                            continue

                legacy_ref = f"legacy-{row_number}"

                # 2. Create Rating
                try:
                    if not dry_run:
                        with transaction.atomic():
                            Rating.objects.get_or_create(
                                legacy_ref=legacy_ref,
                                defaults={
                                    "supplier_order": None,
                                    "rater_company": rater,
                                    "ratee_company": ratee,
                                    "direction": row.get("direction", "").strip()[:20],
                                    "quality": scores["quality"],
                                    "communication": scores["communication"],
                                    "shipping": scores["shipping"],
                                    "documentation": scores["documentation"],
                                    "comment": row.get("comment", "").strip(),
                                    "created_at": created_at,
                                },
                            )
                    created += 1
                except Exception as exc:  # noqa: BLE001
                    self.stderr.write(f"Row {row_number}: DB error — {exc}")
                    failed += 1

        elapsed = time.time() - start

        # 4. Summary
        self.stdout.write(self.style.SUCCESS("\n=== etl_import_ratings summary ==="))
        self.stdout.write(f"  Rows processed       : {row_number}")
        self.stdout.write(f"  Ratings created      : {created}")
        self.stdout.write(f"  Skipped (bad scores) : {skipped_invalid}")
        self.stdout.write(f"  Skipped (no company) : {skipped_company}")
        self.stdout.write(f"  Failed (DB error)    : {failed}")
        self.stdout.write(f"  Elapsed              : {elapsed:.1f}s")
        if dry_run:
            self.stdout.write(self.style.WARNING("  DRY RUN — no data written"))
