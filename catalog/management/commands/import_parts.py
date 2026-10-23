"""
Management command to bulk-import parts from a CSV file.

Usage:
    python manage.py import_parts --file parts.csv --batch-size 1000

CSV columns: mpn,manufacturer_name,description,category,lifecycle,eccn,is_itar,hts_code
"""

import csv

from django.core.management.base import BaseCommand, CommandError

from catalog.models import Manufacturer, Part
from catalog.utils import normalize_mpn, normalize_name


class Command(BaseCommand):
    help = "Bulk-import parts from a CSV file"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            required=True,
            help="Path to the CSV file to import",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Number of records to bulk-create per batch (default: 1000)",
        )

    def handle(self, *args, **options):
        file_path = options["file"]
        batch_size = options["batch_size"]

        try:
            f = open(file_path, newline="", encoding="utf-8-sig")
        except FileNotFoundError:
            raise CommandError(f"File not found: {file_path}")

        with f:
            reader = csv.DictReader(f)
            batch = []
            total = 0
            created = 0

            # Cache manufacturers to avoid repeated DB hits
            manufacturer_cache: dict[str, Manufacturer] = {}

            for row in reader:
                total += 1

                mpn = (row.get("mpn") or "").strip()
                manufacturer_name = (row.get("manufacturer_name") or "").strip()
                description = (row.get("description") or "").strip()
                category = (row.get("category") or "").strip()
                lifecycle = (row.get("lifecycle") or "").strip() or None
                eccn = (row.get("eccn") or "").strip() or None
                is_itar_raw = (row.get("is_itar") or "").strip().lower()
                is_itar = is_itar_raw in ("1", "true", "yes")
                hts_code = (row.get("hts_code") or "").strip() or None

                if not mpn or not manufacturer_name:
                    continue

                mpn_normalized = normalize_mpn(mpn)
                name_normalized = normalize_name(manufacturer_name)

                # Get or create Manufacturer (by name_normalized)
                if name_normalized not in manufacturer_cache:
                    mfr, _ = Manufacturer.objects.get_or_create(
                        name_normalized=name_normalized,
                        defaults={"name": manufacturer_name},
                    )
                    manufacturer_cache[name_normalized] = mfr
                else:
                    mfr = manufacturer_cache[name_normalized]

                # Validate lifecycle value
                valid_lifecycles = {c[0] for c in Part.Lifecycle.choices}
                if lifecycle and lifecycle not in valid_lifecycles:
                    lifecycle = None

                batch.append(
                    Part(
                        mpn=mpn,
                        mpn_normalized=mpn_normalized,
                        manufacturer=mfr,
                        description=description,
                        category=category,
                        lifecycle=lifecycle,
                        eccn=eccn,
                        is_itar=is_itar,
                        hts_code=hts_code,
                    )
                )

                if len(batch) >= batch_size:
                    result = Part.objects.bulk_create(batch, ignore_conflicts=True)
                    created += len(result)
                    batch = []

                if total % 10_000 == 0:
                    self.stdout.write(f"  Processed {total:,} rows...")

            # Flush remaining batch
            if batch:
                result = Part.objects.bulk_create(batch, ignore_conflicts=True)
                created += len(result)

        self.stdout.write(
            self.style.SUCCESS(
                f"Import complete: {total:,} rows processed, {created:,} parts created."
            )
        )
