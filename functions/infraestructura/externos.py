"""Adaptadores pequeños: reloj, cifrado de secretos y la API de costos de Anthropic."""

from __future__ import annotations

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
