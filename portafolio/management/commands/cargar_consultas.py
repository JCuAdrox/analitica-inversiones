from django.core.management.base import BaseCommand

from portafolio.consultas_base import CONSULTAS
from portafolio.models import ConsultaSQL


class Command(BaseCommand):
    help = "Carga o actualiza las consultas SQL base en la tabla ConsultaSQL"

    def handle(self, *args, **opciones):
        for c in CONSULTAS:
            datos = {k: v.strip() if k == "sql" else v for k, v in c.items() if k != "slug"}
            obj, creada = ConsultaSQL.objects.update_or_create(
                slug=c["slug"], defaults=datos
            )
            self.stdout.write(("creada: " if creada else "actualizada: ") + obj.slug)