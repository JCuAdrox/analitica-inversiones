"""Mide cuanto tarda cada consulta SQL de la app para un cliente."""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from portafolio import servicios
from portafolio.models import ConsultaSQL

id_cliente = sys.argv[1] if len(sys.argv) > 1 else "10014876058"
total = 0.0
for c in ConsultaSQL.objects.filter(activa=True).order_by("slug"):
    params = {"id_cliente": id_cliente} if "%(id_cliente)s" in c.sql else None
    inicio = time.perf_counter()
    filas = servicios.ejecutar(c.slug, params)
    seg = time.perf_counter() - inicio
    total += seg
    print(f"{c.slug:<24} {seg:7.2f} s   {len(filas)} filas")
print(f"\nTotal: {total:.2f} s")