#!/bin/bash

# Build the project
echo "Building the project..."
python3.12 -m pip install -r requirements.txt

# Install Node.js dependencies and compile SCSS
echo "Installing Node.js dependencies and compiling SCSS..."
npm install
# Compilar SCSS a CSS con npx
npx sass scss/custom-bootstrap.scss static/css/bootstrap.min.css --style=compressed

echo "Migrating database..."
python3.12 manage.py makemigrations --noinput
python3.12 manage.py migrate --noinput

echo "Collecting static files..."
python3.12 manage.py collectstatic --noinput
