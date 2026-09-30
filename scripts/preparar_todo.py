"""Prepara el proyecto completo en orden y termina verificando con el smoke test.


Uso:
    python scripts/preparar_todo.py                      (usa la foto de mercado del repo)
    python scripts/preparar_todo.py --descargar-mercado  (vuelve a descargar precios)
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MERCADO = ROOT / "mercado" / "mercado_precios.csv"
CSV = [
    "cat_perfil_riesgo", "catalogo_activos", "catalogo_banca",
    "historico_aba_macroactivos", "historico_aba_usd_internacional",
]


def correr(*args):
    print(f"\n=== {' '.join(args)} ===", flush=True)
    subprocess.run([sys.executable, *args], check=True, cwd=ROOT)


def main():
    faltan = [c for c in CSV if not (ROOT / "data" / f"{c}.csv").exists()]
    if faltan:
        sys.exit("Faltan estos archivos en la carpeta data/: " + ", ".join(f"{c}.csv" for c in faltan))

    correr("scripts/load_data.py")
    correr("scripts/run_sql.py")
    if "--descargar-mercado" in sys.argv or not MERCADO.exists():
        correr("scripts/descargar_mercado.py")
    correr("modelo/pipeline.py")
    correr("manage.py", "migrate")
    correr("manage.py", "cargar_consultas")
    correr("scripts/smoke_test.py")
    print("\nProyecto listo. Crea un administrador con: python manage.py createsuperuser")
    print("Y levanta la app con: python manage.py runserver")


if __name__ == "__main__":
    main()