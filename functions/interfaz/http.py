"""Endpoints HTTP: la API pública del cálculo y la puerta por donde Claude Code reporta el gasto."""

from __future__ import annotations

import gzip
import json
import tempfile
import zlib
from pathlib import Path

from flask import Request, Response

from aplicacion import ingesta, organizaciones
from aplicacion.puertos import DatosInvalidos, NoAutorizado
from dominio.consumo import eventos_desde_otlp

from . import contexto

MAX_CUERPO = 5 * 1024 * 1024


def _json(datos, estado=200, **cabeceras) -> Response:
    return Response(json.dumps(datos, ensure_ascii=False), status=estado, mimetype="application/json",
                    headers={"Cache-Control": "no-store", **cabeceras})


def _cuerpo(req: Request) -> bytes:
    crudo = req.get_data(cache=False)
    if len(crudo) > MAX_CUERPO:
        raise DatosInvalidos("El envío es demasiado grande.")
    codificacion = (req.headers.get("Content-Encoding") or "").lower()
    if codificacion == "gzip":
        crudo = gzip.decompress(crudo)
    elif codificacion == "deflate":
        crudo = zlib.decompress(crudo)
    if len(crudo) > 8 * MAX_CUERPO:
        raise DatosInvalidos("El envío es demasiado grande.")
    return crudo


# ---------------------------------------------------------------- API pública (vista de clase y demo)
def api(req: Request) -> Response:
    """/api/caso, /api/precios, /api/resolver y /api/excel: el cálculo sin cuenta, sin guardar nada."""
    ruta = req.path.rstrip("/").split("/api", 1)[-1] or "/"
    try:
        if ruta == "/caso" and req.method == "GET":
            from dominio.caso import caso_base
            return _json(caso_base())
        if ruta == "/precios" and req.method == "GET":
            from dominio.datos import modelos_base
            return _json(modelos_base().drop(columns="capacidad").to_dict("records"))
        if ruta in ("/resolver", "/excel") and req.method == "POST":
            from aplicacion.planes import calcular
            datos = json.loads(_cuerpo(req) or b"{}")
            r = calcular(datos)
            if ruta == "/resolver":
                return _json(r)
            return Response(excel_bytes(r), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": 'attachment; filename="modelos-solver.xlsx"'})
        return _json({"detail": "No existe."}, 404)
    except DatosInvalidos as e:
        return _json({"detail": str(e)}, 422)
    except json.JSONDecodeError:
        return _json({"detail": "El cuerpo no es JSON."}, 400)


def excel_bytes(plan: dict) -> bytes:
    from infraestructura.excel import crear_libro

    with tempfile.TemporaryDirectory() as d:
        ruta = Path(d) / "plan.xlsx"
        crear_libro(plan, ruta)
        return ruta.read_bytes()


# ---------------------------------------------------------------- ingesta OTLP (Claude Code, Gemini CLI)
def _logs_desde_protobuf(crudo: bytes) -> dict:
    """Convierte un ExportLogsServiceRequest en protobuf a la misma forma que OTLP/JSON."""
    from google.protobuf.json_format import MessageToDict
    from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest

    return MessageToDict(ExportLogsServiceRequest.FromString(crudo))


def ingesta_otlp(req: Request) -> Response:
    """Recibe la telemetría OTLP de Claude Code y Gemini CLI y suma el costo de cada llamada.

    Acepta JSON (`http/json`) y protobuf (`http/protobuf`) y cualquier ruta bajo /otlp: Claude
    Code agrega `/v1/logs`; Gemini CLI no documenta su ruta. Métricas y trazas se aceptan y se
    ignoran para que el exportador no reintente. El token va en `x-api-key` (Cloud Run rechaza
    un `Authorization: Bearer` que no sea de Google; se acepta por compatibilidad).
    """
    if req.method != "POST":
        return _json({"detail": "Usa POST."}, 405)
    auth = req.headers.get("Authorization") or ""
    token = req.headers.get("x-api-key") or (auth[7:].strip() if auth.lower().startswith("bearer ") else None)
    r = contexto.repo()
    try:
        org = organizaciones.autorizar_token(r, token)
    except NoAutorizado as e:
        return _json({"detail": str(e)}, 401)
    tipo = (req.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    proto = tipo in ("application/x-protobuf", "application/protobuf")
    vacio = Response(b"", status=200, mimetype="application/x-protobuf") if proto else _json({})
    ruta = req.path.rstrip("/")
    if ruta.endswith("/v1/metrics") or ruta.endswith("/v1/traces"):
        return vacio
    try:
        crudo = _cuerpo(req)
        if proto:
            carga = _logs_desde_protobuf(crudo)
        elif tipo == "application/json":
            carga = json.loads(crudo or b"{}")
        else:
            return _json({"detail": "Usa OTLP por HTTP con JSON o protobuf."}, 415)
    except (json.JSONDecodeError, OSError, zlib.error, DatosInvalidos, ValueError) as e:
        return _json({"detail": f"No se pudo leer el envío: {e}"}, 400)
    except Exception:  # protobuf que no es de logs (métricas o trazas a la misma ruta)
        return vacio
    if not isinstance(carga, dict) or "resourceLogs" not in carga:
        return vacio  # métricas o trazas en formato JSON
    eventos = eventos_desde_otlp(carga)
    resumen = ingesta.registrar(r, r, r, contexto.reloj(), org, eventos)
    if proto:
        vacio.headers["X-Eventos"] = str(resumen["recibidos"])
        return vacio
    # respuesta OTLP de éxito total: objeto vacío
    return _json({}, **{"X-Eventos": str(resumen["recibidos"])})
