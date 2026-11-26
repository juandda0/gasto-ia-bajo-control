"""Casos de uso del gasto real: recibir lo que reporta Claude y conciliar con Anthropic."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from dominio.cierre import topes_vigentes
from dominio.consumo import EventoConsumo, clave_persona, clave_segura, nivel_alerta, periodo, repartir

from .puertos import Cifrador, FuenteCostosAnthropic, Reloj, RepoConsumo, RepoOrganizaciones, RepoPlanes

MAX_EVENTOS_POR_LOTE = 5000


def registrar(org_repo: RepoOrganizaciones, planes: RepoPlanes, consumo: RepoConsumo, reloj: Reloj,
              org: str, eventos: list[EventoConsumo]) -> dict:
    """Suma al mes de la empresa cada evento de costo (una sola vez) y levanta alertas de tope."""
    if not eventos:
        return {"recibidos": 0, "personas": 0, "alertas": 0}
    eventos = eventos[:MAX_EVENTOS_POR_LOTE]
    datos_org = org_repo.leer(org) or {}
    zona = datos_org.get("zona") or "America/Bogota"
    caso = planes.leer_caso(org) or {}
    personas = caso.get("personas") or []

    por_mes: dict[str, list] = defaultdict(list)
    for ev in eventos:
        mes, dia = periodo(ev.momento, zona)
        por_mes[mes].append((ev, clave_persona(ev.email, personas), dia))

    tocadas: dict[str, set[str]] = {}
    for mes, filas in por_mes.items():
        tocadas[mes] = set(consumo.registrar(org, mes, filas))

    alertas = _alertas(planes, consumo, reloj, org, personas, tocadas)
    return {"recibidos": len(eventos), "personas": sum(len(v) for v in tocadas.values()), "alertas": alertas}


def _alertas(planes, consumo, reloj, org, personas, tocadas) -> int:
    seg = planes.leer_seguimiento(org) or {}
    plan_doc = planes.leer_plan(org) or {}
    mes = seg.get("mes")
    if not plan_doc.get("resultado") or mes not in tocadas:
        return 0
    plan = json.loads(plan_doc["resultado"])
    tp = topes_vigentes(plan, bool(seg.get("recorte")))
    nombre = {p["id"]: p.get("nombre") for p in plan["datos"]["personas"]}
    manual = seg.get("manual") or {}
    gasto = repartir(personas, consumo.gasto_de(org, mes))
    nuevas = 0
    for clave in tocadas[mes]:
        if clave not in nombre:
            continue  # gasto de alguien que no está en el equipo: se ve en «Sin asignar»
        total = gasto.get(clave, 0.0) + float(manual.get(clave) or 0)
        tope = float(tp.get(nombre[clave], 0) or 0)
        nivel = nivel_alerta(total, tope)
        if nivel and consumo.crear_alerta(org, f"{mes}-{clave}-{nivel}", {
            "mes": mes, "persona": clave, "nombre": nombre[clave], "nivel": nivel,
            "gastado": round(total, 2), "tope": round(tope, 2), "creadaEn": reloj.ahora(),
        }):
            nuevas += 1
    return nuevas


def sincronizar_anthropic(org_repo: RepoOrganizaciones, planes: RepoPlanes, consumo: RepoConsumo,
                          reloj: Reloj, cifrador: Cifrador, fuente: FuenteCostosAnthropic, org: str) -> dict | None:
    """Trae lo que Anthropic ya facturó este mes (API y Claude Code de la consola), por persona.

    Es la conciliación: la telemetría de Claude Code llega en vivo; la API de costos de Anthropic
    confirma lo facturado con unas horas de retraso. No se suman entre sí.
    """
    cifrada = org_repo.leer_secreto(org, "anthropic_admin")
    if not cifrada:
        return None
    seg = planes.leer_seguimiento(org) or {}
    ahora = reloj.ahora().astimezone(timezone.utc)
    mes = seg.get("mes") or f"{ahora.year}-{ahora.month:02d}"
    a, m = (int(x) for x in mes.split("-"))
    desde = datetime(a, m, 1, tzinfo=timezone.utc)
    hasta = min(ahora.replace(minute=0, second=0, microsecond=0), desde + timedelta(days=31))
    if hasta <= desde:
        return None
    try:
        r = fuente.costo_por_actor(cifrador.descifrar(cifrada), desde, hasta)
    except Exception as e:  # clave revocada, sin permiso, red: se informa en la empresa
        org_repo.actualizar(org, {"anthropic": {**((org_repo.leer(org) or {}).get("anthropic") or {}),
                                                "error": str(e)[:300], "revisadoEn": reloj.ahora()}})
        return None
    personas = (planes.leer_caso(org) or {}).get("personas") or []
    por_persona: dict[str, dict] = {}
    por_modelo: dict[str, float] = defaultdict(float)
    total = 0.0
    for f in r["filas"]:
        clave = clave_persona(f.get("email"), personas) if f.get("email") else "api-" + clave_segura(f.get("usuario") or "sin-actor")
        fila = por_persona.setdefault(clave, {"email": f.get("email") or "", "usuario": f.get("usuario") or "", "usd": 0.0})
        fila["usd"] = round(fila["usd"] + f["usd"], 4)
        por_modelo[clave_segura(f.get("modelo") or "otro")] += f["usd"]
        total += f["usd"]
    datos = {"total": round(total, 4), "porPersona": por_persona,
             "porModelo": {k: round(v, 4) for k, v in por_modelo.items()},
             "datosHasta": r.get("datos_hasta"), "sincronizadoEn": reloj.ahora()}
    consumo.guardar_gasto_api(org, mes, datos)
    org_repo.actualizar(org, {"anthropic": {**((org_repo.leer(org) or {}).get("anthropic") or {}),
                                            "error": None, "revisadoEn": reloj.ahora()}})
    return datos
