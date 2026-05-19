"""
Management command: check_cache_health

Verifica que el backend de caché esté disponible y funcionando.
Útil para diagnosticar problemas en Vercel (p. ej. tabla de DB no creada).

Uso:
  python manage.py check_cache_health
"""
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Verifica que el backend de caché esté funcionando correctamente"

    def handle(self, *args, **options):
        test_key = "agrogest_cache_health_check"
        test_value = "ok"


        backend_name = cache.__class__.__name__
        self.stdout.write(f"Backend de caché: {backend_name}")

        if 'DatabaseCache' in backend_name or 'atomic' in str(type(cache)).lower():
            from django.conf import settings
            location = getattr(settings, 'CACHES', {}).get('default', {}).get('LOCATION', 'unknown')
            self.stdout.write(f"  → DatabaseCache en tabla: {location}")

        try:
            cache.set(test_key, test_value, timeout=10)
            self.stdout.write("✓ Cache SET funcionando")
        except Exception as e:
            raise CommandError(f"✗ Cache SET falló: {e}")

        try:
            retrieved = cache.get(test_key)
            if retrieved != test_value:
                raise CommandError(f"✗ Cache GET devolvió valor incorrecto: {retrieved}")
            self.stdout.write("✓ Cache GET funcionando")
        except Exception as e:
            raise CommandError(f"✗ Cache GET falló: {e}")

        try:
            cache.delete(test_key)
            self.stdout.write("✓ Cache DELETE funcionando")
        except Exception as e:
            raise CommandError(f"✗ Cache DELETE falló: {e}")

        self.stdout.write(self.style.SUCCESS("\n✓ Cache está funcionando correctamente"))

