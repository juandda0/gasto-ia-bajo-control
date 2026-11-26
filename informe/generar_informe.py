"""Genera el informe del proyecto (HTML para imprimir) y lo convierte a PDF.

Todos los números salen del motor (optimizador.ciclo.resolver), así el informe, la app
y el Excel nunca se contradicen. Uso:

    .venv/bin/python informe/generar_informe.py

Deja informe/informe.html e informe/informe.pdf.
"""

import html
import io
import shutil
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "functions"))  # el motor vive en functions/dominio

from dominio import transporte  # noqa: E402
from dominio.caso import caso_base, rendimientos  # noqa: E402
from dominio.ciclo import VALOR_POR_EQUIPO, bolsas, modelo0, modelo1, resolver  # noqa: E402

# ------------------------------------------------------------------ datos de la portada
TITULO = "Gasto en IA bajo control"
SUBTITULO = "Programación lineal para decidir cuánto gasta una empresa en herramientas de IA para sus programadores"
AUTORES = ["[Nombre del estudiante]"]
DOCENTE = "[Nombre del docente]"
CURSO = "Programación Lineal"
UNIVERSIDAD = "Universidad de Córdoba"
FECHA = "Noviembre de 2026"

# Colores de las gráficas (el texto del informe va en blanco y negro)
AZUL, VIOLETA, NARANJA, ROJO, VERDE, GRIS = "#2f7fd8", "#8a4fe0", "#e8862a", "#d64545", "#2e9e6a", "#9a9aa2"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": "#444", "axes.labelcolor": "#222", "xtick.color": "#333", "ytick.color": "#333",
    "axes.grid": True, "grid.color": "#e6e6e6", "grid.linewidth": 0.6, "axes.axisbelow": True,
    "svg.fonttype": "none",
})


# ------------------------------------------------------------------ utilidades
def n(v, d=0):
    """Número con formato colombiano: punto de miles y coma decimal."""
    if v is None:
        return "—"
    v = float(v)
    if abs(v) < 0.5 * 10 ** -d:
        v = 0.0
    s = f"{v:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def nn(v):
    """Número con los decimales justos (hasta 3)."""
    v = float(v)
    for d in range(0, 4):
        if abs(v - round(v, d)) < 1e-9:
            return n(v, d)
    return n(v, 3)


def usd(v, d=0):
    return f"{n(v, d)} USD"


def e(t):
    return html.escape(str(t))


def svg(fig):
    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight")
    plt.close(fig)
    s = buf.getvalue()
    return s[s.index("<svg"):]


def figura(contenido, pie):
    return f'<figure>{contenido}<figcaption>{pie}</figcaption></figure>'


def tabla(cabecera, filas, clase="", num_desde=1):
    """Tabla simple. Las columnas desde num_desde se alinean a la derecha."""
    th = "".join(f'<th class="{"num" if i >= num_desde else ""}">{c}</th>' for i, c in enumerate(cabecera))
    cuerpo = ""
    for f in filas:
        celdas = ""
        for i, c in enumerate(f):
            if isinstance(c, tuple):  # (texto, clase extra)
                celdas += f'<td class="{"num " if i >= num_desde else ""}{c[1]}">{c[0]}</td>'
            else:
                celdas += f'<td class="{"num" if i >= num_desde else ""}">{c}</td>'
        cuerpo += f"<tr>{celdas}</tr>"
    return f'<table class="{clase}"><thead><tr>{th}</tr></thead><tbody>{cuerpo}</tbody></table>'


# ------------------------------------------------------------------ trazas de los métodos de transporte
def traza_transporte(oferta, demanda, costos):
    """Repite noroeste, costo mínimo y Vogel guardando cada paso (para el desarrollo a mano)."""
    oferta, demanda, costos = np.asarray(oferta, float), np.asarray(demanda, float), np.asarray(costos, float)

    def penal(vals):
        vals = sorted(vals)
        return vals[1] - vals[0] if len(vals) > 1 else vals[0]

    def con_traza(elegir, con_penal=False):
        pasos = []

        def envoltura(filas, columnas, s, d):
            info = {}
            if con_penal:
                cols = sorted(columnas)
                info["pf"] = {i: penal([costos[i, j] for j in cols]) for i in sorted(filas)}
                info["pc"] = {j: penal([costos[i, j] for i in filas]) for j in cols}
            i, j = elegir(filas, columnas, s, d)
            info.update(celda=(i, j), q=min(s[i], d[j]))
            pasos.append(info)
            return i, j

        return envoltura, pasos

    def el_no(filas, columnas, s, d):
        return min(filas), min(columnas)

    def el_cm(filas, columnas, s, d):
        return min(((i, j) for i in filas for j in columnas), key=lambda c: (costos[c], -min(s[c[0]], d[c[1]])))

    def el_vogel(filas, columnas, s, d):
        cols = sorted(columnas)
        cand = [(penal([costos[i, j] for j in cols]), "fila", i) for i in sorted(filas)]
        cand += [(penal([costos[i, j] for i in filas]), "columna", j) for j in cols]
        _, tipo, k = max(cand, key=lambda c: c[0])
        if tipo == "fila":
            return k, min(columnas, key=lambda j: costos[k, j])
        return min(filas, key=lambda i: costos[i, k]), k

    salida = {}
    for clave, el, pen, ref in [("noroeste", el_no, False, transporte.esquina_noroeste(oferta, demanda)),
                                ("costo_minimo", el_cm, False, transporte.costo_minimo(oferta, demanda, costos)),
                                ("vogel", el_vogel, True, transporte.vogel(oferta, demanda, costos))]:
        f, pasos = con_traza(el, pen)
        sol = transporte._asignar(oferta, demanda, f)
        assert np.allclose(sol.asignacion, ref.asignacion), clave  # la traza es la misma que usa el motor
        salida[clave] = {"pasos": pasos, "asignacion": sol.asignacion, "costo": sol.costo(costos)}
    return salida


# ------------------------------------------------------------------ gráficas
def fig_rendimiento(caso):
    h, ancho = caso["tramos"]["horas_por_dolar"], caso["tramos"]["ancho"]
    fig, ax = plt.subplots(figsize=(6.2, 2.5))
    x0 = 0
    colores = [AZUL, VIOLETA, NARANJA]
    for k, (hk, a) in enumerate(zip(h, ancho)):
        ax.bar(x0 + a / 2, hk, width=a, color=colores[k], alpha=0.85, edgecolor="white")
        ax.text(x0 + a / 2, hk + 0.006, f"{n(hk, 2)} h por dólar", ha="center", fontsize=8)
        x0 += a
    ax.set_xlabel("Uso del mes (USD a precio de lista)")
    ax.set_ylabel("Horas ahorradas por dólar")
    ax.set_xlim(0, sum(ancho))
    ax.set_ylim(0, max(h) * 1.25)
    ax.grid(axis="x", visible=False)
    return svg(fig)


def fig_uso(r):
    m1, m0 = r["modelo1"], r["modelo0"]
    nombres = [p["nombre"] for p in r["datos"]["personas"]]
    bol = {a["persona"]: a["bolsa_usable"] for a in m0["asignacion"]}
    cub = [min(m1["topes"][x], bol[x]) for x in nombres]
    ext = [m1["extra"][x] for x in nombres]
    tope = [r["datos"]["reglas"]["tope_pct_salario"] * p["salario"] for p in r["datos"]["personas"]]
    gasto = [p["gasto"] for p in r["datos"]["personas"]]
    fig, ax = plt.subplots(figsize=(6.4, 2.8))
    x = np.arange(len(nombres))
    ax.bar(x - 0.2, gasto, 0.36, color=GRIS, label="Gasto del mes pasado")
    ax.bar(x + 0.2, cub, 0.36, color=AZUL, label="Uso óptimo cubierto por la bolsa")
    ax.bar(x + 0.2, ext, 0.36, bottom=cub, color=VIOLETA, label="Uso óptimo extra")
    for i, t in enumerate(tope):
        ax.plot([i - 0.42, i + 0.42], [t, t], color="#222", lw=1, ls="--")
    ax.plot([], [], color="#222", lw=1, ls="--", label="Tope (15 % del salario)")
    ax.set_xticks(x, nombres)
    ax.set_ylabel("USD de uso al mes")
    ax.legend(fontsize=7.5, ncol=2, frameon=False, loc="upper right")
    ax.set_ylim(0, 500)
    ax.grid(axis="x", visible=False)
    return svg(fig)


def fig_grafico(dv):
    (t1, t2), (m1_, m2_), B = dv["tope"], dv["minimo"], dv["presupuesto"]
    c1, c2 = dv["c"]
    fig, ax = plt.subplots(figsize=(5.6, 4.0))
    xs = np.linspace(0, 800, 400)
    # región factible
    pts = [(0, m2_), (0, t2), (B - t2, t2), (t1, B - t1), (t1, m2_)]
    ax.fill([p[0] for p in pts], [p[1] for p in pts], color=AZUL, alpha=0.15, label="Región factible")
    ax.plot(xs, B - xs, color=AZUL, lw=1.4, label=f"x₁ + x₂ ≤ {n(B)} (presupuesto)")
    ax.axvline(t1, color=VIOLETA, lw=1.4, label=f"x₁ ≤ {n(t1)} (tope Backend)")
    ax.axhline(t2, color=NARANJA, lw=1.4, label=f"x₂ ≤ {n(t2)} (tope Frontend)")
    ax.axhline(m2_, color=VERDE, lw=1.4, label=f"x₂ ≥ {n(m2_)} (mínimo Frontend)")
    zopt = dv["optimo"]["Z"]
    ax.plot(xs, (zopt - c1 * xs) / c2, color=ROJO, lw=1.2, ls="--", label=f"Z = {n(zopt)} (recta óptima)")
    ax.plot(xs, (900 - c1 * xs) / c2, color=ROJO, lw=0.8, ls=":", alpha=0.7, label="Z = 900 (otra recta de Z)")
    for v in dv["vertices"]:
        ax.plot(v["x1"], v["x2"], "o", color="#222", ms=4)
        ax.annotate(f"({n(v['x1'])}, {n(v['x2'])})", (v["x1"], v["x2"]), textcoords="offset points",
                    xytext=(5, 5), fontsize=7.5)
    ax.plot(dv["optimo"]["x1"], dv["optimo"]["x2"], "o", color=ROJO, ms=8, mfc="none", mew=1.6)
    ax.set_xlim(0, 760)
    ax.set_ylim(0, 760)
    ax.set_xlabel("x₁: gasto extra del equipo Backend (USD)")
    ax.set_ylabel("x₂: gasto extra del equipo Frontend (USD)")
    ax.legend(fontsize=7, frameon=True, framealpha=0.95, loc="upper right")
    return svg(fig)


def fig_sensibilidad(caso, bolsa, r):
    Bs = np.arange(100, 1301, 10.0)
    obj = [modelo1(caso, bolsa, presupuesto_usd=b)["objetivo"] for b in Bs]
    fig, ax = plt.subplots(figsize=(6.2, 2.8))
    ax.plot(Bs, obj, color=VIOLETA, lw=1.8)
    rp = r["rango_presupuesto"]
    ax.axvspan(rp["desde"], rp["hasta"], color=AZUL, alpha=0.12, label=f"Rango donde el precio sombra es {n(rp['precio_sombra'], 3)}")
    B = r["modelo1"]["presupuesto"]
    ax.plot(B, r["modelo1"]["objetivo"], "o", color=ROJO, ms=6, label=f"Presupuesto actual ({usd(B)})")
    Br = r["recorte"]["modelo1"]["presupuesto"]
    ax.plot(Br, r["recorte"]["modelo1"]["objetivo"], "o", color=NARANJA, ms=6, label=f"Después del recorte ({usd(Br)})")
    ax.set_xlabel("Presupuesto de gasto extra B (USD)")
    ax.set_ylabel("Valor neto (USD)")
    ax.legend(fontsize=7.5, frameon=False, loc="lower right")
    return svg(fig)


def fig_recorte(r):
    nombres = [p["nombre"] for p in r["datos"]["personas"]]
    a = [r["modelo1"]["topes"][x] for x in nombres]
    b = [r["recorte"]["modelo1"]["topes"][x] for x in nombres]
    fig, ax = plt.subplots(figsize=(6.2, 2.5))
    x = np.arange(len(nombres))
    ax.bar(x - 0.19, a, 0.36, color=GRIS, label="Tope antes del recorte")
    ax.bar(x + 0.19, b, 0.36, color=VIOLETA, label="Tope después del recorte")
    for i in range(len(x)):
        ax.text(x[i] - 0.19, a[i] + 6, n(a[i]), ha="center", fontsize=7)
        ax.text(x[i] + 0.19, b[i] + 6, n(b[i]), ha="center", fontsize=7)
    ax.set_xticks(x, nombres)
    ax.set_ylabel("USD de uso al mes")
    ax.set_ylim(0, 430)
    ax.legend(fontsize=7.5, frameon=False, ncol=2, loc="upper right")
    ax.grid(axis="x", visible=False)
    return svg(fig)


def fig_factura(res):
    fig, ax = plt.subplots(figsize=(6.2, 1.7))
    ax.barh([1], [res["factura_antes"]], color=GRIS, height=0.5)
    ax.barh([0], [res["cuotas"]], color=AZUL, height=0.5, label="Cuotas de asientos")
    ax.barh([0], [res["pago_variable"]], left=[res["cuotas"]], color=VIOLETA, height=0.5, label="Pago por uso (API y batch)")
    ax.text(res["factura_antes"] + 15, 1, usd(res["factura_antes"]), va="center", fontsize=8)
    ax.text(res["factura"] + 15, 0, usd(res["factura"]), va="center", fontsize=8)
    ax.set_yticks([0, 1], ["Con el modelo", "Mes pasado"])
    ax.set_xlim(0, res["factura_antes"] * 1.2)
    ax.set_xlabel("USD al mes")
    ax.legend(fontsize=7.5, frameon=False, loc="lower right", bbox_to_anchor=(1, 0.95), ncol=2)
    ax.grid(axis="y", visible=False)
    return svg(fig)


def svg_ciclo():
    """Diagrama del ciclo (dibujado a mano en SVG, blanco y negro)."""
    cajas = [
        (20, 20, "Datos de la empresa", "salario, herramienta, gasto"),
        (250, 20, "Modelo 0 · Qué plan", "Asignación · método húngaro"),
        (480, 20, "Modelo 1 · Cuánto usar", "Simplex · gráfico · tabla"),
        (480, 150, "Modelo 2 · Con qué pagar", "Transporte · Vogel · MODI"),
        (250, 150, "Indicadores", "Análisis de sensibilidad"),
        (20, 150, "Ajuste a mitad de mes", "Dual Simplex"),
    ]
    w, h = 200, 62
    out = ['<svg viewBox="0 0 735 240" xmlns="http://www.w3.org/2000/svg" class="ciclo">',
           '<defs><marker id="fl" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
           '<path d="M0,0 L10,5 L0,10 z" fill="#111"/></marker></defs>']
    for x, y, t, s in cajas:
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="#fff" stroke="#111" stroke-width="1.2"/>')
        out.append(f'<text x="{x + w / 2}" y="{y + 27}" text-anchor="middle" font-size="13" font-weight="600">{e(t)}</text>')
        out.append(f'<text x="{x + w / 2}" y="{y + 46}" text-anchor="middle" font-size="10.5" fill="#555">{e(s)}</text>')
    flechas = [
        ((220, 51), (250, 51), ""), ((450, 51), (480, 51), "bolsa"),
        ((580, 82), (580, 150), "demanda"), ((480, 181), (450, 181), ""), ((250, 181), (220, 181), ""),
    ]
    for (x1, y1), (x2, y2), et in flechas:
        out.append(f'<line x1="{x1}" y1="{y1}" x2="{x2 - 2 if x2 > x1 else x2 + 2}" y2="{y2 - 2 if y2 > y1 else y2}" stroke="#111" stroke-width="1.2" marker-end="url(#fl)"/>')
        if et:
            tx, ty = ((x1 + x2) / 2, y1 - 6) if y1 == y2 else (x1 + 8, (y1 + y2) / 2 + 4)
            out.append(f'<text x="{tx}" y="{ty}" text-anchor="{"middle" if y1 == y2 else "start"}" font-size="10" fill="#555">{et}</text>')
    # retorno: costo real de un dólar más vuelve al Modelo 1
    out.append('<path d="M 680 181 L 700 181 L 700 51 L 682 51" fill="none" stroke="#111" stroke-width="1" stroke-dasharray="4 3" marker-end="url(#fl)"/>')
    out.append('<text x="712" y="116" font-size="10" fill="#555" transform="rotate(90 712 116)" text-anchor="middle">costo real de un dólar más</text>')
    out.append('<text x="350" y="232" text-anchor="middle" font-size="10.5" fill="#555">El ciclo se repite cada mes con el gasto real del mes anterior.</text>')
    out.append("</svg>")
    return "".join(out)


# ------------------------------------------------------------------ tablas de métodos
def matriz_hungara(p, filas, cols, final=None):
    lineas = p.get("lineas") or {"filas": [], "columnas": []}
    lf, lc = set(lineas["filas"]), set(lineas["columnas"])
    cab = "<th></th>" + "".join(f'<th class="num">{e(c)}</th>' for c in cols)
    cuerpo = ""
    for i, fila in enumerate(p["matriz"]):
        tds = ""
        for j, v in enumerate(fila):
            cl = []
            if i in lf or j in lc:
                cl.append("cub2" if (i in lf and j in lc) else "cub")
            if abs(v) < 1e-9:
                cl.append("cero")
            if final is not None and final[i] == j:
                cl.append("asig")
            tds += f'<td class="num {" ".join(cl)}">{nn(v)}</td>'
        cuerpo += f"<tr><th>{e(filas[i])}</th>{tds}</tr>"
    return f'<table class="mat"><thead><tr>{cab}</tr></thead><tbody>{cuerpo}</tbody></table>'


def tabla_simplex(p, pivote=True):
    cols = p["columnas"]
    sale_fila = p["base"].index(p["sale"]) if p.get("sale") in p["base"] else None
    entra_col = cols.index(p["entra"]) if p.get("entra") in cols else None
    razones = p.get("razones")
    por_fila = razones is not None and len(razones) == len(p["base"]) - 1
    cab = "<th>Base</th>" + "".join(f'<th class="num">{e(c)}</th>' for c in cols)
    if por_fila:
        cab += '<th class="num">Razón</th>'
    cuerpo = ""
    for i, fila in enumerate(p["tabla"]):
        tds = ""
        for j, v in enumerate(fila):
            cl = []
            if pivote and sale_fila is not None and i == sale_fila:
                cl.append("fpiv")
            if pivote and entra_col is not None and j == entra_col:
                cl.append("cpiv")
            if pivote and i == sale_fila and j == entra_col:
                cl.append("piv")
            if j == len(fila) - 1 and i < len(p["tabla"]) - 1 and v < -1e-9:
                cl.append("neg")
            tds += f'<td class="num {" ".join(cl)}">{nn(v)}</td>'
        if por_fila:
            rz = razones[i] if i < len(razones) else None
            tds += f'<td class="num tenue">{"—" if rz is None else nn(rz)}</td>'
        nombre = p["base"][i] if p["base"][i] != "Z" else "Z"
        cuerpo += f'<tr class="{"zfila" if nombre == "Z" else ""}"><th>{e(nombre)}</th>{tds}</tr>'
    pie = ""
    if razones is not None and not por_fila:
        pie = '<tr class="razon"><th>|z<sub>j</sub>/a<sub>ij</sub>|</th>' + "".join(
            f'<td class="num tenue">{"—" if (k >= len(razones) or razones[k] is None) else nn(razones[k])}</td>' for k in range(len(cols))) + "</tr>"
    return f'<table class="mat simplex"><thead><tr>{cab}</tr></thead><tbody>{cuerpo}{pie}</tbody></table>'


def tabla_transporte(m2, x, red=None, ciclo=None, entra=None, u=None, v=None):
    orig, dest, cc, of, de = m2["origenes"], m2["destinos"], m2["costos"], m2["oferta"], m2["demanda"]
    signos = {}
    for k, c in enumerate(ciclo or []):
        signos[tuple(c)] = "+" if k % 2 == 0 else "−"
    cab = "<th>Fuente \\ destino</th>" + "".join(f'<th class="num">{e(d)}</th>' for d in dest) + '<th class="num">Oferta</th>'
    if u is not None:
        cab += '<th class="num">u<sub>i</sub></th>'
    cuerpo = ""
    for i, o in enumerate(orig):
        tds = ""
        for j in range(len(dest)):
            c = cc[i][j]
            costo = "M" if c >= m2["M"] - 1e-9 else nn(c)
            q = x[i][j]
            cls = []
            dentro = ""
            if red is not None and red[i][j] is None:  # básica
                cls.append("basica")
                dentro = f"<b>{n(q)}</b>"
            elif red is not None:
                rv = red[i][j]
                dentro = f'<span class="{"redneg" if rv < -1e-9 else "red"}">{nn(rv) if c < m2["M"] - 1e-9 else "M"}</span>'
            elif q > 1e-9:
                cls.append("basica")
                dentro = f"<b>{n(q)}</b>"
            if entra is not None and tuple(entra) == (i, j):
                cls.append("entra")
            sg = signos.get((i, j), "")
            tds += (f'<td class="tcel {" ".join(cls)}"><span class="costo">{costo}</span>'
                    f'{f"<span class=signo>{sg}</span>" if sg else ""}<span class="q">{dentro}</span></td>')
        cuerpo += f"<tr><th>{e(o)}</th>{tds}<td class='num'>{n(of[i])}</td>"
        if u is not None:
            cuerpo += f"<td class='num'>{nn(u[i])}</td>"
        cuerpo += "</tr>"
    cuerpo += "<tr class='dem'><th>Demanda</th>" + "".join(f"<td class='num'>{n(d)}</td>" for d in de) + "<td></td>"
    if u is not None:
        cuerpo += "<td></td>"
    cuerpo += "</tr>"
    if v is not None:
        cuerpo += "<tr class='dem'><th>v<sub>j</sub></th>" + "".join(f"<td class='num'>{nn(x_)}</td>" for x_ in v) + "<td></td><td></td></tr>"
    return f'<table class="mat trans"><thead><tr>{cab}</tr></thead><tbody>{cuerpo}</tbody></table>'


# ------------------------------------------------------------------ informe
def construir(paginas=None):
    paginas = paginas or {}
    caso = caso_base()
    r = resolver(caso)
    m0, m1, m2, dv = r["modelo0"], r["modelo1"], r["modelo2"], r["dos_variables"]
    res, d = r["resultado"], r["datos"]
    bolsa = bolsas(modelo0(caso))
    personas = d["personas"]
    nombres = [p["nombre"] for p in personas]
    reglas = d["reglas"]
    tr = traza_transporte(m2["oferta"], m2["demanda"], m2["costos"])
    asig = {a["persona"]: a for a in m0["asignacion"]}
    ps = m1["precio_sombra"]
    rp = r["rango_presupuesto"]
    rc = r["recorte"]["modelo1"]
    h = caso["tramos"]["horas_por_dolar"]
    ancho = caso["tramos"]["ancho"]
    ahorro = res["factura_antes"] - res["factura"]

    S = []  # secciones del cuerpo
    add = S.append

    # ---------------------------------------------------- 1. Introducción
    add(f"""
<h1 id="s1">1. Introducción</h1>
<p>Las herramientas de inteligencia artificial para programar (Claude, Cursor, Codex de OpenAI, Antigravity de Google)
se cobran de dos formas: un <b>asiento</b> mensual que trae incluida una cantidad de uso, y el <b>pago por uso</b>, en el
que cada consulta se cobra según los tokens que consume. El pago por uso no tiene techo: si un programador deja a un agente
trabajando toda la tarde, la factura sube sin que nadie lo note hasta fin de mes. Ya hay empresas cuyo gasto en IA se
acerca o supera lo que pagan en salarios a las mismas personas que usan esas herramientas.</p>
<p>El problema es que nadie sabe de antemano cuántos tokens va a gastar una tarea, así que no sirve un modelo que pida
esa información. Lo que sí sabe cualquier empresa, incluso una pequeña o poco organizada, es cuánto gana cada programador,
qué herramienta usa y cuánto pagó el mes pasado. Este proyecto parte solo de esos datos.</p>
<p>La propuesta es un <b>ciclo mensual</b> en el que cada método del curso resuelve una pregunta y le pasa su resultado al
siguiente: qué plan le conviene a cada persona (asignación, método húngaro), cuánto debería usar cada una (planteamiento,
método gráfico y Simplex), con qué fuente se paga ese uso (transporte: esquina noroeste, costo mínimo, Vogel y MODI), cuánto
vale un dólar más de presupuesto (análisis de sensibilidad) y cómo se corrige el plan si la gerencia recorta el
presupuesto a mitad de mes (Dual Simplex). El resultado se entrega en un programa con interfaz web, en un libro de Excel
listo para Solver y en este informe.</p>

<h2>1.1 Objetivos</h2>
<p><b>General.</b> Formular y resolver con programación lineal un modelo que le diga a una empresa cuánto gastar en
herramientas de IA para sus programadores, con qué planes y con qué fuentes de pago, sin pedirle datos que no tiene.</p>
<ul>
<li>Plantear cada decisión del problema como un modelo lineal con variables, función objetivo y restricciones explícitas.</li>
<li>Resolver cada modelo con el método del curso que le corresponde y mostrar el desarrollo paso a paso.</li>
<li>Encadenar los modelos para que la salida de uno sea la entrada del siguiente, y comprobar que el resultado
coincide con un solo modelo lineal que lo junte todo.</li>
<li>Entregar la solución en un programa que una empresa pueda usar y en un Excel que se pueda resolver con Solver.</li>
</ul>
""")

    # ---------------------------------------------------- 2. Caso de estudio
    filas_p = [[e(p["nombre"]), e(p["equipo"]), n(p["salario"]), n(p["gasto"]), e(p["herramienta"]),
                n(reglas["tope_pct_salario"] * p["salario"])] for p in personas]
    filas_p.append([("<b>Total</b>", ""), "", (f"<b>{n(d['nomina'])}</b>", ""), (f"<b>{n(res['factura_antes'])}</b>", ""), "", ""])
    filas_pl = [[e(p["plan"]), e(p["familia"]), n(p["cuota"]), n(p["bolsa"]), n(p["cupos"])] for p in d["planes"]]
    filas_r = [[e(x), " · ".join(nn(v) for v in d["rendimientos"][x])] for x in nombres]
    add(f"""
<h1 id="s2">2. Caso de estudio</h1>
<p>Se usa una empresa de ejemplo con seis programadores repartidos en dos equipos. Los salarios, las bolsas de los
asientos y los rendimientos son <b>supuestos</b> del caso; el programa permite cambiarlos. Todo el gasto se mide en
dólares de uso a precio de lista.</p>
<h3>Personas (USD al mes)</h3>
{tabla(["Persona", "Equipo", "Salario", "Gasto en IA del mes pasado", "Herramienta actual", "Tope (15 % del salario)"], filas_p, num_desde=2)}
<p class="nota">El mes pasado todo se pagó por API a precio de lista: la factura fue {usd(res['factura_antes'])}.</p>
<h3>Reglas de la empresa</h3>
<ul>
<li><b>Presupuesto de gasto extra:</b> lo que se paga aparte de las cuotas de los asientos no pasa del
{n(reglas['presupuesto_pct_nomina'] * 100)} % de la nómina: B = {n(reglas['presupuesto_pct_nomina'], 2)} × {n(d['nomina'])} = <b>{usd(d['presupuesto'])}</b>.</li>
<li><b>Tope por persona:</b> nadie usa más del {n(reglas['tope_pct_salario'] * 100)} % de su salario.</li>
<li><b>Mínimo por persona:</b> nadie se queda con menos de {usd(reglas['minimo'])} de uso.</li>
<li><b>Recorte a mitad de mes:</b> la gerencia puede recortar el presupuesto extra un {n(d['recorte'] * 100)} %.</li>
</ul>
<h3>Planes disponibles</h3>
{tabla(["Plan", "Herramienta", "Cuota mensual (USD)", "Uso incluido o bolsa (USD)", "Cupos"], filas_pl, num_desde=2)}
<p class="nota">Si una persona recibe un plan de una herramienta distinta a la que usa, solo aprovecha el
{n(d['aprovechamiento_si_cambia'] * 100)} % de la bolsa (tiene que cambiar su forma de trabajar).</p>
<h3>Fuentes de pago</h3>
<ul>
<li><b>API pago por uso:</b> 1 USD por dólar de uso, sin límite práctico ({n(d['api']['capacidad'])} USD).</li>
<li><b>API en batch:</b> {n(d['batch']['costo'], 1).replace(',0', '')} USD por dólar de uso (mitad de precio), solo para trabajo que puede esperar;
lo usa el equipo Backend y hasta {usd(d['batch']['capacidad'])} al mes. Los proveedores ofrecen este descuento por procesar en lote.</li>
<li><b>Bolsas de los asientos:</b> costo 0, porque la cuota ya se pagó.</li>
</ul>
<h3>Rendimiento decreciente</h3>
<p>Cada dólar de uso ahorra tiempo de trabajo, pero cada vez menos: los primeros {usd(ancho[0])} ahorran {nn(h[0])} horas por
dólar, los {n(ancho[1])} siguientes {nn(h[1])} y el resto {nn(h[2])}. Una hora vale el salario dividido entre
{caso['tramos']['horas_mes']} horas al mes, así que el valor de un dólar en el tramo <i>k</i> para la persona <i>d</i> es</p>
<div class="ec">r<sub>d,k</sub> = h<sub>k</sub> × salario<sub>d</sub> / {caso['tramos']['horas_mes']}</div>
{figura(fig_rendimiento(caso), "Figura 1. Horas ahorradas por cada dólar de uso, por tramo.")}
{tabla(["Persona", "r<sub>d,1</sub> · r<sub>d,2</sub> · r<sub>d,3</sub> (USD de tiempo por dólar)"], filas_r, num_desde=1)}
<p>Los tramos hacen que el problema siga siendo lineal: como r<sub>d,1</sub> &gt; r<sub>d,2</sub> &gt; r<sub>d,3</sub>,
al maximizar el modelo siempre llena primero el tramo que más rinde, sin necesitar variables enteras.</p>
""")

    # ---------------------------------------------------- 3. El ciclo
    add(f"""
<h1 id="s3">3. El ciclo de solución</h1>
<p>El problema completo se divide en cinco preguntas. Cada una se responde con un método del curso y su resultado
alimenta al siguiente paso.</p>
{figura(svg_ciclo(), "Figura 2. Ciclo mensual: cada método le pasa su resultado al siguiente.")}
{tabla(["Paso", "Pregunta", "Método", "Entrega al siguiente"], [
        ["Modelo 0", "¿Qué plan recibe cada persona?", "Asignación, método húngaro", "La bolsa que trae el plan de cada persona"],
        ["Modelo 1", "¿Cuánto debe usar cada una?", "Planteamiento y Simplex; en dos variables, método gráfico y Simplex en tabla", "El uso óptimo, que es la demanda de cada equipo"],
        ["Modelo 2", "¿Con qué fuente se paga?", "Transporte: noroeste, costo mínimo, Vogel y MODI", "El costo real de un dólar más, que vuelve al Modelo 1"],
        ["Indicadores", "¿Vamos bien?", "Análisis de sensibilidad", "Precios sombra, rango del presupuesto y alertas"],
        ["Ajuste", "¿Y si recortan el presupuesto?", "Dual Simplex", "Nuevos topes sin resolver desde cero"],
    ], num_desde=9)}
<p>El ciclo <b>converge</b> cuando el costo de un dólar extra que el Modelo 1 supone es el mismo que el Modelo 2 calcula.
En el caso de estudio esto ocurre en la primera vuelta (sección 6.4). Al final se comprueba que el ciclo da exactamente el
mismo resultado que un solo modelo lineal que junta el Modelo 1 y el Modelo 2 (sección 9).</p>
""")

    # ---------------------------------------------------- 4. Modelo 0
    pasos0 = m0["pasos"]
    final0 = pasos0[-1].get("asignacion")
    bloques = []
    for k, p in enumerate(pasos0):
        txt = p["titulo"]
        if p.get("lineas"):
            lf = [m0["personas"][i] for i in p["lineas"]["filas"]]
            lc = [m0["cupos"][j] for j in p["lineas"]["columnas"]]
            partes = []
            if lf:
                partes.append("filas " + ", ".join(lf))
            if lc:
                partes.append("columnas " + ", ".join(lc))
            num = len(lf) + len(lc)
            txt += f". Líneas: {' y '.join(partes)}. " + ("Como hay 6 líneas, ya se puede asignar." if num == 6 else "Como son menos de 6, todavía no se puede asignar.")
        if p.get("delta"):
            txt += f": δ = {nn(p['delta'])} es el menor valor que quedó sin cubrir."
        bloques.append(f'<div class="paso"><div class="paso-t"><span class="pn">{k}</span>{e(txt)}</div>'
                       f'{matriz_hungara(p, m0["personas"], m0["cupos"], final0 if k == len(pasos0) - 1 else None)}</div>')
    filas_a = [[e(a["persona"]), e(a["cupo"]), n(a["cuota"]), n(a["bolsa_usable"]),
                n(next(p["gasto"] for p in personas if p["nombre"] == a["persona"])), n(a["costo"])] for a in m0["asignacion"]]
    filas_a.append([("<b>Total</b>", ""), "", (f"<b>{n(m0['cuotas'])}</b>", ""), "", "", (f"<b>{n(m0['costo'])}</b>", "")])
    add(f"""
<h1 id="s4">4. Modelo 0: qué plan recibe cada persona</h1>
<h2>4.1 Planteamiento</h2>
<p>Cada persona recibe exactamente un plan y cada cupo de plan se le da a una sola persona. Como hay 6 personas y
6 cupos (2 de Cursor Teams, 1 de Claude Premium, 1 de Claude Standard y 2 de solo API), es un <b>problema de asignación</b>
balanceado. El costo de darle a la persona <i>i</i> el cupo <i>j</i> se estima con lo que gastó el mes pasado:</p>
<div class="ec">c<sub>ij</sub> = cuota<sub>j</sub> + máx(0, gasto<sub>i</sub> − a<sub>ij</sub> × bolsa<sub>j</sub>)</div>
<p>donde a<sub>ij</sub> = 1 si el plan es de la herramienta que la persona ya usa y {nn(d['aprovechamiento_si_cambia'])} si no
(el plan "Solo API" sirve con cualquier herramienta). Por ejemplo, Ana gasta 420 y usa Claude: con Claude Premium paga
100 + máx(0, 420 − 400) = 120; con Cursor Teams paga 30 + máx(0, 420 − 0,6 × 150) = 360.</p>
<div class="modelo">
<p><b>Variables:</b> x<sub>ij</sub> = 1 si la persona <i>i</i> recibe el cupo <i>j</i>, 0 si no.</p>
<p><b>Minimizar</b> Z = Σ<sub>i</sub> Σ<sub>j</sub> c<sub>ij</sub> x<sub>ij</sub></p>
<p><b>Sujeto a</b> Σ<sub>j</sub> x<sub>ij</sub> = 1 para cada persona <i>i</i> &nbsp;·&nbsp;
Σ<sub>i</sub> x<sub>ij</sub> = 1 para cada cupo <i>j</i> &nbsp;·&nbsp; x<sub>ij</sub> ≥ 0</p>
</div>
<p>La matriz de restricciones de la asignación es totalmente unimodular, así que el óptimo del modelo lineal ya sale con
valores 0 y 1. Se resuelve con el método húngaro.</p>
<h2>4.2 Desarrollo con el método húngaro</h2>
<p>En las tablas, las celdas grises están cubiertas por una línea, las de gris oscuro están en el cruce de dos líneas y
los ceros van en negrilla. En la última tabla, el recuadro marca la asignación.</p>
<div class="pasos">{"".join(bloques)}</div>
<h2>4.3 Resultado</h2>
{tabla(["Persona", "Cupo asignado", "Cuota", "Bolsa que aprovecha", "Gasto mes pasado", "Costo c<sub>ij</sub>"], filas_a, num_desde=2)}
<p>El costo mínimo es <b>{usd(m0['costo'])}</b>, contra {usd(m0['costo_todo_api'])} si todos siguieran por API. La función
<code>linear_sum_assignment</code> de SciPy da el mismo valor ({usd(m0['costo_scipy'])}). Lo que pasa al Modelo 1 es la
<b>bolsa</b> que trae el plan de cada persona: Ana {n(bolsa['Ana'])}, Luis {n(bolsa['Luis'])}, Sara {n(bolsa['Sara'])},
Pedro {n(bolsa['Pedro'])}, Carla {n(bolsa['Carla'])} y Diego {n(bolsa['Diego'])} USD. Las cuotas suman
{usd(m0['cuotas'])} y son un costo fijo del mes.</p>
""")

    # ---------------------------------------------------- 5. Modelo 1
    filas_m1 = []
    for p in personas:
        x = p["nombre"]
        g = m1["tramos"][x]
        filas_m1.append([e(x), n(bolsa[x]), n(reglas["tope_pct_salario"] * p["salario"]), n(g[0]), n(g[1]), n(g[2]),
                         (f"<b>{n(m1['topes'][x])}</b>", ""), n(m1["extra"][x])])
    filas_m1.append([("<b>Total</b>", ""), "", "", "", "", "", (f"<b>{n(sum(m1['topes'].values()))}</b>", ""), (f"<b>{n(sum(m1['extra'].values()))}</b>", "")])
    add(f"""
<h1 id="s5">5. Modelo 1: cuánto debe usar cada persona</h1>
<h2>5.1 Planteamiento</h2>
<div class="modelo">
<p><b>Variables:</b> g<sub>d,k</sub> = dólares de uso de la persona <i>d</i> en el tramo <i>k</i> (k = 1, 2, 3);
e<sub>d</sub> = uso extra de la persona <i>d</i>, el que no cubre la bolsa de su plan.</p>
<p><b>Maximizar</b> Z = Σ<sub>d</sub> Σ<sub>k</sub> r<sub>d,k</sub> g<sub>d,k</sub> − Σ<sub>d</sub> c<sub>d</sub> e<sub>d</sub>
&nbsp;&nbsp;(valor del tiempo ahorrado menos lo que se paga aparte)</p>
<p><b>Sujeto a</b>, para cada persona <i>d</i>:</p>
<p class="sang">Σ<sub>k</sub> g<sub>d,k</sub> − e<sub>d</sub> ≤ bolsa<sub>d</sub> &nbsp;&nbsp;(lo que pasa de la bolsa es extra)</p>
<p class="sang">Σ<sub>k</sub> g<sub>d,k</sub> ≤ {nn(reglas['tope_pct_salario'])} × salario<sub>d</sub> &nbsp;&nbsp;(tope por persona)</p>
<p class="sang">Σ<sub>k</sub> g<sub>d,k</sub> ≥ {n(reglas['minimo'])} &nbsp;&nbsp;(mínimo por persona)</p>
<p class="sang">0 ≤ g<sub>d,k</sub> ≤ ancho<sub>k</sub> = {n(ancho[0])}, {n(ancho[1])}, {n(ancho[2])} &nbsp;·&nbsp; e<sub>d</sub> ≥ 0</p>
<p>y para la empresa: Σ<sub>d</sub> e<sub>d</sub> ≤ B = {usd(m1['presupuesto'])} &nbsp;&nbsp;(presupuesto de gasto extra)</p>
</div>
<p>Con 6 personas el modelo tiene 24 variables (18 de tramos y 6 de extra) y 19 restricciones más las cotas de los
tramos. El costo c<sub>d</sub> de un dólar extra empieza en 1 USD (precio de API) y el Modelo 2 lo confirma o lo corrige.
Se resolvió con el Simplex de HiGHS (<code>scipy.optimize.linprog</code>) en {m1['iteraciones']} iteraciones; el mismo
modelo está en la hoja "Modelo 1 reparto" del Excel para Solver.</p>
<h2>5.2 Solución</h2>
{tabla(["Persona", "Bolsa", "Tope", "g<sub>1</sub>", "g<sub>2</sub>", "g<sub>3</sub>", "Uso óptimo", "Extra e<sub>d</sub>"], filas_m1)}
<p>El valor del tiempo ahorrado es <b>{usd(m1['valor_bruto'], 1)}</b> y el gasto extra usa todo el presupuesto
({usd(sum(m1['extra'].values()))}), así que Z = {n(m1['valor_bruto'], 1)} − {n(sum(m1['extra'].values()))} =
<b>{n(m1['objetivo'], 1)}</b>. Se lee así:</p>
<ul>
<li><b>Ana</b> llega a su tope de {usd(m1['topes']['Ana'])}, que cabe en su bolsa de 400: no genera gasto extra.</li>
<li><b>Sara</b> usa solo su bolsa ({usd(m1['topes']['Sara'])}): su tramo 2 vale {nn(d['rendimientos']['Sara'][1])} USD por dólar, pero se
compite por el presupuesto con personas que rinden más.</li>
<li><b>Luis, Pedro y Carla</b> llenan sus tramos 1 y 2 ({usd(250)}). Su tramo 3 rinde menos de 1 USD por dólar, menos de lo
que cuesta, así que no se usa.</li>
<li><b>Diego</b> es la persona marginal: se queda a mitad del tramo 2 ({usd(m1['topes']['Diego'])}) porque ahí se acaba el presupuesto.</li>
</ul>
{figura(fig_uso(r), "Figura 3. Gasto del mes pasado contra el uso óptimo de cada persona.")}
""")

    # ---------------------------------------------------- 6. Vista en dos variables: gráfico y simplex
    sx = dv["simplex"]
    filas_v = [[e(v["vertice"]), n(v["x1"]), n(v["x2"]), (f"<b>{n(v['Z'])}</b>" if v["Z"] == dv["optimo"]["Z"] else n(v["Z"]), "")] for v in dv["vertices"]]
    tablas_sx = ""
    for k, p in enumerate(sx["pasos"]):
        tablas_sx += f'<div class="paso"><div class="paso-t"><span class="pn">{k}</span>{e(p["nota"])}' + (
            f'. Entra <b>{e(p["entra"])}</b> y sale <b>{e(p["sale"])}</b>.' if p.get("entra") else ".") + f'</div>{tabla_simplex(p)}</div>'
    add(f"""
<h1 id="s6">6. Vista por equipos: método gráfico y Simplex en tabla</h1>
<p>Para poder resolver a mano, el Modelo 1 se agrupa por equipos. Se supone que cada dólar extra rinde lo mismo dentro
de cada equipo ({nn(VALOR_POR_EQUIPO['Backend'])} USD en Backend y {nn(VALOR_POR_EQUIPO['Frontend'])} USD en Frontend) y queda un
problema de dos variables.</p>
<h2>6.1 Planteamiento</h2>
<div class="modelo">
<p><b>Variables:</b> x<sub>1</sub> = gasto extra del equipo Backend, x<sub>2</sub> = gasto extra del equipo Frontend (USD).</p>
<p><b>Maximizar</b> Z = {nn(dv['c'][0])} x<sub>1</sub> + {nn(dv['c'][1])} x<sub>2</sub></p>
<p><b>Sujeto a</b></p>
<p class="sang">x<sub>1</sub> + x<sub>2</sub> ≤ {n(dv['presupuesto'])} &nbsp;&nbsp;(presupuesto)</p>
<p class="sang">x<sub>1</sub> ≤ {n(dv['tope'][0])} &nbsp;&nbsp;(tope Backend: Σ máx(0, tope − bolsa) = 0 + 150 + 105 + 205)</p>
<p class="sang">x<sub>2</sub> ≤ {n(dv['tope'][1])} &nbsp;&nbsp;(tope Frontend: 330 + 270, no tienen bolsa)</p>
<p class="sang">x<sub>2</sub> ≥ {n(dv['minimo'][1])} &nbsp;&nbsp;(mínimo Frontend: 50 + 50) &nbsp;·&nbsp; x<sub>1</sub>, x<sub>2</sub> ≥ 0</p>
</div>
<h2>6.2 Método gráfico</h2>
<p>Se dibuja cada restricción como una recta, se marca la región que cumple todas y se evalúa Z en cada vértice. La
recta de Z se desplaza en la dirección de crecimiento (gradiente (2,5; 1,8)) hasta el último punto que toca la región.</p>
{figura(fig_grafico(dv), "Figura 4. Región factible, vértices y recta óptima de Z.")}
{tabla(["Vértice (cruce de restricciones)", "x<sub>1</sub>", "x<sub>2</sub>", "Z"], filas_v)}
<p>El óptimo es <b>x<sub>1</sub> = {n(dv['optimo']['x1'])}, x<sub>2</sub> = {n(dv['optimo']['x2'])}, Z = {n(dv['optimo']['Z'])}</b>,
en el cruce del presupuesto con el tope de Backend: conviene darle a Backend todo lo que puede usar porque cada dólar
rinde más allí, y lo que sobra va a Frontend. La misma vista está en la hoja "Dos equipos" del Excel.</p>
<h2>6.3 Simplex en tabla</h2>
<p>La restricción x<sub>2</sub> ≥ 100 haría que el origen no fuera factible. Para empezar en un punto factible se cambia de
variable: x<sub>1</sub> = {n(sx['cambio']['x1'])} + y<sub>1</sub> y x<sub>2</sub> = {n(sx['cambio']['x2'])} + y<sub>2</sub> con
y<sub>1</sub>, y<sub>2</sub> ≥ 0. Sustituyendo, todas las restricciones quedan "≤" y se agregan las holguras h<sub>1</sub>, h<sub>2</sub>, h<sub>3</sub>:</p>
<div class="modelo">
<p><b>Maximizar</b> Z = {nn(dv['c'][0])} y<sub>1</sub> + {nn(dv['c'][1])} y<sub>2</sub> + {n(sx['cambio']['z0'])}</p>
<p class="sang">y<sub>1</sub> + y<sub>2</sub> + h<sub>1</sub> = {n(sx['b'][0])} &nbsp;·&nbsp; y<sub>1</sub> + h<sub>2</sub> = {n(sx['b'][1])} &nbsp;·&nbsp; y<sub>2</sub> + h<sub>3</sub> = {n(sx['b'][2])}</p>
</div>
<p>La última fila guarda z<sub>j</sub> − c<sub>j</sub>. Entra la columna más negativa, sale la fila con la menor razón
solución / coeficiente (solo coeficientes positivos) y se pivotea. La celda con recuadro es el pivote. El valor de Z en la
tabla no incluye la constante {n(sx['cambio']['z0'])}.</p>
<div class="pasos">{tablas_sx}</div>
<p>Termina en y<sub>1</sub> = 460 y y<sub>2</sub> = 160, es decir x<sub>1</sub> = <b>{n(sx['x1'])}</b>, x<sub>2</sub> = 100 + 160 =
<b>{n(sx['x2'])}</b> y Z = 1.438 + 180 = <b>{n(sx['Z'])}</b>: el mismo vértice del método gráfico, al que Simplex llega en dos
pivoteos pasando por el vértice (460, 100). En la tabla final, el z<sub>j</sub> − c<sub>j</sub> de h<sub>1</sub> (1,8) es el precio
sombra del presupuesto en esta vista y el de h<sub>2</sub> (0,7) el del tope de Backend.</p>
""")

    # ---------------------------------------------------- 7. Modelo 2: transporte
    o, dd = m2["origenes"], m2["destinos"]

    def lista_pasos(clave):
        items = []
        for p in tr[clave]["pasos"]:
            i, j = p["celda"]
            extra = ""
            if "pf" in p:
                pf = ", ".join(f"{o[a].split(' (')[0]} {nn(b)}" for a, b in p["pf"].items())
                pc = ", ".join(f"{dd[a]} {nn(b) if b < 90 else 'M'}" for a, b in p["pc"].items())
                extra = f'<span class="tenue">Penalizaciones: filas [{pf}]; columnas [{pc}].</span> '
            costo = m2["costos"][i][j]
            items.append(f"<li>{extra}Se asigna <b>{n(p['q'])}</b> a {e(o[i])} → {e(dd[j])} (costo {nn(costo)}).</li>")
        return "<ol class='pasos-t'>" + "".join(items) + "</ol>"

    modi_html = ""
    for k, it in enumerate(m2["modi"]):
        if it["entra"] is not None:
            i, j = it["entra"]
            ciclo_txt = " → ".join(f"({o[a].split(' (')[0]}, {dd[b]}) {'+' if t % 2 == 0 else '−'}" for t, (a, b) in enumerate(it["ciclo"]))
            nota = (f"Costo {usd(it['costo'])}. Se calculan u<sub>i</sub> y v<sub>j</sub> con c<sub>ij</sub> = u<sub>i</sub> + v<sub>j</sub> en las "
                    f"casillas básicas (u<sub>1</sub> = 0) y en las vacías el costo reducido c<sub>ij</sub> − u<sub>i</sub> − v<sub>j</sub>. "
                    f"El más negativo es <b>{e(o[i])} → {e(dd[j])}</b> ({nn(it['reducidos'][i][j])}), que entra. "
                    f"Ciclo: {e(ciclo_txt)}. θ = <b>{n(it['theta'])}</b> (el menor valor en las casillas −); sale "
                    f"{e(o[it['sale'][0]])} → {e(dd[it['sale'][1]])}.")
        else:
            nota = f"Costo {usd(it['costo'])}. Ningún costo reducido es negativo: <b>la solución es óptima</b>."
        modi_html += (f'<div class="paso"><div class="paso-t"><span class="pn">{k}</span>{nota}</div>'
                      f'{tabla_transporte(m2, it["asignacion"], red=it["reducidos"], ciclo=it["ciclo"], entra=it["entra"], u=it["u"], v=it["v"])}</div>')
    vog_final = m2["modi"][-1]
    add(f"""
<h1 id="s7">7. Modelo 2: con qué fuente se paga</h1>
<h2>7.1 Planteamiento</h2>
<p>El uso óptimo del Modelo 1 es la <b>demanda</b> de cada equipo: Backend {usd(m2['demanda'][0])} (360 + 250 + 150 + 250)
y Frontend {usd(m2['demanda'][1])} (250 + 200). Las fuentes de pago son la <b>oferta</b>: la API a precio de lista, la
API en batch y las bolsas de los asientos de Backend ({usd(m2['oferta'][2])}: 360 de Ana, 150 de Luis, 150 de Sara y
80 de Pedro). La oferta total ({n(sum(m2['oferta']))}) es mayor que la demanda ({n(m2['demanda'][0] + m2['demanda'][1])}), así
que se agrega un destino <b>ficticio</b> con demanda {n(m2['demanda'][2])} y costo 0. Las rutas que no se pueden usar
(batch y bolsas de Backend hacia Frontend) llevan un costo M muy grande (M = {n(m2['M'])}).</p>
<div class="modelo">
<p><b>Variables:</b> x<sub>ij</sub> = dólares de uso del equipo <i>j</i> que se pagan con la fuente <i>i</i>.</p>
<p><b>Minimizar</b> Z = Σ<sub>i</sub> Σ<sub>j</sub> c<sub>ij</sub> x<sub>ij</sub> &nbsp; <b>s.a.</b>
Σ<sub>j</sub> x<sub>ij</sub> = oferta<sub>i</sub> &nbsp;·&nbsp; Σ<sub>i</sub> x<sub>ij</sub> = demanda<sub>j</sub> &nbsp;·&nbsp; x<sub>ij</sub> ≥ 0</p>
</div>
{tabla_transporte(m2, [[0] * 3 for _ in range(3)])}
<p class="nota">En la esquina de cada casilla está el costo por dólar de uso. Las fuentes se ordenan de la más cara a la
más barata, así la esquina noroeste empieza lejos del óptimo y MODI tiene trabajo que hacer.</p>

<h2>7.2 Soluciones iniciales</h2>
<h3>Esquina noroeste — costo {usd(tr['noroeste']['costo'])}</h3>
{lista_pasos('noroeste')}
{tabla_transporte(m2, tr['noroeste']['asignacion'])}
<h3>Costo mínimo — costo {usd(tr['costo_minimo']['costo'])}</h3>
<p>Se asigna siempre en la casilla más barata que queda; en empate, la que permite asignar más.</p>
{lista_pasos('costo_minimo')}
<h3>Vogel — costo {usd(tr['vogel']['costo'])}</h3>
<p>En cada paso se calcula la penalización de cada fila y columna (diferencia entre sus dos costos más bajos), se toma la
mayor y se asigna en su casilla más barata.</p>
{lista_pasos('vogel')}
{tabla_transporte(m2, tr['vogel']['asignacion'])}
<p>Costo mínimo y Vogel llegan a la misma tabla de {usd(tr['vogel']['costo'])}. La esquina noroeste no mira los costos y
queda en {usd(tr['noroeste']['costo'])}.</p>

<h2>7.3 Prueba de optimalidad MODI</h2>
<p>Se parte de la esquina noroeste. En las tablas, las casillas básicas muestran su asignación en negrilla y las vacías su
costo reducido; el recuadro marca la casilla que entra y los signos + / − el ciclo.</p>
<div class="pasos">{modi_html}</div>
<p>MODI necesita {len(m2['modi']) - 1} iteraciones desde la esquina noroeste (1.460 → 720 → 595). Partiendo de Vogel no necesita
ninguna: todos sus costos reducidos ya son no negativos. La solución óptima paga el uso así: las bolsas cubren
{usd(740)} de Backend, el batch {usd(250)} y la API {usd(20)} de Backend y {usd(450)} de Frontend, por <b>{usd(m2['final']['costo'])}</b>.</p>
<h2>7.4 Lo que vuelve al Modelo 1</h2>
<p>Los potenciales de MODI dicen cuánto cuesta atender un dólar más de cada equipo: v<sub>j</sub> − v<sub>ficticio</sub>.
Con la tabla óptima, v = ({", ".join(nn(x) for x in vog_final['v'])}), así que un dólar más cuesta
{nn(m2['costo_marginal']['Backend'])} USD en Backend y {nn(m2['costo_marginal']['Frontend'])} USD en Frontend: el siguiente dólar se
pagaría por API a precio de lista. Es justo el costo c<sub>d</sub> = 1 que supuso el Modelo 1, así que el ciclo
<b>converge en la primera vuelta</b>. Si una empresa tuviera más batch disponible, este costo bajaría a 0,5, el Modelo 1
se volvería a resolver con ese valor y el ciclo daría otra vuelta.</p>
""")

    # ---------------------------------------------------- 8. Sensibilidad
    filas_ps = [[e(x), n(m1["topes"][x]), nn(ps["topes"][x]), nn(ps["bolsas"][x])] for x in nombres]
    filas_al = []
    for p in personas:
        x = p["nombre"]
        s = res["sobregasto"][x]
        filas_al.append([e(x), n(p["gasto"]), n(m1["topes"][x]),
                         (f"Bajar {n(s)}" if s > 1e-6 else f"Puede usar {n(-s)} más", "")])
    add(f"""
<h1 id="s8">8. Análisis de sensibilidad: los indicadores</h1>
<h2>8.1 Precios sombra</h2>
<p>El precio sombra de una restricción dice cuánto cambia el óptimo si su lado derecho sube una unidad. En el Modelo 1:</p>
<ul>
<li><b>Presupuesto: {n(ps['presupuesto'], 3)}.</b> Un dólar más de presupuesto extra deja {n(ps['presupuesto'], 3)} USD más de valor
neto. Ese dólar iría a Diego, que está a mitad de su tramo 2: rinde {nn(d['rendimientos']['Diego'][1])} y cuesta 1, y
{nn(d['rendimientos']['Diego'][1])} − 1 = {nn(ps['presupuesto'])}. Todavía conviene gastar, pero cada vez rinde menos.</li>
<li><b>Tope de Ana: {nn(ps['topes']['Ana'])}.</b> Si a Ana le subieran el tope un dólar, lo usaría en su tramo 3 ({nn(d['rendimientos']['Ana'][2])}) y
cabría en su bolsa, sin costo. Es la única persona a la que su tope la limita.</li>
<li><b>Bolsas:</b> un dólar más de bolsa vale el rendimiento del tramo en que está la persona, porque le ahorra un dólar de
gasto extra. Esto le dice a la empresa qué plan vale la pena mejorar.</li>
</ul>
{tabla(["Persona", "Uso óptimo", "Precio sombra del tope", "Precio sombra de la bolsa"], filas_ps)}
<h2>8.2 Rango del presupuesto</h2>
<p>Mientras el presupuesto extra esté entre <b>{usd(rp['desde'])} y {usd(rp['hasta'])}</b>, el precio sombra se mantiene en
{n(rp['precio_sombra'], 3)} y la base óptima no cambia (el rango se halló resolviendo el modelo para cada valor de B, en pasos de
1 USD). Por debajo de {usd(rp['desde'])} el dólar marginal sale de un tramo que rinde más y el precio sombra sube; por encima
de {usd(rp['hasta'])} baja. La figura muestra el valor neto como función de B: es cóncava y lineal por tramos, como todo
óptimo de un problema de maximización cuando cambia un lado derecho.</p>
{figura(fig_sensibilidad(caso, bolsa, r), "Figura 5. Valor neto óptimo según el presupuesto de gasto extra.")}
<h2>8.3 Costos reducidos</h2>
<p>Los tramos que no se usan tienen costo reducido negativo: el tramo 3 de Luis, Pedro, Carla y Diego rinde entre
0,45 y 0,55 USD por dólar y cuesta 1, así que meterlo en la solución empeora Z. El de Sara (0,425) tampoco entra.</p>
<h2>8.4 Alertas para la gerencia</h2>
<p>Al comparar el uso óptimo con lo que pasó el mes anterior, la empresa sabe a quién avisarle:</p>
{tabla(["Persona", "Gasto mes pasado", "Tope óptimo", "Alerta"], filas_al)}
""")

    # ---------------------------------------------------- 9. Dual Simplex
    ds = dv["dual_simplex"]
    tablas_ds = ""
    for k, p in enumerate(ds["pasos"]):
        tablas_ds += f'<div class="paso"><div class="paso-t"><span class="pn">{k}</span>{e(p["nota"])}' + (
            f'. Sale <b>{e(p["sale"])}</b> (solución negativa) y entra <b>{e(p["entra"])}</b> (menor |z<sub>j</sub> / a<sub>ij</sub>| con a<sub>ij</sub> &lt; 0).' if p.get("entra") else ".") + f'</div>{tabla_simplex(p)}</div>'
    filas_rc = [[e(x), n(m1["topes"][x]), n(rc["topes"][x]), n(rc["topes"][x] - m1["topes"][x])] for x in nombres]
    add(f"""
<h1 id="s9">9. Ajuste a mitad de mes: Dual Simplex</h1>
<p>A mitad de mes la gerencia recorta el presupuesto extra un {n(d['recorte'] * 100)} %: de {usd(m1['presupuesto'])} a
{usd(rc['presupuesto'])}. Solo cambia un lado derecho, así que la tabla óptima sigue cumpliendo la condición de optimalidad
(todos los z<sub>j</sub> − c<sub>j</sub> ≥ 0) pero puede dejar de ser factible. Es el caso para el Dual Simplex: se sigue
desde la tabla anterior en lugar de empezar de cero.</p>
<h2>9.1 Desarrollo en la vista por equipos</h2>
<p>El nuevo lado derecho se obtiene con B<sup>−1</sup>Δb, donde B<sup>−1</sup> son las columnas de las holguras en la tabla
óptima y Δb = (−{n(ds['recorte'])}, 0, 0). La fila Z cambia en los precios sombra por Δb: 1.438 − 1,8 × 180 = 1.114.</p>
<div class="pasos">{tablas_ds}</div>
<p>Queda y<sub>1</sub> = 440, y<sub>2</sub> = 0: x<sub>1</sub> = <b>{n(ds['x1'])}</b>, x<sub>2</sub> = <b>{n(ds['x2'])}</b> y
Z = 1.100 + 180 = <b>{n(ds['Z'])}</b>. Frontend baja a su mínimo y Backend absorbe el resto del recorte. Con un solo pivoteo
se llega al nuevo óptimo.</p>
<h2>9.2 Recorte en el modelo completo</h2>
<p>El Modelo 1 completo se reoptimizó con el Dual Simplex de HiGHS (<code>method="highs-ds"</code>):</p>
{tabla(["Persona", "Tope antes", "Tope después", "Cambio"], filas_rc)}
{figura(fig_recorte(r), "Figura 6. Topes de uso antes y después del recorte.")}
<p>Pierden uso Pedro y Diego, que eran los que estaban en el margen. El valor neto baja de {n(m1['objetivo'], 1)} a
{n(rc['objetivo'], 1)} ({n(m1['objetivo'] - rc['objetivo'], 1)} menos), justo lo que anticipaban los precios sombra: 100 USD
del recorte a {n(rp['precio_sombra'], 3)} (dentro del rango) y los 80 restantes a {n(rc['precio_sombra']['presupuesto'], 4)}, el nuevo
precio sombra. La factura del mes queda en {usd(r['recorte']['factura'])}.</p>
""")

    # ---------------------------------------------------- 10. Validación
    mu = r["modelo_unido"]
    add(f"""
<h1 id="s10">10. Validación</h1>
<h2>10.1 El ciclo contra un solo modelo</h2>
<p>Para comprobar que dividir el problema en etapas no pierde nada, se armó un modelo lineal unido que decide al mismo
tiempo cuánto usa cada persona y con qué fuente se paga cada dólar (bolsas, batch y API), con el mismo presupuesto.
Su óptimo da los mismos topes y un valor del tiempo ahorrado menos el pago variable de {usd(mu['valor_menos_pago'], 1)}, igual a
lo que da el ciclo ({n(res['valor'], 1)} − {n(res['pago_variable'])}). La diferencia es <b>{usd(res['diferencia_con_unido'], 2)}</b>.</p>
<h2>10.2 Pruebas automáticas</h2>
<p>El programa tiene 99 pruebas que pasan (<code>pytest</code>). Entre ellas:</p>
<ul>
<li>El método húngaro programado a mano da el mismo costo que SciPy en matrices aleatorias.</li>
<li>El Simplex y el Dual Simplex en tabla dan el mismo óptimo que <code>linprog</code> en problemas aleatorios.</li>
<li>MODI llega al óptimo del solver desde las tres soluciones iniciales.</li>
<li>El método gráfico reproduce el ejemplo (460, 260) con Z = 1.618.</li>
<li>El precio sombra predice el cambio del óptimo cuando el presupuesto sube un dólar.</li>
<li>El ciclo da lo mismo que el modelo unido y respeta todas las reglas de la empresa.</li>
</ul>
<h2>10.3 Excel con Solver</h2>
<p>El archivo <code>resultados/modelos-solver.xlsx</code> trae cada modelo en su hoja ("Modelo 0 asignación",
"Modelo 1 reparto", "Modelo 2 transporte" y "Dos equipos"), con las celdas de decisión en amarillo, la función objetivo en
azul y Solver ya configurado (método Simplex LP). Para resolver una hoja: Datos → Solver → Resolver. La hoja
"Solución Python" guarda la respuesta del programa para comparar. Al llenar las celdas de decisión con la solución del
programa, las fórmulas del Excel dan {usd(m0['costo'])}, {n(m1['objetivo'], 1)}, {usd(m2['final']['costo'])} y {n(dv['optimo']['Z'])}.</p>
""")

    # ---------------------------------------------------- 11. Resultados
    filas_fin = []
    for p in personas:
        x = p["nombre"]
        s = res["sobregasto"][x]
        filas_fin.append([e(x), e(asig[x]["plan"]), n(m1["topes"][x]), n(p["gasto"]),
                          (f"Bajar {n(s)}" if s > 1e-6 else f"Puede usar {n(-s)} más", "")])
    add(f"""
<h1 id="s11">11. Resultados</h1>
<p>Esto es lo que el programa le entrega a la empresa: el plan de cada persona y el tope que debe configurar en la consola
de cada proveedor.</p>
{tabla(["Persona", "Plan", "Tope de uso", "Gasto mes pasado", "Acción"], filas_fin, num_desde=2)}
<div class="cifras">
<div><span>Factura del mes</span><b>{usd(res['factura'])}</b><small>antes {usd(res['factura_antes'])}</small></div>
<div><span>Ahorro</span><b>{usd(ahorro)}</b><small>{n(ahorro / res['factura_antes'] * 100)} % menos</small></div>
<div><span>Valor del tiempo ahorrado</span><b>{usd(res['valor'], 1)}</b><small>antes {usd(res['valor_antes'], 1)}</small></div>
<div><span>Valor neto</span><b>{usd(res['neto'], 1)}</b><small>antes {usd(res['neto_antes'], 1)}</small></div>
</div>
{figura(fig_factura(res), "Figura 7. Factura del mes pasado contra la factura con el modelo.")}
<p>La factura baja de {usd(res['factura_antes'])} a <b>{usd(res['factura'])}</b> ({usd(res['cuotas'])} de cuotas y
{usd(res['pago_variable'])} de pago por uso) y el tiempo que ahorra la IA sube, porque el uso se mueve de quien ya estaba en
tramos que rinden poco (Ana, Carla) a quien tenía espacio (Luis, Sara, Diego). El ahorro no sale de usar menos IA: el
uso total pasa de {n(res['factura_antes'])} a {n(sum(m1['topes'].values()))} USD, mejor repartidos y pagados con planes,
bolsas y batch en lugar de API a precio de lista.</p>
""")

    # ---------------------------------------------------- 12. Programa
    add("""
<h1 id="s12">12. El programa</h1>
<p>El programa está hecho en Python. El motor tiene los métodos del curso programados a mano para mostrar cada paso
(húngaro, Simplex y Dual Simplex en tabla, noroeste, costo mínimo, Vogel y MODI) y usa SciPy (HiGHS) para el modelo
completo y para comprobar los resultados. Una API con FastAPI sirve una interfaz web con dos vistas:</p>
<ul>
<li><b>Vista empresa</b>, pensada primero para el celular. La empresa pone sus datos y recibe su plan. Tiene un panel con
las cifras del mes, la lista de lo que hay que hacer, los topes de cada persona y el seguimiento durante el mes con la
proyección al cierre. Al cerrar el mes, el gasto real pasa a ser el dato del mes siguiente: es el ciclo mensual del modelo.
Los métodos trabajan por detrás y se explican en lenguaje de negocio (por ejemplo, el precio sombra aparece como "subir el
presupuesto 100 USD deja tantos USD más").</li>
<li><b>Vista clase</b>, opcional: una página por paso del ciclo con el desarrollo de cada método.</li>
</ul>
<p>El motor también balancea solo el problema de asignación (agrega cupos de solo API o personas ficticias), así la
empresa puede tener cualquier número de personas.</p>
<table><thead><tr><th>Archivo</th><th>Qué hace</th></tr></thead><tbody>
<tr><td><code>optimizador/caso.py</code></td><td>Datos del caso de estudio (única fuente para el programa, el Excel y este informe).</td></tr>
<tr><td><code>optimizador/asignacion.py</code></td><td>Método húngaro con cada paso y la matriz de costos de los planes.</td></tr>
<tr><td><code>optimizador/simplex.py</code></td><td>Simplex y Dual Simplex en tabla.</td></tr>
<tr><td><code>optimizador/transporte.py</code></td><td>Esquina noroeste, costo mínimo, Vogel y MODI.</td></tr>
<tr><td><code>optimizador/grafico.py</code></td><td>Vértices de la región factible para el método gráfico.</td></tr>
<tr><td><code>optimizador/ciclo.py</code></td><td>Arma los modelos y los encadena; el modelo unido para validar.</td></tr>
<tr><td><code>optimizador/excel.py</code></td><td>Genera el libro de Excel con Solver configurado.</td></tr>
<tr><td><code>servidor.py</code> y <code>web/</code></td><td>API e interfaz web.</td></tr>
<tr><td><code>tests/</code></td><td>Las 99 pruebas.</td></tr>
</tbody></table>
<p>Para correrlo: <code>uv venv .venv</code>, <code>uv pip install --python .venv/bin/python -r requirements.txt</code> y
<code>.venv/bin/uvicorn servidor:app --port 8765</code>; luego se abre <code>http://localhost:8765</code>.</p>
""")

    # ---------------------------------------------------- 13. Conclusiones
    add(f"""
<h1 id="s13">13. Conclusiones</h1>
<ul>
<li>El control del gasto en IA se puede plantear con programación lineal sin pedirle a la empresa datos que no tiene:
basta con salarios, herramientas y el gasto del mes anterior.</li>
<li>Cada tema del curso responde una pregunta distinta y su resultado le sirve al siguiente: la asignación decide los
planes, el Simplex reparte el uso, el transporte decide cómo pagarlo, la sensibilidad lo convierte en indicadores y el
Dual Simplex lo ajusta cuando cambian las reglas.</li>
<li>Dividir el problema en etapas no pierde optimalidad: el ciclo da lo mismo que un solo modelo lineal (diferencia 0).</li>
<li>En el caso de estudio la factura baja un {n(ahorro / res['factura_antes'] * 100)} % ({usd(res['factura_antes'])} → {usd(res['factura'])})
y el valor del tiempo ahorrado sube de {usd(res['valor_antes'], 1)} a {usd(res['valor'], 1)}.</li>
<li>Los precios sombra son la parte más útil para la gerencia: dicen cuánto vale un dólar más de presupuesto
({n(ps['presupuesto'], 3)} USD), hasta dónde vale ese número ({usd(rp['desde'])} a {usd(rp['hasta'])}) y qué plan vale la pena mejorar.</li>
</ul>
<h2>13.1 Supuestos y limitaciones</h2>
<ul>
<li>Los rendimientos por tramo (0,2, 0,1 y 0,04 horas por dólar), las bolsas y cuotas de los planes y el {n(d['aprovechamiento_si_cambia'] * 100)} %
de aprovechamiento al cambiar de herramienta son supuestos del caso. Cada empresa los puede ajustar; con el tiempo se
pueden estimar con sus propios datos.</li>
<li>El gasto del mes pasado se usa como estimación del siguiente. Por eso el modelo es un ciclo mensual que se corrige
con lo que realmente pasa.</li>
<li>En la vista por equipos se supone un valor constante por dólar en cada equipo; el modelo completo usa los tramos de
cada persona.</li>
<li>Los precios de los proveedores cambian seguido; el programa trae una tabla de precios oficiales consultada en
noviembre de 2026 como referencia y los planes del caso se pueden editar.</li>
</ul>
<h2>Referencias</h2>
<ul class="refs">
<li>Material del curso de Programación Lineal, Universidad de Córdoba: fundamentos y planteamiento, método gráfico, Simplex,
Dual Simplex, análisis de sensibilidad, métodos de transporte y asignación.</li>
<li>Taha, H. A. <i>Investigación de operaciones</i>. Pearson.</li>
<li>Hillier, F. S. y Lieberman, G. J. <i>Introducción a la investigación de operaciones</i>. McGraw-Hill.</li>
<li>Precios oficiales: Anthropic (platform.claude.com/docs/en/about-claude/pricing), OpenAI (developers.openai.com/api/docs/pricing),
Cursor (cursor.com/docs/models-and-pricing), Google (aistudio.google.com/docs/pricing). Consultados en noviembre de 2026.</li>
<li>Virtanen, P. et al. SciPy 1.0: Fundamental Algorithms for Scientific Computing in Python. <i>Nature Methods</i> 17 (2020).
Huangfu, Q. y Hall, J. A. J. Parallelizing the dual revised simplex method (HiGHS). <i>Mathematical Programming Computation</i> 10 (2018).</li>
</ul>
""")

    indice = [("s1", "Introducción"), ("s2", "Caso de estudio"), ("s3", "El ciclo de solución"),
              ("s4", "Modelo 0: qué plan recibe cada persona"), ("s5", "Modelo 1: cuánto debe usar cada persona"),
              ("s6", "Vista por equipos: método gráfico y Simplex en tabla"), ("s7", "Modelo 2: con qué fuente se paga"),
              ("s8", "Análisis de sensibilidad"), ("s9", "Ajuste a mitad de mes: Dual Simplex"), ("s10", "Validación"),
              ("s11", "Resultados"), ("s12", "El programa"), ("s13", "Conclusiones")]
    toc = "".join(f'<li><a href="#{a}"><span>{k + 1}. {e(t)}</span><span class="pag">{paginas.get(k + 1, "")}</span></a></li>'
                  for k, (a, t) in enumerate(indice))

    resumen = (f"Se formula un ciclo mensual de modelos lineales que le dice a una empresa qué plan de IA darle a cada "
               f"programador (asignación, método húngaro), cuánto debe usar cada uno (Simplex, método gráfico), con qué fuente "
               f"pagarlo (transporte con Vogel y MODI), cuánto vale un dólar más de presupuesto (sensibilidad) y cómo ajustarse "
               f"a un recorte (Dual Simplex). En el caso de estudio la factura baja de {usd(res['factura_antes'])} a "
               f"{usd(res['factura'])} y el valor del tiempo ahorrado sube de {usd(res['valor_antes'], 1)} a {usd(res['valor'], 1)}.")

    portada = f"""
<section class="portada">
  <div class="p-sup">{e(UNIVERSIDAD)} · {e(CURSO)}</div>
  <div class="p-centro">
    <div class="p-etq">Proyecto final</div>
    <h1 class="p-titulo">{e(TITULO)}</h1>
    <p class="p-sub">{e(SUBTITULO)}</p>
  </div>
  <div class="p-pie">
    <div><span>Presentado por</span>{"<br>".join(e(a) for a in AUTORES)}</div>
    <div><span>Docente</span>{e(DOCENTE)}</div>
    <div><span>Fecha</span>{e(FECHA)}</div>
  </div>
</section>
<section class="indice">
  <h2 class="sin-num">Resumen</h2>
  <p>{resumen}</p>
  <h2 class="sin-num">Contenido</h2>
  <ol class="toc">{toc}</ol>
</section>
"""
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>{e(TITULO)} — Informe</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap">
<style>{CSS}</style></head>
<body>{portada}<main>{"".join(S)}</main></body></html>"""


CSS = r"""
@page { size: Letter; margin: 22mm 20mm 20mm 20mm;
  @bottom-right { content: counter(page); font: 9pt 'Geist', sans-serif; color: #666; }
  @bottom-left { content: "Gasto en IA bajo control · Programación Lineal"; font: 8pt 'Geist', sans-serif; color: #888; } }
@page :first { margin: 0; @bottom-right { content: none; } @bottom-left { content: none; } }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: 'Geist', 'DejaVu Sans', sans-serif; font-size: 10pt; line-height: 1.5; color: #111; margin: 0; }
p { margin: 0 0 8pt; text-align: justify; hyphens: auto; }
ul, ol { margin: 0 0 8pt; padding-left: 16pt; }
li { margin-bottom: 3pt; }
b { font-weight: 600; }
code { font-family: 'Geist Mono', monospace; font-size: 8.6pt; background: #f2f2f2; padding: 0 3px; border-radius: 3px; }
h1 { font-size: 17pt; font-weight: 700; letter-spacing: -0.02em; margin: 0 0 10pt; padding-bottom: 6pt; border-bottom: 1.5pt solid #111; break-before: page; break-after: avoid; }
h2 { font-size: 12.5pt; font-weight: 600; margin: 16pt 0 6pt; break-after: avoid; }
h3 { font-size: 10.5pt; font-weight: 600; margin: 12pt 0 5pt; break-after: avoid; }
.sin-num { margin-top: 0; }
.tenue { color: #666; }
.nota { font-size: 8.8pt; color: #555; }
table { border-collapse: collapse; width: 100%; margin: 4pt 0 10pt; font-size: 8.8pt; break-inside: avoid; }
th, td { padding: 3.5pt 6pt; border-bottom: 0.5pt solid #d4d4d4; text-align: left; vertical-align: middle; }
thead th { font-weight: 600; border-bottom: 1pt solid #111; font-size: 8.2pt; color: #333; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.ec { text-align: center; font-size: 10.5pt; margin: 6pt 0 10pt; }
.modelo { border: 0.75pt solid #111; border-radius: 4pt; padding: 8pt 12pt 2pt; margin: 6pt 0 10pt; break-inside: avoid; }
.modelo p { text-align: left; margin-bottom: 5pt; }
.sang { padding-left: 18pt; }
figure { margin: 6pt 0 12pt; text-align: center; break-inside: avoid; }
figure svg { max-width: 100%; height: auto; }
figcaption { font-size: 8.5pt; color: #555; margin-top: 3pt; }
svg.ciclo { width: 100%; font-family: 'Geist', sans-serif; }
/* matrices */
.mat { width: auto; margin: 4pt 0 0; font-size: 8.2pt; }
.mat th, .mat td { padding: 2.5pt 6pt; border: 0.5pt solid #cfcfcf; }
.mat thead th { border-bottom: 1pt solid #111; }
.mat td.cub { background: #e9e9e9; }
.mat td.cub2 { background: #c6c6c6; }
.mat td.cero { font-weight: 700; }
.mat td.asig { outline: 1.6pt solid #111; outline-offset: -2pt; }
.simplex td.fpiv, .simplex td.cpiv { background: #ededed; }
.simplex td.piv { outline: 1.6pt solid #111; outline-offset: -2pt; font-weight: 700; background: #dcdcdc; }
.simplex td.neg { font-weight: 700; text-decoration: underline; }
.simplex tr.zfila th, .simplex tr.zfila td { border-top: 1pt solid #111; font-weight: 600; }
.simplex tr.razon th, .simplex tr.razon td { border: none; font-size: 7.6pt; }
.pasos { display: block; }
.paso { break-inside: avoid; margin: 0 0 10pt; }
.paso-t { font-size: 9pt; margin-bottom: 3pt; text-align: left; }
.pn { display: inline-block; min-width: 15pt; height: 15pt; line-height: 15pt; text-align: center; border-radius: 8pt; background: #111; color: #fff; font-size: 7.5pt; font-weight: 600; margin-right: 6pt; }
.pasos-t { font-size: 8.8pt; }
/* transporte */
.trans { width: 100%; }
.trans td.tcel { position: relative; height: 30pt; min-width: 70pt; text-align: center; vertical-align: bottom; padding-top: 12pt; }
.trans .costo { position: absolute; top: 2pt; right: 4pt; font-size: 7pt; color: #555; border-left: 0.5pt solid #bbb; border-bottom: 0.5pt solid #bbb; padding: 0 3pt; }
.trans .signo { position: absolute; top: 2pt; left: 5pt; font-weight: 700; font-size: 10pt; }
.trans td.basica { background: #efefef; }
.trans td.entra { outline: 1.6pt solid #111; outline-offset: -2pt; }
.trans .red { color: #555; }
.trans .redneg { font-weight: 700; text-decoration: underline; }
.trans tr.dem th, .trans tr.dem td { color: #444; }
/* cifras */
.cifras { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8pt; margin: 6pt 0 12pt; break-inside: avoid; }
.cifras div { border: 0.75pt solid #111; border-radius: 4pt; padding: 7pt 9pt; }
.cifras span { display: block; font-size: 8pt; color: #555; }
.cifras b { display: block; font-size: 14pt; font-weight: 700; letter-spacing: -0.02em; margin: 2pt 0; }
.cifras small { font-size: 8pt; color: #666; }
.refs li { font-size: 8.8pt; }
/* portada */
.portada { height: 279mm; padding: 26mm 22mm; display: flex; flex-direction: column; justify-content: space-between; break-after: page; background: #0b0b0c; color: #f4f4f5; position: relative; overflow: hidden; }
.portada::before { content: ""; position: absolute; inset: auto -30mm -60mm auto; width: 170mm; height: 170mm; border-radius: 50%;
  background: conic-gradient(from 200deg, #4dc3ff, #a774ff, #ff7ab8, #ffb84d, #4dc3ff); filter: blur(60px); opacity: 0.45; }
.portada > * { position: relative; }
.p-sup { font-size: 9.5pt; letter-spacing: 0.04em; color: #c9c9cf; text-transform: uppercase; }
.p-etq { font-family: 'Geist Mono', monospace; font-size: 9pt; color: #a1a1a7; margin-bottom: 10pt; }
.p-titulo { font-size: 40pt; line-height: 1.05; border: none; margin: 0 0 14pt; padding: 0; letter-spacing: -0.035em; break-before: avoid; color: #fff; }
.p-sub { font-size: 13pt; color: #d4d4d8; max-width: 130mm; text-align: left; }
.p-pie { display: grid; grid-template-columns: 1.3fr 1fr 1fr; gap: 10pt; font-size: 10pt; border-top: 0.75pt solid #3a3a3f; padding-top: 10pt; }
.p-pie span { display: block; font-size: 8pt; color: #8b8b92; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 3pt; }
.indice { break-after: page; }
.indice h2 { font-size: 14pt; margin-bottom: 8pt; }
.toc { list-style: none; padding: 0; margin-top: 4pt; }
.toc li { padding: 5pt 0; border-bottom: 0.5pt solid #ddd; font-size: 10.5pt; }
.toc a { color: #111; text-decoration: none; display: flex; justify-content: space-between; }
.toc .pag { color: #555; font-variant-numeric: tabular-nums; }
"""


def buscar_chrome():
    for c in ["google-chrome", "chromium", "chromium-browser"]:
        if shutil.which(c):
            return shutil.which(c)
    base = Path.home() / ".cache/ms-playwright"
    for patron in ["chromium_headless_shell-*/chrome-*/chrome-headless-shell", "chromium-*/chrome-linux*/chrome"]:
        hallados = sorted(base.glob(patron))
        if hallados:
            return str(hallados[-1])
    return None


def paginas_de_secciones(pdf_path):
    """Busca en qué página empieza cada sección (para el índice)."""
    import re
    texto = subprocess.run(["pdftotext", "-layout", str(pdf_path), "-"], capture_output=True, text=True).stdout
    salida = {}
    for num, pagina in enumerate(texto.split("\f"), start=1):
        if num <= 2:  # portada e índice
            continue
        m = re.match(r"\s*(\d+)\. \S", pagina)
        if m and int(m.group(1)) not in salida:
            salida[int(m.group(1))] = num
    return salida


def imprimir(chrome, html_path, pdf_path):
    subprocess.run([chrome, "--headless", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
                    "--virtual-time-budget=15000", "--run-all-compositor-stages-before-draw",
                    f"--print-to-pdf={pdf_path}", html_path.as_uri()], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    carpeta = Path(__file__).resolve().parent
    html_path = carpeta / "informe.html"
    pdf_path = carpeta / "informe.pdf"
    html_path.write_text(construir(), encoding="utf-8")
    chrome = buscar_chrome()
    if not chrome:
        print("HTML:", html_path)
        print("No se encontró Chrome/Chromium: abra informe.html en el navegador e imprímalo a PDF.")
        return
    imprimir(chrome, html_path, pdf_path)
    if shutil.which("pdftotext"):  # segunda pasada con los números de página en el índice
        paginas = paginas_de_secciones(pdf_path)
        html_path.write_text(construir(paginas), encoding="utf-8")
        imprimir(chrome, html_path, pdf_path)
        print("Secciones:", paginas)
    print("HTML:", html_path)
    print("PDF:", pdf_path)


if __name__ == "__main__":
    main()
