from django.core.management import call_command
from django.test import TestCase


class CacheHealthCheckCommandTest(TestCase):
    def test_check_cache_health_succeeds(self):
        """Verifica que el comando check_cache_health funcione sin errores."""
        try:
            call_command("check_cache_health", verbosity=0)
        except Exception as e:
            self.fail(f"check_cache_health falló: {e}")

