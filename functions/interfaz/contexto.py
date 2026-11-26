"""Cableado: crea una sola vez los adaptadores reales que usan las funciones."""

from __future__ import annotations

import os
from functools import lru_cache

from infraestructura.externos import CifradorFernet, CostosAnthropic, RelojReal


@lru_cache(maxsize=1)
def repo():
    import firebase_admin
    from firebase_admin import firestore

    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    from infraestructura.firestore import Firestore

    return Firestore(firestore.client())


@lru_cache(maxsize=1)
def reloj():
    return RelojReal()


def cifrador():
    llave = os.environ.get("CLAVE_CIFRADO")
    if not llave:
        raise RuntimeError("Falta el secreto CLAVE_CIFRADO.")
    return CifradorFernet(llave)


def fuente_anthropic():
    return CostosAnthropic()


def fuente_gasto(servicio: str):
    from infraestructura.externos import GastoCursor, GastoOpenAI

    return {"cursor": GastoCursor, "openai": GastoOpenAI}[servicio]()
