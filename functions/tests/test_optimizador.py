import numpy as np
import pytest
from scipy.optimize import linear_sum_assignment, linprog

from dominio import asignacion, grafico, simplex, transporte
from dominio.caso import caso_base, presupuesto
from dominio.ciclo import bolsas, modelo0, modelo1, resolver


def optimo_transporte(oferta, demanda, costos):
    m, n = costos.shape
    A_eq = []
    for i in range(m):
        fila = np.zeros(m * n)
        fila[i * n:(i + 1) * n] = 1
        A_eq.append(fila)
    for j in range(n):
        fila = np.zeros(m * n)
        fila[j::n] = 1
        A_eq.append(fila)
    res = linprog(costos.ravel(), A_eq=np.array(A_eq), b_eq=np.concatenate([oferta, demanda]), method="highs")
    return res.fun


# ---------------------------------------------------------------- métodos a mano contra SciPy
@pytest.mark.parametrize("semilla", range(25))
def test_hungaro_llega_al_optimo(semilla):
    rng = np.random.default_rng(semilla)
    n = int(rng.integers(2, 7))
    C = rng.integers(0, 40, size=(n, n)).astype(float)
    asign, costo, pasos = asignacion.hungaro(C)
    assert sorted(asign) == list(range(n))
    r, c = linear_sum_assignment(C)
    assert costo == pytest.approx(C[r, c].sum())
    assert pasos[-1]["titulo"].startswith("Asignación")


@pytest.mark.parametrize("semilla", range(20))
def test_simplex_y_dual_simplex_contra_linprog(semilla):
    rng = np.random.default_rng(semilla)
    m, n = int(rng.integers(2, 5)), int(rng.integers(2, 4))
    A = rng.integers(1, 6, size=(m, n)).astype(float)
    b = rng.integers(20, 60, size=m).astype(float)
    c = rng.integers(1, 9, size=n).astype(float)
    t, pasos = simplex.simplex(c, A, b, [f"x{j}" for j in range(n)])
    x, z = t.solucion()
    ref = linprog(-c, A_ub=A, b_ub=b, method="highs")
    assert z == pytest.approx(-ref.fun)
    assert "óptima" in pasos[-1]["nota"]

    delta = np.zeros(m)
    delta[0] = -0.4 * b[0]
    t2, _ = simplex.dual_simplex(t, delta)
    _, z2 = t2.solucion()
    ref2 = linprog(-c, A_ub=A, b_ub=b + delta, method="highs")
    assert z2 == pytest.approx(-ref2.fun)


@pytest.mark.parametrize("metodo", ["noroeste", "costo_minimo", "vogel"])
@pytest.mark.parametrize("semilla", range(15))
def test_modi_llega_al_optimo(metodo, semilla):
    rng = np.random.default_rng(semilla)
    m, n = rng.integers(2, 6, size=2)
    oferta = rng.integers(5, 60, size=m).astype(float)
    demanda = rng.integers(5, 60, size=n).astype(float)
    costos = rng.integers(1, 20, size=(m, n)).astype(float)
    oferta, demanda, costos, _ = transporte.balancear(oferta, demanda, costos)
    inicial = {"noroeste": lambda: transporte.esquina_noroeste(oferta, demanda),
               "costo_minimo": lambda: transporte.costo_minimo(oferta, demanda, costos),
               "vogel": lambda: transporte.vogel(oferta, demanda, costos)}[metodo]()
    assert len(inicial.base) == len(oferta) + len(demanda) - 1
    np.testing.assert_allclose(inicial.asignacion.sum(axis=1), oferta)
    np.testing.assert_allclose(inicial.asignacion.sum(axis=0), demanda)
    final, iteraciones = transporte.modi(costos, inicial)
    assert np.nanmin(iteraciones[-1].costos_reducidos) >= -1e-9
    assert final.costo(costos) == pytest.approx(optimo_transporte(oferta, demanda, costos))


def test_grafico_encuentra_el_vertice_optimo():
    restricciones = [
        grafico.Restriccion("Presupuesto", 1, 1, "<=", 720),
        grafico.Restriccion("Tope A", 1, 0, "<=", 460),
        grafico.Restriccion("Tope B", 0, 1, "<=", 600),
        grafico.Restriccion("Mínimo B", 0, 1, ">=", 100),
    ]
    _, optimo = grafico.resolver(2.5, 1.8, restricciones)
    assert (optimo["x1"], optimo["x2"], optimo["Z"]) == pytest.approx((460, 260, 1618))


# ---------------------------------------------------------------- el caso completo
@pytest.fixture(scope="module")
def r():
    return resolver(caso_base())


def test_el_ciclo_coincide_con_el_modelo_unido(r):
    assert r["ciclo_converge"]
    assert r["resultado"]["diferencia_con_unido"] == pytest.approx(0, abs=1e-6)
    for k, v in r["modelo_unido"]["topes"].items():
        assert r["modelo1"]["topes"][k] == pytest.approx(v)


def test_reglas_de_la_empresa(r):
    caso = caso_base()
    m1 = r["modelo1"]
    assert sum(m1["extra"].values()) <= presupuesto(caso) + 1e-6
    for p in caso["personas"]:
        assert caso["reglas"]["minimo"] - 1e-6 <= m1["topes"][p["nombre"]] <= 0.15 * p["salario"] + 1e-6


def test_hungaro_del_caso_igual_a_scipy(r):
    assert r["modelo0"]["costo"] == pytest.approx(r["modelo0"]["costo_scipy"])


def test_precio_sombra_predice_un_dolar_mas():
    caso = caso_base()
    bolsa = bolsas(modelo0(caso))
    B = presupuesto(caso)
    base = modelo1(caso, bolsa)
    mas = modelo1(caso, bolsa, B + 1)
    assert mas["objetivo"] - base["objetivo"] == pytest.approx(base["precio_sombra"]["presupuesto"], rel=1e-6)


def test_dual_simplex_del_caso_respeta_el_recorte(r):
    caso = caso_base()
    rec = r["recorte"]["modelo1"]
    assert sum(rec["extra"].values()) <= presupuesto(caso) * (1 - caso["recorte"]) + 1e-6
    assert r["dos_variables"]["dual_simplex"]["x1"] + r["dos_variables"]["dual_simplex"]["x2"] == pytest.approx(
        presupuesto(caso) * (1 - caso["recorte"]))


# ---------------------------------------------------------------- uso real: equipos de cualquier tamaño
def test_menos_personas_que_cupos_se_balancea_con_ficticios():
    caso = caso_base()
    caso["personas"] = caso["personas"][:4]
    r = resolver(caso)
    assert len(r["modelo0"]["asignacion"]) == 4
    assert r["modelo0"]["costo"] == pytest.approx(r["modelo0"]["costo_scipy"])
    assert r["dos_variables"] is None  # solo queda un equipo


def test_mas_personas_que_cupos_agrega_solo_api():
    caso = caso_base()
    caso["personas"].append({"nombre": "Nueva", "equipo": "Frontend", "salario": 2000, "gasto": 150, "herramienta": "Cursor"})
    r = resolver(caso)
    assert len(r["modelo0"]["asignacion"]) == 7
    assert r["modelo0"]["costo"] == pytest.approx(r["modelo0"]["costo_scipy"])
    assert abs(r["resultado"]["diferencia_con_unido"]) < 1e-6


def test_reglas_imposibles_dan_un_mensaje_claro():
    caso = caso_base()
    caso["reglas"]["presupuesto_pct_nomina"] = 0.005
    with pytest.raises(ValueError, match="no hay solución"):
        resolver(caso)
