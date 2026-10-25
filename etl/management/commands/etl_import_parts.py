"""
Bulk-imports the 6.6M part numbers from a CSV dump.
Usage: python manage.py etl_import_parts --file parts.csv [--batch-size 5000]

CSV columns: mpn, manufacturer_name, description, category, lifecycle, eccn, is_itar, hts_code

Steps:
1. Pre-load manufacturer cache (name_normalized → Manufacturer id)
2. Read CSV in chunks of batch_size
3. Normalize MPN and manufacturer name
4. get_or_create Manufacturer (batch cache updates)
5. Part.objects.bulk_create(parts_batch, ignore_conflicts=True, batch_size=batch_size)
6. Progress every 50k rows: "Imported X/6,600,000 parts..."
7. Final summary: total created, skipped (duplicates), time elapsed

Uses Django's database connection directly for performance.
Disable auto-commit during bulk operations for speed.
"""

import csv
import time
import unicodedata

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


TOTAL_EXPECTED = 6_600_000
PROGRESS_INTERVAL = 50_000


def normalize_mpn(value: str) -> str:
    return unicodedata.normalize("NFKC", value or "").strip().upper()


def normalize_name(value: str) -> str:
    return unicodedata.normalize("NFKC", value or "").strip().lower()


class Command(BaseCommand):
    help = "Bulk-import 6.6M part numbers from a CSV dump"

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to parts CSV file")
        parser.add_argument(
            "--batch-size",
            type=int,
            default=5000,
            help="Number of rows per bulk_create batch (default: 5000)",
        )

    def handle(self, *args, **options):
        from catalog.models import Manufacturer, Part  # noqa: PLC0415

        filepath = options["file"]
        batch_size = options["batch_size"]

        start = time.time()
        total_created = 0
        total_skipped = 0
        row_number = 0

        # 1. Pre-load manufacturer cache
        self.stdout.write("Loading manufacturer cache...")
        mfr_cache: dict[str, int] = {}
        for mfr_id, name_norm in Manufacturer.objects.values_list("id", "name_normalized"):
            mfr_cache[name_norm] = mfr_id

        self.stdout.write(f"  {len(mfr_cache)} manufacturers cached.")

        try:
            csv_file = open(filepath, newline="", encoding="utf-8-sig")  # noqa: WPS515
        except OSError as exc:
            raise CommandError(f"Cannot open file: {exc}") from exc

        parts_batch: list[Part] = []

        def flush_batch():
            nonlocal total_created, total_skipped
            if not parts_batch:
                return
            created_objs = Part.objects.bulk_create(
                parts_batch,
                ignore_conflicts=True,
                batch_size=batch_size,
            )
            total_created += len(created_objs)
            total_skipped += len(parts_batch) - len(created_objs)
            parts_batch.clear()

        with csv_file:
            reader = csv.DictReader(csv_file)

            # Disable autocommit for speed — commit per batch
            with connection.cursor() as cursor:
                cursor.execute("SET SESSION synchronous_commit = OFF;")

            for row in reader:
                row_number += 1

                mpn_raw = row.get("mpn", "").strip()
                mfr_name_raw = row.get("manufacturer_name", "").strip()

                if not mpn_raw:
                    total_skipped += 1
                    continue

                mpn_norm = normalize_mpn(mpn_raw)
                mfr_norm = normalize_name(mfr_name_raw)

                # 4. get_or_create Manufacturer with cache
                if mfr_norm and mfr_norm not in mfr_cache:
                    mfr_obj, _ = Manufacturer.objects.get_or_create(
                        name_normalized=mfr_norm,
                        defaults={"name": mfr_name_raw},
                    )
                    mfr_cache[mfr_norm] = mfr_obj.id

                manufacturer_id = mfr_cache.get(mfr_norm) if mfr_norm else None

                # 3. Build Part instance (not saved yet)
                is_itar_raw = row.get("is_itar", "").strip().lower()
                parts_batch.append(
                    Part(
                        mpn=mpn_raw,
                        mpn_normalized=mpn_norm,
                        manufacturer_id=manufacturer_id,
                        description=row.get("description", "").strip()[:500],
                        category=row.get("category", "").strip()[:100],
                        lifecycle=row.get("lifecycle", "").strip()[:50],
                        eccn=row.get("eccn", "").strip()[:20],
                        is_itar=is_itar_raw in ("1", "true", "yes"),
                        hts_code=row.get("hts_code", "").strip()[:20],
                    )
                )

                # 5. Flush when batch is full
                if len(parts_batch) >= batch_size:
                    with transaction.atomic():
                        flush_batch()

                # 6. Progress every 50k rows
                if row_number % PROGRESS_INTERVAL == 0:
                    elapsed = time.time() - start
                    self.stdout.write(
                        f"Imported {row_number:,}/{TOTAL_EXPECTED:,} parts... "
                        f"({elapsed:.0f}s elapsed)"
                    )

            # Flush remaining
            with transaction.atomic():
                flush_batch()

        elapsed = time.time() - start

        # 7. Final summary
        self.stdout.write(self.style.SUCCESS("\n=== etl_import_parts summary ==="))
        self.stdout.write(f"  Rows processed : {row_number:,}")
        self.stdout.write(f"  Parts created  : {total_created:,}")
        self.stdout.write(f"  Parts skipped  : {total_skipped:,} (duplicates/blank MPN)")
        self.stdout.write(f"  Manufacturers  : {len(mfr_cache):,} cached")
        self.stdout.write(f"  Elapsed        : {elapsed:.1f}s")
        rate = row_number / elapsed if elapsed else 0
        self.stdout.write(f"  Rate           : {rate:,.0f} rows/s")
