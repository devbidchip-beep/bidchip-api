"""
Celery application configuration for BidChip API.
"""

import os

from celery import Celery

# Set the default Django settings module for the Celery program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("bidchip")

# Use Django's settings file for Celery configuration.
# All celery config keys should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks from all installed apps.
app.autodiscover_tasks()


app.conf.beat_schedule = {
    "close-expired-listings": {
        "task": "listings.tasks.close_expired_listings",
        "schedule": 60.0,  # every 60 seconds
    },
    "release-eligible-payouts": {
        "task": "payments.tasks.release_eligible_payouts",
        "schedule": 900.0,  # every 15 minutes
    },
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
