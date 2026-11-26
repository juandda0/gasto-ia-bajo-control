"""Datos de referencia del proyecto.

Precios por millón de tokens (USD), consultados el 18 de noviembre de 2026 en:
- Claude: https://platform.claude.com/docs/en/about-claude/pricing
- OpenAI (Codex): https://developers.openai.com/api/docs/pricing
- Cursor: https://cursor.com/docs/models-and-pricing
- Gemini (Antigravity): https://aistudio.google.com/docs/pricing

Los puntajes de calidad, las demandas y las capacidades son SUPUESTOS del caso
de estudio y se pueden editar desde la app.
"""

import pandas as pd

FECHA_CONSULTA = "2026-11-18"

# Escenarios de precios: Google ya anunció subidas para Gemini.
ESCENARIOS = {
    "Actual (nov. 2026)": {},
    "Desde el 1 de diciembre de 2026": {
        "Gemini 4 Carbon": (4.00, 20.00),
    },
    "Desde el 1 de enero de 2027": {
        "Gemini 4 Carbon": (4.00, 20.00),
        "Gemini 3.8 Flash": (1.50, 7.50),
    },
}


def modelos_base() -> pd.DataFrame:
    """Un modelo premium y uno económico por herramienta."""
    filas = [
        # herramienta, modelo, tipo, entrada, salida, batch, capacidad (M tokens/mes, supuesto)
        ("Claude", "Claude Opus 5.5", "Premium", 4.00, 20.00, True, 300.0),
        ("Claude", "Claude Haiku 5.5", "Económico", 0.10, 0.50, True, 300.0),
        ("Codex", "GPT-6.2 Astra", "Premium", 8.00, 40.00, True, 300.0),
        ("Codex", "GPT-6 Luna", "Económico", 0.10, 0.50, True, 300.0),
        ("Cursor", "Grok 4.7", "Premium", 2.00, 6.00, False, 200.0),
        ("Cursor", "Composer 2.5", "Económico", 0.50, 2.50, False, 200.0),
        ("Antigravity", "Gemini 4 Carbon", "Premium", 2.00, 10.00, True, 300.0),
        ("Antigravity", "Gemini 3.8 Flash", "Económico", 0.75, 3.75, True, 300.0),
    ]
    return pd.DataFrame(
        filas,
        columns=["herramienta", "modelo", "tipo", "precio_entrada", "precio_salida", "batch", "capacidad"],
    )


def aplicar_escenario(modelos: pd.DataFrame, escenario: str) -> pd.DataFrame:
    modelos = modelos.copy()
    for nombre, (entrada, salida) in ESCENARIOS[escenario].items():
        fila = modelos["modelo"] == nombre
        modelos.loc[fila, ["precio_entrada", "precio_salida"]] = [entrada, salida]
    return modelos


def tareas_empresa() -> pd.DataFrame:
    """Tareas de un equipo de desarrollo (supuestos del caso)."""
    filas = [
        # tarea, demanda (M tokens/mes), proporción de entrada, calidad mínima, urgente
        ("Generación de código", 400.0, 0.85, 85.0, True),
        ("Revisión y pruebas", 250.0, 0.90, 80.0, False),
        ("Arquitectura y planificación", 60.0, 0.70, 90.0, True),
        ("Documentación", 150.0, 0.60, 70.0, False),
    ]
    return pd.DataFrame(filas, columns=["tarea", "demanda", "alfa", "calidad_minima", "urgente"])


def calidad_empresa() -> pd.DataFrame:
    """Calidad supuesta (0 a 100) de cada modelo en cada tarea."""
    datos = {
        "Claude Opus 5.5": [93, 92, 94, 90],
        "Claude Haiku 5.5": [70, 72, 65, 82],
        "GPT-6.2 Astra": [95, 93, 95, 91],
        "GPT-6 Luna": [68, 70, 62, 80],
        "Grok 4.7": [86, 84, 85, 85],
        "Composer 2.5": [80, 76, 70, 78],
        "Gemini 4 Carbon": [89, 88, 90, 88],
        "Gemini 3.8 Flash": [76, 75, 72, 84],
    }
    return pd.DataFrame(datos, index=[t for t in tareas_empresa()["tarea"]])


def tareas_persona() -> pd.DataFrame:
    """Trabajo de un freelancer (supuestos del caso)."""
    filas = [
        # tarea, peso, mínimo y máximo útil (M tokens/mes), proporción de entrada, calidad mínima
        ("Programación", 1.0, 6.0, 15.0, 0.85, 85.0),
        ("Redacción", 0.6, 1.0, 4.0, 0.50, 75.0),
        ("Investigación", 0.8, 1.0, 5.0, 0.75, 80.0),
    ]
    return pd.DataFrame(filas, columns=["tarea", "peso", "minimo", "maximo", "alfa", "calidad_minima"])


def calidad_persona() -> pd.DataFrame:
    tareas = list(tareas_persona()["tarea"])
    empresa = calidad_empresa()
    # Programación toma la calidad de generación de código, redacción la de
    # documentación e investigación la de arquitectura.
    return pd.DataFrame(
        [empresa.iloc[0], empresa.iloc[3], empresa.iloc[2]],
        index=tareas,
    )


def precio_combinado(entrada: float, salida: float, alfa: float) -> float:
    """USD por millón de tokens cuando una fracción alfa de los tokens es de entrada."""
    return alfa * entrada + (1 - alfa) * salida
