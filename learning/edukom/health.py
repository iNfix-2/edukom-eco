import time
import shutil
import logging
from django.http import JsonResponse, HttpRequest
from django.db import connection
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('edukom')


def run_health_checks() -> dict:
    """
    Evaluates system liveness and readiness across database, cache, and disk storage.
    Returns a dictionary payload with health status and component metrics.
    """
    start_time = time.monotonic()
    checks = {}
    is_healthy = True

    # 1. Database Connectivity Check
    db_start = time.monotonic()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            row = cursor.fetchone()
            if row and row[0] == 1:
                db_latency_ms = round((time.monotonic() - db_start) * 1000, 2)
                checks['database'] = {
                    'status': 'healthy',
                    'latency_ms': db_latency_ms
                }
            else:
                checks['database'] = {'status': 'unhealthy', 'error': 'Invalid database response'}
                is_healthy = False
    except Exception as e:
        logger.critical(f"Database health check failed: {str(e)}")
        checks['database'] = {'status': 'unhealthy', 'error': 'Database connection failed'}
        is_healthy = False

    # 2. Cache Connectivity Check (Redis / LocMem)
    cache_start = time.monotonic()
    try:
        probe_key = f"health_probe_{int(time.time())}"
        cache.set(probe_key, "ok", timeout=10)
        cached_val = cache.get(probe_key)
        cache.delete(probe_key)
        
        if cached_val == "ok":
            cache_latency_ms = round((time.monotonic() - cache_start) * 1000, 2)
            checks['cache'] = {
                'status': 'healthy',
                'latency_ms': cache_latency_ms
            }
        else:
            checks['cache'] = {'status': 'degraded', 'error': 'Cache read/write roundtrip failed'}
            # Non-fatal if cache is degraded, but marked degraded
    except Exception as e:
        logger.warning(f"Cache health check warning: {str(e)}")
        checks['cache'] = {'status': 'degraded', 'error': 'Cache service unavailable'}

    # 3. Disk Space Check (Ensure > 10% disk headroom)
    try:
        disk_usage = shutil.disk_usage(settings.BASE_DIR)
        free_pct = round((disk_usage.free / disk_usage.total) * 100, 1)
        total_gb = round(disk_usage.total / (1024 ** 3), 1)
        free_gb = round(disk_usage.free / (1024 ** 3), 1)

        if free_pct < 10.0:
            checks['storage'] = {
                'status': 'critical_low_space',
                'free_gb': free_gb,
                'free_percent': free_pct
            }
            is_healthy = False
        else:
            checks['storage'] = {
                'status': 'healthy',
                'free_gb': free_gb,
                'free_percent': free_pct
            }
    except Exception as e:
        checks['storage'] = {'status': 'unknown', 'error': str(e)}

    total_latency_ms = round((time.monotonic() - start_time) * 1000, 2)
    return {
        'status': 'healthy' if is_healthy else 'unhealthy',
        'is_healthy': is_healthy,
        'timestamp': timezone.now().isoformat(),
        'total_latency_ms': total_latency_ms,
        'components': checks
    }


def health_check_view(request: HttpRequest) -> JsonResponse:
    """
    Production Health Check Probe (/healthz):
    Evaluates system liveness and readiness across database, cache, and disk storage.
    Used by AWS ALB / Cloudflare / Docker / Kubernetes health checks.
    """
    payload = run_health_checks()
    status_code = 200 if payload.get('is_healthy', True) else 503
    return JsonResponse(payload, status=status_code)

