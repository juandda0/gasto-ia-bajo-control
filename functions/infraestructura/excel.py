"""Libro de Excel con cada modelo listo para resolver con Solver.

Cada hoja trae los datos, las celdas de decisión (en amarillo), las fórmulas de la
función objetivo y de las restricciones, y la configuración de Solver de Excel
guardada en el libro. La hoja "Solución Python" trae los resultados del programa
para comparar.
"""

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as col
from openpyxl.workbook.defined_name import DefinedName

DECISION = PatternFill("solid", fgColor="FFF2B3")
OBJETIVO = PatternFill("solid", fgColor="D9E7FF")
TITULO = Font(bold=True, size=13)
NEGRITA = Font(bold=True)
GRIS = Font(color="6B6B6B", italic=True)
LINEA = Border(bottom=Side(style="thin", color="BFBFBF"))


def _titulo(ws, texto, nota):
    ws["A1"] = texto
    ws["A1"].font = TITULO
    ws["A2"] = nota
    ws["A2"].font = GRIS
    ws.column_dimensions["A"].width = 30


def _solver(wb, ws, objetivo, variables, restricciones, maximizar):
    """Guarda el modelo de Solver de Excel (nombres ocultos de la hoja)."""
    idx = wb.sheetnames.index(ws.title)
    hoja = f"'{ws.title}'!"
    nombres = {
        "solver_opt": hoja + objetivo, "solver_adj": hoja + variables,
        "solver_typ": "1" if maximizar else "2", "solver_lin": "1", "solver_neg": "1",
        "solver_eng": "2", "solver_num": str(len(restricciones)), "solver_ver": "3",
    }
    for k, (lhs, rel, rhs) in enumerate(restricciones, start=1):
        nombres[f"solver_lhs{k}"] = hoja + lhs
        nombres[f"solver_rel{k}"] = {"<=": "1", "=": "2", ">=": "3"}[rel]
        nombres[f"solver_rhs{k}"] = hoja + rhs
    for nombre, valor in nombres.items():
        dn = DefinedName(nombre, localSheetId=idx, attr_text=valor, hidden=True)
        ws.defined_names[nombre] = dn


def _instrucciones(ws, fila, objetivo, sentido, variables, restricciones):
    ws.cell(fila, 1, "Cómo resolverlo con Solver").font = NEGRITA
    lineas = [
        f"Objetivo: {objetivo} ({sentido})",
        f"Celdas de decisión: {variables}",
        *[f"Restricción: {a} {rel} {b}" for a, rel, b in restricciones],
        "Variables no negativas · Método: Simplex LP (en LibreOffice: Solver lineal)",
    ]
    for k, t in enumerate(lineas, start=1):
        ws.cell(fila + k, 1, t).font = GRIS


# ---------------------------------------------------------------- hojas
def hoja_datos(wb, r):
    ws = wb.active
    ws.title = "Datos"
    _titulo(ws, "Datos del caso", "Salarios, rendimientos y bolsas son supuestos del caso de estudio.")
    encabezado = ["Persona", "Equipo", "Salario (USD)", "Gasto mes pasado (USD)", "Herramienta actual",
                  "Valor tramo 1", "Valor tramo 2", "Valor tramo 3"]
    for j, h in enumerate(encabezado, start=1):
        ws.cell(4, j, h).font = NEGRITA
    for i, p in enumerate(r["datos"]["personas"], start=5):
        vals = [p["nombre"], p["equipo"], p["salario"], p["gasto"], p["herramienta"], *r["datos"]["rendimientos"][p["nombre"]]]
        for j, v in enumerate(vals, start=1):
            ws.cell(i, j, v)
    reglas = r["datos"]["reglas"]
    f = 5 + len(r["datos"]["personas"]) + 1
    filas = [("Nómina mensual (USD)", r["datos"]["nomina"]),
             ("Presupuesto de gasto extra (USD)", r["datos"]["presupuesto"]),
             ("  como % de la nómina", reglas["presupuesto_pct_nomina"]),
             ("Tope de uso por persona (% del salario)", reglas["tope_pct_salario"]),
             ("Mínimo de uso por persona (USD)", reglas["minimo"]),
             ("Ancho de los tramos (USD)", ", ".join(str(a) for a in r["datos"]["tramos"]["ancho"])),
             ("Horas ahorradas por dólar en cada tramo", ", ".join(str(h) for h in r["datos"]["tramos"]["horas_por_dolar"]))]
    for k, (a, b) in enumerate(filas):
        ws.cell(f + k, 1, a)
        ws.cell(f + k, 3, b)
    for j in range(2, 9):
        ws.column_dimensions[col(j)].width = 16


def hoja_modelo0(wb, r):
    ws = wb.create_sheet("Modelo 0 asignación")
    m0 = r["modelo0"]
    n = len(m0["personas"])
    _titulo(ws, "Modelo 0 · Qué plan le toca a cada persona (asignación)",
            "Costo mensual = cuota + uso que no cubre la bolsa. Se minimiza el costo total.")
    ws.cell(4, 1, "Costos (USD)").font = NEGRITA
    for j, cupo in enumerate(m0["cupos"], start=2):
        ws.cell(4, j, cupo).font = NEGRITA
        ws.column_dimensions[col(j)].width = 17
    for i, nombre in enumerate(m0["personas"]):
        ws.cell(5 + i, 1, nombre)
        for j in range(n):
            ws.cell(5 + i, 2 + j, m0["costos"][i][j])
    f0 = 5 + n + 1
    ws.cell(f0, 1, "Asignación (1 = sí)").font = NEGRITA
    for j, cupo in enumerate(m0["cupos"], start=2):
        ws.cell(f0, j, cupo).font = NEGRITA
    ws.cell(f0, 2 + n, "Suma fila").font = NEGRITA
    for i, nombre in enumerate(m0["personas"]):
        ws.cell(f0 + 1 + i, 1, nombre)
        for j in range(n):
            c = ws.cell(f0 + 1 + i, 2 + j, 0)
            c.fill = DECISION
        ws.cell(f0 + 1 + i, 2 + n, f"=SUM({col(2)}{f0 + 1 + i}:{col(1 + n)}{f0 + 1 + i})")
        ws.cell(f0 + 1 + i, 3 + n, 1)
    fs = f0 + 1 + n
    ws.cell(fs, 1, "Suma columna").font = NEGRITA
    for j in range(n):
        ws.cell(fs, 2 + j, f"=SUM({col(2 + j)}{f0 + 1}:{col(2 + j)}{fs - 1})")
        ws.cell(fs + 1, 2 + j, 1)
    ws.cell(fs + 1, 1, "Debe ser")
    fo = fs + 3
    ws.cell(fo, 1, "Costo total (minimizar)").font = NEGRITA
    obj = ws.cell(fo, 2, f"=SUMPRODUCT({col(2)}5:{col(1 + n)}{4 + n},{col(2)}{f0 + 1}:{col(1 + n)}{fs - 1})")
    obj.fill = OBJETIVO
    var = f"$B${f0 + 1}:${col(1 + n)}${fs - 1}"
    restr = [(f"${col(2 + n)}${f0 + 1}:${col(2 + n)}${fs - 1}", "=", f"${col(3 + n)}${f0 + 1}:${col(3 + n)}${fs - 1}"),
             (f"$B${fs}:${col(1 + n)}${fs}", "=", f"$B${fs + 1}:${col(1 + n)}${fs + 1}")]
    _solver(wb, ws, f"$B${fo}", var, restr, maximizar=False)
    _instrucciones(ws, fo + 2, f"B{fo}", "minimizar", var.replace("$", ""), [(a.replace("$", ""), b, c.replace("$", "")) for a, b, c in restr])


def hoja_modelo1(wb, r):
    ws = wb.create_sheet("Modelo 1 reparto")
    d, m0 = r["datos"], r["modelo0"]
    bolsa = {f["persona"]: f["bolsa_usable"] for f in m0["asignacion"]}
    _titulo(ws, "Modelo 1 · Cuánto debería usar cada persona",
            "Se maximiza el valor del uso menos lo que se paga de extra. Lo que cubre la bolsa ya está pagado.")
    enc = ["Persona", "Valor t1", "Valor t2", "Valor t3", "Uso t1", "Uso t2", "Uso t3", "Extra",
           "Uso total", "Tope", "Mínimo", "Bolsa", "Uso − extra"]
    for j, h in enumerate(enc, start=1):
        ws.cell(4, j, h).font = NEGRITA
        ws.column_dimensions[col(j)].width = 12
    ws.column_dimensions["A"].width = 30
    ancho = d["tramos"]["ancho"]
    personas = d["personas"]
    for i, p in enumerate(personas):
        f = 5 + i
        ws.cell(f, 1, p["nombre"])
        for k in range(3):
            ws.cell(f, 2 + k, round(d["rendimientos"][p["nombre"]][k], 6))
            ws.cell(f, 5 + k, 0).fill = DECISION
        ws.cell(f, 8, 0).fill = DECISION
        ws.cell(f, 9, f"=SUM(E{f}:G{f})")
        ws.cell(f, 10, d["reglas"]["tope_pct_salario"] * p["salario"])
        ws.cell(f, 11, d["reglas"]["minimo"])
        ws.cell(f, 12, bolsa[p["nombre"]])
        ws.cell(f, 13, f"=I{f}-H{f}")
    ult = 4 + len(personas)
    fa = ult + 1
    ws.cell(fa, 1, "Ancho de cada tramo").font = NEGRITA
    for k in range(3):
        ws.cell(fa, 5 + k, ancho[k])
    fb = fa + 2
    ws.cell(fb, 1, "Gasto extra total").font = NEGRITA
    ws.cell(fb, 2, f"=SUM(H5:H{ult})")
    ws.cell(fb + 1, 1, "Presupuesto de gasto extra")
    ws.cell(fb + 1, 2, d["presupuesto"])
    ws.cell(fb + 3, 1, "Valor neto (maximizar)").font = NEGRITA
    obj = ws.cell(fb + 3, 2, f"=SUMPRODUCT(B5:D{ult},E5:G{ult})-SUM(H5:H{ult})")
    obj.fill = OBJETIVO
    # Solver compara rango con rango, así que el ancho de cada tramo se repite por fila (columnas N a P)
    for k in range(3):
        ws.cell(4, 14 + k, f"Ancho t{k + 1}").font = NEGRITA
        for f in range(5, ult + 1):
            ws.cell(f, 14 + k, ancho[k])
    var = f"$E$5:$H${ult}"
    restr_xl = [(f"${col(5 + k)}$5:${col(5 + k)}${ult}", "<=", f"${col(14 + k)}$5:${col(14 + k)}${ult}") for k in range(3)]
    restr_xl += [(f"$I$5:$I${ult}", "<=", f"$J$5:$J${ult}"), (f"$I$5:$I${ult}", ">=", f"$K$5:$K${ult}"),
                 (f"$M$5:$M${ult}", "<=", f"$L$5:$L${ult}"), (f"$B${fb}", "<=", f"$B${fb + 1}")]
    _solver(wb, ws, f"$B${fb + 3}", var, restr_xl, maximizar=True)
    _instrucciones(ws, fb + 5, f"B{fb + 3}", "maximizar", var.replace("$", ""),
                   [(a.replace("$", ""), b, c.replace("$", "")) for a, b, c in restr_xl])


def hoja_modelo2(wb, r):
    ws = wb.create_sheet("Modelo 2 transporte")
    m2 = r["modelo2"]
    O, D = m2["origenes"], m2["destinos"]
    _titulo(ws, "Modelo 2 · Con qué se paga el uso de cada equipo (transporte)",
            f"Costo por dólar de uso. {m2['M']:g} = ruta prohibida (M). Se minimiza el costo total.")
    ws.cell(4, 1, "Costos").font = NEGRITA
    for j, nombre in enumerate(D, start=2):
        ws.cell(4, j, nombre).font = NEGRITA
        ws.column_dimensions[col(j)].width = 14
    for i, nombre in enumerate(O):
        ws.cell(5 + i, 1, nombre)
        for j in range(len(D)):
            ws.cell(5 + i, 2 + j, m2["costos"][i][j])
    f0 = 5 + len(O) + 1
    ws.cell(f0, 1, "Envío (USD de uso)").font = NEGRITA
    for j, nombre in enumerate(D, start=2):
        ws.cell(f0, j, nombre).font = NEGRITA
    ws.cell(f0, 2 + len(D), "Enviado").font = NEGRITA
    ws.cell(f0, 3 + len(D), "Oferta").font = NEGRITA
    for i, nombre in enumerate(O):
        fila = f0 + 1 + i
        ws.cell(fila, 1, nombre)
        for j in range(len(D)):
            ws.cell(fila, 2 + j, 0).fill = DECISION
        ws.cell(fila, 2 + len(D), f"=SUM(B{fila}:{col(1 + len(D))}{fila})")
        ws.cell(fila, 3 + len(D), m2["oferta"][i])
    fr = f0 + 1 + len(O)
    ws.cell(fr, 1, "Recibido").font = NEGRITA
    ws.cell(fr + 1, 1, "Demanda")
    for j in range(len(D)):
        ws.cell(fr, 2 + j, f"=SUM({col(2 + j)}{f0 + 1}:{col(2 + j)}{fr - 1})")
        ws.cell(fr + 1, 2 + j, m2["demanda"][j])
    fo = fr + 3
    ws.cell(fo, 1, "Costo total (minimizar)").font = NEGRITA
    obj = ws.cell(fo, 2, f"=SUMPRODUCT(B5:{col(1 + len(D))}{4 + len(O)},B{f0 + 1}:{col(1 + len(D))}{fr - 1})")
    obj.fill = OBJETIVO
    var = f"$B${f0 + 1}:${col(1 + len(D))}${fr - 1}"
    restr = [(f"${col(2 + len(D))}${f0 + 1}:${col(2 + len(D))}${fr - 1}", "=", f"${col(3 + len(D))}${f0 + 1}:${col(3 + len(D))}${fr - 1}"),
             (f"$B${fr}:${col(1 + len(D))}${fr}", "=", f"$B${fr + 1}:${col(1 + len(D))}${fr + 1}")]
    _solver(wb, ws, f"$B${fo}", var, restr, maximizar=False)
    _instrucciones(ws, fo + 2, f"B{fo}", "minimizar", var.replace("$", ""), [(a.replace("$", ""), b, c.replace("$", "")) for a, b, c in restr])


def hoja_dos_equipos(wb, r):
    ws = wb.create_sheet("Dos equipos")
    dv = r["dos_variables"]
    _titulo(ws, "Vista por equipos · El caso que se resuelve con el método gráfico",
            "x1, x2 = gasto extra de cada equipo, con valor constante por dólar (supuesto).")
    ws.cell(4, 1, "Variable").font = NEGRITA
    ws.cell(4, 2, dv["equipos"][0]).font = NEGRITA
    ws.cell(4, 3, dv["equipos"][1]).font = NEGRITA
    ws.cell(5, 1, "Valor por dólar")
    ws.cell(5, 2, dv["c"][0]); ws.cell(5, 3, dv["c"][1])
    ws.cell(6, 1, "Gasto extra (USD)")
    ws.cell(6, 2, 0).fill = DECISION; ws.cell(6, 3, 0).fill = DECISION
    ws.cell(7, 1, "Tope"); ws.cell(7, 2, dv["tope"][0]); ws.cell(7, 3, dv["tope"][1])
    ws.cell(8, 1, "Mínimo"); ws.cell(8, 2, dv["minimo"][0]); ws.cell(8, 3, dv["minimo"][1])
    ws.cell(10, 1, "Gasto total"); ws.cell(10, 2, "=B6+C6")
    ws.cell(11, 1, "Presupuesto"); ws.cell(11, 2, dv["presupuesto"])
    ws.cell(13, 1, "Z (maximizar)").font = NEGRITA
    obj = ws.cell(13, 2, "=SUMPRODUCT(B5:C5,B6:C6)")
    obj.fill = OBJETIVO
    restr = [("$B$6:$C$6", "<=", "$B$7:$C$7"), ("$B$6:$C$6", ">=", "$B$8:$C$8"), ("$B$10", "<=", "$B$11")]
    _solver(wb, ws, "$B$13", "$B$6:$C$6", restr, maximizar=True)
    _instrucciones(ws, 15, "B13", "maximizar", "B6:C6", [(a.replace("$", ""), b, c.replace("$", "")) for a, b, c in restr])
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 14


def hoja_solucion(wb, r):
    ws = wb.create_sheet("Solución Python")
    _titulo(ws, "Solución calculada por el programa", "Para comparar con lo que da Solver.")
    f = 4
    ws.cell(f, 1, "Modelo 0: plan de cada persona").font = NEGRITA
    for k, a in enumerate(r["modelo0"]["asignacion"], start=1):
        ws.cell(f + k, 1, a["persona"]); ws.cell(f + k, 2, a["plan"]); ws.cell(f + k, 3, a["costo"])
    f += len(r["modelo0"]["asignacion"]) + 1
    ws.cell(f, 1, "Costo total del Modelo 0"); ws.cell(f, 3, r["modelo0"]["costo"])
    f += 2
    ws.cell(f, 1, "Modelo 1: uso de cada persona").font = NEGRITA
    ws.cell(f, 2, "Uso total").font = NEGRITA; ws.cell(f, 3, "Extra").font = NEGRITA
    for k, (nombre, uso) in enumerate(r["modelo1"]["topes"].items(), start=1):
        ws.cell(f + k, 1, nombre); ws.cell(f + k, 2, round(uso, 4)); ws.cell(f + k, 3, round(r["modelo1"]["extra"][nombre], 4))
    f += len(r["modelo1"]["topes"]) + 1
    ws.cell(f, 1, "Valor neto del Modelo 1"); ws.cell(f, 2, round(r["modelo1"]["objetivo"], 4))
    ws.cell(f + 1, 1, "Precio sombra del presupuesto"); ws.cell(f + 1, 2, round(r["modelo1"]["precio_sombra"]["presupuesto"], 4))
    f += 3
    ws.cell(f, 1, "Modelo 2: costo total del transporte").font = NEGRITA
    ws.cell(f, 2, r["modelo2"]["final"]["costo"])
    f += 2
    ws.cell(f, 1, "Dos equipos: óptimo").font = NEGRITA
    o = r["dos_variables"]["optimo"]
    ws.cell(f, 2, o["x1"]); ws.cell(f, 3, o["x2"]); ws.cell(f, 4, o["Z"])
    ws.column_dimensions["B"].width = 18


def crear_libro(r, ruta):
    wb = Workbook()
    hoja_datos(wb, r)
    hoja_modelo0(wb, r)
    hoja_modelo1(wb, r)
    hoja_modelo2(wb, r)
    hoja_dos_equipos(wb, r)
    hoja_solucion(wb, r)
    wb.save(ruta)
    return ruta
