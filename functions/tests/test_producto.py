"""Pruebas de la capa de aplicación con repositorios en memoria: sin Firebase ni red."""

import json
from collections import defaultdict
from datetime import datetime, timezone

import pytest

from aplicacion import ingesta, organizaciones, planes
from aplicacion.puertos import DatosInvalidos, NoAutorizado
from dominio.cierre import normalizar_caso
from dominio.consumo import EventoConsumo, clave_persona, eventos_desde_otlp, nivel_alerta, periodo


class Reloj:
    def __init__(self, t=datetime(2026, 11, 20, 15, tzinfo=timezone.utc)):
        self.t = t

    def ahora(self):
        return self.t


class Cifrador:
    def cifrar(self, t):
        return "x" + t[::-1]

    def descifrar(self, c):
        return c[1:][::-1]


class Memoria:
    """Implementa los tres repositorios en diccionarios."""

    def __init__(self):
        self.orgs, self.inv, self.tokens, self.secretos = {}, defaultdict(dict), {}, defaultdict(dict)
        self.estado, self.hist = defaultdict(dict), defaultdict(dict)
        self.eventos, self.gasto, self.alertas, self.api = set(), defaultdict(dict), {}, {}
        self.n = 0

    # organizaciones
    def crear(self, d):
        self.n += 1
        self.orgs[f"o{self.n}"] = dict(d)
        return f"o{self.n}"

    def leer(self, o):
        return self.orgs.get(o)

    def actualizar(self, o, c):
        self.orgs[o].update(c)

    def ids(self):
        return list(self.orgs)

    def invitaciones_de(self, e):
        return dict(self.inv[e])

    def guardar_invitacion(self, e, o, rol):
        if rol is None:
            self.inv[e].pop(o, None)
        else:
            self.inv[e][o] = rol

    def guardar_token(self, h, d):
        self.tokens[h] = dict(d)

    def leer_token(self, h):
        return self.tokens.get(h)

    def tokens_de(self, o):
        return [{"huella": h, **d} for h, d in self.tokens.items() if d["org"] == o]

    def revocar_token(self, h):
        self.tokens[h]["revocado"] = True

    def guardar_secreto(self, o, n, c):
        self.secretos[o][n] = c

    def leer_secreto(self, o, n):
        return self.secretos[o].get(n)

    # planes
    def leer_caso(self, o):
        return self.estado[o].get("caso")

    def guardar_caso(self, o, c):
        self.estado[o]["caso"] = json.loads(json.dumps(c))

    def leer_seguimiento(self, o):
        return self.estado[o].get("seguimiento")

    def guardar_seguimiento(self, o, s):
        self.estado[o]["seguimiento"] = dict(s)

    def leer_plan(self, o):
        return self.estado[o].get("plan")

    def guardar_plan(self, o, d):
        self.estado[o]["plan"] = d

    def agregar_historial(self, o, h):
        self.hist[o][h["mes"]] = h

    # consumo
    def registrar(self, o, mes, filas):
        tocadas = set()
        for ev, clave, dia in filas:
            if (o, ev.id) in self.eventos:
                continue
            self.eventos.add((o, ev.id))
            g = self.gasto[(o, mes)].setdefault(clave, {"usd": 0.0, "porDia": defaultdict(float), "email": ev.email})
            g["usd"] += ev.usd
            g["porDia"][dia] += ev.usd
            tocadas.add(clave)
        return sorted(tocadas)

    def gasto_de(self, o, mes):
        return self.gasto[(o, mes)]

    def crear_alerta(self, o, i, d):
        if (o, i) in self.alertas:
            return False
        self.alertas[(o, i)] = d
        return True

    def guardar_gasto_api(self, o, mes, d):
        self.api[(o, mes)] = d

    def guardar_externo(self, o, mes, herramienta, filas):
        for clave, f in filas.items():
            g = self.gasto[(o, mes)].setdefault(clave, {"usd": 0.0, "porDia": defaultdict(float), "email": f.get("email")})
            g.setdefault("externo", {})[herramienta] = f["usd"]


def otlp(*registros, recurso=None):
    def attrs(d):
        out = []
        for k, v in d.items():
            if isinstance(v, bool):
                out.append({"key": k, "value": {"boolValue": v}})
            elif isinstance(v, int):
                out.append({"key": k, "value": {"intValue": str(v)}})
            elif isinstance(v, float):
                out.append({"key": k, "value": {"doubleValue": v}})
            else:
                out.append({"key": k, "value": {"stringValue": v}})
        return out
    return {"resourceLogs": [{"resource": {"attributes": attrs(recurso or {"service.name": "claude-code"})},
                              "scopeLogs": [{"logRecords": [{"timeUnixNano": "1763650800000000000",
                                                             "body": {"stringValue": "claude_code.api_request"},
                                                             "attributes": attrs(r)} for r in registros]}]}]}


@pytest.fixture
def mundo():
    m, reloj = Memoria(), Reloj()
    org = organizaciones.crear(m, m, reloj, "u1", "jefa@empresa.co", "Acme", con_ejemplo=True)
    caso = m.leer_caso(org)
    caso["personas"][0]["email"] = "ana@empresa.co"  # Ana, tope 360 en el caso base
    m.guardar_caso(org, caso)
    planes.recalcular(m, reloj, org, m.leer_caso(org))
    return m, reloj, org


# ---------------------------------------------------------------- dominio
def test_lee_eventos_de_costo_y_descarta_lo_demas():
    carga = otlp({"event.name": "api_request", "cost_usd": 0.42, "model": "claude-opus-5-5", "request_id": "r1",
                  "user.email": "Ana@Empresa.co", "input_tokens": 1200, "output_tokens": 300},
                 {"event.name": "user_prompt", "prompt_length": 12})
    evs = eventos_desde_otlp(carga)
    assert len(evs) == 1
    e = evs[0]
    assert (e.id, e.usd, e.email, e.modelo) == ("r1", 0.42, "ana@empresa.co", "claude-opus-5-5")
    assert e.tokens == {"entrada": 1200, "salida": 300}


def test_costo_en_micros_y_correo_en_el_recurso():
    carga = otlp({"event.name": "api_request", "cost_usd_micros": 1_500_000, "request_id": "r2"},
                 recurso={"user.email": "luis@empresa.co"})
    e = eventos_desde_otlp(carga)[0]
    assert e.usd == 1.5 and e.email == "luis@empresa.co"


def test_sin_request_id_la_huella_es_estable():
    reg = {"event.name": "api_request", "cost_usd": 0.1, "session.id": "s", "event.sequence": 7}
    assert eventos_desde_otlp(otlp(reg))[0].id == eventos_desde_otlp(otlp(reg))[0].id


def test_persona_por_correo_y_sin_asignar():
    ps = [{"id": "p1", "email": "ana@empresa.co"}]
    assert clave_persona("ana@empresa.co", ps) == "p1"
    assert clave_persona("otro@empresa.co", ps).startswith("correo-")
    assert clave_persona(None, ps) == "sin-correo"


def test_periodo_en_hora_de_bogota():
    # 1 de diciembre 03:00 UTC = 30 de noviembre 22:00 en Bogotá
    assert periodo(datetime(2026, 12, 1, 3, tzinfo=timezone.utc)) == ("2026-11", "30")


def test_umbrales_de_alerta():
    assert [nivel_alerta(g, 100) for g in (50, 80, 99, 100, 150)] == [0, 80, 80, 100, 100]


def test_normalizar_caso_limpia_lo_que_manda_el_navegador():
    c = normalizar_caso({"personas": [{"nombre": " Ana ", "salario": "-5", "herramienta": "X"},
                                      {"nombre": "Ana", "salario": 1000}], "reglas": {"minimo": 1e12}})
    assert [p["nombre"] for p in c["personas"]] == ["Ana", "Ana 2"]
    assert c["personas"][0]["salario"] == 0 and c["personas"][0]["herramienta"] == "Ninguna"
    assert c["reglas"]["minimo"] == 1e6
    with pytest.raises(ValueError):
        normalizar_caso({"personas": []})


# ---------------------------------------------------------------- aplicación
def test_crear_empresa_deja_plan_calculado(mundo):
    m, _, org = mundo
    plan = m.leer_plan(org)
    assert plan["error"] is None and plan["version"] == 1
    assert json.loads(plan["resultado"])["resultado"]["factura"] > 0
    assert m.leer(org)["roles"] == {"u1": "admin"}


def test_plan_viejo_no_pisa_al_nuevo(mundo):
    m, reloj, org = mundo
    caso = m.leer_caso(org)
    planes.recalcular(m, reloj, org, {**caso, "version": 5})
    planes.recalcular(m, reloj, org, {**caso, "version": 3})
    assert m.leer_plan(org)["version"] == 5


def test_datos_malos_guardan_el_error_y_conservan_el_plan(mundo):
    m, reloj, org = mundo
    anterior = m.leer_plan(org)["resultado"]
    planes.recalcular(m, reloj, org, {"personas": [], "version": 2})
    doc = m.leer_plan(org)
    assert doc["error"] and doc["resultado"] == anterior


def test_token_de_ingesta(mundo):
    m, reloj, org = mundo
    t = organizaciones.crear_token(m, reloj, org, "u1", "Laptops de la empresa")
    assert organizaciones.autorizar_token(m, t["token"]) == org
    assert t["token"] not in json.dumps(m.tokens, default=str)  # solo se guarda la huella
    organizaciones.revocar_token(m, org, "u1", t["id"])
    with pytest.raises(NoAutorizado):
        organizaciones.autorizar_token(m, t["token"])
    with pytest.raises(NoAutorizado):
        organizaciones.crear_token(m, reloj, org, "intruso", "x")


def test_ingesta_suma_una_sola_vez_y_alerta(mundo):
    m, reloj, org = mundo
    evs = [EventoConsumo(id=f"r{i}", usd=100.0, modelo="claude-opus-5-5", momento=reloj.t,
                         email="ana@empresa.co") for i in range(3)]
    r = ingesta.registrar(m, m, m, reloj, org, evs)
    assert r["recibidos"] == 3
    ingesta.registrar(m, m, m, reloj, org, evs)  # reintento del exportador
    assert m.gasto_de(org, "2026-11")["p1"]["usd"] == 300.0
    niveles = sorted(a["nivel"] for (o, _), a in m.alertas.items() if o == org)
    assert niveles == [80]  # 300 de 360
    ingesta.registrar(m, m, m, reloj, org, [EventoConsumo("r9", 70.0, "x", reloj.t, "ana@empresa.co")])
    assert sorted(a["nivel"] for a in m.alertas.values()) == [80, 100]


def test_gasto_de_correo_desconocido_queda_sin_asignar(mundo):
    m, reloj, org = mundo
    ingesta.registrar(m, m, m, reloj, org, [EventoConsumo("z1", 5.0, "x", reloj.t, "nuevo@empresa.co")])
    claves = list(m.gasto_de(org, "2026-11"))
    assert len(claves) == 1 and claves[0].startswith("correo-")
    assert not m.alertas


def test_cerrar_mes_usa_el_gasto_real(mundo):
    m, reloj, org = mundo
    ingesta.registrar(m, m, m, reloj, org, [EventoConsumo("c1", 123.0, "x", reloj.t, "ana@empresa.co")])
    seg = m.leer_seguimiento(org)
    seg["manual"] = {"p2": 40}
    m.guardar_seguimiento(org, seg)
    h = planes.cerrar(m, m, reloj, org, "2026-11")
    assert h["mes"] == "2026-11" and h["porPersona"]["p1"] == 123.0 and h["porPersona"]["p2"] == 40
    caso = m.leer_caso(org)
    assert caso["personas"][0]["gasto"] == 123.0 and caso["version"] == 2
    assert m.leer_seguimiento(org)["mes"] == "2026-12"
    assert planes.cerrar(m, m, reloj, org, "2026-11") is None  # ya estaba cerrado


def test_invitar_y_aceptar(mundo):
    m, _, org = mundo
    organizaciones.invitar(m, org, "u1", "Luis@Empresa.co", "lector")
    assert organizaciones.aceptar_invitaciones(m, "u2", "luis@empresa.co", verificado=False) == []
    assert organizaciones.aceptar_invitaciones(m, "u2", "luis@empresa.co", verificado=True) == [org]
    o = m.leer(org)
    assert o["roles"]["u2"] == "lector" and "u2" in o["miembrosUid"] and not o["invitados"]
    with pytest.raises(NoAutorizado):
        organizaciones.invitar(m, org, "u2", "x@y.co", "admin")  # un lector no invita
    with pytest.raises(DatosInvalidos):
        organizaciones.invitar(m, org, "u1", "no-es-correo", "admin")


class FuenteFalsa:
    def costo_por_actor(self, clave, desde, hasta):
        assert clave == "sk-ant-admin-123"
        return {"filas": [{"email": "ana@empresa.co", "usuario": "user_1", "modelo": "claude-opus-5-5", "usd": 12.5},
                          {"email": None, "usuario": "apikey_9", "modelo": "claude-haiku-5-5", "usd": 1.0}],
                "datos_hasta": "2026-11-20T10:00:00Z"}


def test_conciliacion_con_anthropic(mundo):
    m, reloj, org = mundo
    with pytest.raises(DatosInvalidos):
        organizaciones.guardar_clave_anthropic(m, Cifrador(), org, "u1", "sk-ant-api-normal")
    organizaciones.guardar_clave_anthropic(m, Cifrador(), org, "u1", "sk-ant-admin-123")
    assert m.leer_secreto(org, "anthropic_admin") != "sk-ant-admin-123"
    d = ingesta.sincronizar_anthropic(m, m, m, reloj, Cifrador(), FuenteFalsa(), org)
    assert d["total"] == 13.5 and d["porPersona"]["p1"]["usd"] == 12.5
    assert "api-apikey_9" in d["porPersona"]


def test_gasto_previo_de_un_correo_pasa_a_la_persona_al_agregarla(mundo):
    m, reloj, org = mundo
    ingesta.registrar(m, m, m, reloj, org, [EventoConsumo("n1", 30.0, "x", reloj.t, "nuevo@empresa.co")])
    caso = m.leer_caso(org)
    caso["personas"].append({"id": "p99", "nombre": "Nuevo", "email": "nuevo@empresa.co", "equipo": "Backend",
                             "salario": 2000, "gasto": 0, "herramienta": "Claude"})
    caso["version"] += 1
    m.guardar_caso(org, caso)
    planes.recalcular(m, reloj, org, caso)
    h = planes.cerrar(m, m, reloj, org)
    assert h["porPersona"]["p99"] == 30.0


# ---------------------------------------------------------------- otras herramientas
from dominio.cierre import meses_por_cerrar, zona_valida  # noqa: E402
from dominio.consumo import repartir, total_fila  # noqa: E402
from dominio.precios import costo_gemini, precio_gemini  # noqa: E402


def gemini(**extra):
    reg = {"event.name": "gemini_cli.api_response", "model": "gemini-2.5-pro", "input_token_count": 1_000_000,
           "output_token_count": 100_000, "cached_content_token_count": 200_000, "thoughts_token_count": 50_000,
           "prompt_id": "p1", "session.id": "s1", **extra}
    return otlp(reg, recurso={"service.name": "gemini-cli", "user.email": "Carla@Empresa.co"})


def test_gemini_cli_se_lee_y_se_le_calcula_el_costo():
    e = eventos_desde_otlp(gemini())[0]
    # (1M - 200k) × 1,25 + 200k × 0,125 + (100k + 50k) × 10, por millón
    assert e.origen == "gemini_cli" and e.herramienta == "gemini" and e.email == "carla@empresa.co"
    assert e.usd == pytest.approx(1.0 + 0.025 + 1.5)
    assert eventos_desde_otlp(gemini())[0].id == e.id  # un reintento no se cuenta dos veces


def test_modelo_gemini_desconocido_no_subestima():
    (pin, pout, _), conocido = precio_gemini("gemini-9-ultra")
    assert not conocido and pin >= 2.0 and pout >= 12.0
    assert costo_gemini("gemini-2.5-flash", 1_000_000, 0) == pytest.approx(0.30)


def test_protobuf_da_lo_mismo_que_json():
    from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest

    from interfaz.http import _logs_desde_protobuf

    req = ExportLogsServiceRequest()
    lr = req.resource_logs.add().scope_logs.add().log_records.add()
    lr.time_unix_nano = 1763650800000000000
    for k, v in {"event.name": "api_request", "request_id": "pb1", "user.email": "ana@empresa.co"}.items():
        a = lr.attributes.add(); a.key = k; a.value.string_value = v
    a = lr.attributes.add(); a.key = "cost_usd"; a.value.double_value = 0.75
    e = eventos_desde_otlp(_logs_desde_protobuf(req.SerializeToString()))[0]
    assert (e.id, e.usd, e.email) == ("pb1", 0.75, "ana@empresa.co")


def test_total_suma_telemetria_y_herramientas_externas():
    fila = {"usd": 10.0, "externo": {"cursor": 5.5, "openai": 2.0}}
    assert total_fila(fila) == 17.5
    assert repartir([{"id": "p1", "email": "a@b.co"}], {"correo-x": {"email": "a@b.co", **fila}}) == {"p1": 17.5}


class FuenteTabla:
    def __init__(self, filas):
        self.filas, self.llamadas = filas, 0

    def gasto_por_persona(self, clave, desde, hasta):
        self.llamadas += 1
        assert clave == "clave-cursor-1234567890" and desde < hasta
        return {"filas": self.filas, "periodo": "ciclo"}


def test_sincronizar_cursor_reemplaza_y_no_suma_de_mas(mundo):
    m, reloj, org = mundo
    organizaciones.guardar_clave(m, Cifrador(), org, "u1", "cursor", "clave-cursor-1234567890")
    f = FuenteTabla([{"email": "ana@empresa.co", "usuario": "user_1", "usd": 200.0},
                     {"email": "otra@empresa.co", "usuario": "user_2", "usd": 9.0}])
    ingesta.sincronizar_fuente(m, m, m, reloj, Cifrador(), f, org, "cursor")
    ingesta.sincronizar_fuente(m, m, m, reloj, Cifrador(), f, org, "cursor")  # la hora siguiente
    assert repartir(m.leer_caso(org)["personas"], m.gasto_de(org, "2026-11"))["p1"] == 200.0
    assert m.leer(org)["cursor"]["total"] == 209.0 and not m.leer(org)["cursor"]["error"]
    # Claude + Cursor juntos cruzan el 80 % del tope de Ana (360)
    ingesta.registrar(m, m, m, reloj, org, [EventoConsumo("c9", 100.0, "x", reloj.t, "ana@empresa.co")])
    assert any(a["nivel"] == 80 for a in m.alertas.values())


def test_error_de_la_fuente_queda_en_la_empresa(mundo):
    m, reloj, org = mundo
    organizaciones.guardar_clave(m, Cifrador(), org, "u1", "openai", "sk-admin-abcdefghijklmnop")

    class Rota:
        def gasto_por_persona(self, *a):
            raise RuntimeError("HTTP 401: clave inválida")

    assert ingesta.sincronizar_fuente(m, m, m, reloj, Cifrador(), Rota(), org, "openai") is None
    assert "401" in m.leer(org)["openai"]["error"]
    with pytest.raises(DatosInvalidos):
        organizaciones.guardar_clave(m, Cifrador(), org, "u1", "openai", "no-es-clave")


def test_cierre_segun_la_zona_de_cada_empresa():
    # 1 de diciembre 03:00 UTC: en Madrid ya es diciembre; en Bogotá todavía es 30 de noviembre
    ahora = datetime(2026, 12, 1, 3, tzinfo=timezone.utc)
    assert meses_por_cerrar("2026-11", ahora, "Europe/Madrid") == ["2026-11"]
    assert meses_por_cerrar("2026-11", ahora, "America/Bogota") == []
    assert meses_por_cerrar("2026-11", datetime(2026, 12, 1, 5, 5, tzinfo=timezone.utc), "America/Bogota") == ["2026-11"]
    assert meses_por_cerrar("2026-09", ahora, "Asia/Tokyo") == ["2026-09", "2026-10", "2026-11"]
    assert zona_valida("Marte/Olympus") == "America/Bogota"


def test_cambiar_zona_horaria(mundo):
    m, _, org = mundo
    organizaciones.actualizar_empresa(m, org, "u1", None, "Europe/Madrid")
    assert m.leer(org)["zona"] == "Europe/Madrid"
    with pytest.raises(DatosInvalidos):
        organizaciones.actualizar_empresa(m, org, "u1", None, "Marte/Olympus")
    with pytest.raises(NoAutorizado):
        organizaciones.actualizar_empresa(m, org, "intruso", "X", None)


def test_adaptadores_de_cursor_y_openai(monkeypatch):
    from infraestructura import externos

    pedidos = []

    def falso(url, cab, cuerpo=None, metodo="GET", tiempo=30.0):
        pedidos.append((url, cab, cuerpo, metodo))
        if "cursor" in url:
            return {"teamMemberSpend": [{"email": "Ana@Empresa.co", "userId": "user_1", "overallSpendCents": 12345.5,
                                         "spendCents": 100}], "totalPages": 1, "subscriptionCycleStart": 1762000000000}
        if "/costs" in url:
            return {"data": [{"results": [{"amount": {"value": 4.5, "currency": "usd"}, "user_id": "user-a"}]},
                             {"results": [{"amount": {"value": 1.5, "currency": "usd"}, "user_id": "user-a"}]}],
                    "has_more": False}
        return {"data": [{"id": "user-a", "email": "Luis@Empresa.co"}], "has_more": False}

    monkeypatch.setattr(externos, "_pedir", falso)
    d, h = datetime(2026, 11, 1, tzinfo=timezone.utc), datetime(2026, 11, 20, tzinfo=timezone.utc)
    c = externos.GastoCursor().gasto_por_persona("key_abc", d, h)
    assert c["filas"] == [{"email": "ana@empresa.co", "usuario": "user_1", "usd": 123.455}]
    assert pedidos[0][1]["Authorization"].startswith("Basic ") and pedidos[0][3] == "POST"
    o = externos.GastoOpenAI().gasto_por_persona("sk-admin-x", d, h)
    assert o["filas"] == [{"email": "luis@empresa.co", "usuario": "user-a", "usd": 6.0}]
    assert "group_by=user_id" in pedidos[1][0] and pedidos[1][1]["Authorization"] == "Bearer sk-admin-x"
