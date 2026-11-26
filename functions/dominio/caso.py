"""Datos del caso de estudio: una empresa con seis programadores en dos equipos.

Es la única fuente de los datos que usan el programa, el Excel y el informe.
Los salarios, los rendimientos y las bolsas de los asientos son SUPUESTOS del caso;
los precios por token vienen de las páginas oficiales (ver datos.py).
"""

from copy import deepcopy

CASO_BASE = {
    "empresa": "Empresa de ejemplo",
    "personas": [
        # nombre, equipo, salario mensual (USD), gasto en IA del mes pasado (USD de uso), herramienta actual
        {"nombre": "Ana", "equipo": "Backend", "salario": 2400, "gasto": 420, "herramienta": "Claude"},
        {"nombre": "Luis", "equipo": "Backend", "salario": 2000, "gasto": 180, "herramienta": "Cursor"},
        {"nombre": "Sara", "equipo": "Backend", "salario": 1700, "gasto": 95, "herramienta": "Cursor"},
        {"nombre": "Pedro", "equipo": "Backend", "salario": 1900, "gasto": 260, "herramienta": "Claude"},
        {"nombre": "Carla", "equipo": "Frontend", "salario": 2200, "gasto": 310, "herramienta": "OpenAI"},
        {"nombre": "Diego", "equipo": "Frontend", "salario": 1800, "gasto": 60, "herramienta": "Ninguna"},
    ],
    "reglas": {
        "presupuesto_pct_nomina": 0.06,   # el gasto extra (aparte de las cuotas) no pasa del 6% de la nómina
        "tope_pct_salario": 0.15,         # nadie usa más del 15% de su salario (a precio de lista)
        "minimo": 50,                     # nadie se queda con menos de 50 USD de uso
    },
    # Rendimiento decreciente: horas que ahorra cada dólar en cada tramo y ancho de cada tramo
    "tramos": {"horas_por_dolar": [0.20, 0.10, 0.04], "ancho": [100, 150, 250], "horas_mes": 160},
    # Modelo 0: planes disponibles (cuota mensual y uso incluido en USD de uso a precio de lista)
    "planes": [
        {"plan": "Cursor Teams", "familia": "Cursor", "cuota": 30, "bolsa": 150, "cupos": 2},
        {"plan": "Claude Premium", "familia": "Claude", "cuota": 100, "bolsa": 400, "cupos": 1},
        {"plan": "Claude Standard", "familia": "Claude", "cuota": 25, "bolsa": 80, "cupos": 1},
        {"plan": "Solo API", "familia": "Cualquiera", "cuota": 0, "bolsa": 0, "cupos": 2},
    ],
    # Fracción de la bolsa que aprovecha alguien que tiene que cambiar de herramienta
    "aprovechamiento_si_cambia": 0.6,
    # Modelo 2: fuentes de pago además de las bolsas de los asientos
    "batch": {"capacidad": 250, "costo": 0.5, "equipos": ["Backend"]},
    "api": {"capacidad": 3000, "costo": 1.0},
    "M": 99.0,
    # Escenario de Dual Simplex: recorte del presupuesto a mitad de mes
    "recorte": 0.25,
}


def caso_base():
    return deepcopy(CASO_BASE)


def equipos(caso):
    vistos = []
    for p in caso["personas"]:
        if p["equipo"] not in vistos:
            vistos.append(p["equipo"])
    return vistos


def nomina(caso):
    return sum(p["salario"] for p in caso["personas"])


def presupuesto(caso):
    """Límite del gasto extra: lo que se paga aparte de las cuotas de los asientos."""
    return caso["reglas"]["presupuesto_pct_nomina"] * nomina(caso)


def rendimientos(caso, persona):
    """Valor que produce un dólar de uso en cada tramo = horas ahorradas × costo de la hora."""
    hora = persona["salario"] / caso["tramos"]["horas_mes"]
    return [h * hora for h in caso["tramos"]["horas_por_dolar"]]
