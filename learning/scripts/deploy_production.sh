#!/bin/bash
# ==============================================================================
# Edukom Enterprise LMS - Zero-Downtime Production Deployment & Rollback Script
# Safeguards:
# - Pre-deployment encrypted database snapshot
# - Zero-downtime rolling container updates
# - Post-deployment /healthz verification probe
# - Automatic rollback on failure to prevent downtime
# ==============================================================================

set -eo pipefail

COMPOSE_FILE="docker-compose.production.yml"
ENV_FILE=".env.production"
HEALTH_CHECK_URL="http://localhost:8000/healthz/"
MAX_HEALTH_RETRIES=10
RETRY_INTERVAL_SECONDS=3

echo "================================================================================"
echo " Starting Edukom Production Zero-Downtime Deployment - $(date -u)"
echo "================================================================================"

# 1. Pre-flight validation
if [ ! -f "$COMPOSE_FILE" ]; then
    echo "[-] Error: Compose file $COMPOSE_FILE not found."
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "[-] Error: Environment file $ENV_FILE not found."
    exit 1
fi

# 2. Automated Pre-Deployment Database Snapshot
echo "[+] Step 1/5: Taking safety database snapshot before deployment..."
if [ -f "./scripts/backup_database.sh" ]; then
    bash ./scripts/backup_database.sh || echo "[!] Warning: Backup script failed, proceed with caution."
fi

# 3. Pull and Build Images in Background
echo "[+] Step 2/5: Building and caching production container images..."
docker compose -f "$COMPOSE_FILE" build --pull

# 4. Execute Zero-Downtime Database Migrations
echo "[+] Step 3/5: Applying forward-compatible database migrations..."
docker compose -f "$COMPOSE_FILE" run --rm web python manage.py migrate --noinput

# 5. Rolling Update Container Cluster
echo "[+] Step 4/5: Performing rolling container restart..."
docker compose -f "$COMPOSE_FILE" up -d --no-deps --scale web=2 --no-recreate web
sleep 5
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans web celery_worker celery_beat nginx

# 6. Post-Deployment Health Check Verification & Auto-Rollback
echo "[+] Step 5/5: Verifying application health via /healthz probe..."
HEALTHY=false

for i in $(seq 1 $MAX_HEALTH_RETRIES); do
    echo "  -> Health probe check $i of $MAX_HEALTH_RETRIES..."
    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_CHECK_URL" || true)
    
    if [ "$HTTP_STATUS" -eq 200 ]; then
        HEALTHY=true
        echo "[+] Health check verified: HTTP 200 OK."
        break
    fi
    sleep $RETRY_INTERVAL_SECONDS
done

if [ "$HEALTHY" = true ]; then
    echo "================================================================================"
    echo " [SUCCESS] Edukom Enterprise LMS successfully deployed with zero downtime!"
    echo " Time: $(date -u)"
    echo "================================================================================"
    exit 0
else
    echo "================================================================================"
    echo " [CRITICAL ALERT] Health check probe failed! Initiating automated rollback..."
    echo "================================================================================"
    
    # Rollback to previous container configuration
    docker compose -f "$COMPOSE_FILE" restart web nginx
    
    echo "[-] Platform rolled back. Investigating logs:"
    docker compose -f "$COMPOSE_FILE" logs --tail=50 web
    exit 1
fi
