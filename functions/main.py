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


@scheduler_fn.on_schedule(schedule="5 0 1 * *", timezone=scheduler_fn.Timezone("America/Bogota"),
                          memory=options.MemoryOption.GB_1, timeout_sec=540)
def cierre_mensual(event: scheduler_fn.ScheduledEvent) -> None:
    """El día 1 cierra el mes anterior de cada empresa y deja listo el plan del nuevo."""
    from aplicacion import planes
    from dominio.cierre import siguiente_mes

    r = contexto.repo()
    ahora = contexto.reloj().ahora()
    for org in r.ids():
        seg = r.leer_seguimiento(org) or {}
        mes = seg.get("mes")
        # cierra todo mes anterior al actual (por si un cierre falló antes)
        while mes and siguiente_mes(mes) <= f"{ahora.year}-{ahora.month:02d}":
            try:
                if not planes.cerrar(r, r, contexto.reloj(), org, mes):
                    break
            except Exception as e:  # una empresa con datos rotos no frena a las demás
                print(f"cierre_mensual: {org} {mes}: {e}")
                break
            mes = siguiente_mes(mes)


@scheduler_fn.on_schedule(schedule="every 3 hours", memory=options.MemoryOption.MB_512, timeout_sec=540,
                          secrets=[CLAVE_CIFRADO])
def conciliar_anthropic(event: scheduler_fn.ScheduledEvent) -> None:
    """Trae lo facturado por Anthropic de las empresas que conectaron su clave de administración."""
    from aplicacion import ingesta as casos

    r = contexto.repo()
    for org in r.ids():
        datos = r.leer(org) or {}
        if (datos.get("anthropic") or {}).get("conectado"):
            casos.sincronizar_anthropic(r, r, r, contexto.reloj(), contexto.cifrador(), contexto.fuente_anthropic(), org)
