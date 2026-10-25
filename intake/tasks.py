"""
Celery tasks for the intake app.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_intake_message(self, intake_message_id: str):
    """
    Processes an intake message through the full AI extraction pipeline.
    Retries with exponential backoff on failure.
    """
    from intake.models import IntakeMessage
    from intake.pipeline import run_extraction

    try:
        intake_message = IntakeMessage.objects.get(pk=intake_message_id)
        run_extraction(intake_message)
    except IntakeMessage.DoesNotExist:
        logger.error(
            "process_intake_message: IntakeMessage %s not found", intake_message_id
        )
        return
    except Exception as exc:
        logger.exception(
            "process_intake_message: failed for %s: %s", intake_message_id, exc
        )
        # Exponential backoff: 2^retry * 60 seconds (60s, 120s, 240s)
        countdown = (2 ** self.request.retries) * 60
        raise self.retry(exc=exc, countdown=countdown)


@shared_task
def process_ses_notification(s3_bucket: str, s3_key: str):
    """
    Triggered by SES → SNS → SQS → Celery when an email arrives at sourcing@bidchip.com.

    Steps:
    1. Download raw email from S3
    2. Parse with Python's email.parser.BytesParser
    3. Extract: from_address, subject, body text, attachments
    4. Check for duplicate (idempotent via raw_s3_key)
    5. Identify sender — reject unknown senders
    6. Create IntakeMessage + IntakeFile rows
    7. Queue process_intake_message task
    """
    import email as email_lib
    import mimetypes
    import os
    import uuid
    from email.parser import BytesParser
    from email.policy import default as email_default_policy

    import boto3
    from django.conf import settings

    from accounts.models import User
    from intake.models import IntakeFile, IntakeMessage

    # Step 1: download raw email from S3
    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
    )
    response = s3.get_object(Bucket=s3_bucket, Key=s3_key)
    raw_bytes = response["Body"].read()

    # Step 2: parse email
    parser = BytesParser(policy=email_default_policy)
    msg = parser.parsebytes(raw_bytes)

    # Step 3: extract fields
    from_header = msg.get("From", "")
    # Parse "Name <email@example.com>" format
    from email.utils import parseaddr

    _, from_address = parseaddr(from_header)
    from_address = from_address.lower().strip()
    subject = msg.get("Subject", "")

    # Step 4: duplicate check
    if IntakeMessage.objects.filter(raw_s3_key=s3_key).exists():
        logger.info(
            "process_ses_notification: duplicate s3_key=%s, skipping", s3_key
        )
        return

    # Step 5: identify sender
    user = User.objects.filter(email__iexact=from_address).first()
    if not user:
        logger.warning(
            "process_ses_notification: unknown sender %s, creating rejected record",
            from_address,
        )
        IntakeMessage.objects.create(
            channel=IntakeMessage.Channel.EMAIL,
            from_email=from_address,
            subject=subject[:500],
            raw_s3_key=s3_key,
            status=IntakeMessage.Status.REJECTED_SENDER,
        )
        # TODO: send SES rejection reply to from_address
        return

    # Resolve company from user memberships
    membership = user.memberships.filter(status="active").select_related("company").first()
    company = membership.company if membership else None

    # Step 6: create IntakeMessage
    intake_message = IntakeMessage.objects.create(
        channel=IntakeMessage.Channel.EMAIL,
        from_email=from_address,
        company=company,
        user=user,
        subject=subject[:500],
        raw_s3_key=s3_key,
        status=IntakeMessage.Status.RECEIVED,
    )

    # Extract body text and attachments
    body_text = ""
    attachments = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if content_type == "text/plain" and "attachment" not in disposition:
                try:
                    body_text += part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                except Exception:
                    pass
            elif "attachment" in disposition or part.get_filename():
                filename = part.get_filename() or f"attachment_{uuid.uuid4().hex[:8]}"
                payload = part.get_payload(decode=True)
                if payload:
                    attachments.append((filename, content_type, payload))
    else:
        try:
            body_text = msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", errors="replace"
            )
        except Exception:
            body_text = ""

    # Upload body text to S3 and create IntakeFile
    if body_text.strip():
        body_s3_key = f"intake/{intake_message.pk}/body_text.txt"
        s3.put_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=body_s3_key,
            Body=body_text.encode("utf-8"),
            ContentType="text/plain",
        )
        IntakeFile.objects.create(
            message=intake_message,
            filename="body_text.txt",
            mime="text/plain",
            s3_key=body_s3_key,
            kind=IntakeFile.Kind.BODY_TEXT,
        )

    # Upload attachments to S3 and create IntakeFile rows
    for filename, mime_type, payload in attachments:
        ext = os.path.splitext(filename)[1].lower().lstrip(".")
        kind = _ext_to_kind(ext)
        if kind is None:
            logger.info(
                "process_ses_notification: skipping unsupported attachment %s", filename
            )
            continue

        attachment_s3_key = f"intake/{intake_message.pk}/{uuid.uuid4().hex[:8]}_{filename}"
        s3.put_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=attachment_s3_key,
            Body=payload,
            ContentType=mime_type or "application/octet-stream",
        )
        IntakeFile.objects.create(
            message=intake_message,
            filename=filename,
            mime=mime_type or "",
            s3_key=attachment_s3_key,
            kind=kind,
        )

    # Step 7: queue processing
    process_intake_message.delay(str(intake_message.pk))
    logger.info(
        "process_ses_notification: queued intake message %s for sender %s",
        intake_message.pk,
        from_address,
    )


def _ext_to_kind(ext: str) -> str | None:
    """Map file extension to IntakeFile.Kind value."""
    from intake.models import IntakeFile

    mapping = {
        "xlsx": IntakeFile.Kind.XLSX,
        "xls": IntakeFile.Kind.XLSX,
        "csv": IntakeFile.Kind.CSV,
        "pdf": IntakeFile.Kind.PDF,
        "jpg": IntakeFile.Kind.IMAGE,
        "jpeg": IntakeFile.Kind.IMAGE,
        "png": IntakeFile.Kind.IMAGE,
        "gif": IntakeFile.Kind.IMAGE,
        "tiff": IntakeFile.Kind.IMAGE,
        "tif": IntakeFile.Kind.IMAGE,
        "docx": IntakeFile.Kind.BODY_TEXT,
        "doc": IntakeFile.Kind.BODY_TEXT,
    }
    return mapping.get(ext.lower())
