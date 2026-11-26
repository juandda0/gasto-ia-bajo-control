# Gasto en IA bajo control

Le dice a una empresa qué plan de IA le conviene a cada programador (Claude, Cursor, OpenAI, API),
cuánto debería usar cada uno y, **en vivo**, cuánto lleva gastando cada persona en Claude Code.

La empresa pone lo que ya sabe (salario, herramienta y gasto del mes pasado de cada persona, más sus
reglas). TI conecta Claude Code una sola vez para toda la empresa y el costo de cada llamada llega
solo, asignado a cada persona por su correo. El plan se recalcula solo cuando cambian los datos y el
mes se cierra solo el día 1. Español e inglés; modo claro y oscuro.

Nació como proyecto de Programación Lineal (Universidad de Córdoba); la vista académica sigue en `/clase/`.

## Arquitectura (Firebase, por capas)

```
web/                          navegador (Firebase Hosting)
  js/ui/                      interfaz: pantallas, idioma (en.js) y tema
  js/dominio/                 fechas del mes, reparto del gasto, lectura de CSV (funciones puras)
  js/datos/                   Firebase: Auth, Firestore en tiempo real, acciones del servidor
  clase/                      vista académica del curso (usa la API pública)
functions/                    backend (Cloud Functions, Python 3.13)
  main.py                     solo registra las funciones
  interfaz/                   HTTP (API pública e ingesta OTLP), acciones del panel, cableado
  aplicacion/                 casos de uso: empresas, planes, ingesta, cierre, conciliación
  dominio/                    programación lineal y reglas del negocio, sin red ni base de datos
  infraestructura/            Firestore, API de costos de Anthropic, cifrado, Excel
  tests/                      125 pruebas (motor matemático + casos de uso con repos en memoria)
firestore.rules               miembros leen; admins editan datos; el resto lo escribe solo el servidor
```

Cada capa solo conoce a la de abajo. Los casos de uso hablan con puertos (`aplicacion/puertos.py`), así
las pruebas corren sin Firebase.

### Funciones

| Función | Tipo | Qué hace |
| --- | --- | --- |
| `ingesta` | HTTP (`/otlp`, `/otlp/**`) | Telemetría OTLP (JSON o protobuf) de Claude Code (`claude_code.api_request`, trae `cost_usd`) y Gemini CLI (`gemini_cli.api_response`, el costo se calcula con `dominio/precios.py`); suma cada evento una sola vez y levanta alertas al 80 % y 100 % del tope |
| `recalcular_plan` | Firestore | Cada vez que cambia `estado/caso`, resuelve el ciclo y guarda el plan |
| `app` | Invocable | Acciones del panel: crear empresa, invitar, tokens, claves de Cursor/OpenAI/Anthropic, nombre y zona horaria, cerrar mes, Excel |
| `cierre_mensual` | Programada (cada hora) | Cierra el mes de cada empresa cuando en SU zona horaria ya es día 1; el gasto real pasa a ser el «mes pasado» |
| `sincronizar_fuentes` | Programada (cada hora) | Cursor (Admin API, `POST /teams/spend`) y OpenAI (`/v1/organization/costs` por usuario) cada hora; facturación de Anthropic cada 3 h |
| `api` | HTTP (`/api/**`) | Cálculo público sin cuenta (vista de clase) |

### Fuentes de gasto

| Herramienta | Cómo llega | Cada cuánto |
| --- | --- | --- |
| Claude Code | Telemetría con token de la empresa; costo exacto por llamada | En vivo (segundos) |
| Gemini CLI | Telemetría con el mismo token; costo calculado con precios de lista (supuesto declarado) | En vivo |
| Cursor | Admin API con clave de administración (planes Teams/Enterprise); uso del ciclo de Cursor | Cada hora |
| OpenAI | Costs API de la organización por usuario (incluye Codex con clave de API) | Cada hora |
| Anthropic (API/consola) | Usage and Cost Analytics API; solo para cuadrar la factura, no se suma | Cada 3 horas |
| ChatGPT, Copilot y otras | A mano en Seguimiento | — |

Las claves de administración se guardan cifradas (Fernet, llave en Secret Manager) y solo las usa el servidor.

### Conectar Claude Code (lo hace TI una vez)

En Ajustes se genera un token de la empresa (solo se guarda su huella SHA-256) y se copia este bloque
a la configuración administrada de Claude Code (`managed-settings.json`) o al `~/.claude/settings.json`
de una persona:

```json
{
  "env": {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "OTEL_LOGS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "https://gasto-ia-bajo-control.web.app/otlp",
    "OTEL_EXPORTER_OTLP_HEADERS": "x-api-key=gia_…"
  }
}
```

Solo viajan costo, tokens, modelo y correo; nunca código ni mensajes.

## Correr en local

```bash
uv venv functions/venv --python 3.13
uv pip install --python functions/venv/bin/python -r functions/requirements.txt pytest matplotlib
python3 -c "from cryptography.fernet import Fernet;print('CLAVE_CIFRADO='+Fernet.generate_key().decode())" > functions/.secret.local
firebase emulators:start --project gasto-ia-bajo-control
```

Abrir <http://localhost:5100>. En localhost la web usa los emuladores (Auth 9199, Firestore 8181,
Functions 5101, Hosting 5100, UI 4100). Pruebas: `cd functions && venv/bin/python -m pytest -q tests`.

## Desplegar

Requiere el plan Blaze (Functions, Scheduler y Secret Manager) y el proveedor Google activado en Authentication.

```bash
python3 -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode(), end='')" | firebase functions:secrets:set CLAVE_CIFRADO --data-file - --project gasto-ia-bajo-control
firebase deploy --project gasto-ia-bajo-control
```

## El ciclo: cada método alimenta al siguiente

| Paso | Pregunta | Método del curso | Pasa al siguiente |
| --- | --- | --- | --- |
| Modelo 0 | ¿Qué plan recibe cada persona? | Asignación, método húngaro | Bolsa incluida de cada persona |
| Modelo 1 | ¿Cuánto debe usar cada uno? | Planteamiento, Simplex (y vista en 2 variables con método gráfico y Simplex en tabla) | Uso óptimo = demanda por equipo |
| Modelo 2 | ¿Con qué fuente se paga? | Transporte: esquina noroeste, costo mínimo, Vogel y MODI | Costo real de un dólar más |
| Indicadores | ¿Vamos bien? | Análisis de sensibilidad (precios sombra y rango) | Alertas por persona |
| Ajuste | ¿Y si recortan el presupuesto? | Dual Simplex | Nuevos topes sin empezar de cero |

Al final se comprueba que el ciclo da lo mismo que un solo modelo lineal unido.

Los salarios, rendimientos, bolsas y precios de los planes del caso de ejemplo son supuestos y se
pueden cambiar desde la app. El informe del curso está en `informe/`, la presentación en `presentacion/`
y el libro de Excel con Solver en `resultados/`.
