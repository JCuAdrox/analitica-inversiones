# Analítica de inversiones: portafolios, perfil de riesgo y oportunidades

Prueba técnica para la vacante de aprendiz de la Gerencia de Analítica de Inversiones Bancolombia.

La herramienta toma los archivos entregados (catálogos e históricos de saldos en COP y USD), los limpia y consolida en PostgreSQL, y los muestra en una aplicación Django donde el gerente elige un cliente y ve su portafolio local e internacional a la última fecha disponible. Encima de eso hay un modelo analítico que estima el riesgo real de cada portafolio con datos de mercado, lo compara con el perfil declarado, segmenta a los clientes y genera una lista priorizada de oportunidades comerciales. Opcionalmente, un modelo de lenguaje local redacta un resumen ejecutivo por cliente.

## Cumplimiento de la prueba

| Punto | Dónde está |
|:--|:--|
| 1. Base en Postgres con una tabla por CSV, cargada con Python | `scripts/load_data.py` |
| 2. Limpieza, transformación y consolidación en SQL | `sql/` (vistas del esquema `stg`) y `sql_modelo/` |
| 3. Django que gestiona las consultas SQL y visualiza el portafolio COP y USD | `portafolio/` (consultas editables en el administrador, gráficos con Plotly) |
| 4. Datos de mercado y modelo analítico | `scripts/descargar_mercado.py`, `mercado/`, `modelo/` |
| 5. Repositorio reproducible, sin las bases suministradas | este README, `scripts/preparar_todo.py` |
| 6. Opcional: IA | `portafolio/ia.py` (modelo local con Ollama) |

## Requisitos previos

1. Git.
2. Python 3.12 o superior (probado con 3.14 en Windows y 3.12 en Linux).
3. Docker Desktop para la base de datos, o PostgreSQL 16 instalado localmente.
4. Los 5 archivos CSV de la prueba. No están en el repositorio, por instrucción de la prueba.
5. Opcional, para la IA: [Ollama](https://ollama.com).

Los comandos están escritos para Git Bash en Windows. En macOS o Linux funcionan igual, salvo la activación del entorno virtual (se indica en el paso 5).

## Instalación paso a paso

### 1. Clonar el repositorio

```bash
git clone https://github.com/JCuAdrox/analitica-inversiones.git analitica-inversiones
cd analitica-inversiones
```

### 2. Copiar los datos

Crea la carpeta `data/` y copia ahí los 5 archivos, con estos nombres exactos:

```
data/cat_perfil_riesgo.csv
data/catalogo_activos.csv
data/catalogo_banca.csv
data/historico_aba_macroactivos.csv
data/historico_aba_usd_internacional.csv
```

### 3. Crear el archivo de configuración

```bash
cp .env.example .env
```

Si quieres otra clave para la base de datos, cámbiala en `.env` **antes** del paso 4: Postgres la fija la primera vez que crea la base.

### 4. Levantar PostgreSQL

**Opción A, con Docker** (recomendada). Con Docker Desktop abierto:

```bash
docker compose up -d
docker ps
```

Debe aparecer un contenedor de `postgres:16` en estado `Up`.

**Opción B, con PostgreSQL local.** Crea el usuario y la base con los mismos datos del `.env`:

```bash
psql -U postgres -c "CREATE USER analitica WITH PASSWORD 'cambia_esta_clave';"
psql -U postgres -c "CREATE DATABASE bancolombia OWNER analitica;"
```
En este caso cambia `DB_PORT=5433` por `DB_PORT=5432` en el `.env`, que es el puerto habitual de una instalación local.

### 5. Crear el entorno de Python e instalar dependencias

```bash
python -m venv venv
source venv/Scripts/activate
python -m pip install -r requirements.txt
```

En macOS o Linux, la segunda línea es `source venv/bin/activate`. En PowerShell, `venv\Scripts\Activate.ps1`. Cada vez que abras una terminal nueva hay que volver a activar el entorno.

### 6. Preparar todo con un solo comando

```bash
python scripts/preparar_todo.py
```

Tarda alrededor de un minuto y hace, en orden: cargar los CSV a Postgres, crear las vistas SQL de limpieza y consolidación, correr el modelo analítico con la foto de datos de mercado incluida en el repo, crear las tablas de Django, cargar las consultas gestionables y verificar el resultado con una prueba automática. Debe terminar con:

```
Todo bien.
```

Si alguna verificación sale como `FALLO`, revisa la sección de solución de problemas. El script se puede repetir las veces que quieras: siempre reconstruye todo desde los CSV.

### 7. Levantar la aplicación

```bash
python manage.py createsuperuser
python manage.py runserver
```

Si en Git Bash `createsuperuser` se queda esperando sin mostrar nada, usa `winpty python manage.py createsuperuser`.

Luego abre en el navegador:

1. `http://127.0.0.1:8000/` para el portafolio por cliente.
2. `http://127.0.0.1:8000/modelo/` para el modelo y las oportunidades.
3. `http://127.0.0.1:8000/admin/` para gestionar las consultas SQL (con el usuario del `createsuperuser`).

Los gráficos cargan Plotly desde internet, así que el navegador necesita conexión.

### 8. Opcional: activar la IA

Instala Ollama y descarga el modelo:

```bash
ollama pull qwen2.5:7b
```

Ocupa unos 5 GB de disco. Si el equipo no tiene tarjeta gráfica, usa `qwen2.5:3b` y cambia `OLLAMA_MODEL` en el `.env`. Sin Ollama la aplicación funciona igual: el botón de resumen solo muestra un aviso.

## Cómo está construido

```
CSV ──> tablas crudas (Python) ──> vistas stg (SQL) ──> modelo (Python y SQL) ──> tablas app (SQL) ──> Django + Plotly
```

1. **Carga** (`scripts/load_data.py`): copia cada CSV a una tabla con su mismo nombre, todo como texto, para no perder información antes de limpiar.
2. **Limpieza y consolidación** (`sql/01` a `sql/05b`): normaliza vacíos y `None`, elimina duplicados, envía a una vista de cuarentena las filas dañadas con su motivo, corrige catálogos, arma el portafolio de cada cliente en su última fecha y consolida COP y USD con la TRM del 30 de mayo de 2024.
3. **Modelo** (`modelo/` y `sql_modelo/`): riesgo, perfil, segmentos y oportunidades (ver abajo).
4. **Capa de presentación** (`sql/06` y `sql_modelo/08`): materializa en el esquema `app` los resultados que consume la aplicación. Recalcular las vistas en cada clic tomaba unos 22 segundos por ficha; leyendo de estas tablas toma unos 30 milisegundos.
5. **Aplicación** (`portafolio/`): cada consulta SQL vive en la tabla `ConsultaSQL` y se puede editar desde el administrador. Solo se aceptan consultas de lectura, y además se ejecutan en una transacción de solo lectura.

## Hallazgos de calidad de datos

1. Unos 780 registros duplicados exactos en el histórico COP, y 22 filas con campos corridos o vacíos, que van a `stg.macro_cuarentena` con su motivo.
2. 11 de los 29 clientes tienen el ID en notación científica (truncado por Excel). Se usan como identificador, pero no se pueden cruzar con el archivo USD, y la aplicación lo advierte.
3. Dos IDs fantasma con 1 y 5 fechas, que se excluyen con una regla de mínimo 30 fechas por cliente.
4. Códigos que no cuadran con el catálogo: `1115` se corrige a `1015` (PFCEMARGOS), `10007` se asume como `1007` (Fiducuenta) y `1022` queda como "sin catálogo".
5. En el archivo USD, el corte del 1 de marzo de 2024 trae unas 63 observaciones por activo sin fecha individual. Se conserva, pero el portafolio actual usa el corte del 30 de mayo.
6. Nueve posiciones son notas estructuradas ligadas a índices, que se clasifican aparte.
7. Un cliente trae dos perfiles distintos en la misma fecha; se resuelve con una regla fija (prefiere el perfil definido).

## Modelo analítico

1. **Riesgo real del portafolio.** Cada activo se asocia a su serie de precios de mercado, a un proxy o a un supuesto documentado en `modelo/mapeo_riesgo.csv`. Con un año de retornos semanales se calcula la volatilidad de cada portafolio completo, con y sin el efecto de la TRM. El 97,6 % del valor local depende de supuestos (CDT y fondos sin serie pública), y se marca así en la aplicación.
2. **Perfil inferido y coherencia.** El riesgo del portafolio se compara con el perfil declarado (umbrales de 5 % y 15 %, con prueba de sensibilidad). Resultado: 14 clientes sin perfil declarado, 3 con más riesgo del que declararon y 6 con capacidad de riesgo sin usar.
3. **Segmentación.** KMeans sobre riesgo, concentración, porcentaje internacional y renta variable. El número de segmentos se elige por silueta, exigiendo al menos 5 clientes por segmento; salen 3, estables en 10 de 10 semillas.
4. **Oportunidades.** Ocho reglas en SQL (perfilamiento pendiente, idoneidad, capacidad de riesgo, vencimientos a 180 días, concentración, liquidez, diversificación internacional y datos sin identificar), con prioridad y monto: 57 oportunidades, 11 de prioridad alta.

## IA

El modelo de lenguaje corre en el propio equipo con Ollama, así que los datos de clientes no salen de él. No consulta la base ni calcula nada: recibe un texto con las cifras que ya calculó la aplicación y solo lo redacta. Los próximos pasos no los escribe el modelo sino el sistema, a partir de las oportunidades, y cada número del texto generado se compara con los datos para alertar si aparece alguno que no estaba.

## Limitaciones

1. Con 29 clientes, la segmentación describe la cartera actual; no es un modelo predictivo.
2. El riesgo local se apoya sobre todo en supuestos por clase de activo, y los fondos internacionales en proxies.
3. Los umbrales de perfil son un supuesto razonable, no una norma del banco.
4. Los precios de mercado vienen de Yahoo Finance, cuya licencia limita su redistribución; la foto en `mercado/` se incluye solo para reproducir la prueba.

## Mantenimiento

1. Si modificas una vista SQL, vuelve a correr `python scripts/preparar_todo.py` para refrescar las tablas que lee la aplicación.
2. Para volver a descargar precios de mercado: `python scripts/preparar_todo.py --descargar-mercado`. Los resultados pueden cambiar respecto a la foto incluida.
3. `python scripts/smoke_test.py` verifica en cualquier momento que la aplicación responde con las cifras esperadas.

## Solución de problemas

1. **El puerto está ocupado.** Cambia `DB_PORT` en el `.env` por otro libre (por ejemplo 5434) y repite `docker compose up -d`.
2. **Docker dice que no detecta la virtualización.** Activa en Windows las características "Plataforma de máquina virtual" y "Subsistema de Windows para Linux", reinicia y ejecuta `wsl --install`.
3. **`python` no se encuentra o un script no muestra nada.** El entorno virtual no está activo: repite la activación del paso 5.
4. **`password authentication failed`.** La clave del `.env` no coincide con la de la base. Si usas Docker y cambiaste la clave después de crear la base, recréala con `docker compose down -v` y `docker compose up -d`.
5. **El resumen de IA muestra un aviso.** Ollama no está corriendo o el modelo no está descargado; el mensaje indica cuál de las dos.
