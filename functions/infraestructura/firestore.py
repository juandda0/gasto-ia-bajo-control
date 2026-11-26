"""Adaptadores de Firestore para los puertos de la capa de aplicación.

Estructura de datos (todo cuelga de la empresa, así las reglas de seguridad son simples):

  organizaciones/{org}                              nombre, zona, roles {uid: rol}, miembrosUid [uid]
  organizaciones/{org}/estado/caso                  personas y reglas (lo edita la empresa)
  organizaciones/{org}/estado/seguimiento           mes en curso, anotado a mano, tareas hechas
  organizaciones/{org}/estado/plan                  plan calculado (solo el servidor)
  organizaciones/{org}/historial/{mes}              meses cerrados
  organizaciones/{org}/gasto/{mes}/personas/{clave} gasto en vivo por persona (solo el servidor)
  organizaciones/{org}/conciliacion/{mes}           lo facturado según Anthropic
  organizaciones/{org}/alertas/{id}                 alertas de tope (80 % y 100 %)
  organizaciones/{org}/eventos/{id}                 eventos ya contados (idempotencia, caducan)
  invitaciones/{email}, tokensIngesta/{huella}, secretos/{org}   solo el servidor
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from google.api_core import exceptions as gexc
from google.cloud import firestore as gfs

from dominio.consumo import EventoConsumo, clave_segura

DIAS_EVENTOS = 62  # los eventos crudos se borran solos (política TTL sobre `expiraEn`)
LOTE = 200


def _incrementos(eventos: list[tuple[EventoConsumo, str]]) -> dict:
    usd = sum(e.usd for e, _ in eventos)
    por_dia: dict[str, float] = defaultdict(float)
    por_modelo: dict[str, float] = defaultdict(float)
    por_herramienta: dict[str, float] = defaultdict(float)
    tokens: dict[str, int] = defaultdict(int)
    for e, dia in eventos:
        por_dia[dia] += e.usd
        por_modelo[clave_segura(e.modelo)] += e.usd
        por_herramienta[e.herramienta] += e.usd
        for t, n in e.tokens.items():
            tokens[t] += n
    ultimo = max(e.momento for e, _ in eventos)
    email = next((e.email for e, _ in eventos if e.email), None)
    datos = {
        "usd": gfs.Increment(usd),
        "eventos": gfs.Increment(len(eventos)),
        "porDia": {d: gfs.Increment(v) for d, v in por_dia.items()},
        "porModelo": {m: gfs.Increment(v) for m, v in por_modelo.items()},
        "porHerramienta": {h: gfs.Increment(v) for h, v in por_herramienta.items()},
        "tokens": {t: gfs.Increment(n) for t, n in tokens.items()},
        "ultimo": ultimo,
    }
    if email:
        datos["email"] = email
    return datos


class Firestore:
    """Implementa RepoOrganizaciones, RepoPlanes y RepoConsumo sobre un cliente de Firestore."""

    def __init__(self, db: gfs.Client):
        self.db = db

    # ------------------------------------------------------------ organizaciones
    def _org(self, org: str):
        return self.db.collection("organizaciones").document(org)

    def crear(self, datos: dict) -> str:
        ref = self.db.collection("organizaciones").document()
        ref.set(datos)
        return ref.id

    def leer(self, org: str) -> dict | None:
        s = self._org(org).get()
        return s.to_dict() if s.exists else None

    def actualizar(self, org: str, cambios: dict) -> None:
        # update() reemplaza cada campo de primer nivel completo (los mapas quedan tal como vienen)
        self._org(org).update(cambios)

    def ids(self):
        for s in self.db.collection("organizaciones").select([]).stream():
            yield s.id

    def invitaciones_de(self, email: str) -> dict[str, str]:
        s = self.db.collection("invitaciones").document(email).get()
        return dict((s.to_dict() or {}).get("orgs") or {}) if s.exists else {}

    def guardar_invitacion(self, email: str, org: str, rol: str | None) -> None:
        ref = self.db.collection("invitaciones").document(email)
        if rol is None:
            ref.set({"orgs": {org: gfs.DELETE_FIELD}}, merge=True)
        else:
            ref.set({"orgs": {org: rol}}, merge=True)

    def guardar_token(self, huella: str, datos: dict) -> None:
        self.db.collection("tokensIngesta").document(huella).set(datos)
        # copia sin la huella completa para que el panel liste los tokens de la empresa
        self._org(datos["org"]).collection("tokens").document(huella[:16]).set(
            {k: datos[k] for k in ("nombre", "creadoEn", "fin", "revocado")})

    def leer_token(self, huella: str) -> dict | None:
        s = self.db.collection("tokensIngesta").document(huella).get()
        return s.to_dict() if s.exists else None

    def tokens_de(self, org: str) -> list[dict]:
        q = self.db.collection("tokensIngesta").where(filter=gfs.FieldFilter("org", "==", org))
        return [{"huella": s.id, **s.to_dict()} for s in q.stream()]

    def revocar_token(self, huella: str) -> None:
        ref = self.db.collection("tokensIngesta").document(huella)
        datos = ref.get().to_dict() or {}
        ref.update({"revocado": True})
        if datos.get("org"):
            self._org(datos["org"]).collection("tokens").document(huella[:16]).set({"revocado": True}, merge=True)

    def guardar_secreto(self, org: str, nombre: str, cifrado: str | None) -> None:
        ref = self.db.collection("secretos").document(org)
        ref.set({nombre: cifrado if cifrado is not None else gfs.DELETE_FIELD}, merge=True)

    def leer_secreto(self, org: str, nombre: str) -> str | None:
        s = self.db.collection("secretos").document(org).get()
        return (s.to_dict() or {}).get(nombre) if s.exists else None

    # ------------------------------------------------------------ planes
    def _estado(self, org: str, nombre: str):
        return self._org(org).collection("estado").document(nombre)

    def _leer_estado(self, org: str, nombre: str) -> dict | None:
        s = self._estado(org, nombre).get()
        return s.to_dict() if s.exists else None

    def leer_caso(self, org):
        return self._leer_estado(org, "caso")

    def guardar_caso(self, org, caso):
        self._estado(org, "caso").set(caso)

    def leer_seguimiento(self, org):
        return self._leer_estado(org, "seguimiento")

    def guardar_seguimiento(self, org, seg):
        self._estado(org, "seguimiento").set(seg)

    def leer_plan(self, org):
        return self._leer_estado(org, "plan")

    def guardar_plan(self, org, doc):
        self._estado(org, "plan").set(doc)

    def agregar_historial(self, org, entrada):
        self._org(org).collection("historial").document(entrada["mes"]).set(entrada)

    # ------------------------------------------------------------ consumo
    def _personas_mes(self, org: str, mes: str):
        return self._org(org).collection("gasto").document(mes).collection("personas")

    def registrar(self, org: str, mes: str, filas: list[tuple[EventoConsumo, str, str]]) -> list[str]:
        tocadas: set[str] = set()
        for i in range(0, len(filas), LOTE):
            parte = filas[i:i + LOTE]
            try:
                self._registrar_lote(org, mes, parte)
                tocadas.update(c for _, c, _ in parte)
            except (gexc.Conflict, gexc.AlreadyExists, gexc.InvalidArgument):
                # algún evento ya estaba contado (reintento del cliente): se cuentan uno por uno
                for fila in parte:
                    try:
                        self._registrar_lote(org, mes, [fila])
                        tocadas.add(fila[1])
                    except (gexc.Conflict, gexc.AlreadyExists):
                        pass
        return sorted(tocadas)

    def _registrar_lote(self, org, mes, filas):
        lote = self.db.batch()
        eventos = self._org(org).collection("eventos")
        expira = datetime.now(timezone.utc) + timedelta(days=DIAS_EVENTOS)
        por_persona: dict[str, list] = defaultdict(list)
        for ev, clave, dia in filas:
            lote.create(eventos.document(ev.id), {"mes": mes, "persona": clave, "usd": ev.usd, "modelo": ev.modelo,
                                                  "momento": ev.momento, "origen": ev.origen, "expiraEn": expira})
            por_persona[clave].append((ev, dia))
        for clave, evs in por_persona.items():
            lote.set(self._personas_mes(org, mes).document(clave), {"clave": clave, **_incrementos(evs)}, merge=True)
        lote.set(self._org(org).collection("gasto").document(mes), {"mes": mes, "actualizadoEn": gfs.SERVER_TIMESTAMP},
                 merge=True)
        lote.commit()

    def gasto_de(self, org: str, mes: str) -> dict[str, dict]:
        return {s.id: s.to_dict() for s in self._personas_mes(org, mes).stream()}

    def crear_alerta(self, org: str, id_: str, datos: dict) -> bool:
        try:
            self._org(org).collection("alertas").document(id_).create(datos)
            return True
        except (gexc.Conflict, gexc.AlreadyExists):
            return False

    def guardar_externo(self, org: str, mes: str, herramienta: str, filas: dict[str, dict]) -> None:
        """Reemplaza el acumulado del mes de una herramienta en la ficha de cada persona."""
        claves = list(filas.items())
        for i in range(0, len(claves), 400):
            lote = self.db.batch()
            for clave, f in claves[i:i + 400]:
                datos = {"clave": clave, "externo": {herramienta: round(float(f["usd"]), 4)},
                         "externoEn": gfs.SERVER_TIMESTAMP}
                if f.get("email"):
                    datos["email"] = f["email"]
                lote.set(self._personas_mes(org, mes).document(clave), datos, merge=True)
            lote.set(self._org(org).collection("gasto").document(mes),
                     {"mes": mes, "actualizadoEn": gfs.SERVER_TIMESTAMP}, merge=True)
            lote.commit()

    def guardar_gasto_api(self, org: str, mes: str, datos: dict) -> None:
        self._org(org).collection("conciliacion").document(mes).set(datos)
