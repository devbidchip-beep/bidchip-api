"""
Imports ~590k inventory rows.
Usage: python manage.py etl_import_inventory --file inventory.csv

CSV columns: company_id (maps to Company), mpn, manufacturer_name, quantity,
             date_code_year, packaging, unit_price, ship_from_country

Steps:
1. Load company map (legacy_id → Company UUID)
2. Load part map (mpn_normalized → Part id) — build from DB
3. For each row: resolve company, match part (exact mpn_normalized), create InventoryItem
4. bulk_create in batches of 2000
5. Summary report
"""

import csv
import time
import unicodedata
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

BATCH_SIZE = 2000
TOTAL_EXPECTED = 590_000
PROGRESS_INTERVAL = 10_000


def normalize_mpn(value: str) -> str:
    return unicodedata.normalize("NFKC", value or "").strip().upper()


class Command(BaseCommand):
    help = "Import ~590k inventory rows from a CSV dump"

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to inventory CSV file")
        parser.add_argument(
            "--batch-size",
            type=int,
            default=BATCH_SIZE,
            help="Bulk create batch size (default: 2000)",
        )

    def handle(self, *args, **options):
        from accounts.models import Company  # noqa: PLC0415
        from catalog.models import Part  # noqa: PLC0415
        from listings.models import InventoryItem  # noqa: PLC0415

        filepath = options["file"]
        batch_size = options["batch_size"]
        start = time.time()

        # 1. Load company map: legacy_id → Company UUID
        self.stdout.write("Building company map...")
        company_map: dict[str, object] = {}
        for company in Company.objects.all():
            legacy_id = getattr(company, "legacy_id", None) or str(company.id)
            company_map[str(legacy_id)] = company
        self.stdout.write(f"  {len(company_map)} companies loaded.")

        # 2. Load part map: mpn_normalized → Part pk
        self.stdout.write("Building part map (this may take a moment for 6.6M parts)...")
        part_map: dict[str, int] = {}
        for pk, mpn_norm in Part.objects.values_list("id", "mpn_normalized").iterator(chunk_size=50_000):
            part_map[mpn_norm] = pk
        self.stdout.write(f"  {len(part_map):,} parts loaded into map.")

        try:
            csv_file = open(filepath, newline="", encoding="utf-8-sig")  # noqa: WPS515
        except OSError as exc:
            raise CommandError(f"Cannot open file: {exc}") from exc

        total_created = 0
        total_skipped = 0
        total_failed = 0
        row_number = 0
        batch: list[InventoryItem] = []

        def flush_batch():
            nonlocal total_created
            if not batch:
                return
            created = InventoryItem.objects.bulk_create(
                batch,
                ignore_conflicts=True,
                batch_size=batch_size,
            )
            total_created += len(created)
            batch.clear()

        with csv_file:
            reader = csv.DictReader(csv_file)

            for row in reader:
                row_number += 1

                company_legacy_id = row.get("company_id", "").strip()
                mpn_raw = row.get("mpn", "").strip()

                # Resolve company
                company = company_map.get(company_legacy_id)
                if not company:
                    total_skipped += 1
                    if row_number <= 20:
                        self.stderr.write(
                            f"Row {row_number}: unknown company_id '{company_legacy_id}' — skipped"
                        )
                    continue

                # Resolve part
                mpn_norm = normalize_mpn(mpn_raw)
                part_id = part_map.get(mpn_norm)
                if not part_id:
                    total_skipped += 1
                    continue

                # Parse numeric fields
                try:
                    quantity = int(row.get("quantity", "0").strip() or "0")
                except (ValueError, AttributeError):
                    quantity = 0

                try:
                    unit_price = Decimal(row.get("unit_price", "0").strip() or "0")
                except InvalidOperation:
                    unit_price = Decimal("0")

                try:
                    date_code_year = int(row.get("date_code_year", "").strip() or "0") or None
                except (ValueError, AttributeError):
                    date_code_year = None

                # 3. Build InventoryItem
                try:
                    batch.append(
                        InventoryItem(
                            company=company,
                            part_id=part_id,
                            quantity=quantity,
                            date_code_year=date_code_year,
                            packaging=row.get("packaging", "").strip()[:50],
                            unit_price=unit_price,
                            ship_from_country=row.get("ship_from_country", "").strip()[:2].upper(),
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    self.stderr.write(f"Row {row_number}: build error — {exc}")
                    total_failed += 1
                    continue

                # 4. Flush full batch
                if len(batch) >= batch_size:
                    with transaction.atomic():
                        flush_batch()

                if row_number % PROGRESS_INTERVAL == 0:
                    elapsed = time.time() - start
                    self.stdout.write(
                        f"Processed {row_number:,}/{TOTAL_EXPECTED:,} rows... ({elapsed:.0f}s)"
                    )

            # Flush remainder
            with transaction.atomic():
                flush_batch()

        elapsed = time.time() - start

        # 5. Summary
        self.stdout.write(self.style.SUCCESS("\n=== etl_import_inventory summary ==="))
        self.stdout.write(f"  Rows processed   : {row_number:,}")
        self.stdout.write(f"  Items created    : {total_created:,}")
        self.stdout.write(f"  Rows skipped     : {total_skipped:,} (no company/part match)")
        self.stdout.write(f"  Rows failed      : {total_failed:,}")
        self.stdout.write(f"  Elapsed          : {elapsed:.1f}s")
