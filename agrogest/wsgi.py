"""
WSGI config for agrogest project.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "agrogest.settings")

app = get_wsgi_application()
