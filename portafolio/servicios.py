from decimal import Decimal

from django.db import connection, transaction

from .models import ConsultaSQL


def _limpiar(valor):
    return float(valor) if isinstance(valor, Decimal) else valor


def ejecutar(slug, params=None):
    """Ejecuta una consulta activa por su slug y devuelve una lista de dicts."""
    consulta = ConsultaSQL.objects.get(slug=slug, activa=True)
    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(consulta.sql, params or None)
            columnas = [col[0] for col in cur.description]
            return [
                dict(zip(columnas, map(_limpiar, fila))) for fila in cur.fetchall()
            ]