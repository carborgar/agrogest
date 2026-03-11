#!/bin/sh

# Wait for the database to be available
echo "Waiting for database..."
python manage.py check --database default

echo "Applying migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting server..."
gunicorn agrogest.wsgi:application --bind 0.0.0.0:8000
