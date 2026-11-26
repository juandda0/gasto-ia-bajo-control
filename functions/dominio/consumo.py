"""Consumo real de IA: qué gastó cada persona, a partir de lo que reporta Claude Code.

Claude Code exporta un evento `claude_code.api_request` por cada llamada al modelo, con su
costo en USD, los tokens, el modelo y el correo de quien lo usó (telemetría OpenTelemetry,
formato OTLP/JSON). Aquí solo se interpreta ese formato: nada de red ni de base de datos.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

NOMBRES_EVENTO = {"api_request", "claude_code.api_request"}
TIPOS_TOKEN = {
    "input_tokens": "entrada",
    "output_tokens": "salida",
    "cache_read_tokens": "cacheLeida",
    "cache_creation_tokens": "cacheCreada",
}
SIN_CORREO = "sin-correo"


@dataclass(frozen=True)
class EventoConsumo:
    id: str
    usd: float
    modelo: str
    momento: datetime          # UTC
    email: str | None = None
    sesion: str | None = None
    tokens: dict[str, int] = field(default_factory=dict)
    origen: str = "claude_code"


# ---------------------------------------------------------------- formato OTLP/JSON
def _valor(v: dict):
    """Convierte un AnyValue de OTLP/JSON en un valor de Python."""
    if not isinstance(v, dict):
        return v
    if "stringValue" in v:
        return v["stringValue"]
    if "intValue" in v:  # en OTLP/JSON los enteros de 64 bits llegan como texto
        try:
            return int(v["intValue"])
        except (TypeError, ValueError):
            return None
    if "doubleValue" in v:
        try:
            return float(v["doubleValue"])
        except (TypeError, ValueError):
            return None
    if "boolValue" in v:
        return bool(v["boolValue"])
    if "arrayValue" in v:
        return [_valor(x) for x in v["arrayValue"].get("values", [])]
    if "kvlistValue" in v:
        return _atributos(v["kvlistValue"].get("values", []))
    return None


def _atributos(lista) -> dict:
    return {a.get("key"): _valor(a.get("value", {})) for a in (lista or []) if isinstance(a, dict) and a.get("key")}


def _momento(registro: dict, attrs: dict) -> datetime:
    ts = attrs.get("event.timestamp")
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            pass
    for clave in ("timeUnixNano", "observedTimeUnixNano"):
        try:
            n = int(registro.get(clave) or 0)
        except (TypeError, ValueError):
            n = 0
        if n > 0:
            return datetime.fromtimestamp(n / 1e9, tz=timezone.utc)
    return datetime.now(timezone.utc)


def _numero(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return v if v == v and v >= 0 else 0.0  # descarta NaN y negativos


def eventos_desde_otlp(carga: dict) -> list[EventoConsumo]:
    """Saca los eventos de costo de un lote OTLP/JSON de logs. Ignora todo lo demás."""
    eventos = []
    for rl in (carga or {}).get("resourceLogs", []) or []:
        recurso = _atributos((rl.get("resource") or {}).get("attributes"))
        for sl in rl.get("scopeLogs", []) or []:
            for reg in sl.get("logRecords", []) or []:
                attrs = {**recurso, **_atributos(reg.get("attributes"))}
                cuerpo = _valor(reg.get("body") or {})
                nombre = attrs.get("event.name") or cuerpo
                if nombre not in NOMBRES_EVENTO:
                    continue
                if attrs.get("cost_usd") is not None:
                    usd = _numero(attrs.get("cost_usd"))
                else:
                    usd = _numero(attrs.get("cost_usd_micros")) / 1e6
                tokens = {destino: int(_numero(attrs.get(origen))) for origen, destino in TIPOS_TOKEN.items()
                          if attrs.get(origen) is not None}
                momento = _momento(reg, attrs)
                email = attrs.get("user.email")
                id_ = attrs.get("request_id") or attrs.get("client_request_id")
                if not id_:  # sin identificador: huella estable del registro para no contarlo dos veces
                    base = f"{attrs.get('session.id')}|{attrs.get('event.sequence')}|{momento.isoformat()}|{usd}"
                    id_ = "h" + hashlib.sha256(base.encode()).hexdigest()[:24]
                eventos.append(EventoConsumo(
                    id=str(id_)[:128], usd=usd, modelo=str(attrs.get("model") or "desconocido"),
                    momento=momento, email=email.strip().lower() if isinstance(email, str) and email.strip() else None,
                    sesion=attrs.get("session.id"), tokens=tokens,
                ))
    return eventos


# ---------------------------------------------------------------- reglas del negocio
def clave_persona(email: str | None, personas: list[dict]) -> str:
    """A quién se le carga el gasto: la persona con ese correo, o un grupo «sin asignar» por correo."""
    if not email:
        return SIN_CORREO
    for p in personas:
        if str(p.get("email") or "").strip().lower() == email:
            return str(p["id"])
    return "correo-" + hashlib.sha256(email.encode()).hexdigest()[:16]


def clave_segura(texto: str) -> str:
    """Las claves de un mapa de Firestore no pueden llevar puntos ni barras."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", texto)[:100] or "_"


def periodo(momento: datetime, zona: str = "America/Bogota") -> tuple[str, str]:
    """(mes «AAAA-MM», día «DD») en la zona horaria de la empresa."""
    try:
        local = momento.astimezone(ZoneInfo(zona))
    except Exception:  # zona inválida: se usa UTC
        local = momento.astimezone(timezone.utc)
    return f"{local.year}-{local.month:02d}", f"{local.day:02d}"


UMBRALES = (80, 100)


def nivel_alerta(gastado: float, tope: float) -> int:
    """Mayor umbral cruzado (0, 80 o 100 % del tope)."""
    if tope <= 0:
        return 100 if gastado > 0.5 else 0
    pct = gastado / tope * 100
    return max([u for u in UMBRALES if pct >= u], default=0)


def repartir(personas: list[dict], gasto_mes: dict[str, dict]) -> dict[str, float]:
    """USD del mes por id de persona. Lo que llegó a nombre de un correo antes de que esa persona
    estuviera en el equipo se le suma en cuanto aparece con ese correo."""
    ids = {str(p["id"]) for p in personas}
    por_correo = {str(p.get("email") or "").lower(): str(p["id"]) for p in personas if p.get("email")}
    out: dict[str, float] = {}
    for clave, fila in (gasto_mes or {}).items():
        duenio = clave if clave in ids else por_correo.get(str(fila.get("email") or "").lower())
        if duenio:
            out[duenio] = out.get(duenio, 0.0) + float(fila.get("usd", 0) or 0)
    return out
