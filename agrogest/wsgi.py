"""
WSGI config for agrogest project.

It exposes the WSGI callable as a module-level variable named ``app``.

For more information on this file, see
https://docs.djangoproject.com/en/4.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'agrogest.settings')

application = get_wsgi_application()

if os.environ.get('VERCEL'):
    import django
    django.setup()
    from django.core.management import call_command

    try:
        call_command('migrate', '--noinput')
        call_command('collectstatic', '--noinput')
    except Exception as e:
        print(f"Startup error: {e}")

# para vercel es necesario que se llame app
app = application
