"""Punto de entrada de Cloud Functions: solo registra las funciones y las conecta con la interfaz.

Capas (cada una solo conoce a la de abajo):
  interfaz/        HTTP, acciones del panel, disparadores y tareas programadas
  aplicacion/      casos de uso (crear empresa, recalcular plan, registrar gasto, cerrar mes…)
  dominio/         programación lineal y reglas del negocio, sin red ni base de datos
  infraestructura/ Firestore, Anthropic, cifrado y Excel
"""

import firebase_admin
from firebase_functions import firestore_fn, https_fn, options, scheduler_fn
from firebase_functions.params import SecretParam

from interfaz import acciones, contexto, http

# Debe existir antes de cualquier invocación: las funciones invocables verifican el token de sesión
# con la app por defecto antes de llegar a nuestro código.
if not firebase_admin._apps:
    firebase_admin.initialize_app()

REGION = "us-east1"
CLAVE_CIFRADO = SecretParam("CLAVE_CIFRADO")

options.set_global_options(region=REGION, max_instances=10)


@https_fn.on_request(memory=options.MemoryOption.GB_1, timeout_sec=60, max_instances=3, invoker="public")
def api(req: https_fn.Request) -> https_fn.Response:
    """API pública del cálculo (vista de clase y demo). No guarda nada."""
    return http.api(req)


# Pública a nivel de red (Claude Code no tiene cuenta de Google); la autoriza el token de la empresa.
@https_fn.on_request(memory=options.MemoryOption.MB_512, timeout_sec=30, max_instances=20, cpu=1, concurrency=40,
                     invoker="public")
def ingesta(req: https_fn.Request) -> https_fn.Response:
    """Telemetría OTLP/JSON de Claude Code: costo de cada llamada, en vivo."""
    return http.ingesta_otlp(req)


@https_fn.on_call(memory=options.MemoryOption.GB_1, timeout_sec=120, secrets=[CLAVE_CIFRADO])
def app(req: https_fn.CallableRequest):
    """Acciones del panel. El navegador llama con {accion, ...}."""
    if req.auth is None:
        raise https_fn.HttpsError(https_fn.FunctionsErrorCode.UNAUTHENTICATED, "Inicia sesión.")
    token = req.auth.token or {}
    sesion = acciones.Sesion(req.auth.uid, token.get("email"), bool(token.get("email_verified")))
    resultado, error = acciones.ejecutar(sesion, req.data if isinstance(req.data, dict) else {})
    if error:
        raise https_fn.HttpsError(getattr(https_fn.FunctionsErrorCode, error[0]), error[1])
    return resultado


@firestore_fn.on_document_written(document="organizaciones/{org}/estado/caso", memory=options.MemoryOption.GB_1,
                                  timeout_sec=120)
def recalcular_plan(event: firestore_fn.Event[firestore_fn.Change[firestore_fn.DocumentSnapshot | None]]) -> None:
    """Cada vez que la empresa cambia sus datos, el plan se recalcula solo."""
    from aplicacion import planes

    despues = event.data.after
    if despues is None or not despues.exists:
        return
    r = contexto.repo()
    planes.recalcular(r, contexto.reloj(), event.params["org"], despues.to_dict())


@scheduler_fn.on_schedule(schedule="5 * * * *", memory=options.MemoryOption.GB_1, timeout_sec=540)
def cierre_mensual(event: scheduler_fn.ScheduledEvent) -> None:
    """Cada hora: cierra el mes de las empresas en las que, en SU zona horaria, ya empezó el siguiente.

    Cierra un mes por empresa y por ejecución: el plan del mes nuevo lo recalcula el disparador, y
    si quedaron varios meses atrasados se ponen al día en las horas siguientes.
    """
    from aplicacion import planes
    from dominio.cierre import meses_por_cerrar

    r = contexto.repo()
    ahora = contexto.reloj().ahora()
    for org in r.ids():
        try:
            seg = r.leer_seguimiento(org) or {}
            pendientes = meses_por_cerrar(seg.get("mes"), ahora, (r.leer(org) or {}).get("zona"))
            if pendientes:
                planes.cerrar(r, r, contexto.reloj(), org, pendientes[0])
        except Exception as e:  # una empresa con datos rotos no frena a las demás
            print(f"cierre_mensual: {org}: {e}")


@scheduler_fn.on_schedule(schedule="20 * * * *", memory=options.MemoryOption.MB_512, timeout_sec=540,
                          secrets=[CLAVE_CIFRADO])
def sincronizar_fuentes(event: scheduler_fn.ScheduledEvent) -> None:
    """Cada hora trae el gasto de Cursor y OpenAI; cada 3 horas, lo facturado por Anthropic."""
    r = contexto.repo()
    cada_3h = contexto.reloj().ahora().hour % 3 == 0
    for org in r.ids():
        datos = r.leer(org) or {}
        for servicio in ("cursor", "openai") + (("anthropic",) if cada_3h else ()):
            if (datos.get(servicio) or {}).get("conectado"):
                try:
                    acciones.sincronizar_servicio(org, servicio)
                except Exception as e:
                    print(f"sincronizar_fuentes: {org} {servicio}: {e}")
