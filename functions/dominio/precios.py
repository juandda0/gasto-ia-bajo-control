"""Precios por token de los modelos cuya telemetría no trae el costo (Gemini CLI).

SUPUESTOS DECLARADOS: precios de lista en USD por millón de tokens según la página oficial
https://ai.google.dev/gemini-api/docs/pricing (nivel de pago, contexto estándar). Revísalos
cuando Google los cambie. Claude Code ya manda su costo (`cost_usd`), así que no se usa aquí.
"""

from __future__ import annotations

# prefijo del modelo → (entrada, salida, entrada en caché) en USD por millón de tokens.
# El orden importa: el primer prefijo que coincide gana (los más específicos van primero).
GEMINI = [
    ("gemini-3-pro", (2.00, 12.00, 0.20)),
    ("gemini-3-flash", (0.50, 3.00, 0.05)),
    ("gemini-2.5-pro", (1.25, 10.00, 0.125)),
    ("gemini-2.5-flash-lite", (0.10, 0.40, 0.01)),
    ("gemini-2.5-flash", (0.30, 2.50, 0.03)),
    ("gemini-2.0-flash-lite", (0.075, 0.30, 0.01875)),
    ("gemini-2.0-flash", (0.10, 0.40, 0.025)),
]
# Modelo desconocido: se cobra como el Pro más reciente para no subestimar el gasto.
GEMINI_POR_DEFECTO = (2.00, 12.00, 0.20)


def precio_gemini(modelo: str) -> tuple[tuple[float, float, float], bool]:
    """((entrada, salida, caché) por millón, si es un precio conocido)."""
    m = (modelo or "").lower().removeprefix("models/")
    for prefijo, precio in GEMINI:
        if m.startswith(prefijo):
            return precio, True
    return GEMINI_POR_DEFECTO, False


def costo_gemini(modelo: str, entrada: int, salida: int, cache: int = 0, pensamiento: int = 0) -> float:
    """USD de una respuesta. Supuestos: `entrada` incluye lo leído de caché (como en la API de
    Gemini) y el razonamiento (`thoughts`) se cobra como salida y viene aparte de `salida`."""
    (p_in, p_out, p_cache), _ = precio_gemini(modelo)
    cache = min(max(cache, 0), max(entrada, 0))
    return ((max(entrada, 0) - cache) * p_in + cache * p_cache + (max(salida, 0) + max(pensamiento, 0)) * p_out) / 1e6
