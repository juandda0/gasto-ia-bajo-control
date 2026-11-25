"""Servidor del programa: sirve la interfaz web y resuelve el ciclo con el motor de Python.

Ejecutar con:  .venv/bin/uvicorn servidor:app --port 8765
y abrir http://localhost:8765 (vista empresa) o http://localhost:8765/clase/ (paso a paso)
"""

import json
import tempfile
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from optimizador.caso import caso_base
from optimizador.ciclo import resolver
from optimizador.datos import modelos_base
from optimizador.excel import crear_libro

WEB = Path(__file__).parent / "web"
app = FastAPI(title="Gasto en IA bajo control")


def _json(obj):
    """Convierte numpy y NaN a tipos que acepta JSON."""
    def limpiar(x):
        if isinstance(x, dict):
            return {str(k): limpiar(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [limpiar(v) for v in x]
        if isinstance(x, np.generic):
            x = x.item()
        if isinstance(x, float) and x != x:
            return None
        return x
    return limpiar(obj)


@app.get("/api/caso")
def caso():
    return caso_base()


@app.get("/api/precios")
def precios():
    return modelos_base().drop(columns="capacidad").to_dict("records")


@app.post("/api/resolver")
def resolver_caso(datos: dict):
    try:
        return JSONResponse(_json(resolver(datos)))
    except (ValueError, AssertionError, KeyError) as e:
        raise HTTPException(status_code=422, detail=f"No se pudo resolver con estos datos: {e}")


@app.post("/api/excel")
def excel(datos: dict):
    try:
        r = resolver(datos)
    except (ValueError, AssertionError, KeyError) as e:
        raise HTTPException(status_code=422, detail=f"No se pudo resolver con estos datos: {e}")
    ruta = Path(tempfile.mkdtemp()) / "modelos-solver.xlsx"
    crear_libro(r, ruta)
    return FileResponse(ruta, filename="modelos-solver.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


app.mount("/", StaticFiles(directory=WEB, html=True), name="web")


if __name__ == "__main__":
    print(json.dumps(_json(resolver(caso_base()))["resultado"], indent=2, ensure_ascii=False))
