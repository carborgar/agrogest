#!/bin/sh

echo "Creating cache table (if needed, idempotent)..."
python manage.py createcachetable agrogest_cache --quiet 2>&1 | grep -v 'Table.*already exists' || true

if [ $? -eq 0 ]; then
	echo "✓ Cache table ready"
else
	echo "⚠ Cache table status unknown; connection will retry on first request"
fi

echo "Checking cache health..."
python manage.py check_cache_health || exit 1

echo "Applying migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting server..."
gunicorn agrogest.wsgi:application --bind 0.0.0.0:8000
