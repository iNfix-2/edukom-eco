#!/bin/bash
set -e

echo "=== Starting Edukom Enterprise LMS Production Container ==="

# Wait for PostgreSQL database if POSTGRES_HOST is specified
if [ -n "$POSTGRES_HOST" ]; then
  echo "Waiting for PostgreSQL at $POSTGRES_HOST:${POSTGRES_PORT:-5432}..."
  while ! nc -z "$POSTGRES_HOST" "${POSTGRES_PORT:-5432}"; do
    sleep 1
  done
  echo "PostgreSQL is reachable."
fi

# Apply database migrations
echo "Applying database migrations..."
python manage.py migrate --noinput

# Collect static assets
echo "Collecting static assets..."
python manage.py collectstatic --noinput --clear

# Start Gunicorn WSGI Server
echo "Launching Gunicorn WSGI server..."
exec gunicorn edukom.wsgi:application \
    --name edukom_lms \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-4}" \
    --worker-class gthread \
    --threads "${GUNICORN_THREADS:-2}" \
    --worker-connections 1000 \
    --max-requests 2000 \
    --max-requests-jitter 200 \
    --timeout 60 \
    --keep-alive 5 \
    --access-logfile - \
    --error-logfile - \
    --log-level "${LOG_LEVEL:-info}"
