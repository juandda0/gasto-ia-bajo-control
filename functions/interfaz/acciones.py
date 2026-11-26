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


def sincronizar_servicio(org: str, servicio: str):
    """Trae ya mismo lo de un servicio conectado (lo usan el panel y la tarea programada)."""
    r = contexto.repo()
    if servicio == "anthropic":
        return ingesta.sincronizar_anthropic(r, r, r, contexto.reloj(), contexto.cifrador(),
                                             contexto.fuente_anthropic(), org)
    return ingesta.sincronizar_fuente(r, r, r, contexto.reloj(), contexto.cifrador(),
                                      contexto.fuente_gasto(servicio), org, servicio)


def _guardar_clave(s: Sesion, d: dict):
    servicio = d.get("servicio") or "anthropic"
    estado = organizaciones.guardar_clave(contexto.repo(), contexto.cifrador(), d.get("org", ""), s.uid, servicio,
                                          d.get("clave"))
    if estado.get("conectado"):
        sincronizar_servicio(d["org"], servicio)
    return estado


def _sincronizar(s: Sesion, d: dict):
    organizaciones.exigir(contexto.repo(), d.get("org", ""), s.uid, "admin")
    servicio = d.get("servicio") or "anthropic"
    if servicio not in organizaciones.SERVICIOS:
        raise DatosInvalidos("Servicio desconocido.")
    return {"ok": sincronizar_servicio(d["org"], servicio) is not None}


def _actualizar_empresa(s: Sesion, d: dict):
    return organizaciones.actualizar_empresa(contexto.repo(), d.get("org", ""), s.uid, d.get("nombre"), d.get("zona"))


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
    "guardarClave": _guardar_clave,
    "guardarClaveAnthropic": _guardar_clave,  # compatibilidad: sin `servicio` es Anthropic
    "sincronizar": _sincronizar,
    "sincronizarAnthropic": _sincronizar,
    "actualizarEmpresa": _actualizar_empresa,
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
