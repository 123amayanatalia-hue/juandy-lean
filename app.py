# -*- coding: utf-8 -*-
"""
Juandy Lean · Aplicación de control para el operario
Panadería Juandy S.A.S. · Cartagena de Indias · Proyecto 7S8G04

Ejecutar:  streamlit run app.py
"""
import base64
import html
import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import streamlit as st

# =====================================================================
# 1. CONFIGURACIÓN (puedes cambiar estos valores)
# =====================================================================
MODO_DEMO = True        # True: datos de ejemplo del PDF. False: uso real, sin registros.
PIN_JEFE = "1234"       # Clave del jefe de producción (cámbiala).
URL_APP = ""            # Dirección pública de la app, para el QR. Ej: "https://juandy.streamlit.app"
HORAS_POR_VENCER = 6    # Un lote pasa a "Por vencer" cuando le quedan estas horas o menos.

ZONA = timezone(timedelta(hours=-5))               # Colombia
INICIO_DEMO = datetime(2026, 11, 26, 7, 55)        # Momento que muestra la demostración
INICIO_PLAN = datetime(2026, 10, 26).date()        # Lunes de la semana 1 del plan de 12 semanas
LINEA_BASE = 30.6
META = 19.9
ARCHIVO = Path(__file__).with_name(f"datos_juandy_{'demo' if MODO_DEMO else 'real'}.json")

st.set_page_config(page_title="Juandy Lean", page_icon="🥖", layout="wide",
                   initial_sidebar_state="expanded")

# =====================================================================
# 2. CATÁLOGOS
# =====================================================================
PRODUCTOS = {
    "queso":      {"nombre": "Pan de queso",         "corto": "Queso",          "demanda": 64, "peso": 35.2, "relleno": "queso"},
    "bocadillo":  {"nombre": "Pan de bocadillo",     "corto": "Bocadillo",      "demanda": 36, "peso": 20.1, "relleno": "bocadillo"},
    "arequipe":   {"nombre": "Pan de arequipe",      "corto": "Arequipe",       "demanda": 27, "peso": 15.0, "relleno": "arequipe"},
    "jamon":      {"nombre": "Pan de jamón y queso", "corto": "Jamón y queso",  "demanda": 27, "peso": 14.9, "relleno": "jamón y queso"},
    "mantequilla": {"nombre": "Pan de mantequilla",  "corto": "Mantequilla",    "demanda": 27, "peso": 14.9, "relleno": "mantequilla"},
}
DEMANDA_TOTAL = 182
for _p in PRODUCTOS.values():
    _p["peso_texto"] = f"{_p['peso']:.1f}".replace(".", ",")

NAVEGACION = [
    ("OPERACIÓN", [("inicio", "Inicio"), ("cronograma", "Cronograma"), ("produccion", "Producción")]),
    ("ALMACENAMIENTO", [("inventario", "Inventario y PEPS"), ("lotes", "Registro por lote")]),
    ("PROCEDIMIENTOS", [("procedimientos", "Procedimientos"), ("fichas", "Fichas técnicas"), ("verificacion", "Verificación")]),
    ("CALIDAD", [("inconformidades", "Inconformidades"), ("indicadores", "Indicadores")]),
]
TITULOS = {k: v for _, grupo in NAVEGACION for k, v in grupo}

PASOS = ["Recepción e inspección", "Pesaje", "Mezclado y amasado", "Porcionado y formado",
         "Horneado", "Verificación", "Etiquetado y almacenamiento"]

TABLA_PROCEDIMIENTO = [
    ("Recepción e inspección", "Revisar empaque, olor, impurezas y fecha de vencimiento. Registrar el lote del proveedor.", "Cumple / no cumple por insumo", "Verificación · bloque 1", "Operario de recepción"),
    ("Pesaje", "Poner la báscula en cero; pesar cada ingrediente según la ficha técnica.", "Peso real vs. peso de la ficha", "Procedimientos (paso 2)", "Operario de producción"),
    ("Mezclado y amasado", "Respetar el orden de ingredientes y el tiempo de amasado; evaluar la consistencia.", "Tiempo (min) y consistencia correcta", "Procedimientos (paso 3)", "Operario de producción"),
    ("Porcionado y formado", "Cortar con porcionador o molde; pesar la porción; rayar y agregar el relleno estándar.", "Peso de la porción ± tolerancia en 5 unidades", "Procedimientos (paso 4)", "Operario de producción"),
    ("Horneado", "Precalentar; hornear con temporizador y termómetro; anotar temperatura y tiempo.", "Temperatura (°C) y tiempo (min) por tanda", "Procedimientos (paso 5)", "Hornero"),
    ("Verificación", "Comparar color, cocción y tamaño con la muestra patrón; liberar o apartar.", "Conforme / no conforme y disposición", "Verificación · bloque 4", "Responsable de calidad del turno"),
    ("Etiquetado y almacenamiento", "Registrar el lote, etiquetar fecha y hora, ubicar con PEPS y actualizar el inventario.", "Etiqueta colocada; lote en el inventario", "Registro por lote · Inventario", "Operario de almacenamiento"),
]

BLOQUES = {
    1: ("Recepción", ["Empaque en buen estado", "Olor normal y sin impurezas", "Fecha de vencimiento vigente", "Lote del proveedor registrado"]),
    2: ("Pesaje y mezclado", ["Báscula puesta en cero", "Ingredientes pesados según la ficha", "Orden de ingredientes respetado", "Tiempo de amasado y consistencia correctos"]),
    3: ("Porcionado", ["Peso de la porción dentro de tolerancia (5 unidades)", "Relleno estándar agregado", "Formado y rayado correctos"]),
    4: ("Horneado y almacenamiento", ["Temperatura y tiempo registrados por tanda", "Color y cocción conformes", "Etiqueta de fecha y hora colocada", "Producto ubicado con PEPS"]),
}

MOTIVOS = {"C": ("Calidad", "Calidad, textura o sabor"), "F": ("Frescura", "Frescura"),
           "T": ("Tamaño o relleno", "Tamaño o relleno"), "D": ("Disponibilidad", "Disponibilidad"),
           "E": ("Tiempo de espera", "Tiempo de espera")}

PARAMETROS = [  # clave, nombre, unidad
    ("masa", "Peso de la masa", "g"), ("relleno", "Peso del relleno", "g"),
    ("amasado", "Tiempo de amasado", "min"), ("temperatura", "Temperatura de horneado", "°C"),
    ("horneado", "Tiempo de horneado", "min"), ("vida", "Vida útil antes de venta", "h"),
]

CRITERIOS = "Color dorado uniforme · cocción completa · tamaño igual a la muestra patrón"
INSTRUMENTOS = "Báscula 5 kg · porcionador y molde · termómetro de sonda · temporizador"

ACTIVIDADES_TURNO = [("05:00", "Recepción e inspección"), ("05:30", "Pesaje de ingredientes"),
                     ("06:00", "Mezclado y amasado"), ("06:45", "Porcionado y formado"),
                     ("07:30", "Horneado · tanda 1 queso"), ("08:30", "Verificación y etiquetado"),
                     ("09:00", "Almacenar con PEPS"), ("10:30", "Revisión Kanban")]

FRENTES = [("Línea base y registro", 0, 2, "#3f6b94"), ("Estandarización", 1, 5, "#d9a441"),
           ("Programación e inventario", 3, 8, "#b5472f"), ("5S y almacenamiento", 2, 6, "#4e8a5a"),
           ("Control en la fuente", 4, 8, "#7a5a8c"), ("Cliente, capacitación, Kaizen", 5, 12, "#3e2a1f")]

# Cifras de ejemplo de la semana 5 (solo en modo demostración)
BASE_DEMO = {"motivos": {"C": 12, "F": 8, "T": 6, "D": 9, "E": 4},
             "por_producto": {"queso": 15, "bocadillo": 8, "arequipe": 6, "jamon": 5, "mantequilla": 5},
             "pedidos": 156, "producidas": 500, "desechadas": 45,
             "verif_ok": 44, "verif_total": 50, "agotados": 3, "descartados": 1}
TENDENCIA_DEMO = {1: 31, 2: 30, 3: 28, 4: 27}


# =====================================================================
# 3. UTILIDADES
# =====================================================================
def ahora():
    if MODO_DEMO:
        if "t0" not in st.session_state:
            st.session_state.t0 = datetime.now()
        return INICIO_DEMO + (datetime.now() - st.session_state.t0)
    return datetime.now(ZONA).replace(tzinfo=None)


def iso(d):
    return d.isoformat(timespec="seconds")


def fecha(txt):
    return datetime.fromisoformat(txt)


DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def turno(d):
    return "mañana" if d.hour < 12 else ("tarde" if d.hour < 18 else "noche")


def num(x, dec=1):
    """Número con coma decimal; sin decimales si es entero."""
    if x is None:
        return "—"
    x = round(float(x), dec)
    return str(int(x)) if x == int(x) else f"{x:.{dec}f}".replace(".", ",")


def e(x):
    return html.escape(str(x))


def H(contenido):
    """Dibuja HTML (en una sola línea para que Markdown no lo tome como código)."""
    st.markdown(" ".join(l.strip() for l in contenido.splitlines() if l.strip()),
                unsafe_allow_html=True)


def pill(texto, color):
    return f'<span class="pill {color}">{e(texto)}</span>'


def barra(fraccion, color="verde"):
    ancho = max(0, min(1, fraccion)) * 100
    return f'<div class="barra"><div class="{color}" style="width:{ancho:.0f}%"></div></div>'


def tabla(encabezados, filas):
    th = "".join(f"<th>{e(x)}</th>" for x in encabezados)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in f) + "</tr>" for f in filas)
    H(f'<div class="scroll"><table class="jl"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>')


def titulo(texto, sub=""):
    H(f'<div><div class="titulo">{e(texto)}</div><div class="sub">{e(sub)}</div></div>')


def h4(texto, extra=""):
    H(f'<div class="h4">{e(texto)} {extra}</div>')


def kpi(valor, texto, estilo=""):
    H(f'<div class="kpi {estilo}"><b>{e(valor)}</b><span>{e(texto)}</span></div>')


def tarjeta(nombre):
    return st.container(key=f"card_{nombre}")


def aviso(mensaje, tipo="success"):
    st.session_state.setdefault("avisos", []).append((tipo, mensaje))


def siguiente(nombre):
    """Cambia la clave de un formulario para dejarlo limpio después de guardar."""
    st.session_state[f"n_{nombre}"] = st.session_state.get(f"n_{nombre}", 0) + 1


def n(nombre):
    return st.session_state.get(f"n_{nombre}", 0)


# =====================================================================
# 4. DATOS Y GUARDADO
# =====================================================================
def ficha_vacia():
    f = {k: {"valor": None, "tol": None} for k, _, _ in PARAMETROS}
    f.update(version=0, criterios=CRITERIOS, instrumentos=INSTRUMENTOS)
    return f


def ficha_ejemplo():
    valores = {"masa": (60, 3), "relleno": (15, 2), "amasado": (12, 1),
               "temperatura": (180, 5), "horneado": (18, 2), "vida": (24, None)}
    f = {k: {"valor": v, "tol": t} for k, (v, t) in valores.items()}
    f.update(version=1, criterios=CRITERIOS, instrumentos=INSTRUMENTOS)
    return f


def datos_iniciales():
    db = {
        "lotes": [], "saldo_inicial": {}, "historial": [], "ventas": [], "desechos": [],
        "inconformidades": [], "encuestas": [], "mediciones": [], "problemas": [], "agotados": [],
        "procesos": {p: {"paso": 1, "unidades": 0, "no_conforme": False} for p in PRODUCTOS},
        "fichas": {p: ficha_vacia() for p in PRODUCTOS},
        "turno": {"fecha": str(ahora().date()), "horas": [h for h, _ in ACTIVIDADES_TURNO], "actual": 0},
        "bodega": {"temp": None, "hum": None},
    }
    if not MODO_DEMO:
        return db

    hoy = INICIO_DEMO.replace(hour=0, minute=0)
    ayer = hoy - timedelta(days=1)

    def lote(codigo, prod, horneado, vence, inicial, disp, bloques):
        verif = {str(b): {"fecha": iso(horneado), "resultados": [True] * len(BLOQUES[b][1]), "accion": ""}
                 for b in bloques}
        return {"codigo": codigo, "producto": prod, "horneado": iso(horneado), "vence": iso(vence),
                "inicial": inicial, "disponible": disp, "responsable": "Carlos M.", "observacion": "",
                "verif": verif, "bloqueo": False, "retirado": False}

    t = lambda d, h, m: d.replace(hour=h, minute=m)
    db["lotes"] = [
        lote("L-20261125-02", "arequipe", t(ayer, 11, 20), t(hoy, 7, 20), 36, 12, [1, 2, 3, 4]),
        lote("L-20261125-03", "bocadillo", t(ayer, 15, 10), t(hoy, 12, 25), 36, 30, [1, 2, 3, 4]),
        lote("L-20261126-01", "jamon", t(hoy, 5, 50), t(hoy, 5, 50) + timedelta(hours=24), 27, 25, [1, 2, 3, 4]),
        lote("L-20261126-02", "queso", t(hoy, 6, 40), t(hoy, 6, 40) + timedelta(hours=24), 64, 5, [1, 2]),
    ]
    db["saldo_inicial"] = {"arequipe": 9, "mantequilla": 12}
    db["historial"] = [
        {"fecha": iso(t(hoy, 6, 10)), "lote": "L-20261126-02", "bloque": 2, "cumple": True},
        {"fecha": iso(t(hoy, 6, 55)), "lote": "L-20261126-01", "bloque": 3, "cumple": True},
        {"fecha": iso(t(hoy, 5, 5)), "lote": "L-20261126-02", "bloque": 1, "cumple": True},
        {"fecha": iso(t(ayer, 16, 0)), "lote": "L-20261125-03", "bloque": 4, "cumple": False},
    ]
    for p in ("queso", "bocadillo", "arequipe"):
        db["fichas"][p] = ficha_ejemplo()
    db["procesos"]["queso"] = {"paso": 4, "unidades": 3, "no_conforme": False}
    db["turno"]["actual"] = 3
    db["bodega"] = {"temp": 24, "hum": 62}
    return db


@st.cache_resource
def candado():
    return threading.RLock()


def guardar(db):
    temporal = ARCHIVO.with_suffix(".tmp")
    temporal.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(temporal, ARCHIVO)


def cargar():
    with candado():
        if not ARCHIVO.exists():
            guardar(datos_iniciales())
        db = json.loads(ARCHIVO.read_text(encoding="utf-8"))
        hoy = str(ahora().date())
        if db["turno"]["fecha"] != hoy:  # nuevo día: el turno empieza de cero
            db["turno"].update(fecha=hoy, actual=0)
            guardar(db)
        return db


@contextmanager
def transaccion():
    with candado():
        db = cargar()
        yield db
        guardar(db)


# =====================================================================
# 5. REGLAS DEL NEGOCIO
# =====================================================================
def buscar_lote(db, codigo):
    return next((l for l in db["lotes"] if l["codigo"] == codigo), None)


def verificacion_fallida(lote):
    return any(not all(v["resultados"]) for v in lote["verif"].values())


def estado(lote, t=None):
    t = t or ahora()
    if lote["retirado"]:
        return "Retirado"
    if lote["disponible"] <= 0:
        return "Agotado"
    if t >= fecha(lote["vence"]):
        return "Vencido"
    if lote["bloqueo"] or verificacion_fallida(lote):
        return "Bloqueado"
    if fecha(lote["vence"]) - t <= timedelta(hours=HORAS_POR_VENCER):
        return "Por vencer"
    return "Vigente"


COLOR_ESTADO = {"Vigente": "verde", "Por vencer": "oro", "Vencido": "rojo",
                "Bloqueado": "rojo", "Agotado": "gris", "Retirado": "gris"}


def lotes_peps(db, producto=None):
    """Lotes en inventario, del más antiguo al más nuevo."""
    ls = [l for l in db["lotes"] if not l["retirado"] and l["disponible"] > 0
          and (producto is None or l["producto"] == producto)]
    return sorted(ls, key=lambda l: l["horneado"])


def existencias(db, producto):
    vendibles = sum(l["disponible"] for l in lotes_peps(db, producto)
                    if estado(l) in ("Vigente", "Por vencer"))
    return vendibles + db["saldo_inicial"].get(producto, 0)


def kanban(db, producto):
    """Señal de reposición: inventario vigente menor al 50 % de la demanda diaria."""
    hay, demanda = existencias(db, producto), PRODUCTOS[producto]["demanda"]
    hornear = demanda - hay if hay < demanda * 0.5 else 0
    return hay, demanda, hornear


def prioridades(db):
    """Puntaje = NPR de la etapa × urgencia."""
    acciones = []

    def agregar(npr, urgencia, texto, detalle, destino, **extra):
        puntaje = npr * urgencia
        nivel = "Alta" if puntaje >= 800 else ("Media" if puntaje >= 500 else "Baja")
        puntos = f"{puntaje:,}".replace(",", ".")
        acciones.append({"puntaje": puntaje, "nivel": nivel, "texto": texto,
                         "detalle": f"{detalle}NPR {npr} × {urgencia} = {puntos}",
                         "destino": destino, "extra": extra})

    for pid, p in PRODUCTOS.items():
        hay, demanda, hornear = kanban(db, pid)
        if hornear:
            urg = 5 if hay == 0 else (4 if hay < demanda * 0.2 else 3)
            agregar(252, urg, f"Hornear {hornear} unidades de {p['nombre']}",
                    f"Inventario {hay} de {demanda} · ", "procedimientos", producto=pid)
    for l in lotes_peps(db):
        est, corto = estado(l), PRODUCTOS[l["producto"]]["corto"].lower()
        if est == "Vencido":
            agregar(175, 5, f"Retirar lote {l['codigo']} vencido ({l['disponible']} u.)",
                    "Almacenamiento · ", "inventario")
        elif est == "Por vencer":
            horas = (fecha(l["vence"]) - ahora()).total_seconds() / 3600
            agregar(175, 4, f"Vender primero lote {l['codigo']} ({corto})",
                    f"Quedan {num(horas)} h · ", "inventario", producto=l["producto"])
    for l in lotes_peps(db):
        est = estado(l)
        if est == "Bloqueado":
            agregar(120, 5, f"Revisar lote bloqueado {l['codigo']}", "No se puede vender · ",
                    "verificacion", lote=l["codigo"])
        elif est != "Vencido" and len(l["verif"]) < 4:
            agregar(120, 3, f"Completar verificación del lote {l['codigo']}",
                    f"Faltan {4 - len(l['verif'])} de 4 bloques · ", "verificacion", lote=l["codigo"])
    for pid, p in PRODUCTOS.items():
        if not ficha_completa(db["fichas"][pid]):
            agregar(210, 1, f"Completar ficha técnica de {p['nombre']}", "Faltan valores · ",
                    "fichas", producto=pid)
    return sorted(acciones, key=lambda a: -a["puntaje"])


def ficha_completa(f):
    return all(f[k]["valor"] is not None and (k == "vida" or f[k]["tol"] is not None)
               for k, _, _ in PARAMETROS)


def dentro(valor, parametro):
    """True / False si cumple la tolerancia; None si la ficha no la tiene definida."""
    if parametro["valor"] is None or parametro["tol"] is None:
        return None
    return abs(valor - parametro["valor"]) <= parametro["tol"] + 1e-9


def crear_lote(db, producto, cantidad, responsable, observacion, bloqueado=False):
    t = ahora().replace(microsecond=0)
    prefijo = f"L-{t:%Y%m%d}-"
    ultimo = max([int(l["codigo"].split("-")[-1]) for l in db["lotes"]
                  if l["codigo"].startswith(prefijo)] or [0])
    vida = db["fichas"][producto]["vida"]["valor"] or 24
    lote = {"codigo": f"{prefijo}{ultimo + 1:02d}", "producto": producto, "horneado": iso(t),
            "vence": iso(t + timedelta(hours=vida)), "inicial": int(cantidad),
            "disponible": int(cantidad), "responsable": responsable, "observacion": observacion,
            "verif": {}, "bloqueo": bloqueado, "retirado": False, "nuevo": True}
    db["lotes"].append(lote)
    return lote


def vender(db, producto, cantidad):
    """Descuenta primero lo más antiguo; nunca de un lote vencido o bloqueado."""
    disponible = existencias(db, producto)
    if cantidad > disponible:
        return None, f"Solo hay {disponible} unidades vigentes. No se registró la venta."
    resto, detalle = cantidad, []
    saldo = db["saldo_inicial"].get(producto, 0)
    if saldo:
        usa = min(saldo, resto)
        db["saldo_inicial"][producto] = saldo - usa
        resto -= usa
        detalle.append(f"{usa} del conteo inicial")
    for l in lotes_peps(db, producto):
        if resto == 0:
            break
        if estado(l) in ("Vigente", "Por vencer"):
            usa = min(l["disponible"], resto)
            l["disponible"] -= usa
            resto -= usa
            detalle.append(f"{usa} del lote {l['codigo']}")
    t = iso(ahora())
    db["ventas"].append({"fecha": t, "producto": producto, "cantidad": cantidad, "detalle": detalle})
    if existencias(db, producto) == 0:
        db["agotados"].append({"fecha": t, "producto": producto})
    return detalle, None


def retirar(db, lote):
    db["desechos"].append({"fecha": iso(ahora()), "lote": lote["codigo"], "producto": lote["producto"],
                           "cantidad": lote["disponible"], "vencido": estado(lote) == "Vencido"})
    lote["disponible"] = 0
    lote["retirado"] = True


def semana_de(d):
    return (d - INICIO_PLAN).days // 7 + 1


def indicadores(db, semana):
    en = lambda lista: [r for r in lista if semana_de(fecha(r["fecha"]).date()) == semana]
    base = BASE_DEMO if MODO_DEMO and semana == semana_de(INICIO_DEMO.date()) else None
    motivos = {m: (base["motivos"][m] if base else 0) for m in MOTIVOS}
    por_prod = {p: (base["por_producto"][p] if base else 0) for p in PRODUCTOS}
    for r in en(db["inconformidades"]):
        motivos[r["motivo"]] += 1
        por_prod[r["producto"]] += 1
    b = lambda k: base[k] if base else 0
    pedidos = b("pedidos") + len(en(db["ventas"]))
    nuevos = [{"fecha": l["horneado"], "u": l["inicial"]} for l in db["lotes"] if l.get("nuevo")]
    producidas = b("producidas") + sum(x["u"] for x in en(nuevos))
    desechadas = b("desechadas") + sum(x["cantidad"] for x in en(db["desechos"]))
    checks = [r for r in en(db["historial"]) if "total" in r]
    v_ok = b("verif_ok") + sum(r["ok"] for r in checks)
    v_total = b("verif_total") + sum(r["total"] for r in checks)
    quejas = sum(motivos.values())
    return {
        "motivos": motivos, "por_producto": por_prod,
        "tasa": 100 * quejas / pedidos if pedidos else None,
        "desecho": 100 * desechadas / producidas if producidas else None,
        "cumplen": 100 * v_ok / v_total if v_total else None,
        "agotados": b("agotados") + len(en(db["agotados"])),
        "descartados": b("descartados") + len([d for d in en(db["desechos"]) if d["vencido"]]),
        "problemas": len(en(db["problemas"])),
    }


# =====================================================================
# 6. ESTILO (colores del PDF)
# =====================================================================
ESTILO = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
:root{--cafe:#3e2a1f;--lateral:#5a4030;--oro:#d9a441;--crema:#fbf6ec;--borde:#e8d3ac;--rojo:#b5472f;--verde:#4e8a5a;--suave:#fdf4e1;--gris:#8a7d72}
.stApp{background:var(--crema);color:var(--cafe);font-family:'Inter',sans-serif}
.stApp p,.stApp label,.stApp input,.stApp textarea,.stApp button{font-family:'Inter',sans-serif}
.stApp label p,[data-testid="stMain"] p{color:var(--cafe)}
[data-testid="stHeader"]{background:transparent}
[data-testid="stToolbarActions"],[data-testid="stAppDeployButton"],#MainMenu,footer{display:none}
[data-testid="stMainBlockContainer"],.block-container{padding-top:3.6rem;max-width:1180px}
[data-testid="stSidebar"]{background:var(--lateral)}
.grupo{color:var(--oro);font-size:.72rem;font-weight:800;letter-spacing:.06em;margin-top:.5rem}
[class*="st-key-nav_"],[class*="st-key-nav_"] .stButton,[class*="st-key-nav_"] button{width:100%}
 .stApp [class*="st-key-nav_"] button{background:transparent;border:0;border-radius:6px;justify-content:flex-start;min-height:2.2rem;padding:.2rem .7rem}
[class*="st-key-nav_"] button div{justify-content:flex-start}
[class*="st-key-nav_"] button p{color:#f6ead6!important;font-size:.9rem}
 .stApp [class*="st-key-nav_"] button:hover{background:rgba(255,255,255,.1)}
[data-testid="stSidebar"] [data-testid="stExpander"]{background:var(--crema);border-radius:8px;margin-top:1rem}
.topbar{background:var(--cafe);border-radius:12px;padding:.7rem 1rem;display:flex;align-items:center;gap:.7rem;flex-wrap:wrap;color:#fff}
.logo{background:var(--oro);color:var(--cafe);font-weight:900;border-radius:7px;width:2rem;height:2rem;display:flex;align-items:center;justify-content:center}
.topbar .marca{font-weight:800}.topbar .ok{margin-left:auto;color:#a9dcb3;font-size:.8rem}
.topbar .turno{background:#5a4030;border-radius:20px;padding:.25rem .8rem;font-size:.8rem}
.titulo{font-size:1.5rem;font-weight:800;color:var(--cafe);line-height:1.2}
.sub{font-size:.85rem;color:var(--gris);margin-bottom:.2rem}
.h4{font-weight:800;font-size:.98rem;color:var(--cafe)}
[class*="st-key-card_"]{background:#fff;border:1px solid var(--borde);border-radius:12px;padding:1rem}
.kpi{background:#fff;border:1px solid var(--borde);border-radius:12px;padding:.7rem 1rem;min-height:6rem;margin-bottom:.3rem}
.kpi b{display:block;font-size:1.7rem;color:var(--cafe)}.kpi span{font-size:.8rem;color:var(--gris)}
.kpi.oscuro{background:var(--cafe)}.kpi.oscuro b{color:var(--oro)}.kpi.oscuro span{color:#f6ead6}
.kpi.alerta{background:var(--rojo);border-color:var(--rojo)}.kpi.alerta b,.kpi.alerta span{color:#fff}
.pill{display:inline-block;border-radius:20px;padding:.1rem .65rem;font-size:.74rem;font-weight:700;white-space:nowrap}
.pill.rojo{background:var(--rojo);color:#fff}.pill.verde{background:var(--verde);color:#fff}
.pill.oro{background:var(--oro);color:var(--cafe)}.pill.gris{background:#8a7d72;color:#fff}
.pill.claro{background:#f1e3c6;color:var(--gris)}
.barra{background:#ebdfc6;border-radius:6px;height:.6rem;width:100%;overflow:hidden;margin:.2rem 0}
.barra div{height:100%}.barra .verde{background:var(--verde)}.barra .rojo{background:var(--rojo)}.barra .oro{background:var(--oro)}
.scroll{overflow-x:auto}
table.jl{width:100%;border-collapse:collapse;font-size:.84rem;color:var(--cafe)}
table.jl th{background:var(--cafe);color:#fff;text-align:left;padding:.45rem .6rem;border:0}
table.jl td{padding:.45rem .6rem;border:0;border-bottom:1px solid var(--borde);vertical-align:middle}
table.jl tr:nth-child(odd) td{background:#fffaef}
.cab{background:var(--cafe);color:#fff;font-size:.78rem;font-weight:700;padding:.35rem .6rem;border-radius:4px}
.celda{font-size:.84rem;line-height:1.3}.celda small{color:var(--gris)}
.linea{border-bottom:1px solid var(--borde)}
.caja{background:var(--suave);border-radius:8px;padding:.6rem .8rem;margin-bottom:.4rem}
.caja span{font-size:.75rem;color:var(--gris);display:block}.caja b{font-size:1.15rem}.caja div{font-size:.84rem}
.foto{border:2px dashed #cbb48a;border-radius:8px;text-align:center;padding:1.2rem;color:var(--gris);font-size:.82rem}
.paso{display:flex;align-items:center;gap:.6rem;padding:.4rem .5rem;border-radius:8px;border:1px solid transparent;font-weight:600;font-size:.86rem}
.paso i{font-style:normal;width:1.6rem;height:1.6rem;border-radius:50%;background:#ebdfc6;display:flex;align-items:center;justify-content:center;font-size:.76rem;flex:none}
.paso.hecho i{background:var(--verde);color:#fff}.paso.curso{background:var(--suave);border-color:var(--oro)}.paso.curso i{background:var(--oro)}
.turnos{display:grid;grid-template-columns:repeat(auto-fit,minmax(105px,1fr));gap:.45rem}
.tcard{border:1px solid var(--borde);border-top:5px solid #cbb48a;border-radius:8px;padding:.45rem;font-size:.78rem;display:flex;flex-direction:column;gap:.25rem}
.tcard b{font-size:1rem}.tcard em{font-style:normal;font-weight:700;color:var(--gris);margin-top:auto}
.tcard.hecho{border-top-color:var(--verde)}.tcard.hecho em{color:var(--verde)}
.tcard.curso{border-top-color:var(--oro)}.tcard.curso em{color:#9a6c12}
.gantt{min-width:560px;font-size:.78rem}
.gfila{display:grid;grid-template-columns:190px 1fr;align-items:center;min-height:1.7rem}
.gfila:nth-child(even){background:#fffaef}
.semanas{display:grid;grid-template-columns:repeat(12,1fr)}
.semanas span{background:var(--cafe);color:#fff;text-align:center;font-weight:700;padding:.25rem 0;border-right:1px solid #6b5343}
.pista{position:relative;height:1.7rem}
.pista div{position:absolute;top:.4rem;height:.9rem;border-radius:4px}
.pista i{position:absolute;top:0;bottom:0;border-left:2px dashed var(--rojo)}
.pareto{display:flex;align-items:flex-end;gap:.8rem;height:150px}
.pareto div{flex:1;text-align:center;font-size:.72rem;font-weight:700}
.pareto i{display:block;border-radius:4px 4px 0 0;background:#c9b58b;margin:.15rem 0}.pareto div:first-child i{background:var(--oro)}
.mfila{display:grid;grid-template-columns:1.4rem 11rem 1fr 2rem;gap:.5rem;align-items:center;font-size:.82rem}
.etiqueta{border:3px solid var(--verde);border-radius:10px;overflow:hidden;background:#fff}
.etiqueta header{background:var(--verde);color:#fff;font-weight:800;padding:.45rem .8rem}
.etiqueta div{padding:.5rem .8rem;line-height:1.7;font-size:.9rem}
.qrfalso{width:120px;height:120px;border:5px solid var(--cafe);border-radius:8px;background:repeating-linear-gradient(45deg,var(--cafe) 0 7px,#fff 7px 14px)}
.pie{display:flex;justify-content:space-between;flex-wrap:wrap;gap:.5rem;font-size:.75rem;color:var(--gris);margin-top:1.5rem}
/* Campos */
[data-baseweb="input"],[data-baseweb="base-input"],[data-baseweb="textarea"],[data-baseweb="select"]>div{background:#fff;border-color:var(--borde)}
.stApp input,.stApp textarea{color:var(--cafe);background:#fff}
/* Botones por color */
.stButton button,.stDownloadButton button{border-radius:8px;border:1px solid var(--borde);background:#fff;font-weight:700}
.stButton button p,.stDownloadButton button p{font-weight:700;font-size:.84rem}
[class*="st-key-cafe_"] button{background:var(--cafe)!important;border-color:var(--cafe)!important}
[class*="st-key-oro_"] button{background:var(--oro)!important;border-color:var(--oro)!important}
[class*="st-key-verde_"] button{background:var(--verde)!important;border-color:var(--verde)!important}
[class*="st-key-rojo_"] button{background:var(--rojo)!important;border-color:var(--rojo)!important}
[class*="st-key-gris_"] button{background:#8a7d72!important;border-color:#8a7d72!important}
[class*="st-key-cafe_"] button p,[class*="st-key-verde_"] button p,[class*="st-key-rojo_"] button p,[class*="st-key-gris_"] button p{color:#fff!important}
[class*="st-key-oro_"] button p{color:var(--cafe)!important}
</style>
"""


# =====================================================================
# 7. NAVEGACIÓN
# =====================================================================
def ir(pagina, **extra):
    s = st.session_state
    s.pagina = pagina
    if "producto" in extra:
        s.proc_producto = s.ficha_producto = extra["producto"]
        s.venta_producto = extra["producto"]
        s.lote_producto = extra["producto"]
    if "lote" in extra:
        s.ver_lote = extra["lote"]
        s.pop("ver_bloque", None)


def fijar(clave, valor):
    st.session_state[clave] = valor


def barra_lateral(db):
    with st.sidebar:
        for grupo, paginas in NAVEGACION:
            H(f'<div class="grupo">{grupo}</div>')
            for clave, nombre in paginas:
                activo = clave == st.session_state.pagina
                st.button(("● " if activo else "○ ") + nombre, key=f"nav_{clave}",
                          on_click=ir, args=(clave,))
        H(f"""<style>.stApp .st-key-nav_{st.session_state.pagina} button{{background:#d9a441!important}}
              .st-key-nav_{st.session_state.pagina} button p{{color:#3e2a1f!important;font-weight:800}}</style>""")
        with st.expander("Datos"):
            st.download_button("Descargar respaldo", json.dumps(db, ensure_ascii=False, indent=1),
                               file_name="respaldo_juandy.json", mime="application/json", key="respaldo")
            ok = st.checkbox("Confirmo que quiero borrar los registros", key=f"conf_{n('reset')}")
            st.button("Reiniciar datos", key="rojo_reset", disabled=not ok, on_click=reiniciar)


def reiniciar():
    with candado():
        guardar(datos_iniciales())
    pagina, veces = st.session_state.get("pagina", "inicio"), n("reset")
    st.session_state.clear()
    st.session_state.pagina, st.session_state.n_reset = pagina, veces + 1
    aviso("Datos reiniciados.")


def chips_producto(clave_estado, prefijo):
    actual = st.session_state.setdefault(clave_estado, "queso")
    columnas = st.columns(5)
    for col, (pid, p) in zip(columnas, PRODUCTOS.items()):
        color = "oro" if pid == actual else "gris"
        col.button(p["corto"], key=f"{color}_{prefijo}_{pid}", on_click=fijar, args=(clave_estado, pid))
    return actual


# =====================================================================
# 8. PANTALLAS
# =====================================================================
def pagina_inicio(db):
    t = ahora()
    saludo = {"mañana": "Buenos días", "tarde": "Buenas tardes", "noche": "Buenas noches"}[turno(t)]
    titulo(f"{saludo}, turno {turno(t)}",
           f"{DIAS[t.weekday()]} {t.day} de {MESES[t.month - 1]} · lo más urgente primero")
    acciones = prioridades(db)
    semana = semana_de(t.date())
    alertas = sum(estado(l) in ("Vencido", "Por vencer") for l in lotes_peps(db))
    pendientes = next((4 - len(l["verif"]) for l in reversed(lotes_peps(db))
                       if estado(l) != "Vencido" and len(l["verif"]) < 4), 0)
    c = st.columns(4)
    with c[0]:
        kpi(f"Sem. {min(max(semana, 1), 12)} de 12",
            "Plan Lean Service en curso" if 1 <= semana <= 12 else "Fuera del periodo del plan", "oscuro")
    with c[1]:
        kpi(sum(kanban(db, p)[2] for p in PRODUCTOS), "panes por hornear hoy")
    with c[2]:
        kpi(alertas, "alertas de almacenamiento")
    with c[3]:
        kpi(f"{pendientes} / 4", "bloques de verificación pendientes")

    izq, der = st.columns([3, 2])
    with izq, tarjeta("prioridades"):
        h4("Actividades prioritarias de mi turno")
        if not acciones:
            st.success("No hay actividades pendientes.")
        else:
            cab = st.columns([1, 4, 1.4])
            cab[0].markdown('<div class="cab">Nivel</div>', unsafe_allow_html=True)
            cab[1].markdown('<div class="cab">Actividad</div>', unsafe_allow_html=True)
            cab[2].markdown('<div class="cab">Acción</div>', unsafe_allow_html=True)

        def fila(i, a):
            col = st.columns([1, 4, 1.4], vertical_alignment="center")
            color = {"Alta": "rojo", "Media": "oro", "Baja": "verde"}[a["nivel"]]
            col[0].markdown(f'<div>{pill(a["nivel"], color)}</div>', unsafe_allow_html=True)
            col[1].markdown(f'<div class="celda"><b>{e(a["texto"])}</b><br><small>{e(a["detalle"])}</small></div>',
                            unsafe_allow_html=True)
            estilo = "blanco" if a["nivel"] == "Baja" else "cafe"
            col[2].button("Iniciar", key=f"{estilo}_acc_{i}", on_click=ir,
                          args=(a["destino"],), kwargs=a["extra"])

        for i, a in enumerate(acciones[:6]):
            fila(i, a)
        if len(acciones) > 6:
            with st.expander(f"Ver {len(acciones) - 6} actividades más"):
                for i, a in enumerate(acciones[6:], start=6):
                    fila(i, a)
    with der, tarjeta("disponibilidad"):
        h4("Disponibilidad ahora")
        for pid, p in PRODUCTOS.items():
            hay, demanda, hornear = kanban(db, pid)
            H(f"""<div class="celda"><div style="display:flex;justify-content:space-between;gap:.4rem">
                <b>{p['nombre']}</b><span>{hay} / {demanda}
                {pill('HORNEAR', 'rojo') if hornear else pill('OK', 'verde')}</span></div>
                {barra(hay / demanda, 'rojo' if hornear else 'verde')}</div>""")
        st.button("Ver producción del día", key="oro_ver_prod", on_click=ir, args=("produccion",))


def avanzar_turno():
    with transaccion() as db:
        db["turno"]["actual"] = min(db["turno"]["actual"] + 1, len(ACTIVIDADES_TURNO))


def retroceder_turno():
    with transaccion() as db:
        db["turno"]["actual"] = max(db["turno"]["actual"] - 1, 0)


def guardar_horas(claves):
    horas = [st.session_state[k].strip() for k in claves]
    try:
        horas = [datetime.strptime(h, "%H:%M").strftime("%H:%M") for h in horas]
    except ValueError:
        aviso("Escribe cada hora como HH:MM (por ejemplo 06:45).", "error")
        return
    with transaccion() as db:
        db["turno"]["horas"] = horas
    aviso("Horario actualizado.")


def es_jefe(clave):
    pin = st.text_input("Clave del jefe de producción", type="password", key=f"pin_{clave}")
    if pin and pin != PIN_JEFE:
        st.error("Clave incorrecta.")
    return pin == PIN_JEFE


def pagina_cronograma(db):
    titulo("Cronograma de actividades", "Plan Lean Service y horario del procedimiento")
    semana = semana_de(ahora().date())
    with tarjeta("gantt"):
        h4("Plan de implementación de 12 semanas")
        linea = f'<i style="left:{(semana - .5) / 12 * 100:.2f}%"></i>' if 1 <= semana <= 12 else ""
        semanas = "".join(f"<span>S{i}</span>" for i in range(1, 13))
        filas = f'<div class="gfila"><b></b><div class="semanas">{semanas}</div></div>'
        for nombre, ini, fin, color in FRENTES:
            filas += (f'<div class="gfila"><span>{nombre}</span><div class="pista">'
                      f'<div style="left:{ini / 12 * 100:.2f}%;width:{(fin - ini) / 12 * 100 - .4:.2f}%;background:{color}"></div>{linea}</div></div>')
        H(f'<div class="scroll"><div class="gantt">{filas}</div></div>')
        if linea:
            H(f'<div class="celda" style="color:#b5472f"><b>┆ HOY · S{semana}</b></div>')
    with tarjeta("turno"):
        h4("Cronograma del procedimiento · turno de hoy")
        actual = db["turno"]["actual"]
        cartas = ""
        for i, ((_, nombre), hora) in enumerate(zip(ACTIVIDADES_TURNO, db["turno"]["horas"])):
            clase, texto = ("hecho", "Hecho") if i < actual else (("curso", "En curso") if i == actual else ("", "Pendiente"))
            cartas += f'<div class="tcard {clase}"><b>{e(hora)}</b><span>{nombre}</span><em>{texto}</em></div>'
        H(f'<div class="turnos">{cartas}</div>')
        c1, c2, _ = st.columns([2, 1, 2])
        if actual < len(ACTIVIDADES_TURNO):
            c1.button("Marcar paso en curso como hecho", key="verde_turno", on_click=avanzar_turno)
        else:
            c1.success("Turno completo.")
        c2.button("Deshacer", key="blanco_turno", on_click=retroceder_turno, disabled=actual == 0)
    with st.expander("Mover las horas (jefe de producción)"):
        if es_jefe("horas"):
            claves = []
            cols = st.columns(4)
            for i, ((_, nombre), hora) in enumerate(zip(ACTIVIDADES_TURNO, db["turno"]["horas"])):
                clave = f"hora_{i}_{hora}"
                cols[i % 4].text_input(nombre, value=hora, key=clave)
                claves.append(clave)
            st.button("Guardar horario", key="verde_horas", on_click=guardar_horas, args=(claves,))


def pagina_produccion(db):
    titulo("Producción del día", "Demanda diaria vs. inventario vigente")
    anchos = [2.2, 1.2, 1.8, 1.3, .9, 1.5]
    datos = {p: kanban(db, p) for p in PRODUCTOS}
    with tarjeta("kanban"):
        for col, x in zip(st.columns(anchos), ["Producto", "Demanda diaria", "Inventario vigente", "Señal Kanban", "Hornear", "Acción"]):
            col.markdown(f'<div class="cab">{x}</div>', unsafe_allow_html=True)
        for pid, p in PRODUCTOS.items():
            hay, demanda, hornear = datos[pid]
            col = st.columns(anchos, vertical_alignment="center")
            celdas = [f"<b>{p['nombre']}</b>", str(demanda),
                      barra(hay / demanda, "rojo" if hornear else "verde") + f"{hay} unidades",
                      pill("HORNEAR", "rojo") if hornear else pill("OK", "verde"),
                      f"<b>{hornear or '—'}</b>"]
            for c, x in zip(col, celdas):
                c.markdown(f'<div class="celda">{x}</div>', unsafe_allow_html=True)
            if hornear:
                col[5].button("Iniciar tanda", key=f"oro_tanda_{pid}", on_click=ir,
                              args=("procedimientos",), kwargs={"producto": pid})
    c1, c2 = st.columns(2)
    with c1, tarjeta("pareto"):
        h4("Demanda por producto (Pareto, ene–jun)")
        barras = "".join(f'<div>{p["peso_texto"]}%<i style="height:{p["peso"] / 35.2 * 100:.0f}px"></i>{p["corto"]}</div>'
                         for p in PRODUCTOS.values())
        H(f'<div class="pareto">{barras}</div>')
    with c2, tarjeta("regla"):
        h4("Regla Kanban de reposición")
        total = sum(d[2] for d in datos.values())
        tandas = sum(d[2] > 0 for d in datos.values())
        H(f"""<div class="celda">Cuando el inventario vigente baja del <b>50 %</b> de la demanda diaria,
            se enciende la señal y la app sugiere hornear la diferencia.<br><br>
            <b>Demanda total:</b> ≈ {DEMANDA_TOTAL} panes al día.<br>
            <b>Por hornear hoy:</b> {total} unidades en {tandas} tanda{'s' if tandas != 1 else ''}.</div>""")


# ---------- Procedimientos ----------
def registrar_medicion(db, producto, paso, detalle, valor, cumple, causa=""):
    db["mediciones"].append({"fecha": iso(ahora()), "producto": producto, "paso": paso,
                             "detalle": detalle, "valor": valor, "dentro": cumple, "causa": causa})


def registrar_paso(pid, paso, claves):
    s = st.session_state
    v = {k: s.get(c) for k, c in claves.items()}
    with transaccion() as db:
        proc, ficha = db["procesos"][pid], db["fichas"][pid]
        if proc["paso"] != paso:
            aviso("Este paso ya fue registrado desde otro equipo.", "warning")
            return
        causa = (v.get("causa") or "").strip()
        if paso in (1, 2):
            if not (v["a"] and v["b"]):
                aviso("Marca los dos controles antes de continuar. Si algo falla, usa «Reportar problema».", "error")
                return
            if paso == 1 and not v["texto"].strip():
                aviso("Escribe el lote del proveedor.", "error")
                return
            registrar_medicion(db, pid, paso, v.get("texto", ""), None, True)
            proc["paso"] += 1
        elif paso in (3, 5):
            medidas = [("amasado", "valor")] if paso == 3 else [("temperatura", "valor"), ("horneado", "valor2")]
            if any(v[k] is None for _, k in medidas):
                aviso("Escribe las mediciones antes de continuar.", "error")
                return
            resultados = [(p, v[k], dentro(v[k], ficha[p])) for p, k in medidas]
            falla = any(r is False for _, _, r in resultados) or (paso == 3 and not v["a"])
            if falla and not causa:
                aviso("Fuera de estándar: escribe la causa y la corrección para registrarlo.", "error")
                return
            for p, x, r in resultados:
                registrar_medicion(db, pid, paso, p, x, r, causa)
            if falla:
                aviso("Fuera de estándar: para, corrige, anota la causa y avisa al responsable del turno. El paso no avanzó.", "error")
                return
            proc["paso"] += 1
        elif paso == 4:
            if v["valor"] is None:
                aviso("Escribe el peso medido.", "error")
                return
            r = dentro(v["valor"], ficha["masa"])
            if r is False and not causa:
                aviso("Peso fuera de tolerancia: escribe la causa y la corrección para registrarlo.", "error")
                return
            if r is not False and not v["a"]:
                aviso("Confirma que agregaste el relleno estándar.", "error")
                return
            registrar_medicion(db, pid, paso, "masa", v["valor"], r, causa)
            siguiente(f"med_{pid}")
            if r is False:
                aviso("Registrado fuera de tolerancia: la unidad no cuenta. Corrige y avisa al responsable.", "warning")
                return
            proc["unidades"] += 1
            if proc["unidades"] >= 5:
                proc["paso"] = 5
                aviso("5 unidades verificadas. Sigue el horneado.")
            else:
                aviso(f"Unidad {proc['unidades']} de 5 registrada.")
            return
        elif paso == 6:
            if v["resultado"] is None:
                aviso("Indica si el producto es conforme o no conforme.", "error")
                return
            malo = v["resultado"] == "No conforme"
            if malo and not causa:
                aviso("Anota qué se encontró y qué se hizo con el producto.", "error")
                return
            proc["no_conforme"] = malo
            registrar_medicion(db, pid, paso, v["resultado"], None, not malo, causa)
            if malo:
                db["problemas"].append({"fecha": iso(ahora()), "producto": pid, "paso": paso, "texto": causa})
                aviso("Producto no conforme: apártalo. El lote quedará bloqueado para la venta.", "warning")
            proc["paso"] = 7
        elif paso == 7:
            if not v["cantidad"] or not v["responsable"].strip():
                aviso("Escribe la cantidad y el responsable.", "error")
                return
            lote = crear_lote(db, pid, v["cantidad"], v["responsable"].strip(),
                              "Creado desde el procedimiento", proc["no_conforme"])
            db["procesos"][pid] = {"paso": 1, "unidades": 0, "no_conforme": False}
            s.ultimo_lote = lote["codigo"]
            ir("lotes", producto=pid)
            aviso(f"Lote {lote['codigo']} creado. Completa sus listas de verificación.")
            return
        aviso("Paso registrado.")


def reportar_problema(pid, paso, clave):
    texto = st.session_state.get(clave, "").strip()
    if not texto:
        aviso("Describe el problema.", "error")
        return
    with transaccion() as db:
        db["problemas"].append({"fecha": iso(ahora()), "producto": pid, "paso": paso, "texto": texto})
    siguiente("problema")
    aviso("Problema reportado. Avisa al responsable del turno.", "warning")


def caja(etiqueta, parametro, unidad):
    if parametro["valor"] is None:
        texto = "Por definir"
    else:
        tol = f" ± {num(parametro['tol'])} {unidad}" if parametro["tol"] is not None else ""
        texto = f"{num(parametro['valor'])} {unidad}{tol}"
    H(f'<div class="caja"><span>{e(etiqueta)}</span><b>{texto}</b></div>')


def indicar(valor, parametro):
    if valor is None:
        return
    r = dentro(valor, parametro)
    if r is None:
        H(f'<div>{pill("Sin tolerancia definida", "gris")}</div>')
    else:
        H(f'<div>{pill("✓ Dentro de tolerancia", "verde") if r else pill("✕ Fuera de tolerancia", "rojo")}</div>')


def pagina_procedimientos(db):
    titulo("Procedimiento estándar", f"Elaboración del {PRODUCTOS[st.session_state.get('proc_producto', 'queso')]['nombre'].lower()}")
    pid = chips_producto("proc_producto", "proc")
    p, proc, ficha = PRODUCTOS[pid], db["procesos"][pid], db["fichas"][pid]
    paso = proc["paso"]
    if not ficha_completa(ficha):
        st.warning("La ficha técnica de este pan está pendiente: las mediciones se registran sin comparar.")
    izq, der = st.columns([1, 2])
    with izq, tarjeta("pasos"):
        h4(f"{p['nombre']} · 7 pasos")
        lista = ""
        for i, nombre in enumerate(PASOS, start=1):
            clase = "hecho" if i < paso else ("curso" if i == paso else "")
            lista += f'<div class="paso {clase}"><i>{"✓" if i < paso else i}</i>{nombre}</div>'
        H(f"<div>{lista}</div>")
    with der, tarjeta("paso_actual"):
        h4(f"Paso {paso} · {PASOS[paso - 1]}")
        base = f"p_{pid}_{paso}_{n('med_' + pid)}"
        k = lambda nombre: f"{base}_{nombre}"
        claves = {}
        instruccion = TABLA_PROCEDIMIENTO[paso - 1][1]
        if paso == 4:
            instruccion = f"Cortar con el porcionador, pesar cada porción en la báscula de 5 kg, rayar y agregar el {p['relleno']} estándar."
        H(f'<div class="celda">{e(instruccion)}</div>')
        if paso == 1:
            st.checkbox("Empaque y olor correctos, sin impurezas", key=k("a"))
            st.checkbox("Fecha de vencimiento vigente", key=k("b"))
            st.text_input("Lote del proveedor", key=k("texto"))
            claves = {x: k(x) for x in ("a", "b", "texto")}
        elif paso == 2:
            st.checkbox("Báscula puesta en cero", key=k("a"))
            st.checkbox("Cada ingrediente pesado según la ficha técnica", key=k("b"))
            claves = {x: k(x) for x in ("a", "b")}
        elif paso == 3:
            caja("Tiempo de amasado", ficha["amasado"], "min")
            x = st.number_input("Tiempo medido (min)", min_value=0.0, value=None, step=1.0, format="%g", key=k("valor"))
            indicar(x, ficha["amasado"])
            ok = st.checkbox("Consistencia correcta y orden de ingredientes respetado", key=k("a"))
            claves = {"valor": k("valor"), "a": k("a")}
            if (x is not None and dentro(x, ficha["amasado"]) is False) or (x is not None and not ok):
                st.text_input("Causa y corrección", key=k("causa"))
                claves["causa"] = k("causa")
        elif paso == 4:
            c1, c2 = st.columns(2)
            with c1:
                caja("Peso objetivo", ficha["masa"], "g")
            with c2:
                caja(f"{p['relleno'].capitalize()} por unidad", ficha["relleno"], "g")
            c1, c2 = st.columns(2)
            with c1:
                inicial = 61.0 if MODO_DEMO and pid == "queso" and proc["unidades"] == 3 and n("med_" + pid) == 0 else None
                x = st.number_input("Peso medido (g)", min_value=0.0, value=inicial, step=1.0, format="%g", key=k("valor"))
                indicar(x, ficha["masa"])
            with c2:
                H(f'<div class="celda">Unidades verificadas{barra(proc["unidades"] / 5)}<b>{proc["unidades"]} de 5</b></div>')
            st.checkbox(f"Relleno estándar agregado ({p['relleno']})", value=True, key=k("a"))
            claves = {"valor": k("valor"), "a": k("a")}
            if x is not None and dentro(x, ficha["masa"]) is False:
                st.text_input("Causa y corrección", key=k("causa"))
                claves["causa"] = k("causa")
            H('<div class="foto">Foto de referencia: porción y rayado correctos</div>')
        elif paso == 5:
            c1, c2 = st.columns(2)
            with c1:
                caja("Temperatura", ficha["temperatura"], "°C")
                x = st.number_input("Temperatura medida (°C)", min_value=0.0, value=None, step=1.0, format="%g", key=k("valor"))
                indicar(x, ficha["temperatura"])
            with c2:
                caja("Tiempo de horneado", ficha["horneado"], "min")
                y = st.number_input("Tiempo medido (min)", min_value=0.0, value=None, step=1.0, format="%g", key=k("valor2"))
                indicar(y, ficha["horneado"])
            claves = {"valor": k("valor"), "valor2": k("valor2")}
            if (x is not None and dentro(x, ficha["temperatura"]) is False) or (y is not None and dentro(y, ficha["horneado"]) is False):
                st.text_input("Causa y corrección", key=k("causa"))
                claves["causa"] = k("causa")
        elif paso == 6:
            H(f'<div class="caja"><span>Criterios de aceptación</span><div>{e(ficha["criterios"])}</div></div>')
            r = st.radio("Resultado", ["Conforme", "No conforme"], index=None, horizontal=True, key=k("resultado"))
            claves = {"resultado": k("resultado")}
            if r == "No conforme":
                st.text_input("Qué se encontró y qué se hizo", key=k("causa"))
                claves["causa"] = k("causa")
        else:
            sugerido = kanban(db, pid)[2] or p["demanda"]
            c1, c2 = st.columns(2)
            c1.number_input("Cantidad", min_value=1, value=sugerido, step=1, key=k(f"cantidad{sugerido}"))
            c2.text_input("Responsable", value="Carlos M." if MODO_DEMO else "", key=k("responsable"))
            claves = {"cantidad": k(f"cantidad{sugerido}"), "responsable": k("responsable")}
        c1, c2 = st.columns(2)
        c1.button("Registrar lote y terminar" if paso == 7 else "Registrar y continuar",
                  key="verde_paso", on_click=registrar_paso, args=(pid, paso, claves))
        with c2.expander("Reportar problema"):
            clave = f"problema_{pid}_{paso}_{n('problema')}"
            st.text_area("¿Qué pasó?", key=clave)
            st.button("Enviar reporte", key="rojo_problema", on_click=reportar_problema, args=(pid, paso, clave))
    with st.expander("Ver el procedimiento estándar completo y sus reglas"):
        tabla(["Paso", "Actividad", "Qué se hace", "Qué se controla", "Dónde se registra", "Responsable"],
              [[i, f"<b>{f[0]}</b>", *f[1:]] for i, f in enumerate(TABLA_PROCEDIMIENTO, start=1)])
        st.markdown("- Si un control no se cumple: parar, corregir, anotar la causa y avisar al responsable del turno.\n"
                    "- Producto no conforme no se libera para la venta: se registra y se aparta.\n"
                    "- Cada tanda queda trazada con un código de lote, fecha y hora, responsable y resultados.")


# ---------- Fichas técnicas ----------
def guardar_ficha(pid, claves):
    s = st.session_state
    with transaccion() as db:
        f = db["fichas"][pid]
        for p, _, _ in PARAMETROS:
            valor, tol = s[claves[p + "_v"]], s.get(claves.get(p + "_t", ""))
            if p == "vida" and valor is not None and valor <= 0:
                aviso("La vida útil debe ser mayor que cero.", "error")
                valor = f[p]["valor"]
            f[p] = {"valor": valor, "tol": tol}
        f["criterios"] = s[claves["criterios"]]
        f["instrumentos"] = s[claves["instrumentos"]]
        f["version"] += 1
    aviso("Ficha guardada.")


def pagina_fichas(db):
    titulo("Fichas técnicas", "Valores de referencia de cada producto")
    actual = st.session_state.setdefault("ficha_producto", "queso")
    izq, der = st.columns([1, 2])
    with izq, tarjeta("lista_fichas"):
        h4("Productos")
        for pid, p in PRODUCTOS.items():
            c1, c2 = st.columns([2, 1.2], vertical_alignment="center")
            c1.button(p["nombre"], key=f"{'oro' if pid == actual else 'blanco'}_ficha_{pid}",
                      on_click=fijar, args=("ficha_producto", pid))
            ok = ficha_completa(db["fichas"][pid])
            c2.markdown(f'<div>{pill("Completa", "verde") if ok else pill("Pendiente", "oro")}</div>', unsafe_allow_html=True)
    p, f = PRODUCTOS[actual], db["fichas"][actual]
    with der, tarjeta("ficha"):
        h4(f"Ficha técnica · {p['nombre']}",
           pill(f"Aprobada · v{f['version']}", "verde") if ficha_completa(f) else pill("Pendiente de validar", "oro"))
        filas = []
        for clave, nombre, unidad in PARAMETROS:
            if clave == "relleno":
                nombre = f"Peso del relleno ({p['relleno']})"
            v, t = f[clave]["valor"], f[clave]["tol"]
            filas.append([nombre, f"<b>{num(v)} {unidad}</b>" if v is not None else "Por definir",
                          f"± {num(t)} {unidad}" if t is not None else "—"])
        tabla(["Parámetro", "Valor", "Tolerancia"], filas)
        c1, c2 = st.columns(2)
        with c1:
            H(f'<div class="caja"><span>Criterios de aceptación</span><div>{e(f["criterios"])}</div></div>')
        with c2:
            H(f'<div class="caja"><span>Instrumentos</span><div>{e(f["instrumentos"])}</div></div>')
        if f["vida"]["valor"] is None:
            st.caption("Mientras no se defina la vida útil, los lotes nuevos usan 24 h.")
    with st.expander("Editar ficha (solo jefe de producción)"):
        if es_jefe("ficha"):
            claves = {}
            base = f"f_{actual}_{f['version']}_{n('reset')}"
            for clave, nombre, unidad in PARAMETROS:
                c1, c2 = st.columns(2)
                claves[clave + "_v"] = f"{base}_{clave}_v"
                c1.number_input(f"{nombre} ({unidad})", min_value=0.0, value=None if f[clave]["valor"] is None else float(f[clave]["valor"]),
                                format="%g", key=claves[clave + "_v"])
                if clave != "vida":
                    claves[clave + "_t"] = f"{base}_{clave}_t"
                    c2.number_input(f"Tolerancia ± ({unidad})", min_value=0.0, value=None if f[clave]["tol"] is None else float(f[clave]["tol"]),
                                    format="%g", key=claves[clave + "_t"])
            for campo, nombre in (("criterios", "Criterios de aceptación"), ("instrumentos", "Instrumentos")):
                claves[campo] = f"{base}_{campo}"
                st.text_area(nombre, value=f[campo], key=claves[campo])
            st.button("Guardar ficha", key="verde_ficha", on_click=guardar_ficha, args=(actual, claves))


# ---------- Registro por lote ----------
def registrar_lote(claves):
    s = st.session_state
    pid, cantidad = s[claves["producto"]], s[claves["cantidad"]]
    responsable = s[claves["responsable"]].strip()
    if not cantidad or not responsable:
        aviso("Escribe la cantidad y el responsable.", "error")
        return
    with transaccion() as db:
        lote = crear_lote(db, pid, cantidad, responsable, s[claves["observacion"]].strip())
    s.ultimo_lote, s.lote_producto = lote["codigo"], pid
    siguiente("lote")
    aviso(f"Lote {lote['codigo']} registrado.")


def etiqueta_html(pid, horneado, vence, codigo, cantidad, responsable):
    return f"""<div class="etiqueta"><header>{PRODUCTOS[pid]['nombre'].upper()} · PEPS</header>
        <div>Horneado: <b>{horneado:%d/%m/%Y %H:%M}</b><br>Retirar antes de: <b>{vence:%d/%m/%Y %H:%M}</b><br>
        Lote: <b>{e(codigo)}</b> · {cantidad} u.<br>Resp.: {e(responsable)}</div></div>"""


def etiqueta_imprimible(cuerpo):
    return ("<!doctype html><meta charset='utf-8'><title>Etiqueta</title><style>body{font-family:sans-serif}"
            ".etiqueta{width:80mm;border:3px solid #000}.etiqueta header{font-weight:bold;padding:6px;border-bottom:2px solid #000}"
            ".etiqueta div{padding:6px;line-height:1.7}</style>" + cuerpo + "<script>window.print()</script>")


def pagina_lotes(db):
    titulo("Registro por lote", "Trazabilidad de cada tanda")
    s = st.session_state
    izq, der = st.columns([3, 2])
    with izq, tarjeta("form_lote"):
        h4("Registrar nuevo lote")
        s.setdefault("lote_producto", "queso")
        c1, c2 = st.columns([2, 1])
        pid = c1.selectbox("Producto", list(PRODUCTOS), index=list(PRODUCTOS).index(s.lote_producto),
                           format_func=lambda x: PRODUCTOS[x]["nombre"], key=f"sel_lote_{s.lote_producto}_{n('lote')}",
                           on_change=lambda: s.pop("ultimo_lote", None))
        sugerido = kanban(db, pid)[2] or PRODUCTOS[pid]["demanda"]
        claves = {"producto": f"sel_lote_{s.lote_producto}_{n('lote')}",
                  "cantidad": f"l_cant_{pid}_{sugerido}_{n('lote')}",
                  "responsable": f"l_resp_{n('lote')}", "observacion": f"l_obs_{n('lote')}"}
        limpiar = lambda: s.pop("ultimo_lote", None)
        cantidad = c2.number_input("Cantidad", min_value=1, value=sugerido, step=1, key=claves["cantidad"], on_change=limpiar)
        c1, c2 = st.columns(2)
        responsable = c1.text_input("Responsable", value="Carlos M." if MODO_DEMO else "", key=claves["responsable"], on_change=limpiar)
        t = ahora()
        with c2:
            H(f'<div class="caja"><span>Fecha y hora de horneado</span><div><b style="font-size:.9rem">{t:%d/%m/%Y %H:%M}</b> · automática</div></div>')
        st.text_input("Observación", value="Tanda 1 del día" if MODO_DEMO else "", key=claves["observacion"])
        st.button("Registrar lote y generar etiqueta", key="verde_lote", on_click=registrar_lote, args=(claves,))
    with der, tarjeta("etiqueta"):
        h4("Etiqueta por fecha")
        lote = buscar_lote(db, s.get("ultimo_lote"))
        if lote:
            cuerpo = etiqueta_html(lote["producto"], fecha(lote["horneado"]), fecha(lote["vence"]),
                                   lote["codigo"], lote["inicial"], lote["responsable"])
            H(cuerpo)
            st.download_button("Imprimir etiqueta", etiqueta_imprimible(cuerpo), file_name=f"{lote['codigo']}.html",
                               mime="text/html", key="imprimir")
            st.caption("Se descarga la etiqueta; al abrirla aparece la ventana de impresión.")
        else:
            vida = db["fichas"][pid]["vida"]["valor"] or 24
            prefijo = f"L-{t:%Y%m%d}-"
            sig = max([int(l["codigo"].split("-")[-1]) for l in db["lotes"] if l["codigo"].startswith(prefijo)] or [0]) + 1
            H(etiqueta_html(pid, t, t + timedelta(hours=vida), f"{prefijo}{sig:02d}", cantidad or 0, responsable))
            st.caption("Vista previa: registra el lote para imprimirla.")
    with tarjeta("recientes"):
        h4("Lotes recientes")
        filas = []
        for l in sorted(db["lotes"], key=lambda l: l["horneado"], reverse=True)[:10]:
            est = estado(l)
            dia = fecha(l["horneado"])
            hora = f"{dia:%H:%M}" if (t.date() - dia.date()).days <= 1 else f"{dia:%d/%m %H:%M}"
            filas.append([f"<b>{l['codigo']}</b>", PRODUCTOS[l["producto"]]["nombre"], hora, l["inicial"],
                          f"{len(l['verif'])} / 4", pill(est, COLOR_ESTADO[est])])
        if filas:
            tabla(["Lote", "Producto", "Hora", "Cant.", "Verificación", "Estado"], filas)
        else:
            st.info("Todavía no hay lotes registrados.")


# ---------- Inventario ----------
def registrar_venta(clave_prod, clave_cant):
    pid, cantidad = st.session_state[clave_prod], st.session_state[clave_cant]
    if not cantidad:
        aviso("Escribe la cantidad.", "error")
        return
    with transaccion() as db:
        detalle, error = vender(db, pid, int(cantidad))
    if error:
        aviso(error, "error")
    else:
        st.session_state.venta_producto = pid
        siguiente("venta")
        aviso(f"Venta registrada (PEPS): {', '.join(detalle)}.")


def elegir_venta(pid):
    st.session_state.venta_producto = pid
    siguiente("venta")
    aviso(f"{PRODUCTOS[pid]['nombre']} seleccionado. Escribe la cantidad en «Registrar venta»; sale primero lo más antiguo.", "info")


def retirar_lotes(codigo=None):
    with transaccion() as db:
        objetivo = [l for l in lotes_peps(db) if (l["codigo"] == codigo if codigo else estado(l) == "Vencido")]
        for l in objetivo:
            retirar(db, l)
    aviso(f"{len(objetivo)} lote(s) retirado(s) y registrado(s) como desecho." if objetivo else "No hay lotes por retirar.")


def guardar_bodega(c_temp, c_hum):
    with transaccion() as db:
        db["bodega"] = {"temp": st.session_state[c_temp], "hum": st.session_state[c_hum]}
    aviso("Lectura de bodega guardada.")


def pagina_inventario(db):
    titulo("Inventario y almacenamiento", "Existencias por lote y fecha")
    lotes = lotes_peps(db)
    estados = [estado(l) for l in lotes]
    bodega = db["bodega"]
    c = st.columns(4)
    with c[0]:
        kpi(f"{num(bodega['temp'])} °C", "temperatura de bodega")
    with c[1]:
        kpi(f"{num(bodega['hum'])} %", "humedad relativa")
    with c[2]:
        kpi(sum(x in ("Vigente", "Por vencer") for x in estados), "lotes vigentes")
    with c[3]:
        alertas = sum(x in ("Vencido", "Por vencer") for x in estados)
        kpi(alertas, "por vencer o vencidos", "alerta" if alertas else "")
    with tarjeta("existencias"):
        h4("Existencias en orden de salida (PEPS: primero en entrar, primero en salir)")
        anchos = [.7, 1.7, 1.8, 1.1, 1, 1.2, 1.3, 1.4]
        for col, x in zip(st.columns(anchos), ["Orden", "Lote", "Producto", "Horneado", "Disp. / inicial", "Vida útil", "Estado", "Acción"]):
            col.markdown(f'<div class="cab">{x}</div>', unsafe_allow_html=True)
        t = ahora()
        for i, (l, est) in enumerate(zip(lotes, estados), start=1):
            ini, fin = fecha(l["horneado"]), fecha(l["vence"])
            queda = max(0, (fin - t) / (fin - ini))
            dias = (t.date() - ini.date()).days
            cuando = "" if dias == 0 else ("ayer" if dias == 1 else f"{ini:%d/%m}")
            col = st.columns(anchos, vertical_alignment="center")
            celdas = [f"<b>{i}</b>", l["codigo"], PRODUCTOS[l["producto"]]["nombre"], f"{ini:%H:%M} {cuando}",
                      f"{l['disponible']} / {l['inicial']}",
                      barra(queda, "verde" if est == "Vigente" else "oro"), pill(est, COLOR_ESTADO[est])]
            for co, x in zip(col, celdas):
                co.markdown(f'<div class="celda">{x}</div>', unsafe_allow_html=True)
            cod = l["codigo"]
            if est == "Vencido":
                col[7].button("Retirar", key=f"rojo_ret_{cod}", on_click=retirar_lotes, args=(cod,))
            elif est == "Bloqueado":
                col[7].button("Revisar", key=f"blanco_rev_{cod}", on_click=ir, args=("verificacion",), kwargs={"lote": cod})
            else:
                primero = est == "Por vencer"
                col[7].button("Vender primero" if primero else "Vender", key=f"{'oro' if primero else 'cafe'}_ven_{cod}",
                              on_click=elegir_venta, args=(l["producto"],))
        if not lotes:
            st.info("No hay lotes en inventario.")
        sueltos = [f"{v} de {PRODUCTOS[p]['nombre'].lower()}" for p, v in db["saldo_inicial"].items() if v]
        if sueltos:
            st.caption(f"Además hay existencias del conteo inicial, sin lote: {' y '.join(sueltos)}. Se venden primero.")
    c1, c2 = st.columns(2)
    with c1, tarjeta("venta"):
        h4("Registrar venta")
        previo = st.session_state.get("venta_producto", "queso")
        a, b = st.columns([2, 1])
        cp, cc = f"v_prod_{previo}_{n('venta')}", f"v_cant_{n('venta')}"
        a.selectbox("Producto", list(PRODUCTOS), index=list(PRODUCTOS).index(previo),
                    format_func=lambda x: PRODUCTOS[x]["nombre"], key=cp)
        b.number_input("Cantidad", min_value=1, value=10 if MODO_DEMO and n("venta") == 0 else 1, step=1, key=cc)
        st.button("Vender", key="cafe_vender", on_click=registrar_venta, args=(cp, cc))
        st.caption("Descuenta del lote más antiguo vigente.")
    with c2, tarjeta("vencidos"):
        h4("Vencidos")
        st.button("Descartar lotes vencidos", key="rojo_descartar", on_click=retirar_lotes,
                  disabled="Vencido" not in estados)
        st.caption("Queda registrado como desecho.")
    with st.expander("Registrar lectura del termohigrómetro"):
        a, b = st.columns(2)
        ct, ch = f"temp_{bodega['temp']}", f"hum_{bodega['hum']}"
        a.number_input("Temperatura (°C)", min_value=0.0, max_value=60.0, value=float(bodega["temp"] or 25), format="%g", key=ct)
        b.number_input("Humedad relativa (%)", min_value=0.0, max_value=100.0, value=float(bodega["hum"] or 60), format="%g", key=ch)
        st.button("Guardar lectura", key="verde_bodega", on_click=guardar_bodega, args=(ct, ch))


# ---------- Verificación ----------
def guardar_verificacion(codigo, bloque, claves, clave_accion):
    s = st.session_state
    respuestas = [s.get(k) for k in claves]
    if any(r is None for r in respuestas):
        aviso("Responde todos los puntos de control.", "error")
        return
    resultados = [r == "Cumple" for r in respuestas]
    accion = s.get(clave_accion, "").strip()
    if not all(resultados) and not accion:
        aviso("Hay un «No cumple»: anota la acción correctiva antes de guardar.", "error")
        return
    with transaccion() as db:
        lote = buscar_lote(db, codigo)
        t = iso(ahora())
        lote["verif"][str(bloque)] = {"fecha": t, "resultados": resultados, "accion": accion}
        db["historial"].append({"fecha": t, "lote": codigo, "bloque": bloque, "cumple": all(resultados),
                                "ok": sum(resultados), "total": len(resultados), "accion": accion})
    s.ver_bloque = bloque
    if all(resultados):
        aviso("Verificación guardada.")
    else:
        aviso(f"Verificación guardada. El lote {codigo} queda bloqueado hasta que el bloque cumpla.", "warning")


def bloquear(codigo, valor):
    with transaccion() as db:
        buscar_lote(db, codigo)["bloqueo"] = valor
    aviso(f"Lote {codigo} {'bloqueado: no se puede vender' if valor else 'desbloqueado'}.", "warning" if valor else "success")


def pagina_verificacion(db):
    titulo("Listas de verificación", "Cuatro bloques por lote")
    s = st.session_state
    lotes = sorted([l for l in db["lotes"] if not l["retirado"]], key=lambda l: l["horneado"], reverse=True)
    if not lotes:
        st.info("Registra un lote para poder verificarlo.")
        return
    codigos = [l["codigo"] for l in lotes]
    if s.get("ver_lote") not in codigos:
        s.ver_lote = next((l["codigo"] for l in lotes if len(l["verif"]) < 4), codigos[0])
        s.pop("ver_bloque", None)
    codigo = st.selectbox("Lote", codigos, index=codigos.index(s.ver_lote), key=f"sel_ver_{s.ver_lote}",
                          format_func=lambda c: f"{c} · {PRODUCTOS[buscar_lote(db, c)['producto']]['nombre']}")
    if codigo != s.ver_lote:
        s.ver_lote = codigo
        s.pop("ver_bloque", None)
    lote = buscar_lote(db, codigo)
    if "ver_bloque" not in s:
        if MODO_DEMO and codigo == "L-20261126-02":
            s.ver_bloque = 4
        else:
            s.ver_bloque = next((b for b in BLOQUES if str(b) not in lote["verif"]), 4)
    bloque = s.ver_bloque
    for col, (b, (nombre, _)) in zip(st.columns(4), BLOQUES.items()):
        v = lote["verif"].get(str(b))
        color = "oro" if b == bloque else ("gris" if not v else ("verde" if all(v["resultados"]) else "rojo"))
        marca = "" if not v else ("✓ " if all(v["resultados"]) else "✕ ")
        col.button(f"{marca}{b} · {nombre}", key=f"{color}_bloque_{b}", on_click=fijar, args=("ver_bloque", b))
    izq, der = st.columns([3, 2])
    with izq, tarjeta("checklist"):
        est = estado(lote)
        h4(f"Lote {codigo} · {PRODUCTOS[lote['producto']]['nombre']} · bloque {bloque}", pill(est, COLOR_ESTADO[est]))
        previo = lote["verif"].get(str(bloque))
        ejemplo = MODO_DEMO and codigo == "L-20261126-02" and bloque == 4 and not previo
        marca = previo["fecha"] if previo else "nuevo"
        base = f"chk_{codigo}_{bloque}_{marca}_{n('reset')}"
        claves = []
        for i, punto in enumerate(BLOQUES[bloque][1]):
            if previo:
                idx = 0 if previo["resultados"][i] else 1
            else:
                idx = (1 if i == 2 else 0) if ejemplo else None
            claves.append(f"{base}_{i}")
            st.radio(punto, ["Cumple", "No cumple"], index=idx, horizontal=True, key=claves[-1])
        accion = previo["accion"] if previo else ("Colocar la etiqueta antes de ubicar el lote en la vitrina" if ejemplo else "")
        st.text_input("Acción correctiva (obligatoria si hay un «No cumple»)", value=accion, key=f"{base}_accion")
        c1, c2 = st.columns(2)
        c1.button("Guardar verificación", key="verde_verif", on_click=guardar_verificacion,
                  args=(codigo, bloque, claves, f"{base}_accion"))
        if lote["bloqueo"]:
            c2.button("Quitar bloqueo manual", key="blanco_desbloquear", on_click=bloquear, args=(codigo, False))
        else:
            c2.button("Bloquear liberación del lote", key="blanco_bloquear", on_click=bloquear, args=(codigo, True))
    with der, tarjeta("historial"):
        h4("Historial reciente")
        hoy = ahora().date()
        filas = []
        for r in sorted(db["historial"], key=lambda r: r["fecha"], reverse=True)[:8]:
            d = fecha(r["fecha"])
            dias = (hoy - d.date()).days
            cuando = f"{d:%H:%M}" if dias == 0 else ("Ayer" if dias == 1 else f"{d:%d/%m}")
            detalle = f"<br><small>{e(r['lote'])}{' · ' + e(r['accion']) if r.get('accion') else ''}</small>"
            filas.append([cuando, BLOQUES[r["bloque"]][0] + detalle,
                          pill("Cumple", "verde") if r["cumple"] else pill("No cumple", "rojo")])
        if filas:
            tabla(["Hora", "Bloque", "Resultado"], filas)
        else:
            st.caption("Sin registros todavía.")


# ---------- Inconformidades ----------
def registrar_inconformidad(claves):
    s = st.session_state
    v = {k: s.get(c) for k, c in claves.items()}
    if not v["unidades"]:
        aviso("Escribe las unidades.", "error")
        return
    with transaccion() as db:
        lote = None if v["lote"] == "Sin lote" else v["lote"]
        db["inconformidades"].append({"fecha": iso(ahora()), "tipo": v["tipo"], "producto": v["producto"],
                                      "unidades": int(v["unidades"]), "lote": lote,
                                      "motivo": s.get("motivo", "C"), "nota": v["nota"].strip()})
        if v.get("apartar") and lote:
            buscar_lote(db, lote)["bloqueo"] = True
    siguiente("inc")
    aviso("Inconformidad registrada.")


def direccion_encuesta():
    base = URL_APP or getattr(getattr(st, "context", None), "url", "") or ""
    return base.split("?")[0].rstrip("/") + "/?vista=encuesta" if base else ""


def qr_html(url):
    if url:
        try:
            import segno
            return f'<img width="130" alt="Código QR" src="{segno.make(url).png_data_uri(scale=5, border=2, dark="#3e2a1f")}">'
        except ImportError:
            pass
    return '<div class="qrfalso" title="QR de ejemplo"></div>'


def pagina_inconformidades(db):
    titulo("Inconformidades y voz del cliente", "Registro diario con códigos de motivo")
    izq, der = st.columns([3, 2])
    with izq, tarjeta("form_inc"):
        h4("Registrar inconformidad")
        base = f"i_{n('inc')}"
        claves = {k: f"{base}_{k}" for k in ("tipo", "producto", "unidades", "nota")}
        st.radio("Tipo", ["Queja", "Devolución", "Producto no conforme"], horizontal=True, key=claves["tipo"])
        c1, c2, c3 = st.columns([2, 1, 1.6])
        pid = c1.selectbox("Producto", list(PRODUCTOS), format_func=lambda x: PRODUCTOS[x]["nombre"], key=claves["producto"])
        c2.number_input("Unidades", min_value=1, value=2 if MODO_DEMO and n("inc") == 0 else 1, step=1, key=claves["unidades"])
        codigos = [l["codigo"] for l in sorted(db["lotes"], key=lambda l: l["horneado"], reverse=True) if l["producto"] == pid]
        claves["lote"] = f"{base}_lote_{pid}"
        c3.selectbox("Lote", codigos + ["Sin lote"], key=claves["lote"])
        st.caption("Motivo")
        actual = st.session_state.setdefault("motivo", "C")
        cols = st.columns(3)
        for i, (m, (nombre, _)) in enumerate(MOTIVOS.items()):
            cols[i % 3].button(f"{m} · {nombre}", key=f"{'oro' if m == actual else 'gris'}_motivo_{m}",
                               on_click=fijar, args=("motivo", m))
        st.text_input("Nota", placeholder="Ej.: Cliente indica que estaba duro", key=claves["nota"])
        if st.session_state[claves["tipo"]] == "Producto no conforme":
            claves["apartar"] = f"{base}_apartar"
            st.checkbox("Apartar el lote (bloquear su venta)", value=True, key=claves["apartar"])
        st.button("Registrar", key="verde_inc", on_click=registrar_inconformidad, args=(claves,))
    with der, tarjeta("qr"):
        h4("Voz del cliente · encuesta por QR")
        url = direccion_encuesta()
        H(f"""<div class="celda">{qr_html(url)}<p>El cliente escanea el código en el mostrador y califica
            <b>sabor, frescura y tamaño</b> en 3 preguntas. Las respuestas entran solas al registro.</p></div>""")
        H('<div class="celda"><a href="?vista=encuesta" target="_blank">Abrir la encuesta</a></div>')
        respuestas = db["encuestas"]
        if respuestas:
            prom = {k: sum(r[k] for r in respuestas) / len(respuestas) for k in ("sabor", "frescura", "tamano")}
            st.caption(f"{len(respuestas)} respuesta(s) · sabor {num(prom['sabor'])} · frescura {num(prom['frescura'])} · tamaño {num(prom['tamano'])} (de 5)")
    semana = semana_de(ahora().date())
    motivos = indicadores(db, semana)["motivos"]
    with tarjeta("pareto_motivos"):
        h4(f"Pareto de motivos · semana {semana}", pill("datos de ejemplo", "claro") if MODO_DEMO else "")
        maximo = max(motivos.values()) or 1
        H("<div>" + "".join(f'<div class="mfila"><b>{m}</b><span>{MOTIVOS[m][1]}</span>{barra(c / maximo, "oro")}<b>{c}</b></div>'
                            for m, c in motivos.items()) + "</div>")
    if db["inconformidades"]:
        with st.expander("Ver registros"):
            tabla(["Fecha", "Tipo", "Producto", "U.", "Lote", "Motivo", "Nota"],
                  [[f"{fecha(r['fecha']):%d/%m %H:%M}", r["tipo"], PRODUCTOS[r["producto"]]["nombre"], r["unidades"],
                    e(r["lote"] or "—"), r["motivo"], e(r["nota"])] for r in reversed(db["inconformidades"])])


def enviar_encuesta():
    s = st.session_state
    base = f"enc_{n('encuesta')}"
    valores = {k: s.get(f"{base}_{k}") for k in ("sabor", "frescura", "tamano")}
    if any(v is None for v in valores.values()):
        aviso("Responde las 3 preguntas.", "error")
        return
    with transaccion() as db:
        db["encuestas"].append({"fecha": iso(ahora()), **valores, "comentario": s.get(f"{base}_com", "")[:300]})
    siguiente("encuesta")
    aviso("¡Gracias por tu opinión!")


def pagina_encuesta():
    """Vista para el cliente (sin menú)."""
    H('<style>[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],[data-testid="stExpandSidebarButton"]{display:none}</style>')
    titulo("Panadería Juandy", "Cuéntanos cómo estuvo tu pan (1 = malo, 5 = excelente)")
    base = f"enc_{n('encuesta')}"
    for clave, pregunta in (("sabor", "¿Cómo estuvo el sabor?"), ("frescura", "¿Qué tan fresco estaba?"), ("tamano", "¿Qué te pareció el tamaño?")):
        st.radio(pregunta, [1, 2, 3, 4, 5], index=None, horizontal=True, key=f"{base}_{clave}")
    st.text_input("Comentario (opcional)", max_chars=300, key=f"{base}_com")
    st.button("Enviar", key="verde_encuesta", on_click=enviar_encuesta)


# ---------- Indicadores ----------
def grafica_tendencia(puntos):
    y = lambda v: 20 + (35 - max(15, min(v, 35))) * 8
    x = lambda s: 50 + (s - 1) * (430 / max(4, max(puntos, default=5) - 1))
    p = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 560 215" font-family="Arial" font-size="11">']
    for v in (35, 30, 25, 20, 15):
        p.append(f'<line x1="40" x2="540" y1="{y(v)}" y2="{y(v)}" stroke="#ebdfc6"/><text x="5" y="{y(v) + 4}" fill="#8a7d72">{v}%</text>')
    for v, color, texto in ((LINEA_BASE, "#b5472f", "Línea base"), (META, "#4e8a5a", "Meta")):
        p.append(f'<line x1="40" x2="540" y1="{y(v)}" y2="{y(v)}" stroke="{color}" stroke-dasharray="5 4"/>'
                 f'<text x="540" y="{y(v) - 5}" text-anchor="end" fill="{color}">{texto} {num(v)} %</text>')
    if puntos:
        linea = " ".join(f"{x(s)},{y(v)}" for s, v in puntos.items())
        p.append(f'<polyline points="{linea}" fill="none" stroke="#3e2a1f" stroke-width="2.5"/>')
        for s, v in puntos.items():
            p.append(f'<circle cx="{x(s)}" cy="{y(v)}" r="5" fill="#d9a441" stroke="#3e2a1f" stroke-width="2"/>'
                     f'<text x="{x(s)}" y="{y(v) - 10}" text-anchor="middle" font-weight="bold" fill="#3e2a1f">{v:.0f}%</text>'
                     f'<text x="{x(s)}" y="208" text-anchor="middle" fill="#3e2a1f">S{s}</text>')
    p.append("</svg>")
    datos = base64.b64encode("".join(p).encode("utf-8")).decode()
    H(f'<div><img style="width:100%" alt="Tasa de inconformidad por semana" src="data:image/svg+xml;base64,{datos}"></div>')


def pagina_indicadores(db):
    titulo("Indicadores de seguimiento", "Comparación con la línea base y la meta")
    semana = semana_de(ahora().date())
    ind = indicadores(db, semana)
    puntos = {}
    for s in range(1, semana + 1):
        if MODO_DEMO and s in TENDENCIA_DEMO:
            puntos[s] = TENDENCIA_DEMO[s]
        else:
            tasa = indicadores(db, s)["tasa"]
            if tasa is not None:
                puntos[s] = tasa
    tasa = ind["tasa"]
    dif = None if tasa is None else tasa - LINEA_BASE
    texto_dif = "—" if dif is None else f"{'−' if dif < 0 else '+'}{num(abs(dif))} pts"
    pc = lambda v: "—" if v is None else f"{v:.0f} %"
    c = st.columns(4)
    with c[0]:
        kpi(pc(tasa), f"tasa de inconformidad · sem. {semana}", "oscuro")
    with c[1]:
        kpi(texto_dif, f"frente a la línea base ({num(LINEA_BASE)} %)")
    with c[2]:
        kpi(pc(ind["desecho"]), "desecho interno")
    with c[3]:
        kpi(pc(ind["cumplen"]), "verificaciones que cumplen")
    quejas = sum(ind["motivos"].values())
    motivo = MOTIVOS[max(ind["motivos"], key=ind["motivos"].get)][1].replace(", textura o sabor", " y textura").lower() if quejas else "sin registros"
    producto = PRODUCTOS[max(ind["por_producto"], key=ind["por_producto"].get)]["nombre"].lower() if quejas else "sin registros"
    izq, der = st.columns([3, 2])
    with izq, tarjeta("tendencia"):
        h4("Tasa de inconformidad por semana", pill("datos de ejemplo", "claro") if MODO_DEMO else "")
        grafica_tendencia(puntos)
        st.caption("Tasa = inconformidades registradas ÷ ventas registradas en la semana.")
    with der, tarjeta("kaizen"):
        h4("Resumen para el Kaizen")
        H(f"""<div class="celda">• Motivo principal: <b>{motivo}</b><br>• Producto con más quejas: <b>{producto}</b><br>
            • Agotados esta semana: <b>{ind['agotados']}</b><br>• Lotes descartados por vencimiento: <b>{ind['descartados']}</b><br>
            • Problemas reportados en el procedimiento: <b>{ind['problemas']}</b></div>""")
        problemas = [p for p in db["problemas"] if semana_de(fecha(p["fecha"]).date()) == semana]
        resumen = "\n".join([
            f"RESUMEN KAIZEN · Panadería Juandy · semana {semana}{' (incluye datos de ejemplo)' if MODO_DEMO else ''}",
            f"Tasa de inconformidad: {pc(tasa)} ({texto_dif} frente a {num(LINEA_BASE)} %; meta {num(META)} %)",
            f"Desecho interno: {pc(ind['desecho'])}", f"Verificaciones que cumplen: {pc(ind['cumplen'])}",
            f"Motivo principal: {motivo}", f"Producto con más quejas: {producto}",
            f"Agotados: {ind['agotados']}", f"Lotes descartados por vencimiento: {ind['descartados']}",
            "", "Problemas reportados:",
            *([f"- {PRODUCTOS[p['producto']]['nombre']}, paso {p['paso']}: {p['texto']}" for p in problemas] or ["- Ninguno"]),
            "", "Acciones y responsables:", "1.", "2.", "3."])
        st.download_button("Exportar resumen", resumen, file_name=f"kaizen_semana_{semana}.txt",
                           mime="text/plain", key="oro_exportar")


# =====================================================================
# 9. APLICACIÓN
# =====================================================================
PANTALLAS = {
    "inicio": pagina_inicio, "cronograma": pagina_cronograma, "produccion": pagina_produccion,
    "inventario": pagina_inventario, "lotes": pagina_lotes, "procedimientos": pagina_procedimientos,
    "fichas": pagina_fichas, "verificacion": pagina_verificacion,
    "inconformidades": pagina_inconformidades, "indicadores": pagina_indicadores,
}


def mostrar_avisos():
    for tipo, mensaje in st.session_state.pop("avisos", []):
        getattr(st, tipo)(mensaje)


def main():
    H(ESTILO)
    if st.query_params.get("vista") == "encuesta":
        mostrar_avisos()
        pagina_encuesta()
        return
    st.session_state.setdefault("pagina", "inicio")
    db = cargar()
    barra_lateral(db)
    t = ahora()
    pagina = st.session_state.pagina
    H(f"""<div class="topbar"><div class="logo">J</div><span class="marca">Juandy Lean</span><span>· {TITULOS[pagina]}</span>
        <span class="ok">● Guardado</span><span class="turno">Turno {turno(t)} · {DIAS[t.weekday()][:3]} {t.day} {MESES[t.month - 1][:3]}</span></div>""")
    mostrar_avisos()
    PANTALLAS[pagina](db)
    nota = "Pantallas de demostración con datos de ejemplo" if MODO_DEMO else "Valores técnicos por validar con la panadería"
    H(f'<div class="pie"><span>Panadería Juandy S.A.S. · Propuesta de software Lean Service · Proyecto 7S8G04</span>{pill(nota, "claro")}</div>')


main()
