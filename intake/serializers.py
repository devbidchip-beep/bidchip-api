from rest_framework import serializers

from .models import IntakeExtraction, IntakeFile, IntakeMessage


class IntakeFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntakeFile
        fields = ["id", "filename", "mime", "kind", "text_extracted", "created_at"]
        read_only_fields = fields


class ListingBriefSerializer(serializers.Serializer):
    """Minimal listing summary embedded in extraction."""
    id = serializers.UUIDField()
    number = serializers.CharField()


class IntakeExtractionSerializer(serializers.ModelSerializer):
    listing = ListingBriefSerializer(read_only=True)

    class Meta:
        model = IntakeExtraction
        fields = [
            "id",
            "model",
            "prompt_version",
            "result",
            "confidence",
            "line_count",
            "listing",
            "created_at",
        ]
        read_only_fields = fields


class IntakeMessageSerializer(serializers.ModelSerializer):
    files = IntakeFileSerializer(many=True, read_only=True)
    extractions = IntakeExtractionSerializer(many=True, read_only=True)

    class Meta:
        model = IntakeMessage
        fields = [
            "id",
            "channel",
            "from_email",
            "company",
            "user",
            "subject",
            "status",
            "received_at",
            "created_at",
            "updated_at",
            "files",
            "extractions",
        ]
        read_only_fields = fields
