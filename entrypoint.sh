#!/bin/sh

echo "Applying migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting server..."
# Varios workers e hilos: el asistente espera al proveedor hasta ~25 s y no debe bloquear al resto.
# agrogest/wsgi.py expone `app` (no `application`).
gunicorn agrogest.wsgi:app --bind 0.0.0.0:8000 --workers 2 --threads 4 --timeout 40
