from django.contrib import admin

from notify.models import Notification, NotificationTemplate


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ["key", "subject", "version", "is_active", "updated_at"]
    list_filter = ["is_active"]
    search_fields = ["key", "subject"]


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["user", "template", "channel", "status", "sent_at", "created_at"]
    list_filter = ["status", "channel"]
    search_fields = ["user__email", "template__key"]
    readonly_fields = ["created_at", "sent_at"]
