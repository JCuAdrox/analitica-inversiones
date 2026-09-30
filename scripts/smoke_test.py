"""Prueba de humo: consulta el dashboard y verifica cifras clave."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.test import Client
from django.test.utils import setup_test_environment

from portafolio import servicios

setup_test_environment()

CASOS = [
    ("10020203023", ["Privada", "MODERADO", "1.829.947.172", "73.183",
                     "2.112.949.192", "13,4 %", "15/05/2024", "30/05/2024"]),
    ("10014876058", ["Personal", "SIN DEFINIR", "8.704.400", "2.249.378",
                     "8.707.092.528", "99,9 %"]),
    ("10032184607", ["MODERADO", "94,5 %", "SIN CATALOGO", "SIN CODIGO"]),
    ("1.00901E+11", ["Empresas", "CONSERVADOR", "llegó truncado",
                     "no tiene portafolio internacional"]),
    ("10026419826", ["Diagnóstico del modelo", "SIN PERFIL DECLARADO",
                     "Vencimiento próximo", "vence en 7 días"]),
]


def main():
    fallos = 0
    n = len(servicios.ejecutar("clientes"))
    print(("OK   " if n == 29 else "FALLO"), f"clientes en el selector: {n} (esperado 29)")
    fallos += n != 29

    cliente = Client()
    for id_cliente, textos in CASOS:
        resp = cliente.get("/", {"id_cliente": id_cliente})
        html = resp.content.decode()
        if resp.status_code != 200:
            print("FALLO", id_cliente, "estado HTTP", resp.status_code)
            fallos += 1
            continue
        for t in textos:
            ok = t in html
            fallos += not ok
            print(("OK   " if ok else "FALLO"), id_cliente, "contiene:", t)

    resp = cliente.get("/modelo/")
    html = resp.content.decode()
    for t in ["Segmentos de clientes", "Oportunidades priorizadas",
              "Perfilamiento pendiente", "Revisar idoneidad"]:
        ok = resp.status_code == 200 and t in html
        fallos += not ok
        print(("OK   " if ok else "FALLO"), "/modelo/ contiene:", t)    
    resp = cliente.get("/", {"id_cliente": "' OR 1=1 --"})
    ok = resp.status_code == 200
    fallos += not ok
    print(("OK   " if ok else "FALLO"), "ID invalido no rompe la pagina")

    print("\nTodo bien." if fallos == 0 else f"\n{fallos} verificaciones fallaron.")
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()