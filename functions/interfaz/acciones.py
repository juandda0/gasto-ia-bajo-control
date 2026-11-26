"""Acciones del panel (una sola función invocable): cada una exige sesión y, si toca, rol de admin."""

from __future__ import annotations

import base64

from aplicacion import ingesta, organizaciones
from aplicacion.puertos import DatosInvalidos, NoAutorizado, NoEncontrado

from . import contexto


class Sesion:
    def __init__(self, uid: str, email: str | None, verificado: bool):
        self.uid, self.email, self.verificado = uid, email, verificado


def _crear(s: Sesion, d: dict):
    r = contexto.repo()
    org = organizaciones.crear(r, r, contexto.reloj(), s.uid, s.email, d.get("nombre", ""),
                               bool(d.get("conEjemplo", True)), d.get("zona") or "America/Bogota")
    return {"org": org}


def _aceptar(s: Sesion, d: dict):
    return {"orgs": organizaciones.aceptar_invitaciones(contexto.repo(), s.uid, s.email, s.verificado)}


def _invitar(s: Sesion, d: dict):
    organizaciones.invitar(contexto.repo(), d.get("org", ""), s.uid, d.get("email", ""), d.get("rol", "lector"))
    return {"ok": True}


def _quitar(s: Sesion, d: dict):
    organizaciones.quitar_miembro(contexto.repo(), d.get("org", ""), s.uid, d.get("uid", ""))
    return {"ok": True}


def _crear_token(s: Sesion, d: dict):
    return organizaciones.crear_token(contexto.repo(), contexto.reloj(), d.get("org", ""), s.uid, d.get("nombre", ""))


def _revocar_token(s: Sesion, d: dict):
    organizaciones.revocar_token(contexto.repo(), d.get("org", ""), s.uid, d.get("id", ""))
    return {"ok": True}


def _clave_anthropic(s: Sesion, d: dict):
    r = contexto.repo()
    estado = organizaciones.guardar_clave_anthropic(r, contexto.cifrador(), d.get("org", ""), s.uid, d.get("clave"))
    if estado.get("conectado"):
        ingesta.sincronizar_anthropic(r, r, r, contexto.reloj(), contexto.cifrador(), contexto.fuente_anthropic(),
                                      d["org"])
    return estado


def _sincronizar(s: Sesion, d: dict):
    r = contexto.repo()
    organizaciones.exigir(r, d.get("org", ""), s.uid, "admin")
    datos = ingesta.sincronizar_anthropic(r, r, r, contexto.reloj(), contexto.cifrador(),
                                          contexto.fuente_anthropic(), d["org"])
    return {"ok": datos is not None}


def _cerrar_mes(s: Sesion, d: dict):
    from aplicacion import planes

    r = contexto.repo()
    organizaciones.exigir(r, d.get("org", ""), s.uid, "admin")
    h = planes.cerrar(r, r, contexto.reloj(), d["org"])
    return {"mes": h["mes"], "real": h["real"]} if h else {}


def _excel(s: Sesion, d: dict):
    import json

    from .http import excel_bytes

    r = contexto.repo()
    organizaciones.exigir(r, d.get("org", ""), s.uid, "lector")
    plan = (r.leer_plan(d["org"]) or {}).get("resultado")
    if not plan:
        raise DatosInvalidos("Todavía no hay un plan calculado.")
    return {"archivo": base64.b64encode(excel_bytes(json.loads(plan))).decode()}


ACCIONES = {
    "crearOrganizacion": _crear,
    "aceptarInvitaciones": _aceptar,
    "invitarMiembro": _invitar,
    "quitarMiembro": _quitar,
    "crearToken": _crear_token,
    "revocarToken": _revocar_token,
    "guardarClaveAnthropic": _clave_anthropic,
    "sincronizarAnthropic": _sincronizar,
    "cerrarMes": _cerrar_mes,
    "exportarExcel": _excel,
}


def ejecutar(s: Sesion, datos: dict):
    """Devuelve (resultado, error). El error es (código, mensaje) para la capa de Firebase."""
    accion = ACCIONES.get((datos or {}).get("accion"))
    if not accion:
        return None, ("INVALID_ARGUMENT", "Acción desconocida.")
    try:
        return accion(s, datos), None
    except NoAutorizado as e:
        return None, ("PERMISSION_DENIED", str(e))
    except NoEncontrado as e:
        return None, ("NOT_FOUND", str(e))
    except DatosInvalidos as e:
        return None, ("INVALID_ARGUMENT", str(e))
