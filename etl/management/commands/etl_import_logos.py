"""
Imports 1,027 manufacturer logos from S3.
Usage: python manage.py etl_import_logos --source-bucket bidchip-auction --prefix logos/

Steps:
1. List objects in source S3 bucket under prefix
2. For each logo file: extract manufacturer name from filename
3. Match to Manufacturer by name_normalized (exact, then fuzzy)
4. If matched: copy object to new S3 bucket (settings.AWS_STORAGE_BUCKET_NAME)
   under 'manufacturer_logos/{manufacturer_id}.{ext}'
5. Update Manufacturer.logo = new S3 key
6. Summary: matched, unmatched, copied
"""

import os
import unicodedata

import boto3
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


def normalize_name(value: str) -> str:
    return unicodedata.normalize("NFKC", value or "").strip().lower()


def stem_to_name(stem: str) -> str:
    """Convert filename stem to a candidate manufacturer name for matching."""
    return normalize_name(stem.replace("_", " ").replace("-", " "))


class Command(BaseCommand):
    help = "Import manufacturer logos from S3"

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-bucket",
            default="bidchip-auction",
            help="Source S3 bucket containing logo files",
        )
        parser.add_argument(
            "--prefix",
            default="logos/",
            help="S3 key prefix to list logo objects under",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="List and match without copying or updating DB",
        )

    def handle(self, *args, **options):
        from catalog.models import Manufacturer  # noqa: PLC0415

        source_bucket = options["source_bucket"]
        prefix = options["prefix"]
        dry_run = options["dry_run"]
        dest_bucket = settings.AWS_STORAGE_BUCKET_NAME

        if not dest_bucket:
            raise CommandError("AWS_STORAGE_BUCKET_NAME is not set in settings")

        s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )

        # 1. List source objects
        self.stdout.write(f"Listing s3://{source_bucket}/{prefix} ...")
        paginator = s3.get_paginator("list_objects_v2")
        logo_keys: list[str] = []
        for page in paginator.paginate(Bucket=source_bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):
                    continue
                logo_keys.append(key)

        self.stdout.write(f"  Found {len(logo_keys)} logo files.")

        # Build manufacturer lookup: name_normalized → Manufacturer
        mfr_by_norm: dict[str, object] = {}
        for mfr in Manufacturer.objects.all():
            mfr_by_norm[mfr.name_normalized] = mfr

        matched = 0
        unmatched = 0
        copied = 0
        unmatched_keys: list[str] = []

        for key in logo_keys:
            filename = os.path.basename(key)
            stem, _, ext = filename.rpartition(".")
            ext = ext.lower()

            if not stem:
                unmatched += 1
                unmatched_keys.append(key)
                continue

            # 2 & 3. Extract and match manufacturer name
            candidate = stem_to_name(stem)
            mfr = mfr_by_norm.get(candidate)

            if mfr is None:
                # Fuzzy fallback: check if candidate is contained in any known name
                for norm_name, mfr_obj in mfr_by_norm.items():
                    if candidate in norm_name or norm_name in candidate:
                        mfr = mfr_obj
                        break

            if mfr is None:
                unmatched += 1
                unmatched_keys.append(key)
                continue

            matched += 1
            dest_key = f"manufacturer_logos/{mfr.id}.{ext}"

            # 4. Copy to destination bucket
            if not dry_run:
                try:
                    s3.copy_object(
                        CopySource={"Bucket": source_bucket, "Key": key},
                        Bucket=dest_bucket,
                        Key=dest_key,
                    )
                    copied += 1

                    # 5. Update Manufacturer.logo
                    mfr.logo = dest_key
                    mfr.save(update_fields=["logo"])
                except Exception as exc:  # noqa: BLE001
                    self.stderr.write(f"  Error copying {key}: {exc}")
            else:
                self.stdout.write(f"  [dry-run] Would copy {key} → s3://{dest_bucket}/{dest_key}")
                copied += 1

        # 6. Summary
        self.stdout.write(self.style.SUCCESS("\n=== etl_import_logos summary ==="))
        self.stdout.write(f"  Logo files found : {len(logo_keys)}")
        self.stdout.write(f"  Matched          : {matched}")
        self.stdout.write(f"  Unmatched        : {unmatched}")
        self.stdout.write(f"  Copied           : {copied}")
        if unmatched_keys:
            self.stdout.write("  Unmatched files (first 20):")
            for k in unmatched_keys[:20]:
                self.stdout.write(f"    {k}")
        if dry_run:
            self.stdout.write(self.style.WARNING("  DRY RUN — no data written"))
