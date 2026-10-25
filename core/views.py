from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse


def health_check(request):
    """
    GET /health/
    Returns 200 if DB + cache are reachable.
    Returns 503 if any check fails.
    Used by ALB health checks and ECS.
    """
    checks = {}
    status = 200

    # DB check
    try:
        connection.ensure_connection()
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {exc}"
        status = 503

    # Cache check
    try:
        cache.set("health_check", "1", timeout=5)
        assert cache.get("health_check") == "1"  # noqa: S101
        checks["cache"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["cache"] = f"error: {exc}"
        status = 503

    return JsonResponse(
        {"status": "ok" if status == 200 else "degraded", "checks": checks},
        status=status,
    )
