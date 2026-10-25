"""
Views for the intake app.
"""

import logging
import os
import uuid

import boto3
from django.conf import settings
from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import IntakeFile, IntakeMessage
from .serializers import IntakeMessageSerializer
from .tasks import process_intake_message

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = ["xlsx", "xls", "csv", "pdf", "docx", "jpg", "jpeg", "png"]
MAX_FILE_SIZE_MB = 10


class IntakeUploadView(APIView):
    """
    POST /api/v1/intake/upload/

    Authenticated members upload a file directly.
    Accepts multipart/form-data with 'file' field.
    File size limit: 10MB; allowed types: xlsx, xls, csv, pdf, docx, jpg, png.
    Creates IntakeMessage (channel='upload') + IntakeFile.
    Queues process_intake_message task.
    Returns { intake_id, status: 'processing' }.
    """

    parser_classes = [MultiPartParser]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response(
                {"detail": "No file provided."}, status=status.HTTP_400_BAD_REQUEST
            )

        # Check file size
        max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
        if file_obj.size > max_bytes:
            return Response(
                {"detail": f"File exceeds {MAX_FILE_SIZE_MB}MB limit."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check extension
        ext = os.path.splitext(file_obj.name)[1].lower().lstrip(".")
        if ext not in ALLOWED_EXTENSIONS:
            return Response(
                {"detail": f"File type '{ext}' not allowed. Allowed: {ALLOWED_EXTENSIONS}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Determine IntakeFile.kind
        kind = _ext_to_kind(ext)

        # Resolve company from user memberships
        membership = (
            request.user.memberships.filter(status="active")
            .select_related("company")
            .first()
        )
        company = membership.company if membership else None

        # Create IntakeMessage
        intake_message = IntakeMessage.objects.create(
            channel=IntakeMessage.Channel.UPLOAD,
            from_email=request.user.email,
            company=company,
            user=request.user,
            subject=file_obj.name,
            status=IntakeMessage.Status.RECEIVED,
        )

        # Upload to S3
        s3_key = f"intake/{intake_message.pk}/{uuid.uuid4().hex[:8]}_{file_obj.name}"
        try:
            s3 = boto3.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_S3_REGION_NAME,
            )
            s3.upload_fileobj(
                file_obj,
                settings.AWS_STORAGE_BUCKET_NAME,
                s3_key,
                ExtraArgs={"ContentType": file_obj.content_type or "application/octet-stream"},
            )
        except Exception as exc:
            logger.exception("IntakeUploadView: S3 upload failed: %s", exc)
            intake_message.status = IntakeMessage.Status.FAILED
            intake_message.save(update_fields=["status", "updated_at"])
            return Response(
                {"detail": "File upload failed. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Create IntakeFile
        IntakeFile.objects.create(
            message=intake_message,
            filename=file_obj.name,
            mime=file_obj.content_type or "",
            s3_key=s3_key,
            kind=kind,
        )

        # Queue Celery task
        process_intake_message.delay(str(intake_message.pk))

        return Response(
            {"intake_id": str(intake_message.pk), "status": "processing"},
            status=status.HTTP_202_ACCEPTED,
        )


class IntakeListView(generics.ListAPIView):
    """
    GET /api/v1/intake/

    Lists IntakeMessages for the current user's company.
    Filter by status: ?status=received
    """

    serializer_class = IntakeMessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        membership = (
            user.memberships.filter(status="active").select_related("company").first()
        )
        if not membership:
            return IntakeMessage.objects.none()

        qs = IntakeMessage.objects.filter(company=membership.company).prefetch_related(
            "files", "extractions", "extractions__listing"
        )

        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        return qs.order_by("-received_at")


class IntakeDetailView(generics.RetrieveAPIView):
    """
    GET /api/v1/intake/{id}/

    Returns IntakeMessage + files + extractions + linked listing draft.
    """

    serializer_class = IntakeMessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        membership = (
            user.memberships.filter(status="active").select_related("company").first()
        )
        if not membership:
            return IntakeMessage.objects.none()

        return IntakeMessage.objects.filter(
            company=membership.company
        ).prefetch_related("files", "extractions", "extractions__listing")


def _ext_to_kind(ext: str) -> str:
    """Map file extension to IntakeFile.Kind value."""
    mapping = {
        "xlsx": IntakeFile.Kind.XLSX,
        "xls": IntakeFile.Kind.XLSX,
        "csv": IntakeFile.Kind.CSV,
        "pdf": IntakeFile.Kind.PDF,
        "jpg": IntakeFile.Kind.IMAGE,
        "jpeg": IntakeFile.Kind.IMAGE,
        "png": IntakeFile.Kind.IMAGE,
        "docx": IntakeFile.Kind.BODY_TEXT,
    }
    return mapping.get(ext, IntakeFile.Kind.BODY_TEXT)
