"""
Celery tasks for the catalog app.
"""

import io
import logging
import uuid

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

# Redis key prefix for deduplication: "bid_match:{listing_id}:{company_id}"
BID_MATCH_REDIS_KEY_PREFIX = "bid_match"
BID_MATCH_TTL = 86400 * 7  # 7 days


@shared_task
def match_new_listings_to_inventory():
    """
    Runs every 2 minutes via Celery Beat.
    Finds newly published listings (published_at > now() - 3 minutes).
    For each listing line with a matched Part:
      Finds InventoryItem rows where part=line.part AND is_active=True
        AND company != listing.buyer_company
      For each unique company with matching inventory:
        Sends 'new_listing_match' notification to company members with role=seller
        (deduplicated via Redis key per (listing_id, company_id))
    """
    from accounts.models import CompanyMember
    from catalog.models import InventoryItem
    from django.core.cache import cache
    from listings.models import Listing
    from notify.service import notify

    now = timezone.now()
    cutoff = now - timezone.timedelta(minutes=3)

    recent_listings = Listing.objects.filter(
        status=Listing.Status.PUBLISHED,
        published_at__gte=cutoff,
    ).prefetch_related("lines")

    if not recent_listings.exists():
        return

    # Check Redis availability for dedup
    try:
        cache.get("__ping__")
        redis_available = True
    except Exception:
        redis_available = False
        logger.warning("match_new_listings_to_inventory: cache unavailable, dedup skipped")

    for listing in recent_listings:
        notified_companies = set()

        for line in listing.lines.select_related("part").filter(part__isnull=False):
            # Find matching inventory at other companies
            matching_items = InventoryItem.objects.filter(
                part=line.part,
                is_active=True,
            ).exclude(
                company=listing.buyer_company
            ).values_list("company_id", flat=True).distinct()

            for company_id in matching_items:
                if company_id in notified_companies:
                    continue

                # Dedup via Redis
                redis_key = f"{BID_MATCH_REDIS_KEY_PREFIX}:{listing.pk}:{company_id}"
                if redis_available:
                    if cache.get(redis_key):
                        logger.debug(
                            "match_new_listings_to_inventory: already notified company %s for listing %s",
                            company_id,
                            listing.pk,
                        )
                        continue
                    cache.set(redis_key, "1", timeout=BID_MATCH_TTL)

                notified_companies.add(company_id)

                # Notify seller members of the company
                seller_members = CompanyMember.objects.filter(
                    company_id=company_id,
                    role=CompanyMember.Role.SELLER,
                    status="active",
                ).select_related("user")

                for member in seller_members:
                    try:
                        notify(
                            member.user,
                            "new_listing_match",
                            {
                                "listing_number": listing.number,
                                "listing_id": str(listing.pk),
                                "part_mpn": line.part.mpn if line.part else "",
                            },
                        )
                    except Exception as exc:
                        logger.warning(
                            "match_new_listings_to_inventory: notify failed for user %s: %s",
                            member.user.pk,
                            exc,
                        )

    logger.info(
        "match_new_listings_to_inventory: processed %d recent listings",
        recent_listings.count(),
    )


@shared_task
def process_inventory_import(import_id: str):
    """
    Processes a CSV inventory import job.
    CSV columns (flexible, tries to match): mpn, manufacturer, quantity,
    date_code_year, packaging, unit_price, ship_from_country.

    Steps:
    1. Download CSV from S3
    2. Parse with pandas, map columns case-insensitively
    3. For each row: normalize MPN, try to match Part, create/update InventoryItem
    4. Update InventoryImport.rows_ok / rows_failed / status
    5. Generate error report CSV for failed rows, upload to S3
    """
    import boto3
    import pandas as pd
    from django.conf import settings

    from catalog.models import InventoryImport, InventoryItem, Manufacturer, Part
    from catalog.utils import normalize_mpn, normalize_name

    try:
        import_job = InventoryImport.objects.get(pk=import_id)
    except InventoryImport.DoesNotExist:
        logger.error("process_inventory_import: InventoryImport %s not found", import_id)
        return

    import_job.status = InventoryImport.Status.PROCESSING
    import_job.save(update_fields=["status", "updated_at"])

    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
    )

    try:
        response = s3.get_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=import_job.file)
        csv_bytes = response["Body"].read()
    except Exception as exc:
        logger.exception("process_inventory_import: S3 download failed: %s", exc)
        import_job.status = InventoryImport.Status.FAILED
        import_job.save(update_fields=["status", "updated_at"])
        return

    try:
        df = pd.read_csv(io.BytesIO(csv_bytes), dtype=str)
    except Exception as exc:
        logger.exception("process_inventory_import: CSV parse failed: %s", exc)
        import_job.status = InventoryImport.Status.FAILED
        import_job.save(update_fields=["status", "updated_at"])
        return

    # Normalize column names: lowercase, strip
    df.columns = [c.strip().lower() for c in df.columns]

    # Column aliases for flexible matching
    col_map = {
        "mpn": ["mpn", "part_number", "part number", "mfr_pn", "mfr pn"],
        "manufacturer": ["manufacturer", "mfr", "brand", "make"],
        "quantity": ["quantity", "qty", "stock", "on_hand", "on hand"],
        "date_code_year": ["date_code_year", "date code year", "dc_year", "dc year", "datecode"],
        "packaging": ["packaging", "package", "pkg"],
        "unit_price": ["unit_price", "unit price", "price", "cost"],
        "ship_from_country": ["ship_from_country", "ship from country", "country", "origin"],
    }

    def find_col(aliases):
        for alias in aliases:
            if alias in df.columns:
                return alias
        return None

    col_mpn = find_col(col_map["mpn"])
    col_mfr = find_col(col_map["manufacturer"])
    col_qty = find_col(col_map["quantity"])
    col_dc = find_col(col_map["date_code_year"])
    col_pkg = find_col(col_map["packaging"])
    col_price = find_col(col_map["unit_price"])
    col_country = find_col(col_map["ship_from_country"])

    if not col_mpn or not col_qty:
        logger.error(
            "process_inventory_import: required columns mpn/quantity not found in %s",
            import_id,
        )
        import_job.status = InventoryImport.Status.FAILED
        import_job.save(update_fields=["status", "updated_at"])
        return

    rows_ok = 0
    rows_failed = 0
    failed_rows = []

    df = df.fillna("")
    import_job.rows_total = len(df)
    import_job.save(update_fields=["rows_total", "updated_at"])

    valid_packaging = {c.value for c in InventoryItem.Packaging}

    for idx, row in df.iterrows():
        try:
            mpn_raw = str(row[col_mpn]).strip()
            if not mpn_raw:
                raise ValueError("MPN is empty")

            qty_raw = str(row[col_qty]).strip()
            quantity = int(float(qty_raw))
            if quantity < 0:
                raise ValueError(f"Negative quantity: {quantity}")

            manufacturer_raw = str(row[col_mfr]).strip() if col_mfr else ""
            date_code_year = None
            if col_dc and row[col_dc]:
                try:
                    date_code_year = int(float(str(row[col_dc]).strip()))
                except (ValueError, TypeError):
                    pass

            packaging_raw = str(row[col_pkg]).strip().lower() if col_pkg else ""
            packaging = packaging_raw if packaging_raw in valid_packaging else ""

            unit_price = None
            if col_price and row[col_price]:
                try:
                    unit_price = float(str(row[col_price]).replace("$", "").replace(",", "").strip())
                except (ValueError, TypeError):
                    pass

            ship_from_country = (
                str(row[col_country]).strip().upper()[:2] if col_country and row[col_country]
                else ""
            )

            # Normalize MPN and try to match catalog Part
            normalized_mpn = normalize_mpn(mpn_raw)
            part = Part.objects.filter(mpn_normalized=normalized_mpn).first()

            # Resolve manufacturer
            manufacturer = None
            if part:
                manufacturer = part.manufacturer
            elif manufacturer_raw:
                from catalog.models import ManufacturerAlias

                normalized_mfr = normalize_name(manufacturer_raw)
                alias = ManufacturerAlias.objects.filter(
                    alias_normalized=normalized_mfr
                ).select_related("manufacturer").first()
                if alias:
                    manufacturer = alias.manufacturer
                else:
                    manufacturer = Manufacturer.objects.filter(
                        name_normalized=normalized_mfr
                    ).first()

            InventoryItem.objects.update_or_create(
                company=import_job.company,
                mpn_raw=mpn_raw,
                manufacturer_raw=manufacturer_raw,
                import_job=import_job,
                defaults={
                    "part": part,
                    "manufacturer": manufacturer,
                    "quantity": quantity,
                    "date_code_year": date_code_year,
                    "packaging": packaging,
                    "unit_price": unit_price,
                    "ship_from_country": ship_from_country,
                    "source": InventoryItem.Source.CSV,
                    "is_active": True,
                },
            )
            rows_ok += 1

        except Exception as exc:
            rows_failed += 1
            failed_rows.append({**dict(row), "_error": str(exc)})
            logger.debug(
                "process_inventory_import: row %d failed: %s", idx, exc
            )

    # Update job counts
    import_job.rows_ok = rows_ok
    import_job.rows_failed = rows_failed
    import_job.status = InventoryImport.Status.DONE
    import_job.save(update_fields=["rows_ok", "rows_failed", "status", "updated_at"])

    # Upload error report if any failures
    if failed_rows:
        try:
            error_df = pd.DataFrame(failed_rows)
            error_csv = error_df.to_csv(index=False).encode("utf-8")
            error_key = f"inventory_imports/{import_id}/errors_{uuid.uuid4().hex[:8]}.csv"
            s3.put_object(
                Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                Key=error_key,
                Body=error_csv,
                ContentType="text/csv",
            )
            import_job.error_report = error_key
            import_job.save(update_fields=["error_report", "updated_at"])
        except Exception as exc:
            logger.warning(
                "process_inventory_import: failed to upload error report: %s", exc
            )

    logger.info(
        "process_inventory_import: %s done — ok=%d failed=%d",
        import_id,
        rows_ok,
        rows_failed,
    )
