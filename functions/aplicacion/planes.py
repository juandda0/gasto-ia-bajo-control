"""Casos de uso del plan: calcularlo solo cuando cambian los datos y cerrar el mes."""

from __future__ import annotations

import json
import math

import numpy as np

from dominio.cierre import cerrar_mes, normalizar_caso
from dominio.ciclo import resolver
from dominio.consumo import repartir

from .puertos import DatosInvalidos, NoEncontrado, Reloj, RepoConsumo, RepoPlanes


def a_json(obj):
    """Convierte numpy, NaN e infinitos a tipos que aceptan JSON y Firestore."""
    if isinstance(obj, dict):
        return {str(k): a_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [a_json(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return a_json(obj.tolist())
    if isinstance(obj, np.generic):
        obj = obj.item()
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def calcular(caso: dict) -> dict:
    """Plan completo para un caso (sin guardar nada). Lanza DatosInvalidos si no se puede."""
    try:
        return a_json(resolver(normalizar_caso(caso)))
    except (ValueError, AssertionError, KeyError, TypeError, IndexError) as e:
        raise DatosInvalidos(f"No se pudo calcular el plan con estos datos: {e}") from e


def recalcular(planes: RepoPlanes, reloj: Reloj, org: str, caso: dict | None) -> dict:
    """Se dispara cada vez que la empresa cambia sus datos: deja el plan nuevo (o el error) guardado.

    El resultado se guarda como texto JSON: trae matrices (listas de listas) que Firestore no admite
    como campos, y el navegador lo lee de una vez.
    """
    if not caso:
        return {}
    version = caso.get("version", 0)
    anterior = planes.leer_plan(org) or {}
    if anterior.get("version", -1) > version:
        return anterior  # llegó tarde un cambio viejo: no pisa el plan más nuevo
    try:
        doc = {"version": version, "calculadoEn": reloj.ahora(), "error": None,
               "resultado": json.dumps(calcular(caso), ensure_ascii=False)}
    except DatosInvalidos as e:
        doc = {**{k: v for k, v in anterior.items() if k == "resultado"}, "version": version,
               "calculadoEn": reloj.ahora(), "error": str(e).replace("No se pudo calcular el plan con estos datos: ", "")}
    planes.guardar_plan(org, doc)
    return doc


def cerrar(planes: RepoPlanes, consumo: RepoConsumo, reloj: Reloj, org: str, mes: str | None = None) -> dict | None:
    """Cierra el mes en curso. Con `mes`, solo lo cierra si el seguimiento va en ese mes (idempotente)."""
    seg = planes.leer_seguimiento(org)
    caso = planes.leer_caso(org)
    plan_doc = planes.leer_plan(org) or {}
    if not seg or not caso:
        raise NoEncontrado("La empresa aún no tiene datos.")
    if mes and seg.get("mes") != mes:
        return None
    if not plan_doc.get("resultado"):
        raise DatosInvalidos("Todavía no hay un plan calculado para cerrar el mes.")
    plan = json.loads(plan_doc["resultado"])
    gastado = repartir(caso.get("personas") or [], consumo.gasto_de(org, seg["mes"]))
    for pid, v in (seg.get("manual") or {}).items():
        if v is not None and v != "":
            gastado[pid] = gastado.get(pid, 0.0) + float(v)
    nuevo_caso, historial, nuevo_seg = cerrar_mes(caso, seg, plan, gastado)
    nuevo_caso["version"] = int(caso.get("version", 0)) + 1
    nuevo_caso["ejemplo"] = False
    historial["cerradoEn"] = reloj.ahora()
    planes.agregar_historial(org, historial)
    planes.guardar_seguimiento(org, nuevo_seg)
    planes.guardar_caso(org, nuevo_caso)  # el disparador recalcula el plan del mes nuevo
    return historial
