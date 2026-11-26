"""Adaptadores pequeños: reloj, cifrado de secretos y las APIs de costos de Anthropic, Cursor y OpenAI."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import anthropic
from cryptography.fernet import Fernet


class RelojReal:
    def ahora(self) -> datetime:
        return datetime.now(timezone.utc)


class CifradorFernet:
    """Cifra las claves de las empresas con una llave maestra que vive en Secret Manager."""

    def __init__(self, llave: str):
        self._f = Fernet(llave.encode() if isinstance(llave, str) else llave)

    def cifrar(self, texto: str) -> str:
        return self._f.encrypt(texto.encode()).decode()

    def descifrar(self, cifrado: str) -> str:
        return self._f.decrypt(cifrado.encode()).decode()


class CostosAnthropic:
    """Usage and Cost Analytics API (beta) de Anthropic, agrupada por persona y modelo."""

    AGENTE = "GastoIABajoControl/1.0"

    def costo_por_actor(self, clave_admin: str, desde: datetime, hasta: datetime) -> dict:
        cliente = anthropic.Anthropic(api_key=clave_admin, max_retries=2, timeout=60.0,
                                      default_headers={"User-Agent": self.AGENTE})
        pagina = cliente.beta.organization.analytics.cost.list(
            starting_at=desde, ending_at=hasta, group_by=["actor", "model"], limit=1000,
        )
        filas = []
        for fila in pagina:  # el SDK pide las páginas siguientes solo
            d = fila.to_dict()
            grupo = d.get("group") or {}
            actor = grupo.get("actor") or {}
            centavos = float((d.get("cost") or {}).get("amount") or 0)  # texto decimal en centavos
            filas.append({
                "email": (actor.get("email_address") or actor.get("email") or "").strip().lower() or None,
                "usuario": actor.get("user_id") or actor.get("service_account_id") or actor.get("api_key_id")
                or actor.get("type") or "",
                "modelo": grupo.get("model") or "otro",
                "usd": centavos / 100,
            })
        refrescado = getattr(pagina, "data_refreshed_at", None)
        return {"filas": filas, "datos_hasta": str(refrescado) if refrescado else None}


AGENTE = "GastoIABajoControl/1.0"


class ErrorServicio(Exception):
    """La API de la herramienta respondió con error (clave inválida, plan sin API, límite…)."""


def _pedir(url: str, cabeceras: dict, cuerpo: dict | None = None, metodo: str = "GET", tiempo: float = 30.0) -> dict:
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(url, data=datos, method=metodo, headers={
        "User-Agent": AGENTE, "Accept": "application/json",
        **({"Content-Type": "application/json"} if datos else {}), **cabeceras})
    try:
        with urllib.request.urlopen(req, timeout=tiempo) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        detalle = e.read()[:300].decode(errors="replace")
        raise ErrorServicio(f"HTTP {e.code}: {detalle}") from e


class GastoCursor:
    """Admin API de Cursor (planes Teams y Enterprise): gasto de cada miembro.

    POST https://api.cursor.com/teams/spend con autenticación básica (la clave es el usuario, sin
    contraseña). `overallSpendCents` es todo el uso del ciclo de facturación de Cursor a precio de
    lista, incluido lo que cubre el asiento; `spendCents` sería solo lo cobrado aparte.
    """

    URL = "https://api.cursor.com/teams/spend"

    def gasto_por_persona(self, clave_admin: str, desde: datetime, hasta: datetime) -> dict:
        auth = "Basic " + base64.b64encode(f"{clave_admin}:".encode()).decode()
        filas, pagina, ciclo = [], 1, None
        while pagina <= 50:
            r = _pedir(self.URL, {"Authorization": auth}, {"page": pagina, "pageSize": 100}, "POST")
            ciclo = r.get("subscriptionCycleStart") or ciclo
            for m in r.get("teamMemberSpend") or []:
                centavos = m.get("overallSpendCents", m.get("spendCents")) or 0
                filas.append({"email": (m.get("email") or "").strip().lower() or None,
                              "usuario": m.get("userId") or "", "usd": float(centavos) / 100})
            if pagina >= int(r.get("totalPages") or 1):
                break
            pagina += 1
        inicio = datetime.fromtimestamp(int(ciclo) / 1000, tz=timezone.utc).date().isoformat() if ciclo else None
        return {"filas": filas, "periodo": f"ciclo de Cursor desde {inicio}" if inicio else "ciclo de Cursor"}


class GastoOpenAI:
    """Costs API de la organización de OpenAI (clave de administración), por usuario.

    GET /v1/organization/costs agrupado por `user_id`, y /v1/organization/users para el correo.
    Si la organización no permite agrupar por usuario, se trae el total como «sin asignar».
    """

    BASE = "https://api.openai.com/v1/organization"

    def _todo(self, ruta: str, cabeceras: dict, params: dict, cursor: str, siguiente) -> list:
        out, paginas = [], 0
        while paginas < 40:
            r = _pedir(f"{self.BASE}/{ruta}?{urllib.parse.urlencode(params, doseq=True)}", cabeceras)
            out.extend(r.get("data") or [])
            if not r.get("has_more"):
                break
            params = {**params, cursor: siguiente(r)}
            paginas += 1
        return out

    def gasto_por_persona(self, clave_admin: str, desde: datetime, hasta: datetime) -> dict:
        cab = {"Authorization": f"Bearer {clave_admin}"}
        base = {"start_time": int(desde.timestamp()), "end_time": int(hasta.timestamp()) + 1,
                "bucket_width": "1d", "limit": 31}
        try:
            cubetas = self._todo("costs", cab, {**base, "group_by": ["user_id"]}, "page", lambda r: r.get("next_page"))
        except ErrorServicio as e:
            if "HTTP 400" not in str(e):
                raise
            cubetas = self._todo("costs", cab, base, "page", lambda r: r.get("next_page"))
        por_usuario: dict[str, float] = {}
        for c in cubetas:
            for res in c.get("results") or []:
                valor = float(((res.get("amount") or {}).get("value")) or 0)
                usuario = res.get("user_id") or "organizacion"
                por_usuario[usuario] = por_usuario.get(usuario, 0.0) + valor
        correos = {}
        if any(u != "organizacion" for u in por_usuario):
            for u in self._todo("users", cab, {"limit": 100}, "after", lambda r: r.get("last_id")):
                correos[u.get("id")] = (u.get("email") or "").strip().lower() or None
        filas = [{"email": correos.get(u), "usuario": u, "usd": v} for u, v in por_usuario.items()]
        return {"filas": filas, "periodo": "mes en curso (API de OpenAI)"}
