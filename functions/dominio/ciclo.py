"""El ciclo completo: Modelo 0 (asignación) → Modelo 1 (reparto) → Modelo 2 (pago) →
sensibilidad → Dual Simplex, más el modelo unido que sirve de referencia.

resolver(caso) devuelve un diccionario listo para JSON con cada paso, que usan la
interfaz, el Excel y el informe.
"""

import numpy as np
from scipy.optimize import linear_sum_assignment, linprog

from . import asignacion, grafico, simplex, transporte
from .caso import equipos, nomina, presupuesto, rendimientos

EPS = 1e-7


# ---------------------------------------------------------------- Modelo 0
def modelo0(caso):
    """Qué plan le toca a cada persona: problema de asignación con el método húngaro."""
    C, cupos, nombres_filas = asignacion.matriz_planes(caso)
    asign, costo, pasos = asignacion.hungaro(C)
    r, c = linear_sum_assignment(C)  # verificación con SciPy
    personas = caso["personas"]
    filas = []
    for i, j in enumerate(asign):
        if i >= len(personas):  # fila ficticia: ese cupo no se contrata
            continue
        p, cu = personas[i], cupos[j]
        aprovecha = 1.0 if cu["familia"] in (p["herramienta"], "Cualquiera") else caso["aprovechamiento_si_cambia"]
        filas.append({"persona": p["nombre"], "plan": cu["plan"], "cupo": cu["nombre_cupo"], "cuota": cu["cuota"],
                      "bolsa_usable": aprovecha * cu["bolsa"], "costo": float(C[i, j])})
    return {
        "costos": C.tolist(),
        "cupos": [cu["nombre_cupo"] for cu in cupos],
        "personas": nombres_filas,
        "pasos": [_paso_json(p) for p in pasos],
        "asignacion": filas,
        "costo": costo,
        "costo_scipy": float(C[r, c].sum()),
        "costo_todo_api": float(sum(p["gasto"] for p in personas)),
        "cuotas": float(sum(f["cuota"] for f in filas)),
    }


def _paso_json(p):
    q = dict(p)
    q["matriz"] = np.round(p["matriz"], 6).tolist()
    return q


def bolsas(m0):
    return {f["persona"]: f["bolsa_usable"] for f in m0["asignacion"]}


# ---------------------------------------------------------------- Modelo 1
def modelo1(caso, bolsa, presupuesto_usd=None, costo_por_equipo=None, metodo="highs"):
    """Reparto del uso por tramos de rendimiento decreciente.

    Variables: g[d,k] = uso de la persona d en el tramo k; e[d] = uso extra de d, el que
    no cubre la bolsa de su asiento. Lo que cae dentro de la bolsa ya está pagado.
    max  Σ r[d,k]·g[d,k] − Σ c[d]·e[d]
    s.a. Σ_k g[d,k] − e[d] ≤ bolsa[d]       (lo que pasa de la bolsa es extra)
         Σ_k g[d,k] ≤ 15% del salario        (tope por persona)
         Σ_k g[d,k] ≥ 50                      (mínimo por persona)
         Σ e[d] ≤ presupuesto de gasto extra
         0 ≤ g[d,k] ≤ ancho del tramo,  e[d] ≥ 0
    """
    personas = caso["personas"]
    reglas, anchos = caso["reglas"], caso["tramos"]["ancho"]
    B = presupuesto(caso) if presupuesto_usd is None else presupuesto_usd
    costo_por_equipo = costo_por_equipo or {}
    n, K = len(personas), len(anchos)
    nv = n * K + n
    c, bounds = np.zeros(nv), []
    for i, p in enumerate(personas):
        for k, r in enumerate(rendimientos(caso, p)):
            c[i * K + k] = -r
            bounds.append((0, anchos[k]))
    for i, p in enumerate(personas):
        c[n * K + i] = costo_por_equipo.get(p["equipo"], 1.0)
        bounds.append((0, None))
    A, b, nombres = [], [], []
    for i, p in enumerate(personas):
        uso = np.zeros(nv)
        uso[i * K:(i + 1) * K] = 1
        A.append(uso); b.append(reglas["tope_pct_salario"] * p["salario"]); nombres.append(("tope", p["nombre"]))
        A.append(-uso); b.append(-reglas["minimo"]); nombres.append(("minimo", p["nombre"]))
        extra = uso.copy(); extra[n * K + i] = -1
        A.append(extra); b.append(bolsa[p["nombre"]]); nombres.append(("bolsa", p["nombre"]))
    total = np.zeros(nv); total[n * K:] = 1
    A.append(total); b.append(B); nombres.append(("presupuesto", "total"))
    res = linprog(c, A_ub=np.array(A), b_ub=np.array(b), bounds=bounds, method=metodo)
    if res.status == 2:
        raise ValueError("con estas reglas no hay solución: el presupuesto de gasto extra no alcanza para darle "
                         "el mínimo a cada persona, o el mínimo es mayor que el tope. Sube el presupuesto o baja el mínimo.")
    if res.status != 0:
        raise ValueError(res.message)
    g = res.x[:n * K].reshape(n, K)
    e = res.x[n * K:]
    marg = -res.ineqlin.marginals
    valor = float(sum(r * g[i, k] for i, p in enumerate(personas) for k, r in enumerate(rendimientos(caso, p))))
    return {
        "presupuesto": B,
        "topes": {p["nombre"]: float(g[i].sum()) for i, p in enumerate(personas)},
        "extra": {p["nombre"]: float(e[i]) for i, p in enumerate(personas)},
        "tramos": {p["nombre"]: g[i].round(6).tolist() for i, p in enumerate(personas)},
        "valor_bruto": valor,
        "objetivo": float(-res.fun),
        "precio_sombra": {
            "presupuesto": float(marg[-1]),
            "topes": {nm: float(m) for (t, nm), m in zip(nombres, marg) if t == "tope"},
            "bolsas": {nm: float(m) for (t, nm), m in zip(nombres, marg) if t == "bolsa"},
        },
        # valor que le falta a cada tramo para entrar a la solución (0 si ya se usa)
        "costos_reducidos": {p["nombre"]: (-res.lower.marginals[i * K:(i + 1) * K]).round(6).tolist()
                             for i, p in enumerate(personas)},
        "iteraciones": int(res.nit),
        "metodo": metodo,
    }


def rango_presupuesto(caso, bolsa, paso=1.0):
    """Intervalo del presupuesto en que el precio sombra no cambia (análisis paramétrico)."""
    B = presupuesto(caso)
    base = modelo1(caso, bolsa)["precio_sombra"]["presupuesto"]

    def igual(x):
        try:
            return abs(modelo1(caso, bolsa, x)["precio_sombra"]["presupuesto"] - base) < 1e-6
        except ValueError:
            return False

    # El precio sombra es constante por tramos y no crece con B (el óptimo es cóncavo), así que
    # el conjunto de B con el mismo precio es un intervalo: se busca cada borde duplicando el
    # salto y luego partiendo a la mitad hasta la precisión `paso`.
    def borde(direccion, limite):
        bueno, salto = B, paso
        while True:
            x = B + direccion * salto
            if (direccion < 0 and x < limite) or (direccion > 0 and x > limite):
                x = limite
            if not igual(x):
                malo = x
                break
            bueno = x
            if x == limite:
                return bueno
            salto *= 2
        while abs(malo - bueno) > paso + 1e-9:
            medio = (bueno + malo) / 2
            if igual(medio):
                bueno = medio
            else:
                malo = medio
        return bueno

    lo = borde(-1, 0.0)
    hi = borde(1, 5 * B)
    lo, hi = float(np.ceil(lo - 1e-9)), float(np.floor(hi + 1e-9))
    return {"desde": lo, "hasta": hi, "precio_sombra": base}


def valor_de(caso, usos):
    """Valor bruto de un reparto dado, llenando los tramos en orden."""
    total = 0.0
    for p in caso["personas"]:
        resto = usos[p["nombre"]]
        for r, a in zip(rendimientos(caso, p), caso["tramos"]["ancho"]):
            u = min(resto, a)
            total += r * u
            resto -= u
    return total


# ---------------------------------------------------------------- Modelo 2
def modelo2(caso, m1, bolsa):
    """Con qué se paga el uso de cada equipo: transporte con noroeste, costo mínimo, Vogel y MODI.

    Los orígenes se ordenan de la fuente más cara a la más barata, así la esquina noroeste
    empieza lejos del óptimo y MODI tiene que mejorarla.
    """
    eqs = equipos(caso)
    en_bolsa = {e: 0.0 for e in eqs}
    for p in caso["personas"]:
        en_bolsa[p["equipo"]] += min(m1["topes"][p["nombre"]], bolsa[p["nombre"]])
    M = caso["M"]
    fuentes = [("API pago por uso", caso["api"]["capacidad"], [caso["api"]["costo"]] * len(eqs)),
               ("API en batch", caso["batch"]["capacidad"],
                [caso["batch"]["costo"] if e in caso["batch"]["equipos"] else M for e in eqs])]
    for e in eqs:
        if en_bolsa[e] > EPS:
            fuentes.append((f"Bolsas de asientos ({e})", round(en_bolsa[e], 6), [0.0 if x == e else M for x in eqs]))
    demanda = [sum(m1["topes"][p["nombre"]] for p in caso["personas"] if p["equipo"] == e) for e in eqs]
    o, d, cc, ficticio = transporte.balancear([f[1] for f in fuentes], demanda, [f[2] for f in fuentes])
    destinos = eqs + (["Ficticio"] if ficticio == "destino" else [])
    origenes = [f[0] for f in fuentes] + (["Ficticio"] if ficticio == "origen" else [])
    iniciales = {
        "noroeste": transporte.esquina_noroeste(o, d),
        "costo_minimo": transporte.costo_minimo(o, d, cc),
        "vogel": transporte.vogel(o, d, cc),
    }
    final, pasos = transporte.modi(cc, iniciales["noroeste"])
    _, pasos_v = transporte.modi(cc, iniciales["vogel"])
    v = pasos_v[-1].v
    j_fict = destinos.index("Ficticio") if "Ficticio" in destinos else None
    marginal = {e: float(v[j] - (v[j_fict] if j_fict is not None else 0.0)) for j, e in enumerate(eqs)}
    return {
        "origenes": origenes, "destinos": destinos, "oferta": o.tolist(), "demanda": d.tolist(),
        "costos": cc.tolist(), "M": M,
        "iniciales": {k: {"asignacion": s.asignacion.tolist(), "costo": s.costo(cc)} for k, s in iniciales.items()},
        "modi": [_paso_modi(p) for p in pasos],
        "iteraciones_modi_desde_vogel": len(pasos_v) - 1,
        "final": {"asignacion": final.asignacion.tolist(), "costo": final.costo(cc)},
        "costo_marginal": marginal,
    }


def _paso_modi(p):
    return {"costo": p.costo, "u": p.u.tolist(), "v": p.v.tolist(), "asignacion": p.asignacion.tolist(),
            "reducidos": [[None if np.isnan(z) else round(float(z), 6) for z in fila] for fila in p.costos_reducidos],
            "entra": p.entra, "ciclo": p.ciclo, "theta": p.theta, "sale": p.sale}


# ---------------------------------------------------------------- Vista por equipos (a mano)
VALOR_POR_EQUIPO = {"Backend": 2.5, "Frontend": 1.8}  # supuesto: valor constante de un dólar extra por equipo


def dos_variables(caso, bolsa):
    """Gasto extra por equipo con valor constante: método gráfico, Simplex y Dual Simplex en tabla.

    x1, x2 = USD de gasto extra de cada equipo. El tope de cada equipo es lo que le falta
    para llegar al 15% de los salarios después de usar sus bolsas, y el mínimo es lo que
    falta para que cada persona tenga sus 50 USD.
    """
    eqs = equipos(caso)
    reglas, B = caso["reglas"], presupuesto(caso)
    tope, minimo = [], []
    for e in eqs:
        gente = [p for p in caso["personas"] if p["equipo"] == e]
        tope.append(sum(max(0.0, reglas["tope_pct_salario"] * p["salario"] - bolsa[p["nombre"]]) for p in gente))
        minimo.append(sum(max(0.0, reglas["minimo"] - bolsa[p["nombre"]]) for p in gente))
    c = [VALOR_POR_EQUIPO.get(e, 2.0) for e in eqs]
    restr = [grafico.Restriccion("Presupuesto", 1, 1, "<=", B),
             grafico.Restriccion(f"Tope {eqs[0]}", 1, 0, "<=", tope[0]),
             grafico.Restriccion(f"Tope {eqs[1]}", 0, 1, "<=", tope[1])]
    for k, nombre in enumerate(eqs):
        if minimo[k] > EPS:
            restr.append(grafico.Restriccion(f"Mínimo {nombre}", 1 - k, k, ">=", minimo[k]))
    tabla, optimo = grafico.resolver(c[0], c[1], restr)

    # Simplex a mano: con x = mínimo + y todas las restricciones quedan "≤" y el origen es factible
    z0 = c[0] * minimo[0] + c[1] * minimo[1]
    A = [[1, 1], [1, 0], [0, 1]]
    b = [B - minimo[0] - minimo[1], tope[0] - minimo[0], tope[1] - minimo[1]]
    t, pasos_s = simplex.simplex(c, A, b, ["y1", "y2"], ["h1", "h2", "h3"])
    y, zy = t.solucion()
    recorte = caso["recorte"] * B
    t2, pasos_d = simplex.dual_simplex(t, [-recorte, 0, 0])
    y2, zy2 = t2.solucion()
    return {
        "equipos": eqs, "c": c, "presupuesto": B, "tope": tope, "minimo": minimo,
        "restricciones": [r.__dict__ for r in restr],
        "vertices": tabla.to_dict("records"),
        "optimo": {"x1": float(optimo["x1"]), "x2": float(optimo["x2"]), "Z": float(optimo["Z"])},
        "simplex": {"cambio": {"x1": minimo[0], "x2": minimo[1], "z0": z0}, "A": A, "b": b, "pasos": pasos_s,
                    "x1": minimo[0] + y["y1"], "x2": minimo[1] + y["y2"], "Z": z0 + zy},
        "dual_simplex": {"recorte": recorte, "pasos": pasos_d,
                         "x1": minimo[0] + y2["y1"], "x2": minimo[1] + y2["y2"], "Z": z0 + zy2},
    }


# ---------------------------------------------------------------- Modelo unido (referencia)
def modelo_unido(caso, bolsa, presupuesto_usd=None):
    """Un solo problema lineal con el reparto y el pago juntos, persona por persona."""
    personas, K = caso["personas"], len(caso["tramos"]["ancho"])
    n = len(personas)
    B = presupuesto(caso) if presupuesto_usd is None else presupuesto_usd
    flujos = []  # (persona, fuente, costo, grupo de capacidad, cuenta como extra)
    for i, p in enumerate(personas):
        flujos.append((i, "bolsa", 0.0, f"bolsa_{i}", False))
        if p["equipo"] in caso["batch"]["equipos"]:
            flujos.append((i, "batch", caso["batch"]["costo"], "batch", True))
        flujos.append((i, "api", caso["api"]["costo"], "api", True))
    nv = n * K + len(flujos)
    c, bounds = np.zeros(nv), []
    for i, p in enumerate(personas):
        for k, r in enumerate(rendimientos(caso, p)):
            c[i * K + k] = -r
            bounds.append((0, caso["tramos"]["ancho"][k]))
    for f, fl in enumerate(flujos):
        c[n * K + f] = fl[2]
        bounds.append((0, None))
    A_ub, b_ub, A_eq, b_eq = [], [], [], []
    for i, p in enumerate(personas):
        uso = np.zeros(nv); uso[i * K:(i + 1) * K] = 1
        A_ub.append(uso.copy()); b_ub.append(caso["reglas"]["tope_pct_salario"] * p["salario"])
        A_ub.append(-uso); b_ub.append(-caso["reglas"]["minimo"])
        eq = uso.copy()
        for f, fl in enumerate(flujos):
            if fl[0] == i:
                eq[n * K + f] = -1
        A_eq.append(eq); b_eq.append(0)
    extra = np.zeros(nv)
    for f, fl in enumerate(flujos):
        extra[n * K + f] = 1 if fl[4] else 0
    A_ub.append(extra); b_ub.append(B)
    cap = {"batch": caso["batch"]["capacidad"], "api": caso["api"]["capacidad"]}
    cap.update({f"bolsa_{i}": bolsa[p["nombre"]] for i, p in enumerate(personas)})
    for gr in cap:
        fila = np.zeros(nv)
        for f, fl in enumerate(flujos):
            if fl[3] == gr:
                fila[n * K + f] = 1
        A_ub.append(fila); b_ub.append(cap[gr])
    res = linprog(c, A_ub=np.array(A_ub), b_ub=b_ub, A_eq=np.array(A_eq), b_eq=b_eq, bounds=bounds, method="highs")
    if res.status != 0:
        raise ValueError(res.message)
    g = res.x[:n * K].reshape(n, K)
    pago = float(sum(res.x[n * K + f] * flujos[f][2] for f in range(len(flujos))))
    return {"topes": {p["nombre"]: float(g[i].sum()) for i, p in enumerate(personas)},
            "valor_bruto": float(-(c[:n * K] @ res.x[:n * K])), "pago_variable": pago,
            "valor_menos_pago": float(-res.fun)}


# ---------------------------------------------------------------- Todo junto
def _vista_dos_equipos(caso, bolsa):
    """La vista a mano (gráfico, Simplex en tabla, Dual Simplex) solo existe con dos equipos."""
    if len(equipos(caso)) != 2:
        return None
    try:
        return dos_variables(caso, bolsa)
    except (ValueError, AssertionError):
        return None


def resolver(caso):
    m0 = modelo0(caso)
    bolsa = bolsas(m0)
    m1 = modelo1(caso, bolsa)
    m2 = modelo2(caso, m1, bolsa)
    # vuelta del ciclo: el costo marginal de cada equipo entra de nuevo al Modelo 1
    m1b = modelo1(caso, bolsa, costo_por_equipo=m2["costo_marginal"])
    converge = all(abs(m1b["topes"][k] - m1["topes"][k]) < 1e-6 for k in m1["topes"])
    recorte = modelo1(caso, bolsa, presupuesto(caso) * (1 - caso["recorte"]), metodo="highs-ds")
    m2_recorte = modelo2(caso, recorte, bolsa)
    unido = modelo_unido(caso, bolsa)
    gasto_antes = {p["nombre"]: p["gasto"] for p in caso["personas"]}
    factura = m0["cuotas"] + m2["final"]["costo"]
    return {
        "datos": {"personas": caso["personas"], "nomina": nomina(caso), "presupuesto": presupuesto(caso),
                  "reglas": caso["reglas"], "tramos": caso["tramos"], "planes": caso["planes"],
                  "batch": caso["batch"], "api": caso["api"], "recorte": caso["recorte"],
                  "aprovechamiento_si_cambia": caso["aprovechamiento_si_cambia"],
                  "rendimientos": {p["nombre"]: rendimientos(caso, p) for p in caso["personas"]}},
        "modelo0": m0,
        "modelo1": m1,
        "rango_presupuesto": rango_presupuesto(caso, bolsa),
        "modelo2": m2,
        "ciclo_converge": converge,
        "dos_variables": _vista_dos_equipos(caso, bolsa),
        "recorte": {"modelo1": recorte, "factura": m0["cuotas"] + m2_recorte["final"]["costo"]},
        "modelo_unido": unido,
        "resultado": {
            "factura_antes": float(sum(gasto_antes.values())),
            "cuotas": m0["cuotas"],
            "pago_variable": m2["final"]["costo"],
            "factura": factura,
            "valor_antes": valor_de(caso, gasto_antes),
            "valor": m1["valor_bruto"],
            "neto_antes": valor_de(caso, gasto_antes) - float(sum(gasto_antes.values())),
            "neto": m1["valor_bruto"] - factura,
            "diferencia_con_unido": (m1["valor_bruto"] - m2["final"]["costo"]) - unido["valor_menos_pago"],
            "sobregasto": {k: gasto_antes[k] - m1["topes"][k] for k in gasto_antes},
        },
    }
