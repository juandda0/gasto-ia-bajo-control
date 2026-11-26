"""Reglas puras de la empresa: limpiar los datos que llegan del navegador y cerrar el mes."""

from __future__ import annotations

from copy import deepcopy

from .caso import caso_base

MAX_PERSONAS = 2000
HERRAMIENTAS = {"Claude", "Cursor", "OpenAI", "Gemini", "Ninguna"}


def _num(v, minimo=0.0, maximo=1e9) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return minimo
    if x != x:
        return minimo
    return min(max(x, minimo), maximo)


def normalizar_caso(caso: dict) -> dict:
    """Deja el caso listo para el motor: nombres únicos, números válidos, reglas en rango.

    Lo que no viene se toma del caso base, así el navegador solo manda lo que la empresa edita.
    """
    base = caso_base()
    caso = deepcopy(caso or {})
    personas_in = caso.get("personas") or []
    if not isinstance(personas_in, list) or not personas_in:
        raise ValueError("Agrega al menos una persona.")
    if len(personas_in) > MAX_PERSONAS:
        raise ValueError(f"Máximo {MAX_PERSONAS} personas por empresa.")
    vistos: dict[str, int] = {}
    personas = []
    for i, p in enumerate(personas_in):
        p = p if isinstance(p, dict) else {}
        nombre = str(p.get("nombre") or "").strip()[:80] or f"Persona {i + 1}"
        if nombre in vistos:
            vistos[nombre] += 1
            nombre = f"{nombre} {vistos[nombre]}"
        else:
            vistos[nombre] = 1
        herramienta = p.get("herramienta") if p.get("herramienta") in HERRAMIENTAS else "Ninguna"
        personas.append({
            "id": str(p.get("id") or f"p{i + 1}")[:40],
            "nombre": nombre,
            "email": str(p.get("email") or "").strip().lower()[:200],
            "equipo": str(p.get("equipo") or "").strip()[:60] or "General",
            "salario": _num(p.get("salario")),
            "gasto": _num(p.get("gasto")),
            "herramienta": herramienta,
        })
    reglas = {**base["reglas"], **(caso.get("reglas") or {})}
    reglas = {
        "presupuesto_pct_nomina": _num(reglas["presupuesto_pct_nomina"], 0.0, 1.0),
        "tope_pct_salario": _num(reglas["tope_pct_salario"], 0.0, 1.0),
        "minimo": _num(reglas["minimo"], 0.0, 1e6),
    }
    limpio = {**base, **{k: v for k, v in caso.items() if k in base}}
    limpio.update(personas=personas, reglas=reglas, recorte=_num(caso.get("recorte", base["recorte"]), 0.0, 0.9))
    limpio["empresa"] = str(caso.get("empresa") or base["empresa"])[:120]
    return limpio


def zona_valida(zona: str | None) -> str:
    """Zona horaria IANA (America/Bogota, Europe/Madrid…); si no es válida, Bogotá."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        ZoneInfo(str(zona))
        return str(zona)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return "America/Bogota"


def meses_por_cerrar(mes_seguimiento: str | None, ahora, zona: str) -> list[str]:
    """Meses que ya terminaron en la hora local de la empresa y siguen abiertos (en orden).

    El cierre automático corre cada hora; cada empresa se cierra cuando en SU zona horaria ya es
    día 1, no a la hora de Bogotá. `ahora` es un datetime con zona (UTC).
    """
    from zoneinfo import ZoneInfo

    if not mes_seguimiento:
        return []
    local = ahora.astimezone(ZoneInfo(zona_valida(zona)))
    actual = f"{local.year}-{local.month:02d}"
    pendientes, mes = [], mes_seguimiento
    while mes < actual and len(pendientes) < 24:
        pendientes.append(mes)
        mes = siguiente_mes(mes)
    return pendientes


def topes_vigentes(plan: dict, con_recorte: bool) -> dict[str, float]:
    """Topes por nombre de persona; con recorte si la empresa lo aplicó en el seguimiento."""
    if con_recorte:
        return plan["recorte"]["modelo1"]["topes"]
    return plan["modelo1"]["topes"]


def siguiente_mes(mes: str) -> str:
    a, m = (int(x) for x in mes.split("-"))
    return f"{a + 1}-01" if m == 12 else f"{a}-{m + 1:02d}"


def cerrar_mes(caso: dict, seguimiento: dict, plan: dict, gastado: dict[str, float]) -> tuple[dict, dict, dict]:
    """El gasto real del mes pasa a ser el «mes pasado» de cada persona y empieza el mes siguiente.

    `gastado` va por id de persona (automático + anotado a mano). Devuelve
    (caso nuevo, entrada del historial, seguimiento nuevo).
    """
    mes = seguimiento["mes"]
    tp = topes_vigentes(plan, bool(seguimiento.get("recorte")))
    nombres = {p["id"]: p["nombre"] for p in plan["datos"]["personas"]}
    real = sum(float(gastado.get(pid, 0) or 0) for pid in nombres)
    historial = {
        "mes": mes,
        "real": round(real, 2),
        "plan": round(sum(tp.get(n, 0) for n in nombres.values()), 2),
        "antes": plan["resultado"]["factura_antes"],
        "factura": plan["resultado"]["factura"],
        "porPersona": {pid: round(float(gastado.get(pid, 0) or 0), 2) for pid in nombres},
    }
    nuevo = deepcopy(caso)
    for p in nuevo["personas"]:
        if p.get("id") in gastado:
            p["gasto"] = round(float(gastado[p["id"]] or 0), 2)
    seg = {"mes": siguiente_mes(mes), "recorte": False, "manual": {}, "hechos": {}}
    return nuevo, historial, seg
