"""Ejecuta el modelo completo en orden: mapeo, riesgo, segmentacion y vistas SQL."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PASOS = [
    ["modelo/construir_mapeo.py"],
    ["modelo/riesgo_portafolio.py"],
    ["modelo/segmentacion.py"],
    ["scripts/run_sql.py", "sql_modelo"],
]

for paso in PASOS:
    print(f"\n=== {' '.join(paso)} ===")
    subprocess.run([sys.executable, *paso], check=True, cwd=ROOT)
print("\nModelo completo ejecutado.")