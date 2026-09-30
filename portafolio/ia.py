"""Resumen ejecutivo de un cliente con un modelo de lenguaje local (Ollama).

El modelo no consulta la base ni calcula nada: solo redacta a partir de los hechos
que arma este módulo con las mismas consultas SQL de la app."""
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request

from django.core.cache import cache
from django.db import DatabaseError

from . import servicios
from .models import ConsultaSQL

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
TIMEOUT = 180

VERSION_PROMPT = 5

INSTRUCCIONES = """Eres un asistente para gerentes comerciales de inversión de Valores Bancolombia.
Redactas un resumen ejecutivo de UN cliente usando ÚNICAMENTE los datos que se te entregan.
Reglas obligatorias:
1. No inventes cifras, productos, fechas ni hechos que no estén en los datos.
2. Copia las cifras exactamente como aparecen en los datos, sin recalcularlas.
3. Si un dato no está, no lo menciones ni lo supongas.
4. No recomiendes productos, inversiones ni acciones concretas: los próximos pasos
   los agrega el sistema a partir de reglas, y la decisión es del gerente.
5. Escribe en español de Colombia, con tono profesional y claro. Máximo 130 palabras.
6. Usa exactamente dos secciones, cada título en su propia línea y en mayúsculas:
SITUACIÓN y ALERTAS. En ALERTAS resume en dos o tres frases los riesgos y temas
urgentes, empezando por lo de prioridad ALTA. No copies la lista de oportunidades
ni uses corchetes: el sistema la agrega después. Texto plano, sin markdown.
7. La comparación entre el riesgo del portafolio y el perfil declarado ya viene
escrita en los datos: úsala tal cual, sin cambiar su sentido.
8. Llama urgente solo a lo que tenga prioridad ALTA."""

GLOSARIO = ("Glosario: CDT es un Certificado de Depósito a Término, emitido por bancos. "
            "FIC es un Fondo de Inversión Colectiva. HHI es un índice de concentración "
            "(1 significa todo en una sola posición). TRM es la tasa de cambio peso dólar. "
            "Nota estructurada: producto cuyo rendimiento está ligado a índices bursátiles. "
            "El nivel de riesgo inferido describe el portafolio, no la tolerancia al riesgo "
            "del cliente, que solo se define con el perfilamiento.")            

COMPARACION = {
    "SIN PERFIL DECLARADO": "El cliente no tiene perfil de riesgo declarado, así que no hay "
                            "comparación posible: el perfilamiento está pendiente.",
    "MAS RIESGO QUE SU PERFIL": "El portafolio tiene MÁS riesgo del que corresponde a su perfil "
                                "declarado {declarado}.",
    "MENOS RIESGO QUE SU PERFIL": "El portafolio tiene MENOS riesgo del que permite su perfil "
                                  "declarado {declarado}.",
    "COHERENTE": "El nivel de riesgo del portafolio es coherente con su perfil declarado {declarado}.",
}

ACCIONES = {
    "Vencimiento próximo": "Preparar la propuesta de reinversión",
    "Revisar idoneidad": "Revisar la idoneidad del portafolio frente al perfil declarado",
    "Perfilamiento pendiente": "Completar el perfilamiento de riesgo del cliente",
    "Capacidad de riesgo sin usar": "Presentar alternativas acordes a su perfil declarado",
    "Diversificación internacional": "Evaluar con el cliente alternativas de diversificación internacional",
    "Liquidez ociosa": "Revisar con el cliente el destino de la liquidez",
    "Concentración alta": "Revisar la concentración del portafolio",
    "Posiciones sin identificar": "Corregir en las fuentes de datos las posiciones sin identificar",
}
ORDEN = {"ALTA": 1, "MEDIA": 2, "BAJA": 3}


def _fmt(numero, decimales=0):
    texto = f"{numero:,.{decimales}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _pesos(valor):
    if valor is None:
        return "no disponible"
    if abs(valor) >= 1e6:
        return f"$ {_fmt(valor / 1e6, 1)} millones"
    return f"$ {_fmt(valor)}"


def _posiciones(n):
    return f"{n} posición" if n == 1 else f"{n} posiciones"


def _seguro(slug, params):
    try:
        return servicios.ejecutar(slug, params)
    except (DatabaseError, ConsultaSQL.DoesNotExist):
        return []


def _composicion(filas):
    return ", ".join(f"{f['clase']} {_fmt(f['pct'], 1)} %" for f in filas) or "sin datos"


def _ordenar(oportunidades):
    """Por prioridad; dentro de la misma prioridad, primero lo que tiene fecha limite."""
    return sorted(oportunidades, key=lambda o: (
        ORDEN.get(o["prioridad"], 9), o["tipo"] != "Vencimiento próximo", -(o["monto_cop"] or 0)))


def proximos_pasos(oportunidades):
    """Seccion armada por reglas, no por el modelo: cada paso sale de una oportunidad."""
    if not oportunidades:
        return "PRÓXIMOS PASOS\nSin oportunidades detectadas: mantener el seguimiento habitual."
    lineas = ["PRÓXIMOS PASOS"]
    for i, o in enumerate(oportunidades, 1):
        accion = ACCIONES.get(o["tipo"], o["tipo"])
        lineas.append(f"{i}. [{o['prioridad']}] {accion}. {o['detalle']}.")
    return "\n".join(lineas)


def hechos_cliente(id_cliente):
    """Arma en texto los hechos del cliente y la lista de oportunidades ordenada.
    Lanza LookupError si el cliente no existe."""
    p = {"id_cliente": id_cliente}
    r = _seguro("resumen_cliente", p)
    if not r:
        raise LookupError(id_cliente)
    r = r[0]
    m = (_seguro("modelo_cliente", p) or [None])[0]

    lineas = [f"Cliente: {id_cliente}"]
    if r["id_tipo"] == "TRUNCADO":
        lineas.append("Nota: el ID llegó truncado, no se puede cruzar con el portafolio internacional.")
    lineas.append(f"Banca: {r['banca'] or 'no disponible'}. "
                  f"Perfil de riesgo declarado: {r['perfil_riesgo'] or 'no disponible'}.")
    lineas.append(f"Portafolio local (COP) al {r['fecha_cop']:%d/%m/%Y}: {_pesos(r['aba_cop'])}, "
                  f"en {_posiciones(r['n_pos_cop'])}.")
    lineas.append("Composición local: " + _composicion(_seguro("cop_por_clase", p)) + ".")

    if r["tiene_usd"]:
        linea = (f"Portafolio internacional (USD) al {r['fecha_usd']:%d/%m/%Y}: "
                 f"US$ {_fmt(r['valor_usd'])}, en {_posiciones(r['n_pos_usd'])}")
        if r.get("valor_usd_en_cop") is not None:
            linea += f", equivalente a {_pesos(r['valor_usd_en_cop'])} con TRM de {_fmt(r['trm'], 2)}"
        lineas.append(linea + ".")
        lineas.append("Composición internacional: " + _composicion(_seguro("usd_por_tipo", p)) + ".")
    else:
        lineas.append("No tiene portafolio internacional registrado.")

    lineas.append(f"Total consolidado: {_pesos(r['total_consolidado_cop'])}.")
    if r.get("pct_internacional") is not None:
        lineas.append(f"Exposición internacional: {_fmt(r['pct_internacional'], 1)} %.")

    if m:
        lineas.append(f"Segmento del modelo: {m['segmento'] or 'no disponible'}.")
        lineas.append(f"Nivel de riesgo del portafolio, inferido por el modelo: {m['perfil_inferido']}.")
        comparacion = COMPARACION.get(m["coherencia"], m["coherencia"])
        lineas.append("Comparación: " + comparacion.format(declarado=m["perfil_declarado"]))
        lineas.append(f"Riesgo de mercado: {_fmt(m['riesgo_mercado'], 1)} % anual sin efecto cambiario; "
                      f"{_fmt(m['riesgo_total_con_fx'], 1)} % con efecto de la TRM.")
        if m["confianza_dato"] == "BAJA":
            lineas.append("Confianza del dato de riesgo: BAJA, se apoya en supuestos por clase de activo.")
        if not m["clasificacion_estable"]:
            lineas.append("El perfil inferido cambia si se mueven los umbrales: tomarlo como indicativo.")

    oportunidades = _ordenar(_seguro("oportunidades_cliente", p))
    if oportunidades:
        lineas.append(f"Oportunidades detectadas ({len(oportunidades)}):")
        for o in oportunidades:
            lineas.append(f"[{o['prioridad']}] {o['tipo']}: {o['detalle']}. "
                          f"Monto asociado: {_pesos(o['monto_cop'])}.")
    else:
        lineas.append("Oportunidades detectadas: ninguna.")

    lineas.append(GLOSARIO)
    return "\n".join(lineas), oportunidades


NUMERO = re.compile(r"\d[\d.,]*\d|\d")


def _a_numero(token):
    """Convierte un numero en formato colombiano a (valor, decimales). None si no se puede."""
    t = token.strip(".,")
    try:
        if "," in t:
            entero, _, dec = t.rpartition(",")
            return float(entero.replace(".", "") + "." + dec), len(dec)
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
            return float(t.replace(".", "")), 0
        return float(t), len(t.split(".")[1]) if "." in t else 0
    except ValueError:
        return None, 0


def cifras_no_verificadas(texto, hechos):
    """Numeros del texto (de 2 o mas digitos) que no estan en los hechos, ni tal cual
    ni como redondeo de alguna cifra de los hechos (por ejemplo 100,0 escrito como 100)."""
    solo_digitos = lambda s: re.sub(r"\D", "", s)
    fichas = NUMERO.findall(hechos)
    base_txt = {solo_digitos(n) for n in fichas}
    base_num = [v for v, _ in map(_a_numero, fichas) if v is not None]
    fuera = set()
    for n in NUMERO.findall(texto):
        if len(solo_digitos(n)) < 2 or solo_digitos(n) in base_txt:
            continue
        valor, dec = _a_numero(n)
        if valor is not None and any(round(b, dec) == valor for b in base_num):
            continue
        fuera.add(n.strip(".,"))
    return sorted(fuera)


def _llamar_ollama(hechos):
    cuerpo = json.dumps({
        "model": OLLAMA_MODEL,
        "stream": False,
        "options": {"temperature": 0.2},
        "messages": [
            {"role": "system", "content": INSTRUCCIONES},
            {"role": "user", "content": "Datos del cliente:\n" + hechos},
        ],
    }).encode("utf-8")
    peticion = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat", data=cuerpo, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(peticion, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))["message"]["content"].strip()


def generar_resumen(id_cliente):
    """Devuelve un dict listo para JSON con el resumen o con el motivo del error."""
    hechos, oportunidades = hechos_cliente(id_cliente)
    firma = f"{VERSION_PROMPT}|{OLLAMA_MODEL}|{hechos}"
    clave = "ia:" + hashlib.sha256(firma.encode("utf-8")).hexdigest()
    guardado = cache.get(clave)
    if guardado:
        return {**guardado, "desde_cache": True}

    inicio = time.perf_counter()
    try:
        texto = _llamar_ollama(hechos)
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "ignore")
        return {"ok": False, "hechos": hechos,
                "error": f"Ollama respondió con error ({e.code}). Verifica que el modelo "
                         f"{OLLAMA_MODEL} esté descargado con: ollama pull {OLLAMA_MODEL}. "
                         f"Detalle: {detalle[:200]}"}
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        return {"ok": False, "hechos": hechos,
                "error": f"No se pudo conectar con Ollama en {OLLAMA_URL}. Verifica que esté "
                         f"instalado y corriendo. El resto de la app funciona sin IA. ({e})"}

    # si el modelo escribe pasos por su cuenta, se descartan: esa seccion la arma el sistema
    texto = re.split(r"\n\s*PR[OÓ]XIMOS PASOS", texto, flags=re.IGNORECASE)[0].strip()
    texto = re.sub(r"\[(ALTA|MEDIA|BAJA)\]\s*", "", texto)
    resultado = {
        "ok": True,
        "texto": texto + "\n\n" + proximos_pasos(oportunidades),
        "modelo": OLLAMA_MODEL,
        "segundos": round(time.perf_counter() - inicio, 1),
        "cifras_no_verificadas": cifras_no_verificadas(texto, hechos),
        "hechos": hechos,
        "desde_cache": False,
    }
    cache.set(clave, resultado, 60 * 60 * 24)
    return resultado