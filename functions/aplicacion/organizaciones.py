"""Casos de uso de la empresa: crearla, invitar a su gente y conectar Claude."""

from __future__ import annotations

import hashlib
import re
import secrets

from dominio.caso import caso_base

from .puertos import Cifrador, DatosInvalidos, NoAutorizado, NoEncontrado, Reloj, RepoOrganizaciones, RepoPlanes

ROLES = ("admin", "lector")
PREFIJO_TOKEN = "gia_"
CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def huella(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def rol_de(org: dict, uid: str) -> str | None:
    return (org.get("roles") or {}).get(uid)


def exigir(repo: RepoOrganizaciones, org_id: str, uid: str, rol: str = "lector") -> dict:
    """Devuelve la empresa si `uid` es miembro con al menos `rol`."""
    org = repo.leer(org_id) if org_id else None
    if not org:
        raise NoEncontrado("No existe esa empresa.")
    tiene = rol_de(org, uid)
    if tiene is None or (rol == "admin" and tiene != "admin"):
        raise NoAutorizado("No tienes permiso para esto en esta empresa.")
    return org


def crear(repo: RepoOrganizaciones, planes: RepoPlanes, reloj: Reloj, uid: str, email: str | None,
          nombre: str, con_ejemplo: bool, zona: str = "America/Bogota") -> str:
    nombre = (nombre or "").strip()[:120]
    if not nombre:
        raise DatosInvalidos("Ponle un nombre a la empresa.")
    ahora = reloj.ahora()
    org_id = repo.crear({
        "nombre": nombre, "creadaEn": ahora, "creadaPor": uid, "zona": zona,
        "roles": {uid: "admin"}, "miembrosUid": [uid],
        "miembros": {uid: {"email": email or "", "rol": "admin"}},
    })
    caso = caso_base()
    caso["empresa"] = nombre
    if not con_ejemplo:
        caso["personas"] = [{"nombre": "", "email": email or "", "equipo": "General", "salario": 2000,
                             "gasto": 100, "herramienta": "Claude"}]
    caso["personas"] = [{**p, "id": f"p{i + 1}", "email": p.get("email", "")} for i, p in enumerate(caso["personas"])]
    caso["ejemplo"] = bool(con_ejemplo)
    caso["version"] = 1
    planes.guardar_caso(org_id, caso)
    mes = f"{ahora.year}-{ahora.month:02d}"
    planes.guardar_seguimiento(org_id, {"mes": mes, "recorte": False, "manual": {}, "hechos": {}})
    return org_id


def invitar(repo: RepoOrganizaciones, org_id: str, uid: str, email: str, rol: str) -> None:
    exigir(repo, org_id, uid, "admin")
    email = (email or "").strip().lower()
    if not CORREO.match(email):
        raise DatosInvalidos("Ese correo no es válido.")
    if rol not in ROLES:
        raise DatosInvalidos("Rol desconocido.")
    repo.guardar_invitacion(email, org_id, rol)
    org = repo.leer(org_id) or {}
    pendientes = dict(org.get("invitados") or {})
    pendientes[email.replace(".", ",")] = {"email": email, "rol": rol}
    repo.actualizar(org_id, {"invitados": pendientes})


def aceptar_invitaciones(repo: RepoOrganizaciones, uid: str, email: str | None, verificado: bool) -> list[str]:
    """Al entrar por primera vez, la persona queda en las empresas que la invitaron."""
    if not email or not verificado:
        return []
    email = email.strip().lower()
    unidas = []
    for org_id, rol in repo.invitaciones_de(email).items():
        org = repo.leer(org_id)
        if not org:
            continue
        roles = dict(org.get("roles") or {})
        roles.setdefault(uid, rol)
        miembros = dict(org.get("miembros") or {})
        miembros[uid] = {"email": email, "rol": roles[uid]}
        invitados = {k: v for k, v in (org.get("invitados") or {}).items() if v.get("email") != email}
        uids = sorted(set(org.get("miembrosUid") or []) | {uid})
        repo.actualizar(org_id, {"roles": roles, "miembros": miembros, "miembrosUid": uids, "invitados": invitados})
        repo.guardar_invitacion(email, org_id, None)
        unidas.append(org_id)
    return unidas


def quitar_miembro(repo: RepoOrganizaciones, org_id: str, uid: str, quien: str) -> None:
    org = exigir(repo, org_id, uid, "admin")
    if quien == uid:
        raise DatosInvalidos("No puedes quitarte a ti mismo.")
    roles = {k: v for k, v in (org.get("roles") or {}).items() if k != quien}
    miembros = {k: v for k, v in (org.get("miembros") or {}).items() if k != quien}
    repo.actualizar(org_id, {"roles": roles, "miembros": miembros, "miembrosUid": sorted(roles)})


# ---------------------------------------------------------------- conexión con Claude
def crear_token(repo: RepoOrganizaciones, reloj: Reloj, org_id: str, uid: str, nombre: str) -> dict:
    """Token de la empresa para que Claude Code reporte el gasto. Se muestra una sola vez."""
    exigir(repo, org_id, uid, "admin")
    token = PREFIJO_TOKEN + secrets.token_urlsafe(32)
    h = huella(token)
    datos = {"org": org_id, "nombre": (nombre or "Claude Code").strip()[:60], "creadoEn": reloj.ahora(),
             "creadoPor": uid, "fin": token[-4:], "revocado": False}
    repo.guardar_token(h, datos)
    return {"token": token, "id": h[:16], **{k: datos[k] for k in ("nombre", "fin")}}


def revocar_token(repo: RepoOrganizaciones, org_id: str, uid: str, id_corto: str) -> None:
    exigir(repo, org_id, uid, "admin")
    for t in repo.tokens_de(org_id):
        if t["huella"].startswith(id_corto) and len(id_corto) >= 8:
            repo.revocar_token(t["huella"])
            return
    raise NoEncontrado("No existe ese token.")


def autorizar_token(repo: RepoOrganizaciones, token: str | None) -> str:
    """Devuelve la empresa dueña del token o lanza NoAutorizado."""
    if not token or not token.startswith(PREFIJO_TOKEN) or len(token) > 200:
        raise NoAutorizado("Token inválido.")
    datos = repo.leer_token(huella(token))
    if not datos or datos.get("revocado"):
        raise NoAutorizado("Token inválido o revocado.")
    return datos["org"]


# Servicios cuya clave de administración guarda la empresa: (campo en la empresa, validación, mensaje)
SERVICIOS = {
    "anthropic": ("anthropic", lambda c: c.startswith("sk-ant-admin"),
                  "Usa una clave de administración (empieza por sk-ant-admin)."),
    "openai": ("openai", lambda c: c.startswith("sk-") and len(c) >= 20,
               "Usa una clave de administración de OpenAI (empieza por sk-)."),
    "cursor": ("cursor", lambda c: len(c) >= 16 and " " not in c,
               "Esa clave de Cursor no parece válida."),
}


def guardar_clave(repo: RepoOrganizaciones, cifrador: Cifrador, org_id: str, uid: str, servicio: str,
                  clave: str | None) -> dict:
    """Guarda (cifrada) la clave de administración de un servicio, o la borra si viene vacía."""
    exigir(repo, org_id, uid, "admin")
    if servicio not in SERVICIOS:
        raise DatosInvalidos("Servicio desconocido.")
    campo, valida, mensaje = SERVICIOS[servicio]
    clave = (clave or "").strip()
    if not clave:
        repo.guardar_secreto(org_id, f"{servicio}_admin", None)
        repo.actualizar(org_id, {campo: {"conectado": False}})
        return {"conectado": False}
    if not valida(clave) or len(clave) > 400:
        raise DatosInvalidos(mensaje)
    repo.guardar_secreto(org_id, f"{servicio}_admin", cifrador.cifrar(clave))
    estado = {"conectado": True, "fin": clave[-4:]}
    repo.actualizar(org_id, {campo: estado})
    return estado


def guardar_clave_anthropic(repo, cifrador, org_id, uid, clave):
    return guardar_clave(repo, cifrador, org_id, uid, "anthropic", clave)


def actualizar_empresa(repo: RepoOrganizaciones, org_id: str, uid: str, nombre: str | None, zona: str | None) -> dict:
    """Nombre y zona horaria (la zona decide a qué hora local se cierra el mes y qué día es «hoy»)."""
    from dominio.cierre import zona_valida

    exigir(repo, org_id, uid, "admin")
    cambios = {}
    if nombre is not None:
        nombre = nombre.strip()[:120]
        if not nombre:
            raise DatosInvalidos("Ponle un nombre a la empresa.")
        cambios["nombre"] = nombre
    if zona is not None:
        if zona_valida(zona) != zona:
            raise DatosInvalidos("Zona horaria desconocida.")
        cambios["zona"] = zona
    if cambios:
        repo.actualizar(org_id, cambios)
    return cambios
