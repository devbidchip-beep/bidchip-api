"""
Notification service — create Notification records and dispatch Celery tasks.
Never raises; notification failures must not break business logic.
"""

import logging

from celery import shared_task
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)


def notify(user, template_key: str, context: dict, channel: str = "email"):
    """
    Creates a Notification record and queues a Celery task to send it.
    If no active template exists for the key, logs a warning and returns None.
    Never raises.
    """
    try:
        from notify.models import Notification, NotificationTemplate

        try:
            template = NotificationTemplate.objects.get(key=template_key, is_active=True)
        except NotificationTemplate.DoesNotExist:
            logger.warning("notify: no active template for key=%s", template_key)
            return None

        notification = Notification.objects.create(
            user=user,
            template=template,
            channel=channel,
            context=context,
            status=Notification.Status.QUEUED,
        )

        send_notification.delay(str(notification.pk))
        return notification
    except Exception as exc:
        logger.exception("notify: unexpected error for template_key=%s user=%s: %s", template_key, user, exc)
        return None


@shared_task(bind=True, max_retries=3)
def send_notification(self, notification_id: str):
    """
    Celery task. Renders the template with context (simple str.format_map).
    For email: uses Django's send_mail (SES in prod, console in dev).
    Sets status=sent or failed.
    """
    from django.conf import settings
    from notify.models import Notification

    try:
        notification = Notification.objects.select_related("template", "user").get(pk=notification_id)
    except Notification.DoesNotExist:
        logger.error("send_notification: Notification %s not found", notification_id)
        return

    try:
        ctx = notification.context or {}
        subject = notification.template.subject.format_map(ctx)
        body_text = notification.template.body_text.format_map(ctx)
        body_html = notification.template.body_html.format_map(ctx)

        if notification.channel == "email":
            from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@bidchip.com")
            result = send_mail(
                subject=subject,
                message=body_text,
                from_email=from_email,
                recipient_list=[notification.user.email],
                html_message=body_html,
                fail_silently=False,
            )
            # SES returns message ID via django-ses; generic send_mail returns int
            notification.ses_message_id = str(result) if result else ""

        notification.status = "sent"
        notification.sent_at = timezone.now()
        notification.save(update_fields=["status", "sent_at", "ses_message_id"])

    except Exception as exc:
        logger.exception("send_notification: failed for %s: %s", notification_id, exc)
        notification.status = "failed"
        notification.save(update_fields=["status"])
        raise self.retry(exc=exc, countdown=60)
