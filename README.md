# Gasto en IA bajo control

Proyecto de Programación Lineal (Universidad de Córdoba). Le dice a una empresa qué
plan de IA le conviene a cada programador (Claude, Cursor, OpenAI, API), cuánto
debería usar cada uno, con qué fuente pagarlo y cuándo se está gastando de más.

La empresa solo pone lo que ya sabe: salario, herramienta y gasto del mes pasado
de cada persona, más sus reglas (presupuesto, tope por persona, mínimo, recorte).
Nadie tiene que estimar tokens.

**En línea:** <https://gasto-ia-bajo-control.vercel.app> · paso a paso del curso en
<https://gasto-ia-bajo-control.vercel.app/clase/>

## Cómo correrla

Con [uv](https://docs.astral.sh/uv/):

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/uvicorn servidor:app --port 8765
```

Luego abrir <http://localhost:8765>. (Se usa el puerto 8765 porque el 8000 suele estar ocupado.)

`requirements.txt` trae solo lo que necesita la app; `requirements-dev.txt` le suma `pytest`.

## Despliegue

La app está en [Vercel](https://vercel.com) como una función de Python (FastAPI). `index.py` es el punto de
entrada y solo importa la `app` de `servidor.py`; la misma función sirve la API y la carpeta `web/`.
`.vercelignore` deja por fuera el informe, la presentación, los resultados y las pruebas.

```bash
vercel deploy --prod
```

Cada push a `main` en GitHub también publica una versión nueva.

## Dos vistas

- **Vista empresa** (`/`): la que usa el cliente, pensada primero para el celular. Tiene cuatro pantallas:
  - **Panel:** las cifras del mes, el gasto día a día, alertas y la evolución mes a mes.
  - **Datos:** las personas y las reglas, en lenguaje de negocio.
  - **Plan:** qué plan darle a cada uno, sus topes, qué hacer y qué pasa si cambia o se recorta el presupuesto.
  - **Seguimiento:** se anota el gasto del mes y se ve la proyección al cierre; al cerrar el mes, el gasto real alimenta el plan del siguiente.

  Todo se guarda solo en el navegador.
- **Vista clase** (`/clase/`): opcional. El paso a paso de cada método del curso con los datos de la empresa.

Pruebas: `.venv/bin/python -m pytest`

## El ciclo: cada método alimenta al siguiente

| Paso | Pregunta | Método del curso | Pasa al siguiente |
| --- | --- | --- | --- |
| Modelo 0 | ¿Qué plan recibe cada persona? | Asignación, método húngaro | Bolsa incluida de cada persona |
| Modelo 1 | ¿Cuánto debe usar cada uno? | Planteamiento, Simplex (y vista en 2 variables con método gráfico y Simplex en tabla) | Uso óptimo = demanda por equipo |
| Modelo 2 | ¿Con qué fuente se paga? | Transporte: esquina noroeste, costo mínimo, Vogel y MODI | Costo real de un dólar más |
| Indicadores | ¿Vamos bien? | Análisis de sensibilidad (precios sombra y rango) | Alertas por persona |
| Ajuste | ¿Y si recortan el presupuesto? | Dual Simplex | Nuevos topes sin empezar de cero |

Al final se comprueba que el ciclo da lo mismo que un solo modelo lineal unido.

## Archivos

- `optimizador/caso.py`: datos del caso de ejemplo (personas, reglas, planes, tramos de rendimiento).
- `optimizador/asignacion.py`: método húngaro programado a mano, con cada paso.
- `optimizador/simplex.py`: Simplex y Dual Simplex en tabla, programados a mano.
- `optimizador/transporte.py`: esquina noroeste, costo mínimo, Vogel y MODI, programados a mano.
- `optimizador/grafico.py`: método gráfico (vértices de la región factible).
- `optimizador/ciclo.py`: arma los modelos y los encadena (`resolver(caso)`).
- `optimizador/excel.py`: genera el libro de Excel listo para Solver.
- `optimizador/datos.py`: tabla de precios oficiales consultada (referencia).
- `servidor.py`: API (FastAPI) que sirve `web/` (vista empresa) y `web/clase/` (vista clase).
- `resultados/modelos-solver.xlsx`: libro de Excel con los modelos (celdas amarillas = decisiones, azul = objetivo).
- `informe/`: informe del proyecto en PDF.
- `presentacion/`: presentación de avance.
- `tests/`: pruebas (húngaro contra SciPy, Simplex y Dual Simplex contra `linprog`, MODI contra el óptimo, ciclo = modelo unido, precios sombra).

Los salarios, rendimientos, bolsas y precios de los planes son supuestos del caso
de ejemplo y se pueden cambiar desde la app.
