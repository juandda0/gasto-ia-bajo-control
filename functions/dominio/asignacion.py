"""Problema de asignación resuelto con el método húngaro, paso a paso.

Se programa a mano para poder mostrar cada matriz: reducción por filas y columnas,
cubrir los ceros con el mínimo de líneas y ajustar hasta poder asignar.
"""

import numpy as np

EPS = 1e-9


def _emparejar(ceros):
    """Máximo emparejamiento fila-columna usando solo celdas en cero (caminos aumentantes)."""
    n, m = ceros.shape
    col_de = [-1] * n
    fila_de = [-1] * m

    def intentar(i, visto):
        for j in range(m):
            if ceros[i, j] and not visto[j]:
                visto[j] = True
                if fila_de[j] == -1 or intentar(fila_de[j], visto):
                    col_de[i], fila_de[j] = j, i
                    return True
        return False

    for i in range(n):
        intentar(i, [False] * m)
    return col_de, fila_de


def _cubrir(ceros):
    """Mínimo de líneas que cubren todos los ceros (teorema de König)."""
    n, m = ceros.shape
    col_de, fila_de = _emparejar(ceros)
    marcadas_f = {i for i in range(n) if col_de[i] == -1}
    marcadas_c = set()
    pendientes = list(marcadas_f)
    while pendientes:
        i = pendientes.pop()
        for j in range(m):
            if ceros[i, j] and j not in marcadas_c:
                marcadas_c.add(j)
                k = fila_de[j]
                if k != -1 and k not in marcadas_f:
                    marcadas_f.add(k)
                    pendientes.append(k)
    filas = [i for i in range(n) if i not in marcadas_f]
    columnas = sorted(marcadas_c)
    return filas, columnas, col_de


def hungaro(costos):
    """Minimiza el costo total asignando una fila a cada columna (matriz cuadrada).

    Devuelve (asignación como lista columna-por-fila, costo, pasos). Cada paso trae la
    matriz de ese momento y una descripción, para mostrarlo en el programa y el informe.
    """
    C = np.asarray(costos, dtype=float)
    n = C.shape[0]
    assert C.shape == (n, n), "la matriz debe ser cuadrada (agregar filas o columnas ficticias)"
    M = C.copy()
    pasos = [{"titulo": "Matriz de costos", "matriz": M.copy(), "lineas": None}]

    M = M - M.min(axis=1, keepdims=True)
    pasos.append({"titulo": "Se resta el mínimo de cada fila", "matriz": M.copy(), "lineas": None})
    M = M - M.min(axis=0, keepdims=True)
    pasos.append({"titulo": "Se resta el mínimo de cada columna", "matriz": M.copy(), "lineas": None})

    for _ in range(4 * n):
        ceros = np.abs(M) < EPS
        filas, columnas, col_de = _cubrir(ceros)
        lineas = len(filas) + len(columnas)
        pasos.append({"titulo": f"Se cubren los ceros con {lineas} líneas", "matriz": M.copy(),
                      "lineas": {"filas": filas, "columnas": columnas}})
        if lineas == n:
            asignacion = col_de
            costo = float(sum(C[i, asignacion[i]] for i in range(n)))
            pasos.append({"titulo": "Asignación óptima sobre los ceros", "matriz": M.copy(), "lineas": None,
                          "asignacion": list(asignacion)})
            return list(asignacion), costo, pasos
        cubierta_f = np.zeros(n, bool)
        cubierta_f[filas] = True
        cubierta_c = np.zeros(n, bool)
        cubierta_c[columnas] = True
        libres = ~cubierta_f[:, None] & ~cubierta_c[None, :]
        delta = M[libres].min()
        M = M - delta * libres + delta * (cubierta_f[:, None] & cubierta_c[None, :])
        pasos.append({"titulo": f"Se resta {delta:g} a lo no cubierto y se suma en los cruces", "matriz": M.copy(),
                      "lineas": None, "delta": float(delta)})
    raise RuntimeError("el método húngaro no convergió")


def matriz_planes(caso):
    """Costo mensual de darle cada cupo de plan a cada persona, con su uso del mes pasado.

    costo = cuota + lo que excede la bolsa que esa persona puede aprovechar, a precio de lista.
    Quien ya usa la herramienta del plan aprovecha toda la bolsa; quien tendría que cambiar,
    solo una fracción.

    La matriz se balancea para el método húngaro: si faltan cupos se agregan de "Solo API"
    (pagar por uso no tiene límite de cupos) y si sobran se agregan personas ficticias con
    costo 0 (los cupos que les toquen no se contratan). Devuelve (C, cupos, filas), donde
    filas son los nombres de las filas, incluidas las ficticias.
    """
    cupos = []
    for p in caso["planes"]:
        for k in range(int(p["cupos"])):
            cupos.append(dict(p, nombre_cupo=f"{p['plan']}" + (f" {k + 1}" if p["cupos"] > 1 else "")))
    personas = caso["personas"]
    libre = next((p for p in caso["planes"] if p["familia"] == "Cualquiera"), None)
    extra = 0
    while len(cupos) < len(personas):
        if libre is None:
            raise ValueError("faltan cupos de planes y no hay un plan de solo API para completar")
        extra += 1
        cupos.append(dict(libre, nombre_cupo=f"{libre['plan']} extra {extra}"))
    filas = [p["nombre"] for p in personas] + [f"Ficticio {k + 1}" for k in range(len(cupos) - len(personas))]
    f = caso["aprovechamiento_si_cambia"]
    C = np.zeros((len(filas), len(cupos)))
    for i, per in enumerate(personas):
        for j, cu in enumerate(cupos):
            aprovecha = 1.0 if cu["familia"] in (per["herramienta"], "Cualquiera") else f
            C[i, j] = cu["cuota"] + max(0.0, per["gasto"] - aprovecha * cu["bolsa"])
    return C, cupos, filas
