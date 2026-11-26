"""Método Simplex y Dual Simplex en forma de tabla, para mostrar cada iteración.

Problema de la forma: max c·x  s.a.  A x ≤ b,  x ≥ 0  (b puede volverse negativo al
cambiar el lado derecho, y ahí entra el Dual Simplex).
"""

import numpy as np

EPS = 1e-9


class Tabla:
    def __init__(self, c, A, b, nombres_x, nombres_h):
        A = np.asarray(A, float)
        m, n = A.shape
        self.nombres = list(nombres_x) + list(nombres_h)
        self.T = np.zeros((m + 1, n + m + 1))
        self.T[:m, :n] = A
        self.T[:m, n:n + m] = np.eye(m)
        self.T[:m, -1] = b
        self.T[m, :n] = -np.asarray(c, float)   # fila Z: z_j - c_j
        self.base = list(range(n, n + m))
        self.n, self.m = n, m

    def foto(self, nota, entra=None, sale=None, razones=None):
        return {
            "nota": nota,
            "columnas": self.nombres + ["Solución"],
            "base": [self.nombres[k] for k in self.base] + ["Z"],
            "tabla": self.T.round(6).tolist(),
            "entra": None if entra is None else self.nombres[entra],
            "sale": None if sale is None else self.nombres[self.base[sale]],
            "razones": razones,
        }

    def pivotear(self, fila, col):
        self.T[fila] /= self.T[fila, col]
        for i in range(self.T.shape[0]):
            if i != fila:
                self.T[i] -= self.T[i, col] * self.T[fila]
        self.base[fila] = col

    def solucion(self):
        x = np.zeros(self.n + self.m)
        for i, k in enumerate(self.base):
            x[k] = self.T[i, -1]
        return {self.nombres[k]: float(x[k]) for k in range(self.n)}, float(self.T[-1, -1])


def simplex(c, A, b, nombres_x, nombres_h=None, max_iter=50):
    """Simplex primal desde el origen. Devuelve (tabla final, iteraciones)."""
    nombres_h = nombres_h or [f"s{i + 1}" for i in range(len(b))]
    t = Tabla(c, A, b, nombres_x, nombres_h)
    pasos = [t.foto("Tabla inicial: la solución es el origen")]
    for _ in range(max_iter):
        z = t.T[-1, :-1]
        col = int(np.argmin(z))
        if z[col] >= -EPS:
            pasos[-1]["nota"] += ". Ningún z_j − c_j es negativo: es la solución óptima"
            break
        colv = t.T[:-1, col]
        razones = [float(t.T[i, -1] / colv[i]) if colv[i] > EPS else None for i in range(t.m)]
        validas = [(r, i) for i, r in enumerate(razones) if r is not None]
        if not validas:
            raise ValueError("problema no acotado")
        _, fila = min(validas)
        pasos[-1].update(entra=t.nombres[col], sale=t.nombres[t.base[fila]], razones=razones)
        t.pivotear(fila, col)
        sol, z_val = t.solucion()
        pasos.append(t.foto(f"Entra {t.nombres[col]}: Z = {z_val:g}"))
    return t, pasos


def dual_simplex(t, delta_b, max_iter=50):
    """Cambia el lado derecho de una tabla óptima y la corrige con el Dual Simplex.

    delta_b: cambio del lado derecho original de cada restricción. Las columnas de las
    holguras de la tabla final son B⁻¹, así que la nueva solución es b̄ + B⁻¹·Δb.
    """
    delta_b = np.asarray(delta_b, float)
    Binv = t.T[:-1, t.n:t.n + t.m]
    t.T[:-1, -1] += Binv @ delta_b
    t.T[-1, -1] += t.T[-1, t.n:t.n + t.m] @ delta_b  # Z cambia según los precios sombra
    pasos = [t.foto("Se cambia el lado derecho: la tabla sigue siendo óptima pero ya no es factible")]
    for _ in range(max_iter):
        rhs = t.T[:-1, -1]
        fila = int(np.argmin(rhs))
        if rhs[fila] >= -EPS:
            pasos[-1]["nota"] += ". Todas las soluciones son no negativas: es factible y óptima"
            break
        filav = t.T[fila, :-1]
        z = t.T[-1, :-1]
        razones = [float(abs(z[j] / filav[j])) if filav[j] < -EPS else None for j in range(t.n + t.m)]
        validas = [(r, j) for j, r in enumerate(razones) if r is not None]
        if not validas:
            raise ValueError("el problema quedó infactible")
        _, col = min(validas)
        pasos[-1].update(entra=t.nombres[col], sale=t.nombres[t.base[fila]], razones=razones)
        t.pivotear(fila, col)
        _, z_val = t.solucion()
        pasos.append(t.foto(f"Sale {pasos[-1]['sale']} y entra {t.nombres[col]}: Z = {z_val:g}"))
    return t, pasos
