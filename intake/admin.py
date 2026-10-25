from django.contrib import admin

from .models import IntakeExtraction, IntakeFile, IntakeMessage


class IntakeFileInline(admin.TabularInline):
    model = IntakeFile
    extra = 0
    readonly_fields = ["filename", "mime", "kind", "s3_key", "text_extracted", "created_at"]
    can_delete = False


class IntakeExtractionInline(admin.StackedInline):
    model = IntakeExtraction
    extra = 0
    readonly_fields = [
        "model",
        "prompt_version",
        "result",
        "confidence",
        "line_count",
        "listing",
        "created_at",
    ]
    can_delete = False


@admin.register(IntakeMessage)
class IntakeMessageAdmin(admin.ModelAdmin):
    list_display = ["channel", "from_email", "company", "status", "received_at"]
    list_filter = ["channel", "status"]
    search_fields = ["from_email", "subject"]
    readonly_fields = ["received_at", "created_at", "updated_at"]
    inlines = [IntakeFileInline, IntakeExtractionInline]
    ordering = ["-received_at"]


@admin.register(IntakeExtraction)
class IntakeExtractionAdmin(admin.ModelAdmin):
    list_display = ["message", "model", "confidence", "line_count", "listing", "created_at"]
    readonly_fields = [
        "id",
        "message",
        "model",
        "prompt_version",
        "result",
        "confidence",
        "line_count",
        "listing",
        "created_at",
    ]
    ordering = ["-created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
