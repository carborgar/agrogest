from django.core.management.base import BaseCommand

from core.models import KNOWN_FLAGS, FeatureFlag


class Command(BaseCommand):
    help = (
        "Crea en BD los feature flags definidos en KNOWN_FLAGS que todavía no existan. "
        "Los flags ya existentes no se modifican (respeta la configuración del admin)."
    )

    def handle(self, *args, **options):
        created_count = 0
        for name, description in KNOWN_FLAGS.items():
            flag, created = FeatureFlag.objects.get_or_create(
                name=name,
                defaults={'enabled': True, 'description': description},
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"  ✅ Creado: {name}"))
                created_count += 1
            else:
                self.stdout.write(f"  — Ya existe: {name} ({'activo' if flag.enabled else 'inactivo'})")

        if created_count:
            self.stdout.write(self.style.SUCCESS(f"\n{created_count} flag(s) creado(s)."))
        else:
            self.stdout.write("\nTodo al día, no había nada nuevo que crear.")

