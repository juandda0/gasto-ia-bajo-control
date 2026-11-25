"""Método gráfico para problemas de dos variables."""

from dataclasses import dataclass
from itertools import combinations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

TOL = 1e-9


@dataclass
class Restriccion:
    nombre: str
    a1: float
    a2: float
    sentido: str  # "<=" o ">="
    b: float

    def cumple(self, x1: float, x2: float) -> bool:
        lhs = self.a1 * x1 + self.a2 * x2
        return lhs <= self.b + 1e-7 if self.sentido == "<=" else lhs >= self.b - 1e-7


def vertices(restricciones: list[Restriccion]) -> pd.DataFrame:
    """Intersecciones de cada par de rectas (incluidos los ejes) que cumplen todas las restricciones."""
    rectas = [(r.nombre, r.a1, r.a2, r.b) for r in restricciones]
    rectas += [("x₁ = 0", 1.0, 0.0, 0.0), ("x₂ = 0", 0.0, 1.0, 0.0)]
    puntos = []
    for (n1, a, b, c), (n2, d, e, f) in combinations(rectas, 2):
        det = a * e - b * d
        if abs(det) < TOL:
            continue
        x1 = (c * e - b * f) / det
        x2 = (a * f - c * d) / det
        if x1 < -1e-7 or x2 < -1e-7:
            continue
        if all(r.cumple(x1, x2) for r in restricciones):
            x1, x2 = max(x1, 0.0) + 0.0, max(x2, 0.0) + 0.0
            if not any(abs(x1 - p["x1"]) < 1e-6 and abs(x2 - p["x2"]) < 1e-6 for p in puntos):
                puntos.append({"vertice": f"{n1} ∩ {n2}", "x1": x1, "x2": x2})
    return pd.DataFrame(puntos, columns=["vertice", "x1", "x2"])


def resolver(c1: float, c2: float, restricciones: list[Restriccion], maximizar: bool = True):
    """Evalúa Z en cada vértice. Devuelve (tabla de vértices, fila óptima o None)."""
    tabla = vertices(restricciones)
    if tabla.empty:
        return tabla, None
    tabla["Z"] = c1 * tabla["x1"] + c2 * tabla["x2"]
    optimo = tabla.loc[tabla["Z"].idxmax() if maximizar else tabla["Z"].idxmin()]
    return tabla, optimo


def graficar(c1: float, c2: float, restricciones: list[Restriccion], tabla: pd.DataFrame, optimo, etiquetas=("x₁", "x₂")):
    fig, ax = plt.subplots(figsize=(7, 5.5))
    limite = max(tabla["x1"].max(), tabla["x2"].max(), 1.0) * 1.4 if not tabla.empty else 10.0
    xs = np.linspace(0, limite, 400)
    colores = plt.rcParams["axes.prop_cycle"].by_key()["color"]

    for k, r in enumerate(restricciones):
        color = colores[k % len(colores)]
        if abs(r.a2) > TOL:
            ax.plot(xs, (r.b - r.a1 * xs) / r.a2, color=color, label=f"{r.nombre} ({_texto(r)})")
        else:
            ax.axvline(r.b / r.a1, color=color, label=f"{r.nombre} ({_texto(r)})")

    if len(tabla) >= 3:
        centro = tabla[["x1", "x2"]].mean()
        angulos = np.arctan2(tabla["x2"] - centro["x2"], tabla["x1"] - centro["x1"])
        poligono = tabla.assign(ang=angulos).sort_values("ang")
        ax.fill(poligono["x1"], poligono["x2"], color="#2a9d8f", alpha=0.25, label="Región factible")

    if not tabla.empty:
        ax.scatter(tabla["x1"], tabla["x2"], color="black", zorder=3, s=20)
    if optimo is not None:
        ax.scatter([optimo["x1"]], [optimo["x2"]], color="#e63946", zorder=4, s=80, label="Óptimo")
        if abs(c2) > TOL:
            ax.plot(xs, (optimo["Z"] - c1 * xs) / c2, "--", color="#e63946", alpha=0.7, label=f"Z = {optimo['Z']:.1f}")
        ax.annotate(
            f"({optimo['x1']:.2f}, {optimo['x2']:.2f})",
            (optimo["x1"], optimo["x2"]),
            textcoords="offset points",
            xytext=(8, 8),
        )

    ax.set_xlim(0, limite)
    ax.set_ylim(0, limite)
    ax.set_xlabel(f"{etiquetas[0]} (millones de tokens)")
    ax.set_ylabel(f"{etiquetas[1]} (millones de tokens)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="upper right")
    fig.tight_layout()
    return fig


def _texto(r: Restriccion) -> str:
    return f"{r.a1:g}x₁ + {r.a2:g}x₂ {'≤' if r.sentido == '<=' else '≥'} {r.b:g}"
