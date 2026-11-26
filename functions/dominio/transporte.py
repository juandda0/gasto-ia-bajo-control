"""Problema de transporte: soluciones iniciales y prueba de optimalidad MODI.

Los métodos están programados a mano (sin solver) para mostrar cada paso.
Orígenes = herramientas (oferta = capacidad), destinos = tareas (demanda).
"""

from collections import deque
from dataclasses import dataclass, field

import numpy as np

EPS = 1e-9


@dataclass
class Solucion:
    asignacion: np.ndarray
    base: list[tuple[int, int]]  # celdas básicas (incluye ceros si hay degeneración)

    def costo(self, costos: np.ndarray) -> float:
        return float((self.asignacion * costos).sum())


@dataclass
class IteracionModi:
    u: np.ndarray
    v: np.ndarray
    costos_reducidos: np.ndarray  # c_ij - u_i - v_j (NaN en celdas básicas)
    entra: tuple[int, int] | None = None
    ciclo: list[tuple[int, int]] = field(default_factory=list)  # signos alternados: +, -, +, ...
    theta: float = 0.0
    sale: tuple[int, int] | None = None
    costo: float = 0.0
    asignacion: np.ndarray | None = None  # cómo estaba la tabla al empezar la iteración


def balancear(oferta, demanda, costos):
    """Agrega un destino u origen ficticio con costo cero si oferta y demanda no coinciden.

    Devuelve (oferta, demanda, costos, ficticio) donde ficticio es "destino", "origen" o None.
    """
    oferta = np.asarray(oferta, dtype=float)
    demanda = np.asarray(demanda, dtype=float)
    costos = np.asarray(costos, dtype=float)
    diferencia = oferta.sum() - demanda.sum()
    if diferencia > EPS:
        return oferta, np.append(demanda, diferencia), np.column_stack([costos, np.zeros(len(oferta))]), "destino"
    if diferencia < -EPS:
        return np.append(oferta, -diferencia), demanda, np.vstack([costos, np.zeros(len(demanda))]), "origen"
    return oferta, demanda, costos, None


def _asignar(oferta, demanda, elegir_celda):
    """Esqueleto común: asigna en la celda elegida y tacha una sola línea por paso,
    así quedan siempre m + n - 1 celdas básicas."""
    s, d = oferta.copy(), demanda.copy()
    m, n = len(s), len(d)
    filas, columnas = set(range(m)), set(range(n))
    x = np.zeros((m, n))
    base = []
    while filas and columnas:
        i, j = elegir_celda(filas, columnas, s, d)
        q = min(s[i], d[j])
        x[i, j] = q
        base.append((i, j))
        s[i] -= q
        d[j] -= q
        if s[i] <= EPS and (d[j] > EPS or len(filas) > 1):
            filas.discard(i)
        else:
            columnas.discard(j)
    return Solucion(x, base)


def esquina_noroeste(oferta, demanda) -> Solucion:
    oferta, demanda = np.asarray(oferta, float), np.asarray(demanda, float)
    return _asignar(oferta, demanda, lambda filas, columnas, s, d: (min(filas), min(columnas)))


def costo_minimo(oferta, demanda, costos) -> Solucion:
    oferta, demanda, costos = np.asarray(oferta, float), np.asarray(demanda, float), np.asarray(costos, float)

    def elegir(filas, columnas, s, d):
        # Menor costo; en empate, la celda que permite asignar más
        return min(((i, j) for i in filas for j in columnas), key=lambda c: (costos[c], -min(s[c[0]], d[c[1]])))

    return _asignar(oferta, demanda, elegir)


def vogel(oferta, demanda, costos) -> Solucion:
    oferta, demanda, costos = np.asarray(oferta, float), np.asarray(demanda, float), np.asarray(costos, float)

    def penalizacion(valores):
        valores = sorted(valores)
        return valores[1] - valores[0] if len(valores) > 1 else valores[0]

    def elegir(filas, columnas, s, d):
        cols = sorted(columnas)
        candidatas = [(penalizacion([costos[i, j] for j in cols]), "fila", i) for i in sorted(filas)]
        candidatas += [(penalizacion([costos[i, j] for i in filas]), "columna", j) for j in cols]
        _, tipo, k = max(candidatas, key=lambda c: c[0])
        if tipo == "fila":
            return k, min(columnas, key=lambda j: costos[k, j])
        return min(filas, key=lambda i: costos[i, k]), k

    return _asignar(oferta, demanda, elegir)


def _potenciales(costos, base):
    m, n = costos.shape
    u, v = np.full(m, np.nan), np.full(n, np.nan)
    u[0] = 0.0
    pendientes = list(base)
    while pendientes:
        avance = False
        for celda in list(pendientes):
            i, j = celda
            if not np.isnan(u[i]) and np.isnan(v[j]):
                v[j] = costos[i, j] - u[i]
            elif np.isnan(u[i]) and not np.isnan(v[j]):
                u[i] = costos[i, j] - v[j]
            elif np.isnan(u[i]) and np.isnan(v[j]):
                continue
            pendientes.remove(celda)
            avance = True
        if not avance:
            raise ValueError("La base no es un árbol conexo: no se pueden calcular u y v.")
    return u, v


def _ciclo(base, entra):
    """Ciclo que forma la celda que entra con la base (un árbol de filas y columnas)."""
    vecinos = {}
    for i, j in base:
        vecinos.setdefault(("f", i), []).append((("c", j), (i, j)))
        vecinos.setdefault(("c", j), []).append((("f", i), (i, j)))
    inicio, fin = ("c", entra[1]), ("f", entra[0])
    previo = {inicio: None}
    cola = deque([inicio])
    while cola:
        nodo = cola.popleft()
        if nodo == fin:
            break
        for vecino, celda in vecinos.get(nodo, []):
            if vecino not in previo:
                previo[vecino] = (nodo, celda)
                cola.append(vecino)
    camino = []
    nodo = fin
    while previo[nodo] is not None:
        nodo, celda = previo[nodo]
        camino.append(celda)
    camino.reverse()  # de la columna de la celda que entra hasta su fila
    return [entra] + camino


def modi(costos, inicial: Solucion, max_iter: int = 50) -> tuple[Solucion, list[IteracionModi]]:
    """Mejora la solución inicial hasta que ningún costo reducido sea negativo."""
    costos = np.asarray(costos, float)
    x = inicial.asignacion.copy()
    base = list(inicial.base)
    iteraciones = []
    for _ in range(max_iter):
        u, v = _potenciales(costos, base)
        reducidos = costos - u[:, None] - v[None, :]
        for celda in base:
            reducidos[celda] = np.nan
        it = IteracionModi(u, v, reducidos, costo=float((x * costos).sum()), asignacion=x.copy())
        iteraciones.append(it)
        if np.nanmin(reducidos) >= -EPS:
            break
        entra = tuple(int(k) for k in np.unravel_index(np.nanargmin(reducidos), reducidos.shape))
        ciclo = _ciclo(base, entra)
        menos = ciclo[1::2]
        theta = min(x[c] for c in menos)
        sale = min((c for c in menos if x[c] - theta <= EPS), key=lambda c: costos[c], default=menos[0])
        for k, celda in enumerate(ciclo):
            x[celda] += theta if k % 2 == 0 else -theta
        x[np.abs(x) < EPS] = 0.0
        base.remove(sale)
        base.append(entra)
        it.entra, it.ciclo, it.theta, it.sale = entra, ciclo, theta, sale
    return Solucion(x, base), iteraciones
