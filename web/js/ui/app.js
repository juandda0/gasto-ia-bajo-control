/* Capa de interfaz: pantallas de la empresa. Los datos llegan en vivo desde Firestore (capa de
   datos); el plan lo calcula el servidor cada vez que cambian los datos; el gasto de Claude Code
   llega solo. Aquí solo se pinta y se reacciona a lo que hace la persona.
   Todos los textos pasan por t() (español → inglés). */
import { accion, alCambiarSesion, entrarConGoogle, salir, URL_INGESTA, LOCAL } from "../datos/firebase.js";
import { escucharEmpresa, escucharMisEmpresas, guardarCaso, guardarSeguimiento } from "../datos/repositorio.js";
import { diaDelMes, diasDe, leerCsv, nombreMes as nombreMesEs, PLANTILLA_CSV, repartirGasto } from "../dominio/seguimiento.js";
import { cambiarIdioma, cambiarTema, lang, locale, t, temaActual } from "./preferencias.js";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const fmt = (v, d = 0) => Number(v).toLocaleString(locale(), { minimumFractionDigits: d, maximumFractionDigits: d });
const usd = (v, d = 0) => `${fmt(v, d)} USD`;
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const nombreMes = m => nombreMesEs(m, locale());
const mesCorto = m => nombreMes(m).split(" ")[0];
const quieto = matchMedia("(prefers-reduced-motion: reduce)").matches;
const HERRAMIENTAS = ["Claude", "Cursor", "OpenAI", "Gemini", "Ninguna"];
const nombreHerramienta = h => (h === "Ninguna" ? t("Ninguna") : h);
const COLOR_AVATAR = ["#ff9ec0", "#ffd08a", "#a6ffc9", "#9fdcff", "#cdb2ff", "#ffb8a0"];
const CLAVE_ORG = "gia-org";
const leerLocal = k => { try { return localStorage.getItem(k); } catch (_) { return null; } };
const guardarLocal = (k, v) => { try { localStorage.setItem(k, v); } catch (_) { /* sin almacenamiento */ } };
const plural = (n, uno, varios) => (n === 1 ? t(uno, { n }) : t(varios, { n }));

const G = {
  usuario: null, empresas: null, org: null, empresa: null, admin: false,
  caso: null, seg: null, plan: null, gasto: { mes: null, personas: {} }, hist: [], alertas: [], conciliacion: null, tokens: [],
  vista: "panel", confirmarCierre: false, tokenNuevo: null, pendienteRender: false, escucha: null, ocupado: false,
};
const rr = () => G.plan && G.plan.resultado;           // último plan calculado
const calculando = () => !!G.caso && (!G.plan || (G.plan.version || 0) < (G.caso.version || 0));
const errorPlan = () => (G.plan && !calculando() ? G.plan.error : null);
const zona = () => (G.empresa && G.empresa.zona) || "America/Bogota";
const conectado = () => G.tokens.some(x => !x.revocado) || Object.keys(G.gasto.personas || {}).length > 0;

/* ------------------------------------------------------------ guardar (en Firestore) */
let tCaso = null, tSeg = null;
function programar() {
  clearTimeout(tCaso);
  G.caso.version = (G.caso.version || 0) + 1;
  G.caso.ejemplo = false;
  pintarEstado();
  tCaso = setTimeout(() => {
    tCaso = null;
    guardarCaso(G.org, JSON.parse(JSON.stringify(G.caso))).catch(e => aviso(t("No se guardó: {e}", { e: e.message }), true));
  }, 650);
}
function guardarSeg() {
  clearTimeout(tSeg);
  tSeg = setTimeout(() => guardarSeguimiento(G.org, G.seg).catch(e => aviso(t("No se guardó: {e}", { e: e.message }), true)), 400);
}
let siguienteId = 1;
const conId = p => (p.id ? p : { ...p, id: `p${siguienteId++}` });
const ajustarIds = () => G.caso.personas.forEach(p => { const k = parseInt(String(p.id || "").replace(/\D/g, ""), 10); if (k >= siguienteId) siguienteId = k + 1; });

async function descargarExcel() {
  try {
    const { archivo } = await accion("exportarExcel", { org: G.org });
    const bytes = Uint8Array.from(atob(archivo), c => c.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: "plan-gasto-ia.xlsx" });
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    aviso(t("Excel descargado."));
  } catch (e) { aviso(t(e.message), true); }
}

/* ------------------------------------------------------------ efectos sobrios */
function aviso(texto, error = false) {
  const el = $("#aviso");
  el.textContent = texto;
  el.classList.toggle("error", error);
  el.classList.add("ver");
  clearTimeout(aviso.t);
  aviso.t = setTimeout(() => el.classList.remove("ver"), 3200);
}
function contar(raiz = document) {
  $$("[data-contar]", raiz).forEach(el => {
    const fin = parseFloat(el.dataset.contar), dec = +(el.dataset.dec || 0), desde = parseFloat(el.dataset.desde || fin);
    if (quieto || desde === fin) { el.textContent = fmt(fin, dec); return; }
    const t0 = performance.now(), dur = 700;
    const paso = ahora => {
      const k = Math.min(1, (ahora - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      el.textContent = fmt(desde + (fin - desde) * e, dec);
      if (k < 1) requestAnimationFrame(paso);
    };
    requestAnimationFrame(paso);
  });
}
function hace(fecha) {
  if (!fecha) return t("nunca");
  const s = Math.max(0, (Date.now() - fecha.getTime()) / 1000);
  if (s < 60) return t("hace segundos");
  if (s < 3600) return t("hace {n} min", { n: Math.round(s / 60) });
  if (s < 86400) return t("hace {n} h", { n: Math.round(s / 3600) });
  return fecha.toLocaleDateString(locale(), { day: "numeric", month: "short" });
}
const fechaDe = ts => (ts && ts.toDate ? ts.toDate() : ts ? new Date(ts) : null);

/* ------------------------------------------------------------ datos derivados */
const P = () => rr().datos.personas;
const asig = nombre => rr().modelo0.asignacion.find(a => a.persona === nombre);
const topes = () => (G.seg && G.seg.recorte ? rr().recorte.modelo1.topes : rr().modelo1.topes);
const iniciales = n => String(n || "?").split(/\s+/).map(x => x[0] || "").join("").slice(0, 2).toUpperCase();
const colorDe = id => COLOR_AVATAR[(parseInt(String(id).replace(/\D/g, ""), 10) || 0) % COLOR_AVATAR.length];
const reparto = () => repartirGasto(G.caso ? G.caso.personas : [], G.gasto.mes === (G.seg && G.seg.mes) ? G.gasto.personas : {});
const diaSeg = () => diaDelMes(G.seg.mes, zona());
function gastoDe(id, R = reparto()) {
  const auto = R.porId[id] || 0, man = G.seg.manual?.[id];
  const tiene = auto > 0 || (man != null && man !== "");
  return { auto, manual: Number(man) || 0, total: auto + (Number(man) || 0), tiene };
}
function donde(p, plan) {
  if (!plan) return "";
  if (plan.plan !== "Solo API") return t("{plan} · límite en su panel", { plan: plan.plan });
  return p.herramienta === "Ninguna" ? t("Pago por uso · la API que elija") : t("Pago por uso · API de {h}", { h: p.herramienta });
}
const nombrePlan = plan => (plan === "Solo API" ? t("Solo API") : plan);
function horas(r, nombre) {
  const h = r.datos.tramos.horas_por_dolar, g = r.modelo1.tramos[nombre] || [];
  return g.reduce((s, v, k) => s + v * h[k], 0);
}
function horasCon(r, uso) {
  const h = r.datos.tramos.horas_por_dolar, a = r.datos.tramos.ancho;
  let resto = uso, s = 0;
  a.forEach((w, k) => { const x = Math.min(resto, w); s += x * h[k]; resto -= x; });
  return s;
}
function flujoBatch() {
  const m2 = rr().modelo2, i = m2.origenes.indexOf("API en batch");
  if (i < 0) return { total: 0, equipos: [] };
  let total = 0; const eqs = [];
  m2.destinos.forEach((d, j) => { if (d !== "Ficticio" && m2.final.asignacion[i][j] > 1e-6) { total += m2.final.asignacion[i][j]; eqs.push(d); } });
  return { total, equipos: eqs };
}
const lista = (xs, max = 6) => xs.slice(0, max).join(", ") + (xs.length > max ? t(" y {n} más", { n: xs.length - max }) : "");
const busqueda = p => esc(`${p.nombre} ${p.email || ""} ${p.equipo}`.toLowerCase());
const buscador = (n, donde) => (n > 8 ? `<label class="campo buscar" data-libre><input type="search" placeholder="${esc(t("Buscar por nombre, correo o equipo"))}" data-buscar="${donde}" aria-label="${esc(t("Buscar persona"))}"></label>` : "");

/* ------------------------------------------------------------ acceso: entrar y elegir empresa */
function pantallaEntrar() {
  return `<section class="pantalla acceso">
    <div class="tarjeta acceso-caja">
      <svg class="logo grande" viewBox="0 0 24 24" aria-hidden="true"><path class="logo-signo" d="M18 4 6.5 9.75 18 15.5"/><path class="logo-tope" d="M6.5 20.5H18"/></svg>
      <h1>${t("Cuánto gasta tu empresa en IA, en vivo")}</h1>
      <p>${t("Conecta Claude Code una vez y ve el gasto de cada persona mientras trabaja. El plan te dice qué asiento darle a cada uno y cuánto debería usar.")}</p>
      <button class="btn primario ancho" data-accion="entrar">${t("Entrar con Google")}</button>
      <small class="tenue">${t("Sin tarjeta. Tus datos solo los ve tu empresa.")}</small>
    </div>
  </section>`;
}
function pantallaNuevaEmpresa() {
  return `<section class="pantalla acceso">
    <form class="tarjeta acceso-caja" id="formEmpresa">
      <h1>${t("Crea el espacio de tu empresa")}</h1>
      <p>${t("Después invitas a tu equipo. Puedes empezar con datos de ejemplo y cambiarlos por los tuyos.")}</p>
      <label class="campo"><span>${t("Nombre de la empresa")}</span><input name="nombre" required maxlength="120" autocomplete="organization" placeholder="Acme S.A.S."></label>
      <label class="opcion"><input type="radio" name="ejemplo" value="si" checked> <span><b>${t("Con datos de ejemplo")}</b><small>${t("Seis programadores de muestra para ver cómo funciona.")}</small></span></label>
      <label class="opcion"><input type="radio" name="ejemplo" value="no"> <span><b>${t("En blanco")}</b><small>${t("Empiezas con tu propio equipo.")}</small></span></label>
      <button class="btn primario ancho" type="submit">${t("Crear empresa")}</button>
      ${G.usuario ? `<small class="tenue">${t("Entraste como {e}", { e: esc(G.usuario.email) })} · <a href="#" data-accion="salir">${t("salir")}</a></small>` : ""}
    </form>
  </section>`;
}

/* ------------------------------------------------------------ pantalla: datos */
function campoNumero(id, campo, etq, valor, sufijo = "USD") {
  return `<label class="campo"><span>${etq}</span><span class="con-sufijo"><input type="number" inputmode="decimal" min="0" step="10" data-id="${id}" data-campo="${campo}" value="${esc(valor)}"><b>${sufijo}</b></span></label>`;
}
const opcionesHerramienta = actual => HERRAMIENTAS.map(h => `<option value="${h}" ${h === actual ? "selected" : ""}>${nombreHerramienta(h)}</option>`).join("");
function tarjetaPersona(p) {
  return `<div class="tarjeta persona" data-tarjeta="${p.id}" data-busqueda="${busqueda(p)}">
    <div class="cab">
      <span class="avatar" style="background:${colorDe(p.id)}">${esc(iniciales(p.nombre))}</span>
      <label class="campo"><input data-id="${p.id}" data-campo="nombre" value="${esc(p.nombre)}" placeholder="${esc(t("Nombre"))}" aria-label="${esc(t("Nombre"))}" autocomplete="off"></label>
      <button class="btn fantasma icono" data-quitar="${p.id}" aria-label="${esc(t("Quitar a {n}", { n: p.nombre || t("esta persona") }))}" title="${esc(t("Quitar"))}" data-solo-admin>✕</button>
    </div>
    <label class="campo"><span>${t("Correo con el que usa Claude")}</span><input type="email" data-id="${p.id}" data-campo="email" value="${esc(p.email || "")}" placeholder="${esc(t("nombre@empresa.com"))}" autocomplete="off"></label>
    <div class="rejilla">
      <label class="campo"><span>${t("Equipo")}</span><input data-id="${p.id}" data-campo="equipo" value="${esc(p.equipo)}" list="equipos" autocomplete="off"></label>
      <label class="campo"><span>${t("Herramienta que usa")}</span><select data-id="${p.id}" data-campo="herramienta">${opcionesHerramienta(p.herramienta)}</select></label>
      ${campoNumero(p.id, "salario", t("Salario al mes"), p.salario)}
      ${campoNumero(p.id, "gasto", t("Gastó en IA el mes pasado"), p.gasto)}
    </div>
  </div>`;
}
function resumenDatos() {
  const ps = G.caso.personas, nom = ps.reduce((s, p) => s + (Number(p.salario) || 0), 0), gas = ps.reduce((s, p) => s + (Number(p.gasto) || 0), 0);
  return `<span>${plural(ps.length, "<b>{n}</b> persona", "<b>{n}</b> personas")}</span><span>${t("Nómina")} <b>${usd(nom)}</b></span><span>${t("Gastaron en IA")} <b>${usd(gas)}</b>${nom ? ` · ${t("{p} % de la nómina", { p: fmt((gas / nom) * 100, 1) })}` : ""}</span>`;
}
function deslizador(id, etq, valor, min, max, paso, formato, ayuda) {
  return `<div class="rango"><label for="${id}">${etq} <b id="${id}-v">${formato(valor)}</b></label><input id="${id}" type="range" min="${min}" max="${max}" step="${paso}" value="${valor}">${ayuda ? `<small>${ayuda}</small>` : ""}</div>`;
}
const fPres = v => t("{p} % de la nómina", { p: fmt(v, 1) });
const fTope = v => t("{p} % del salario", { p: fmt(v) });
function pantallaDatos() {
  const reg = G.caso.reglas, eqs = [...new Set(G.caso.personas.map(x => x.equipo).filter(Boolean))];
  return `<section class="pantalla">
    <div class="titulo">
      <h1>${t("Tu equipo y lo que gastó en IA el mes pasado")}</h1>
      <p>${t("Con el salario, la herramienta y el gasto del mes pasado de cada programador armamos el plan. El correo sirve para asignarle a cada uno lo que gasta en Claude.")}</p>
      ${G.caso.ejemplo ? `<p style="margin-top:12px;font-size:13.5px"><span class="chip ojo">${t("Datos de ejemplo")}</span> ${t("Cámbialos por los tuyos o")} <a href="#" data-accion="vaciar">${t("empieza en blanco")}</a>.</p>` : ""}
    </div>
    <div class="barra-acciones" data-solo-admin>
      <button class="btn" data-accion="agregar">＋ ${t("Agregar programador")}</button>
      <label class="btn fantasma">${t("Importar CSV")}<input type="file" accept=".csv,text/csv" id="archivoCsv" hidden></label>
      <a class="btn fantasma" href="data:text/csv;charset=utf-8,${encodeURIComponent(PLANTILLA_CSV)}" download="plantilla-equipo.csv">${t("Plantilla")}</a>
    </div>
    ${buscador(G.caso.personas.length, "listaPersonas")}
    <div class="lista dos" id="listaPersonas">${G.caso.personas.map(tarjetaPersona).join("")}</div>
    <datalist id="equipos">${eqs.map(e => `<option value="${esc(e)}">`).join("")}</datalist>
    <div class="resumen-datos" id="resumenDatos">${resumenDatos()}</div>
    <div class="seccion">
      <details class="avanzado">
        <summary><span><b style="font-weight:600">${t("Reglas de la empresa")}</b><br><span class="tenue" style="font-size:13px">${t("Opcional · ya vienen con valores recomendados")}</span></span></summary>
        <div class="dentro">
          ${deslizador("rPres", t("Gasto extra máximo"), reg.presupuesto_pct_nomina * 100, 1, 15, 0.5, fPres, t("Lo que se paga aparte de las cuotas de los asientos."))}
          ${deslizador("rTope", t("Tope por persona"), reg.tope_pct_salario * 100, 5, 30, 1, fTope, t("Nadie usa más que esto en IA."))}
          ${deslizador("rMin", t("Mínimo por persona"), reg.minimo, 0, 150, 10, v => usd(v), t("Nadie se queda sin IA."))}
        </div>
      </details>
    </div>
    <div class="accion"><div class="dentro">
      <a class="btn primario ancho" href="#plan" id="verPlan">${t("Ver mi plan")} →</a>
      <div class="nota" id="notaEstado"></div>
    </div></div>
  </section>`;
}
function montarDatos() {
  const cont = $("#listaPersonas");
  cont.addEventListener("input", e => {
    const el = e.target.closest("[data-campo]"); if (!el) return;
    const p = G.caso.personas.find(x => x.id === el.dataset.id); if (!p) return;
    p[el.dataset.campo] = el.type === "number" ? (el.value === "" ? "" : Number(el.value)) : el.value;
    if (el.dataset.campo === "nombre") $(`[data-tarjeta="${p.id}"] .avatar`).textContent = iniciales(p.nombre);
    $(`[data-tarjeta="${p.id}"]`).dataset.busqueda = busqueda(p);
    $("#resumenDatos").innerHTML = resumenDatos();
    programar();
  });
  cont.addEventListener("change", e => { if (e.target.tagName === "SELECT") e.target.dispatchEvent(new Event("input", { bubbles: true })); });
  const unir = (id, aplicar, formato) => {
    const el = $(`#${id}`);
    el.addEventListener("input", () => { $(`#${id}-v`).textContent = formato(+el.value); });
    el.addEventListener("change", () => { aplicar(+el.value); programar(); });
  };
  unir("rPres", v => (G.caso.reglas.presupuesto_pct_nomina = v / 100), fPres);
  unir("rTope", v => (G.caso.reglas.tope_pct_salario = v / 100), fTope);
  unir("rMin", v => (G.caso.reglas.minimo = v), v => usd(v));
  const csv = $("#archivoCsv");
  if (csv) csv.addEventListener("change", async () => {
    const f = csv.files[0]; if (!f) return;
    if (f.size > 2e6) return aviso(t("El archivo es muy grande (máximo 2 MB)."), true);
    const nuevas = leerCsv(await f.text());
    if (!nuevas.length) return aviso(t("No encontré personas en ese CSV. Revisa que tenga encabezado (usa la plantilla)."), true);
    if (G.caso.ejemplo) G.caso.personas = [];
    let agregadas = 0, actualizadas = 0;
    for (const n of nuevas) {
      const ya = n.email && G.caso.personas.find(p => (p.email || "").toLowerCase() === n.email);
      if (ya) { Object.assign(ya, n); actualizadas++; } else { G.caso.personas.push(conId(n)); agregadas++; }
    }
    programar(); render(false);
    aviso(t("{a} agregadas, {b} actualizadas.", { a: agregadas, b: actualizadas }));
  });
}

/* ------------------------------------------------------------ pantalla: plan */
function tareasDelPlan() {
  const r = rr(), mes = G.seg.mes, ts = [];
  const grupos = {};
  r.modelo0.asignacion.forEach(a => { (grupos[a.plan] = grupos[a.plan] || []).push(a); });
  Object.entries(grupos).forEach(([plan, xs]) => {
    if (xs[0].cuota > 0) ts.push({ k: `asiento-${plan}`, b: plural(xs.length, "Contrata {n} asiento de {plan}", "Contrata {n} asientos de {plan}").replace("{plan}", plan), s: t("{c} al mes · para {quien}", { c: usd(xs[0].cuota * xs.length), quien: lista(xs.map(x => x.persona)) }) });
  });
  if (grupos["Solo API"]) ts.push({ k: "api", b: t("Deja a {quien} con pago por uso", { quien: lista(grupos["Solo API"].map(x => x.persona)) }), s: t("No les conviene un asiento: pagan solo lo que usan.") });
  ts.push({ k: "topes", b: t("Pon un límite de gasto a cada persona"), s: t("En el panel de cada herramienta. Los valores están en «Por persona».") });
  ts.push({ k: "conectar", b: t("Conecta Claude Code para ver el gasto en vivo"), s: t("Una sola configuración para toda la empresa, en Ajustes.") });
  const bt = flujoBatch();
  if (bt.total > 0) ts.push({ k: "batch", b: t("Manda {v} de trabajo que pueda esperar a la API en batch", { v: usd(bt.total) }), s: t("Pruebas, documentación o revisiones de la noche de {eq}: cuesta la mitad.", { eq: bt.equipos.join(t(" y ")) }) });
  const tp = r.modelo1.topes;
  const altos = P().filter(p => p.gasto - tp[p.nombre] > 0.5).map(p => p.nombre);
  if (altos.length) ts.push({ k: "altos", b: t("Habla con {quien}", { quien: lista(altos) }), s: t("El mes pasado gastaron más que su tope. Lo que recortan es lo que menos les rendía.") });
  const bajos = P().filter(p => tp[p.nombre] - p.gasto > 20).map(p => p.nombre);
  if (bajos.length) ts.push({ k: "bajos", b: t("Anima a {quien} a usar más la IA", { quien: lista(bajos) }), s: t("Tienen espacio y cada dólar ahí rinde más que en otros.") });
  return ts.map(x => ({ ...x, k: `${mes}:${x.k}`.replace(/[.~*/[\]]/g, "_") }));
}
function filaPlan(p) {
  const tp = rr().modelo1.topes[p.nombre], a = asig(p.nombre), dif = p.gasto - tp;
  const max = Math.max(tp, p.gasto, 1);
  const chip = dif > 0.5 ? `<span class="chip mal">${t("Bajar {v}", { v: usd(dif) })}</span>` : dif < -0.5 ? `<span class="chip bien">${t("Puede usar {v} más", { v: usd(-dif) })}</span>` : `<span class="chip ok">${t("Justo")}</span>`;
  const c = G.caso.personas.find(x => x.id === p.id) || p;
  return `<div class="tarjeta fila-persona" data-busqueda="${busqueda(c)}">
    <div class="arriba">
      <span class="avatar" style="background:${colorDe(p.id)}">${esc(iniciales(p.nombre))}</span>
      <div class="nombre"><b>${esc(p.nombre)}</b><span>${esc(donde(p, a))}</span></div>
      <div class="tope"><b>${usd(tp)}</b><span>${t("tope al mes")}</span></div>
    </div>
    <div class="barra" aria-label="${esc(t("Mes pasado {g} contra tope {t}", { g: usd(p.gasto), t: usd(tp) }))}"><i class="lleno ${dif > 0.5 ? "mal" : ""}" style="width:${(Math.min(p.gasto, max) / max) * 100}%"></i><i class="marca-tope" style="left:calc(${(tp / max) * 100}% - 1px)"></i></div>
    <div class="leyenda-barra"><span>${t("Mes pasado {v}", { v: usd(p.gasto) })}</span><span>${t("Tope {v}", { v: usd(tp) })}</span></div>
    <div class="linea-chips"><span class="chip plan">${esc(a ? nombrePlan(a.plan) : "")}</span>${chip}<button class="btn fantasma chico" data-editar="${p.id}" style="margin-left:auto" data-solo-admin>${t("Editar")}</button></div>
    <div class="editar" id="ed-${p.id}" hidden>
      <div class="rejilla">
        ${campoNumero(p.id, "gasto", t("Gastó el mes pasado"), c.gasto)}
        ${campoNumero(p.id, "salario", t("Salario al mes"), c.salario)}
        <label class="campo"><span>${t("Herramienta")}</span><select data-id="${p.id}" data-campo="herramienta">${opcionesHerramienta(c.herramienta)}</select></label>
        <label class="campo"><span>${t("Equipo")}</span><input data-id="${p.id}" data-campo="equipo" value="${esc(c.equipo)}"></label>
      </div>
    </div>
  </div>`;
}
function pantallaEspera() {
  const e = errorPlan();
  return `<section class="pantalla"><div class="titulo"><h1>${t("Tu plan")}</h1><p>${e ? `<span class="rojo">${esc(t(e))}</span>` : t("Calculando el plan…")}</p></div>${e ? `<a class="btn" href="#datos">${t("Revisar los datos")}</a>` : ""}</section>`;
}
function pantallaPlan() {
  if (!rr()) return pantallaEspera();
  const r = rr(), R = r.resultado, ahorro = R.factura_antes - R.factura, e = errorPlan();
  const hAhora = P().reduce((s, p) => s + horas(r, p.nombre), 0), hAntes = P().reduce((s, p) => s + horasCon(r, p.gasto), 0);
  const ps = r.modelo1.precio_sombra.presupuesto, rg = r.rango_presupuesto, reg = G.caso.reglas;
  const rec = r.recorte.modelo1, cambios = P().filter(p => Math.abs(rec.topes[p.nombre] - r.modelo1.topes[p.nombre]) > 0.5);
  const tareas = tareasDelPlan(), hechos = G.seg.hechos || {};
  const textoPresupuesto = ps > 0.005
    ? t("Subir el presupuesto <b>100 USD</b> te dejaría unos <b>{v}</b> más de valor neto. Vale mientras el gasto extra esté entre {a} y {b}.", { v: usd(ps * 100), a: usd(rg.desde), b: usd(rg.hasta) })
    : t("Ya tienes presupuesto de sobra: subirlo no aporta nada. Podrías bajar el gasto extra hasta <b>{v}</b> sin perder valor.", { v: usd(rg.desde) });
  return `<section class="pantalla">
    ${e ? `<p class="rojo" style="margin:0 0 12px">${esc(t(e))} ${t("Se muestra el último plan que sí se pudo calcular.")}</p>` : ""}
    <div class="columnas">
      <div class="col">
        <div class="tarjeta factura" id="factura"><div class="contenido">
          <div class="etq">${t("Factura de IA de {m}", { m: esc(nombreMes(G.seg.mes).toLowerCase()) })}</div>
          <div class="monto"><span data-contar="${R.factura}" data-desde="${pantallaPlan.ultima ?? R.factura}">${fmt(R.factura)}</span> <small>USD</small></div>
          <div class="tenue" style="font-size:13.5px">${t("antes {v}", { v: usd(R.factura_antes) })}</div>
          <div class="insignia ${ahorro < 0 ? "mala" : ""}">${ahorro >= 0 ? t("Ahorras {v} · {p} %", { v: usd(ahorro), p: fmt((ahorro / Math.max(R.factura_antes, 1)) * 100) }) : t("Sube {v}, pero rinde más", { v: usd(-ahorro) })}</div>
          <div class="mini-cifras">
            <div><span>${t("Tiempo que ahorra la IA")}</span><b>${fmt(hAhora)} h</b><span>${t("antes {v}", { v: `${fmt(hAntes)} h` })}</span></div>
            <div><span>${t("Valor neto")}</span><b>${usd(R.neto)}</b><span>${t("antes {v}", { v: usd(R.neto_antes) })}</span></div>
            <div><span>${t("Cuotas fijas")}</span><b>${usd(R.cuotas)}</b><span>${t("+ {v} por uso", { v: usd(R.pago_variable) })}</span></div>
          </div>
        </div></div>
        <div class="acciones-plan">
          <a class="btn primario ancho solo-escritorio" href="#seguimiento">${t("Ver el gasto del mes")} →</a>
          <div class="secundarias"><a class="btn" href="/clase/#modelo0">${t("Ver el cálculo paso a paso")}</a><button class="btn fantasma" data-accion="excel">${t("Descargar Excel")}</button></div>
          <p>${t("Calculado con programación lineal: método húngaro, Simplex, transporte con Vogel y MODI, sensibilidad y Dual Simplex. Se recalcula solo cuando cambian los datos.")}</p>
        </div>
        <div class="seccion"><h2>${t("Qué hacer este mes")} <span id="cuentaTareas">${t("{a} de {b}", { a: tareas.filter(x => hechos[x.k]).length, b: tareas.length })}</span></h2>
          <div class="tareas">${tareas.map(x => `<label class="tarea ${hechos[x.k] ? "hecha" : ""}"><input type="checkbox" data-tarea="${esc(x.k)}" ${hechos[x.k] ? "checked" : ""}><div><b>${esc(x.b)}</b><span>${esc(x.s)}</span></div></label>`).join("")}</div>
        </div>
      </div>
      <div class="col">
        <div class="seccion"><h2>${t("Por persona")}</h2>${buscador(P().length, "listaPlan")}<div class="lista" id="listaPlan">${P().map(filaPlan).join("")}</div></div>
        <div class="seccion"><h2>${t("¿Y si cambio el presupuesto?")}</h2>
          <div class="tarjeta indicador">
            ${deslizador("pPres", t("Gasto extra máximo"), reg.presupuesto_pct_nomina * 100, 1, 15, 0.5, v => `${fmt(v, 1)} % · ${usd((v / 100) * r.datos.nomina)}`)}
            <p style="margin:0;color:var(--tx-2);font-size:14px">${textoPresupuesto}</p>
          </div>
        </div>
        <div class="seccion"><h2>${t("Si recortan el presupuesto a mitad de mes")}</h2>
          <div class="tarjeta indicador">
            ${deslizador("pRec", t("Recorte"), (G.caso.recorte ?? r.datos.recorte) * 100, 5, 50, 5, v => `${fmt(v)} %`)}
            <div class="cambios">
              ${cambios.length ? cambios.slice(0, 12).map(p => `<div><span>${esc(p.nombre)}</span><span>${usd(r.modelo1.topes[p.nombre])} → <b>${usd(rec.topes[p.nombre])}</b></span></div>`).join("") + (cambios.length > 12 ? `<div><span>${t("y {n} más", { n: cambios.length - 12 })}</span><span></span></div>` : "") : `<div><span>${t("Nadie cambia")}</span><span>${t("el presupuesto sobraba")}</span></div>`}
              <div><span>${t("Factura nueva")}</span><b>${usd(r.recorte.factura)}</b></div>
            </div>
            <p style="margin:0;color:var(--tx-3);font-size:13px">${t("Bajan primero los que menos rinden en su último dólar; el resto no se toca.")}</p>
            <button class="btn" data-accion="aplicarRecorte" data-solo-admin>${G.seg.recorte ? t("Recorte aplicado en el seguimiento ✓") : t("Aplicar este recorte en el seguimiento")}</button>
          </div>
        </div>
      </div>
    </div>
    <div class="accion solo-movil"><div class="dentro"><a class="btn primario ancho" href="#seguimiento">${t("Ver el gasto del mes")} →</a><div class="nota" id="notaEstado"></div></div></div>
  </section>`;
}
function montarPlan() {
  const cont = $("#listaPlan");
  if (!cont) return;
  pantallaPlan.ultima = rr().resultado.factura;
  cont.addEventListener("click", e => {
    const b = e.target.closest("[data-editar]"); if (!b) return;
    const ed = $(`#ed-${b.dataset.editar}`); ed.hidden = !ed.hidden; b.textContent = ed.hidden ? t("Editar") : t("Listo");
    if (!ed.hidden) ed.querySelector("input").focus();
  });
  cont.addEventListener("change", e => {
    const el = e.target.closest("[data-campo]"); if (!el) return;
    const p = G.caso.personas.find(x => x.id === el.dataset.id); if (!p) return;
    p[el.dataset.campo] = el.type === "number" ? Number(el.value) || 0 : el.value;
    programar();
  });
  $$(".tarea input").forEach(c => c.addEventListener("change", () => {
    G.seg.hechos = { ...(G.seg.hechos || {}), [c.dataset.tarea]: c.checked };
    if (!c.checked) delete G.seg.hechos[c.dataset.tarea];
    guardarSeg();
    c.closest(".tarea").classList.toggle("hecha", c.checked);
    const tareas = tareasDelPlan();
    $("#cuentaTareas").textContent = t("{a} de {b}", { a: tareas.filter(x => G.seg.hechos[x.k]).length, b: tareas.length });
  }));
  const unir = (id, aplicar, formato) => {
    const el = $(`#${id}`);
    el.addEventListener("input", () => { $(`#${id}-v`).textContent = formato(+el.value); });
    el.addEventListener("change", () => { aplicar(+el.value); programar(); aviso(t("Recalculando el plan…")); });
  };
  unir("pPres", v => (G.caso.reglas.presupuesto_pct_nomina = v / 100), v => `${fmt(v, 1)} % · ${usd((v / 100) * rr().datos.nomina)}`);
  unir("pRec", v => (G.caso.recorte = v / 100), v => `${fmt(v)} %`);
}

/* ------------------------------------------------------------ pantalla: seguimiento (gasto en vivo) */
function estadoDe(p, R) {
  const tp = topes()[p.nombre], g = gastoDe(p.id, R), dias = diasDe(G.seg.mes), dia = Math.max(1, Math.min(diaSeg(), dias));
  if (!g.tiene) return { t: tp, g: 0, proy: 0, clase: "", chip: `<span class="chip">${t("Sin gasto aún")}</span>`, nivel: 0 };
  const proy = (g.total / dia) * dias;
  if (g.total > tp + 0.5) return { t: tp, g: g.total, proy, clase: "mal", chip: `<span class="chip mal">${t("Se pasó {v}", { v: usd(g.total - tp) })}</span>`, nivel: 2 };
  if (proy > tp + 0.5) return { t: tp, g: g.total, proy, clase: "ojo", chip: `<span class="chip ojo">${t("A este ritmo llega a {v}", { v: usd(proy) })}</span>`, nivel: 1 };
  return { t: tp, g: g.total, proy, clase: "", chip: `<span class="chip bien">${t("Va bien")}</span>`, nivel: 0 };
}
function barraSeg(p, R) {
  const s = estadoDe(p, R), max = Math.max(s.t, s.g, s.proy, 1), g = gastoDe(p.id, R);
  return `<div class="barra"><i class="lleno ${s.clase}" style="width:${(s.g / max) * 100}%"></i>${s.proy > 0 ? `<i class="proy" style="left:calc(${(Math.min(s.proy, max) / max) * 100}% - 1px)" title="${esc(t("Proyección a fin de mes"))}"></i>` : ""}<i class="marca-tope" style="left:calc(${(s.t / max) * 100}% - 1px)"></i></div>
    <div class="leyenda-barra"><span>${t("Lleva {v}", { v: usd(s.g) })}${g.auto > 0 ? ` · Claude ${usd(g.auto, 2)}` : ""}${s.proy > 0 ? ` · ${t("cierra en ~{v}", { v: usd(s.proy) })}` : ""}</span><span>${t("Tope {v}", { v: usd(s.t) })}</span></div>`;
}
function totalesSeg(R = reparto()) {
  const ps = P(), tp = topes();
  const g = ps.reduce((s, p) => s + gastoDe(p.id, R).total, 0), tt = ps.reduce((s, p) => s + tp[p.nombre], 0);
  const dias = diasDe(G.seg.mes), dia = Math.max(1, Math.min(diaSeg(), dias));
  const alertas = ps.filter(p => estadoDe(p, R).nivel > 0).length;
  const sin = R.sinAsignar.reduce((s, x) => s + x.usd, 0);
  return { g, t: tt, proy: (g / dia) * dias, alertas, sin, dia, dias };
}
function enVivo(R) {
  if (!conectado()) return `<a class="estado-vivo apagado" href="#ajustes"><i></i>${t("Claude Code sin conectar")}</a>`;
  if (!R.ultimo) return `<span class="estado-vivo quieto"><i></i>${t("Conectado · esperando el primer gasto del mes")}</span>`;
  return `<span class="estado-vivo ${Date.now() - R.ultimo < 15 * 60000 ? "" : "quieto"}"><i></i>${t("En vivo · último gasto {h}", { h: hace(R.ultimo) })}</span>`;
}
function pantallaSeguimiento() {
  if (!rr()) return pantallaEspera();
  const R = reparto(), T = totalesSeg(R);
  const filas = P().map(p => {
    const a = asig(p.nombre), man = G.seg.manual?.[p.id];
    const c = G.caso.personas.find(x => x.id === p.id) || p;
    return `<div class="tarjeta fila-persona" data-seg="${p.id}" data-busqueda="${busqueda(c)}">
      <div class="arriba">
        <span class="avatar" style="background:${colorDe(p.id)}">${esc(iniciales(p.nombre))}</span>
        <div class="nombre"><b>${esc(p.nombre)}</b><span>${esc(donde(p, a))}</span></div>
        <label class="campo" style="width:128px" title="${esc(t("Gasto en otras herramientas (Cursor, OpenAI…) que no se reporta solo"))}"><span class="con-sufijo"><input type="number" inputmode="decimal" min="0" step="5" data-manual="${p.id}" value="${man == null ? "" : esc(man)}" placeholder="${esc(t("+ otro"))}" aria-label="${esc(t("Gasto en otras herramientas de {n}", { n: p.nombre }))}"><b>USD</b></span></label>
      </div>
      <div class="b">${barraSeg(p, R)}</div>
      <div class="linea-chips e">${estadoDe(p, R).chip}</div>
    </div>`;
  }).join("");
  const hist = G.hist.slice(-6).reverse();
  const maxH = Math.max(1, ...hist.map(h => Math.max(h.antes, h.real)));
  return `<section class="pantalla">
    <div class="titulo">
      <h1>${t("Gasto de {m}, persona por persona", { m: esc(mesCorto(G.seg.mes).toLowerCase()) })}</h1>
      <p>${t("Lo de Claude Code llega solo, en vivo. Si alguien usa otra herramienta (Cursor, OpenAI…), anota a mano lo que lleva en su casilla.")}</p>
    </div>
    <div class="columnas">
      <div class="col">
        <div class="tarjeta" id="tarjetaMes"><div class="contenido" style="display:grid;gap:14px">
          <div class="mes"><b>${esc(nombreMes(G.seg.mes))} · ${t("día {a} de {b}", { a: T.dia, b: T.dias })}</b>${G.seg.recorte ? `<button class="chip ojo" data-accion="quitarRecorte" style="border:0;cursor:pointer">${t("Con recorte del {p} %", { p: fmt((G.caso.recorte ?? rr().datos.recorte) * 100) })} ✕</button>` : ""}</div>
          <div id="vivo">${enVivo(R)}</div>
          <div class="mini-cifras" id="totalesSeg">${htmlTotales(T)}</div>
        </div></div>
        <div class="seccion"><h2>${t("Por persona")}</h2>${buscador(P().length, "listaSeg")}<div class="lista" id="listaSeg">${filas}</div></div>
      </div>
      <div class="col">
        ${R.sinAsignar.length ? `<div class="seccion"><h2>${t("Sin asignar")} <span>${usd(T.sin, 2)}</span></h2>
          <div class="tarjeta lista">${R.sinAsignar.slice(0, 20).map(x => `<div class="sin-asignar"><div><b>${esc(x.email || t("Sin correo"))}</b><span>${x.email ? t("Usa Claude con este correo y no está en el equipo") : t("Claude Code no envió el correo (ver Ajustes)")}</span></div><b>${usd(x.usd, 2)}</b>${x.email ? `<button class="btn chico" data-agregar-correo="${esc(x.email)}" data-solo-admin>${t("Agregar")}</button>` : ""}</div>`).join("")}</div></div>` : ""}
        <div class="seccion"><h2>${t("Cerrar el mes")}</h2>
          <div class="tarjeta" style="display:grid;gap:12px">
            <p style="margin:0;color:var(--tx-2);font-size:14px">${t("El día 1 se cierra solo: lo que gastó cada persona pasa a ser su dato del mes pasado y se calcula el plan del siguiente. Si quieres, ciérralo antes.")}</p>
            <button class="btn ${G.confirmarCierre ? "primario" : ""}" data-accion="cerrar" data-solo-admin>${G.confirmarCierre ? t("Toca otra vez para confirmar") : t("Cerrar {m} ahora", { m: esc(nombreMes(G.seg.mes)) })}</button>
          </div>
        </div>
        ${hist.length ? `<div class="seccion"><h2>${t("Meses anteriores")}</h2><div class="tarjeta historial">${hist.map(h => `<div class="h"><span>${esc(nombreMes(h.mes))}</span><b>${usd(h.real)}</b><div class="barra"><i class="lleno ${h.real > h.plan + 0.5 ? "ojo" : ""}" style="width:${(h.real / maxH) * 100}%"></i><i class="marca-tope" style="left:calc(${(Math.min(h.plan, maxH) / maxH) * 100}% - 1px)"></i></div><small class="tenue" style="grid-column:1/3">${t("Uso real {r} · topes {p} · antes del plan se gastaba {a}", { r: usd(h.real), p: usd(h.plan), a: usd(h.antes) })}</small></div>`).join("")}</div></div>` : ""}
      </div>
    </div>
    <div class="accion"><div class="dentro"><a class="btn ancho" href="#plan">← ${t("Ver el plan")}</a><div class="nota" id="notaEstado"></div></div></div>
  </section>`;
}
function htmlTotales(T) {
  return `<div><span>${t("Uso hasta hoy")}</span><b>${usd(T.g)}</b><span>${t("de {v} en topes", { v: usd(T.t) })}</span></div>
    <div><span>${t("Cierre estimado")}</span><b class="${T.proy > T.t + 0.5 ? "ambar" : ""}">${usd(T.proy)}</b><span>${t("al ritmo actual")}</span></div>
    <div><span>${t("Alertas")}</span><b class="${T.alertas ? "rojo" : "verde"}">${T.alertas}</b><span>${T.alertas ? t("personas a revisar") : t("todo en orden")}</span></div>`;
}
function refrescarSeguimiento() {
  // actualización en vivo sin repintar la pantalla (no se pierde lo que se está escribiendo)
  const R = reparto();
  P().forEach(p => { const f = $(`[data-seg="${p.id}"]`); if (!f) return; $(".b", f).innerHTML = barraSeg(p, R); $(".e", f).innerHTML = estadoDe(p, R).chip; });
  const el = $("#totalesSeg"); if (el) el.innerHTML = htmlTotales(totalesSeg(R));
  const v = $("#vivo"); if (v) v.innerHTML = enVivo(R);
  pintarFlujo();
}
function montarSeguimiento() {
  const cont = $("#listaSeg"); if (!cont) return;
  cont.addEventListener("input", e => {
    const el = e.target.closest("[data-manual]"); if (!el) return;
    const id = el.dataset.manual, manual = { ...(G.seg.manual || {}) };
    if (el.value === "") delete manual[id]; else manual[id] = Math.max(0, Number(el.value) || 0);
    G.seg.manual = manual;
    guardarSeg();
    refrescarSeguimiento();
  });
}
async function cerrarMes() {
  if (!G.confirmarCierre) { G.confirmarCierre = true; render(false); setTimeout(() => { if (G.confirmarCierre) { G.confirmarCierre = false; if (G.vista === "seguimiento") render(false); } }, 5000); return; }
  G.confirmarCierre = false;
  try {
    const r = await accion("cerrarMes", { org: G.org });
    aviso(t("Mes cerrado con {v} de uso real. Calculando el plan del siguiente…", { v: usd(r.real || 0) }));
    location.hash = "#panel";
  } catch (e) { aviso(t(e.message), true); }
}

/* ------------------------------------------------------------ pantalla: panel */
function graficaMes(R, T) {
  // uso acumulado del mes contra la suma de topes, con la proyección al cierre
  const dias = T.dias, W = 340, H = 150, x0 = 30, x1 = 330, y0 = 12, y1 = 124;
  let acum = 0; const puntos = [[0, 0]];
  for (let d = 1; d <= T.dia; d++) { acum += R.porDia[d] || 0; puntos.push([d, acum]); }
  puntos[puntos.length - 1][1] = T.g; // incluye lo anotado a mano
  const max = Math.max(T.t, T.proy, 1) * 1.12;
  const X = d => x0 + (d / dias) * (x1 - x0), Y = v => y1 - (v / max) * (y1 - y0);
  const real = puntos.map(([d, v]) => `${X(d).toFixed(1)},${Y(v).toFixed(1)}`).join(" ");
  const pasa = T.proy > T.t + 0.5;
  let s = `<svg class="grafica" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(t("Uso acumulado del mes contra los topes"))}">`;
  [0, 0.5, 1].forEach(f => { const v = max * f; s += `<line class="rejilla-g" x1="${x0}" x2="${x1}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${x0 - 6}" y="${Y(v) + 4}" text-anchor="end" font-size="9">${fmt(v)}</text>`; });
  s += `<line class="tope-g" x1="${x0}" x2="${x1}" y1="${Y(T.t)}" y2="${Y(T.t)}" stroke-dasharray="3 4"/><text class="fuerte" x="${x1}" y="${Y(T.t) - 5}" text-anchor="end" font-size="9.5">${t("topes {v}", { v: usd(T.t) })}</text>`;
  s += `<polygon points="${X(0)},${y1} ${real} ${X(T.dia)},${y1}" fill="var(--verde)" fill-opacity=".12"/>`;
  s += `<polyline points="${real}" fill="none" stroke="var(--verde)" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>`;
  if (T.g > 0) s += `<line x1="${X(T.dia)}" y1="${Y(T.g)}" x2="${X(dias)}" y2="${Y(T.proy)}" stroke="${pasa ? "var(--ambar)" : "var(--tx-3)"}" stroke-width="1.6" stroke-dasharray="4 4"/><circle cx="${X(dias)}" cy="${Y(T.proy)}" r="3.5" fill="${pasa ? "var(--ambar)" : "var(--tx-3)"}"/>`;
  s += `<circle class="punto-g" cx="${X(T.dia)}" cy="${Y(T.g)}" r="4"/>`;
  s += `<text x="${x0}" y="${H - 4}" font-size="9">${t("día {n}", { n: 1 })}</text><text x="${x1}" y="${H - 4}" text-anchor="end" font-size="9">${t("día {n}", { n: dias })}</text></svg>`;
  return s;
}
function graficaMeses() {
  const filas = G.hist.slice(-5).map(h => ({ mes: h.mes, antes: h.antes, con: h.real ?? h.factura }));
  filas.push({ mes: G.seg.mes, antes: rr().resultado.factura_antes, con: rr().resultado.factura, actual: true });
  const max = Math.max(1, ...filas.map(f => Math.max(f.antes, f.con)));
  return `<div class="meses">${filas.map(f => `<div class="m ${f.actual ? "actual" : ""}">
    <div class="col-barras"><i class="b-antes" style="height:${(f.antes / max) * 100}%" title="${esc(t("Sin el plan {v}", { v: usd(f.antes) }))}"></i><i class="b-con" style="height:${(f.con / max) * 100}%" title="${esc(t("Con el plan {v}", { v: usd(f.con) }))}"></i></div>
    <span>${esc(mesCorto(f.mes).slice(0, 3))}</span></div>`).join("")}</div>
    <div class="leyenda"><span><i class="b-antes"></i>${t("Gasto sin el plan")}</span><span><i style="background:var(--verde)"></i>${t("Con el plan (real en meses cerrados)")}</span></div>`;
}
function pantallaPanel() {
  if (!rr()) return pantallaEspera();
  const R = reparto(), T = totalesSeg(R), Rs = rr().resultado, tp = topes(), ahorro = Rs.factura_antes - Rs.factura;
  const ahorroTotal = G.hist.reduce((s, h) => s + (h.antes - h.real), 0) + ahorro;
  const hAhora = P().reduce((s, p) => s + horas(rr(), p.nombre), 0);
  const conDato = P().filter(p => gastoDe(p.id, R).tiene).length;
  const alertas = P().map(p => ({ p, s: estadoDe(p, R) })).filter(x => x.s.nivel > 0).sort((a, b) => b.s.nivel - a.s.nivel || b.s.g - a.s.g);
  const tareas = tareasDelPlan(), hechos = G.seg.hechos || {}, hechas = tareas.filter(x => hechos[x.k]).length;
  const eqs = [...new Set(P().map(p => p.equipo))].map(eq => {
    const gente = P().filter(p => p.equipo === eq);
    return { eq, t: gente.reduce((s, p) => s + tp[p.nombre], 0), g: gente.reduce((s, p) => s + gastoDe(p.id, R).total, 0), n: gente.length };
  }).sort((a, b) => b.g - a.g);
  const pct = T.t ? (T.g / T.t) * 100 : 0;
  const top = P().map(p => ({ p, g: gastoDe(p.id, R).total })).filter(x => x.g > 0).sort((a, b) => b.g - a.g).slice(0, 5);
  const conc = G.conciliacion, mes = mesCorto(G.seg.mes);
  const sub = alertas.length
    ? plural(alertas.length, "Una persona va camino de pasarse de su tope.", "{n} personas van camino de pasarse de su tope.")
    : conDato ? t("Nadie va camino de pasarse de su tope.") : conectado() ? t("Claude Code está conectado: el gasto aparece aquí en cuanto alguien lo use.") : t("Conecta Claude Code en Ajustes y el gasto aparece aquí solo.");
  return `<section class="pantalla">
    <div class="titulo">
      <h1>${conDato ? t("{m} va en {g} de {t}", { m: esc(mes), g: usd(T.g), t: usd(T.t) }) : t("{m}: factura estimada de {v}", { m: esc(mes), v: usd(Rs.factura) })}</h1>
      <p>${sub} ${ahorro > 0 ? t("Con el plan pagas {v} menos que el mes pasado.", { v: usd(ahorro) }) : ""}</p>
      <div id="vivo" style="margin-top:10px">${enVivo(R)}</div>
    </div>
    <div class="kpis">
      <a class="tarjeta kpi" href="#seguimiento"><span>${t("Uso hasta hoy")}</span><b><span data-contar="${T.g}" data-desde="${pantallaPanel.ultimo ?? T.g}">${fmt(T.g)}</span> <small>USD</small></b><div class="barra fina"><i class="lleno ${T.proy > T.t + 0.5 ? "ojo" : ""}" style="width:${Math.min(100, pct)}%"></i></div><em>${t("{p} % de los topes · día {d}", { p: fmt(pct), d: T.dia })}</em></a>
      <a class="tarjeta kpi" href="#seguimiento"><span>${t("Cierre estimado")}</span><b class="${T.proy > T.t + 0.5 ? "ambar" : ""}">${fmt(T.proy)} <small>USD</small></b><em>${t("al ritmo de hoy")}</em></a>
      <a class="tarjeta kpi" href="#plan"><span>${t("Factura con el plan")}</span><b>${fmt(Rs.factura)} <small>USD</small></b><em>${t("antes {a} · ahorro {cual} {v}", { a: usd(Rs.factura_antes), cual: G.hist.length ? t("acumulado") : t("del mes"), v: usd(ahorroTotal) })}</em></a>
      <a class="tarjeta kpi" href="#plan"><span>${t("Tiempo que ahorra la IA")}</span><b>${fmt(hAhora)} <small>h</small></b><em>${t("valor {v}", { v: usd(Rs.valor) })}</em></a>
    </div>
    <div class="columnas">
      <div class="col">
        <div class="seccion"><h2>${t("Gasto del mes")} <a href="#seguimiento" class="enlace">${t("Ver por persona")} →</a></h2>
          <div class="tarjeta">
            ${conDato ? graficaMes(R, T) : `<div class="vacio"><b>${t("Todavía no llega gasto este mes")}</b><span>${conectado() ? t("Ya está conectado. Aparece en segundos cuando alguien use Claude Code.") : t("Conecta Claude Code una vez para toda la empresa; tarda 5 minutos.")}</span>${conectado() ? "" : `<a class="btn chico" href="#ajustes">${t("Conectar Claude")}</a>`}</div>`}
            ${conDato ? `<div class="leyenda-barra" style="margin-top:6px"><span>${t("{a} de {b} personas con gasto", { a: conDato, b: P().length })}</span><span class="${T.proy > T.t + 0.5 ? "ambar" : ""}">${t("Cierre estimado {v}", { v: usd(T.proy) })}</span></div>` : ""}
          </div>
        </div>
        <div class="seccion"><h2>${t("Por equipo")}</h2>
          <div class="tarjeta lista">${eqs.map(e => { const max = Math.max(e.t, e.g, 1); return `<div style="display:grid;gap:6px">
            <div class="leyenda-barra" style="color:var(--tx-2)"><span><b style="color:var(--tx);font-weight:600">${esc(e.eq)}</b> · ${plural(e.n, "{n} persona", "{n} personas")}</span><span>${t("{a} de {b}", { a: usd(e.g), b: usd(e.t) })}</span></div>
            <div class="barra"><i class="lleno ${e.g > e.t + 0.5 ? "mal" : ""}" style="width:${(e.g / max) * 100}%"></i><i class="marca-tope" style="left:calc(${(e.t / max) * 100}% - 1px)"></i></div></div>`; }).join("")}</div>
        </div>
        ${top.length ? `<div class="seccion"><h2>${t("Quién más gasta este mes")}</h2><div class="tarjeta lista">${top.map(({ p, g }) => `<div class="leyenda-barra" style="color:var(--tx-2)"><span><b style="color:var(--tx);font-weight:600">${esc(p.nombre)}</b> · ${esc(p.equipo)}</span><span>${t("{a} de {b}", { a: usd(g, 2), b: usd(tp[p.nombre]) })}</span></div>`).join("")}</div></div>` : ""}
      </div>
      <div class="col">
        <div class="seccion"><h2>${t("Alertas")} <span>${alertas.length}</span></h2>
          <div class="lista">${alertas.length ? alertas.slice(0, 8).map(({ p, s }) => `<a class="tarjeta alerta-fila" href="#seguimiento"><span class="avatar" style="background:${colorDe(p.id)}">${esc(iniciales(p.nombre))}</span><div><b>${esc(p.nombre)}</b><span>${s.nivel === 2 ? t("Se pasó: lleva {g} de {t}", { g: usd(s.g), t: usd(s.t) }) : t("A este ritmo cierra en {p} (tope {t})", { p: usd(s.proy), t: usd(s.t) })}</span></div><i class="punto ${s.nivel === 2 ? "mal" : "ojo"}"></i></a>`).join("") + (alertas.length > 8 ? `<a class="enlace" href="#seguimiento">${t("y {n} más", { n: alertas.length - 8 })} →</a>` : "")
            : `<div class="tarjeta vacio"><b>${conDato ? t("Todo en orden") : t("Sin alertas por ahora")}</b><span>${conDato ? t("Nadie va camino de pasarse de su tope.") : t("Aparecen cuando llegue el gasto del mes.")}</span></div>`}</div>
        </div>
        ${conc ? `<div class="seccion"><h2>${t("Facturado por Anthropic")}</h2><div class="tarjeta lista">
          <div class="leyenda-barra" style="color:var(--tx-2)"><span>${t("API y consola de Anthropic este mes")}</span><b style="color:var(--tx)">${usd(conc.total || 0, 2)}</b></div>
          <small class="tenue">${t("Confirmado hasta {f}. Llega con unas horas de retraso; sirve para cuadrar la factura.", { f: conc.datosHasta ? new Date(conc.datosHasta).toLocaleString(locale(), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—" })}</small></div></div>` : ""}
        <div class="seccion"><h2>${t("Mes a mes")}</h2><div class="tarjeta">${graficaMeses()}</div></div>
        <div class="seccion"><h2>${t("Qué hacer este mes")} <a href="#plan" class="enlace">${t("Ver plan")} →</a></h2>
          <a class="tarjeta progreso" href="#plan"><div class="leyenda-barra" style="color:var(--tx-2)"><span>${t("{a} de {b} tareas hechas", { a: hechas, b: tareas.length })}</span><span>${fmt((hechas / Math.max(tareas.length, 1)) * 100)} %</span></div><div class="barra fina"><i class="lleno" style="width:${(hechas / Math.max(tareas.length, 1)) * 100}%"></i></div>
            ${tareas.filter(x => !hechos[x.k]).slice(0, 2).map(x => `<span class="sig">○ ${esc(x.b)}</span>`).join("")}</a>
        </div>
      </div>
    </div>
  </section>`;
}
function montarPanel() { pantallaPanel.ultimo = totalesSeg().g; }

/* ------------------------------------------------------------ pantalla: ajustes (conectar Claude, equipo) */
function bloqueConfig(token) {
  const env = {
    CLAUDE_CODE_ENABLE_TELEMETRY: "1",
    OTEL_LOGS_EXPORTER: "otlp",
    OTEL_EXPORTER_OTLP_PROTOCOL: "http/json",
    OTEL_EXPORTER_OTLP_ENDPOINT: URL_INGESTA,
    // x-api-key y no Authorization: Cloud Run valida todo «Bearer» como token de Google y lo rechaza
    OTEL_EXPORTER_OTLP_HEADERS: `x-api-key=${token}`,
  };
  return JSON.stringify({ env }, null, 2);
}
const rolTexto = r => (r === "admin" ? t("Administra") : t("Solo ve"));
function pantallaAjustes() {
  const e = G.empresa || {}, an = e.anthropic || {};
  const miembros = Object.entries(e.miembros || {}).map(([uid, m]) => ({ uid, ...m }));
  const invitados = Object.values(e.invitados || {});
  const tokens = (G.tokens || []).filter(x => !x.revocado);
  const R = reparto();
  const ejemploToken = G.tokenNuevo ? G.tokenNuevo.token : t("gia_…(genera un token)");
  return `<section class="pantalla">
    <div class="titulo"><h1>${t("Ajustes de {e}", { e: esc(e.nombre || t("la empresa")) })}</h1>
      <p>${t("Conecta Claude una vez y el gasto de cada persona llega solo. Lo demás es opcional.")}</p></div>
    <div class="columnas">
      <div class="col">
        <div class="seccion"><h2>${t("1 · Conectar Claude Code")} <span>${enVivo(R)}</span></h2>
          <div class="tarjeta lista">
            ${G.admin ? `
            <p class="texto">${t("Genera un token para tu empresa y pon esta configuración en los equipos de tu gente. Claude Code reporta el costo de cada llamada en segundos y lo asignamos a cada persona por su correo.")}</p>
            ${G.tokenNuevo ? `<div class="aviso-token"><b>${t("Copia el token ahora: no se vuelve a mostrar.")}</b></div>` : ""}
            <pre class="codigo" id="config">${esc(bloqueConfig(ejemploToken))}</pre>
            <div class="barra-acciones">
              <button class="btn primario" data-accion="crearToken">${tokens.length ? t("Generar otro token") : t("Generar token")}</button>
              <button class="btn fantasma" data-accion="copiarConfig" ${G.tokenNuevo ? "" : "disabled"}>${t("Copiar configuración")}</button>
            </div>
            <details class="avanzado"><summary><b style="font-weight:600">${t("Dónde va la configuración")}</b></summary><div class="dentro texto">
              <p>${t("<b>Para toda la empresa (recomendado).</b> Tu equipo de TI la instala como configuración administrada, y nadie la puede desactivar:")}</p>
              <ul><li>macOS: <code>/Library/Application Support/ClaudeCode/managed-settings.json</code></li>
              <li>${t("Linux y WSL")}: <code>/etc/claude-code/managed-settings.json</code></li>
              <li>Windows: <code>C:\\Program Files\\ClaudeCode\\managed-settings.json</code></li></ul>
              <p>${t("<b>Para una persona.</b> Pega el bloque <code>env</code> en <code>~/.claude/settings.json</code>.")}</p>
              <p>${t("<b>Si alguien usa Claude Code con clave de API</b> (sin cuenta de Claude), su correo no viaja solo: agrega <code>\"OTEL_RESOURCE_ATTRIBUTES\": \"user.email=su-correo@empresa.com\"</code> en su configuración.")}</p>
              <p class="tenue">${t("Solo se envían costos, tokens, modelo y correo. Nunca el código ni los mensajes.")}</p>
            </div></details>
            ${tokens.length ? `<div class="lista">${tokens.map(x => `<div class="sin-asignar"><div><b>${esc(t(x.nombre))}</b><span>${t("termina en …{f} · creado {h}", { f: esc(x.fin), h: hace(fechaDe(x.creadoEn)) })}</span></div><span></span><button class="btn chico fantasma" data-revocar="${esc(x.id)}">${t("Revocar")}</button></div>`).join("")}</div>` : ""}
            ` : `<p class="texto">${t("Pídele a un administrador de tu empresa que conecte Claude Code.")}</p>`}
          </div>
        </div>
        <div class="seccion"><h2>${t("2 · Facturación de Anthropic")} <span class="tenue">${t("opcional")}</span></h2>
          <div class="tarjeta lista">
            <p class="texto">${t("Si tu empresa usa la API o la consola de Anthropic, conecta una clave de administración (<code>sk-ant-admin…</code>) y traemos lo facturado cada 3 horas para cuadrarlo con el gasto en vivo. Se guarda cifrada y solo la usa el servidor.")}</p>
            ${an.conectado ? `<div class="leyenda-barra" style="color:var(--tx-2)"><span>${t("Conectada · termina en …{f}", { f: esc(an.fin || "") })}</span><span>${an.revisadoEn ? t("revisada {h}", { h: hace(fechaDe(an.revisadoEn)) }) : ""}</span></div>` : ""}
            ${an.error ? `<p class="rojo" style="margin:0;font-size:13.5px">${t("No se pudo leer la facturación: {e}", { e: esc(an.error) })}</p>` : ""}
            ${G.admin ? `<form class="barra-acciones" id="formAnthropic"><label class="campo" style="flex:1;min-width:220px"><input type="password" name="clave" placeholder="sk-ant-admin…" autocomplete="off" aria-label="${esc(t("Clave de administración de Anthropic"))}"></label><button class="btn" type="submit">${an.conectado ? t("Cambiar") : t("Conectar")}</button>${an.conectado ? `<button class="btn fantasma" type="button" data-accion="sincronizar">${t("Traer ahora")}</button><button class="btn fantasma" type="button" data-accion="desconectarAnthropic">${t("Quitar")}</button>` : ""}</form>` : ""}
          </div>
        </div>
      </div>
      <div class="col">
        <div class="seccion"><h2>${t("3 · Quién entra al panel")} <span>${miembros.length}</span></h2>
          <div class="tarjeta lista">
            ${miembros.map(m => `<div class="sin-asignar"><div><b>${esc(m.email || m.uid)}</b><span>${rolTexto(m.rol)}${m.uid === G.usuario.uid ? ` · ${t("tú")}` : ""}</span></div><span></span>${G.admin && m.uid !== G.usuario.uid ? `<button class="btn chico fantasma" data-quitar-miembro="${esc(m.uid)}">${t("Quitar")}</button>` : ""}</div>`).join("")}
            ${invitados.map(i => `<div class="sin-asignar"><div><b>${esc(i.email)}</b><span>${t("Invitado · {r}", { r: rolTexto(i.rol).toLowerCase() })}</span></div><span class="chip">${t("pendiente")}</span></div>`).join("")}
            ${G.admin ? `<form class="barra-acciones" id="formInvitar"><label class="campo" style="flex:1;min-width:200px"><input type="email" name="email" required placeholder="${esc(t("correo@empresa.com"))}" aria-label="${esc(t("Correo de la persona"))}"></label><label class="campo"><select name="rol" aria-label="${esc(t("Permiso"))}"><option value="lector">${t("Solo ve")}</option><option value="admin">${t("Administra")}</option></select></label><button class="btn" type="submit">${t("Invitar")}</button></form>
            <small class="tenue">${t("Entra con Google usando ese correo y queda dentro.")}</small>` : ""}
          </div>
        </div>
        <div class="seccion"><h2>${t("Tu cuenta")}</h2>
          <div class="tarjeta lista">
            <div class="leyenda-barra" style="color:var(--tx-2)"><span>${esc(G.usuario.email || "")}</span><span>${G.admin ? t("Administras") : t("Solo ves")}</span></div>
            <div class="barra-acciones">${(G.empresas || []).length > 1 ? `<label class="campo" style="flex:1"><select id="cambiarEmpresa" aria-label="${esc(t("Cambiar de empresa"))}" data-libre>${G.empresas.map(x => `<option value="${esc(x.id)}" ${x.id === G.org ? "selected" : ""}>${esc(x.nombre)}</option>`).join("")}</select></label>` : ""}<button class="btn fantasma" data-accion="nuevaEmpresa">${t("Crear otra empresa")}</button><button class="btn fantasma" data-accion="salir">${t("Salir")}</button></div>
          </div>
        </div>
      </div>
    </div>
  </section>`;
}
function montarAjustes() {
  const fi = $("#formInvitar");
  if (fi) fi.addEventListener("submit", async e => {
    e.preventDefault();
    const f = new FormData(fi);
    try { await accion("invitarMiembro", { org: G.org, email: f.get("email"), rol: f.get("rol") }); aviso(t("Invitación lista.")); fi.reset(); }
    catch (err) { aviso(t(err.message), true); }
  });
  const fa = $("#formAnthropic");
  if (fa) fa.addEventListener("submit", async e => {
    e.preventDefault();
    const clave = new FormData(fa).get("clave");
    if (!clave) return;
    try { await accion("guardarClaveAnthropic", { org: G.org, clave }); aviso(t("Clave guardada. Trayendo la facturación…")); fa.reset(); }
    catch (err) { aviso(t(err.message), true); }
  });
  const ce = $("#cambiarEmpresa");
  if (ce) ce.addEventListener("change", () => abrirEmpresa(ce.value));
}

/* ------------------------------------------------------------ navegación y estado */
const PANTALLAS = {
  panel: [pantallaPanel, montarPanel], datos: [pantallaDatos, montarDatos], plan: [pantallaPlan, montarPlan],
  seguimiento: [pantallaSeguimiento, montarSeguimiento], ajustes: [pantallaAjustes, montarAjustes],
};
function pintarEstado() {
  const el = $("#notaEstado"); if (!el) return;
  const e = errorPlan();
  el.classList.toggle("error", !!e);
  if (calculando()) el.textContent = t("Calculando el plan…");
  else if (e) el.textContent = t(e);
  else if (rr() && G.vista === "datos") el.textContent = t("Plan listo: {a} al mes (antes {b}) · guardado", { a: usd(rr().resultado.factura), b: usd(rr().resultado.factura_antes) });
  else el.textContent = t("Se guarda solo, para todo tu equipo.");
  const cta = $("#verPlan"); if (cta) cta.classList.toggle("cargando", calculando());
}
const ICONO_SOL = `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4 6 18M18 6l1.4-1.4"/></svg>`;
const ICONO_LUNA = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg>`;
const ICONO_AJUSTES = `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>`;
function pintarCabecera() {
  // textos fijos del encabezado y botones de idioma y tema (siempre visibles, también al entrar)
  $$("[data-t]").forEach(el => { el.textContent = t(el.dataset.t); });
  $("#pasos")?.setAttribute("aria-label", t("Secciones"));
  const pref = $("#preferencias");
  if (pref) {
    const oscuro = temaActual() === "dark";
    pref.innerHTML = `<button class="pref" data-accion="idioma" aria-label="${esc(t("Cambiar idioma"))}" title="${esc(t("Cambiar idioma"))}">${lang() === "es" ? "EN" : "ES"}</button>
      <button class="pref" data-accion="tema" aria-label="${esc(oscuro ? t("Usar modo claro") : t("Usar modo oscuro"))}" title="${esc(oscuro ? t("Usar modo claro") : t("Usar modo oscuro"))}">${oscuro ? ICONO_SOL : ICONO_LUNA}</button>`;
  }
  const c = $("#cuenta");
  if (c) c.innerHTML = G.caso ? `<a href="#ajustes" class="empresa-actual ${G.vista === "ajustes" ? "on" : ""}" title="${esc(t("Ajustes de la empresa"))}" aria-label="${esc(t("Ajustes de la empresa"))}"><span>${esc(G.empresa?.nombre || "")}</span>${ICONO_AJUSTES}</a>` : "";
}
function pintarFlujo() {
  const enApp = !!G.caso;
  document.body.classList.toggle("sin-app", !enApp);
  pintarCabecera();
  if (!enApp) return;
  const hecho = {
    panel: !!rr(), datos: !!(G.caso && G.caso.personas.length), plan: !!rr() && !errorPlan(),
    seguimiento: !!(rr() && G.seg && P().some(p => gastoDe(p.id).tiene)),
  };
  const alertas = rr() && G.seg ? totalesSeg().alertas : 0;
  $$(".pasos .paso").forEach(el => {
    const p = el.dataset.p;
    el.classList.toggle("on", p === G.vista);
    el.classList.toggle("hecho", !!hecho[p]);
    el.classList.toggle("alerta", p === "seguimiento" && alertas > 0);
    const a = el.querySelector("a");
    if (p === G.vista) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  $('[data-linea="plan"]').classList.toggle("lleno", hecho.datos && hecho.plan);
  $('[data-linea="seguimiento"]').classList.toggle("lleno", hecho.plan && hecho.seguimiento);
}
function render(animar = true) {
  let html, montar = () => {};
  if (G.usuario === null) html = `<p class="tenue cargando-app">${t("Cargando…")}</p>`;
  else if (!G.usuario) html = pantallaEntrar();
  else if ((G.empresas && !G.empresas.length) || G.vista === "nuevaEmpresa") html = pantallaNuevaEmpresa();
  else if (!G.caso || !G.seg) html = `<p class="tenue cargando-app">${t("Abriendo tu empresa…")}</p>`;
  else { const [pintar, m] = PANTALLAS[G.vista] || PANTALLAS.panel; html = pintar(); montar = m; }
  $("#app").innerHTML = html;
  if (!animar) { const s = $(".pantalla"); if (s) s.style.animation = "none"; }
  pintarFlujo();
  montar();
  if (!G.admin && G.caso) $$("#app input, #app select").forEach(el => { if (!el.closest("[data-libre]")) el.disabled = true; });
  document.body.classList.toggle("lector", !G.admin);
  contar($("#app"));
  pintarEstado();
  const f = $("#formEmpresa");
  if (f) f.addEventListener("submit", crearEmpresa);
}
/** Repinta por un cambio que llegó del servidor sin interrumpir a quien está escribiendo. */
function refrescar() {
  const activo = document.activeElement;
  const escribiendo = activo && $("#app").contains(activo) && /INPUT|SELECT|TEXTAREA/.test(activo.tagName);
  const filasSeg = $$("#listaSeg > [data-seg]").map(f => f.dataset.seg).join();
  if (G.vista === "seguimiento" && $("#listaSeg") && (escribiendo || (rr() && filasSeg === P().map(p => p.id).join()))) return refrescarSeguimiento();
  if (escribiendo || (G.vista === "datos" && $("#listaPersonas"))) { G.pendienteRender = true; pintarEstado(); pintarFlujo(); return; }
  cancelAnimationFrame(refrescar.raf);
  refrescar.raf = requestAnimationFrame(() => { const y = scrollY; render(false); scrollTo(0, y); });
}
document.addEventListener("focusout", () => setTimeout(() => {
  if (G.pendienteRender && G.vista !== "datos" && !$("#app").contains(document.activeElement)) { G.pendienteRender = false; refrescar(); }
}, 0));

function irA(vista) {
  if (!PANTALLAS[vista] && vista !== "nuevaEmpresa") vista = "panel";
  G.vista = vista;
  G.confirmarCierre = false;
  G.pendienteRender = false;
  render();
  scrollTo({ top: 0, behavior: "auto" });
}
addEventListener("hashchange", () => irA(location.hash.slice(1)));

async function crearEmpresa(e) {
  e.preventDefault();
  if (G.ocupado) return;
  const f = new FormData(e.target);
  G.ocupado = true;
  const b = e.target.querySelector("button[type=submit]"); b.classList.add("cargando"); b.disabled = true;
  try {
    const { org } = await accion("crearOrganizacion", { nombre: f.get("nombre"), conEjemplo: f.get("ejemplo") === "si", zona: Intl.DateTimeFormat().resolvedOptions().timeZone });
    guardarLocal(CLAVE_ORG, org);
    G.vista = "datos";
    history.replaceState(null, "", "#datos");
    G.abrirAlLlegar = org;
  } catch (err) { aviso(t(err.message), true); b.classList.remove("cargando"); b.disabled = false; }
  finally { G.ocupado = false; }
}

const PARTE_A_ESTADO = { historial: "hist", alertas: "alertas", tokens: "tokens", conciliacion: "conciliacion", gasto: "gasto", plan: "plan" };
function abrirEmpresa(id) {
  if (G.escucha) G.escucha.parar();
  const datos = (G.empresas || []).find(x => x.id === id);
  if (!datos) return;
  guardarLocal(CLAVE_ORG, id);
  Object.assign(G, { org: id, empresa: datos, admin: (datos.roles || {})[G.usuario.uid] === "admin", caso: null, seg: null, plan: null,
    gasto: { mes: null, personas: {} }, hist: [], alertas: [], conciliacion: null, tokens: [], tokenNuevo: null });
  render();
  G.escucha = escucharEmpresa(id, G.admin, (parte, valor) => {
    if (parte === "caso") {
      if (!valor) return;
      const local = G.caso && (G.caso.version || 0) > (valor.version || 0); // mi cambio aún no llega
      if (!local && !tCaso) { G.caso = valor; ajustarIds(); }
    } else if (parte === "seguimiento") {
      if (!valor) return;
      G.seg = { manual: {}, hechos: {}, ...valor };
      G.escucha.cambiarMes(valor.mes);
    } else if (parte === "empresa") {
      if (!valor) return;
      G.empresa = valor; G.admin = (valor.roles || {})[G.usuario.uid] === "admin";
    } else if (PARTE_A_ESTADO[parte]) {
      const vacio = parte === "conciliacion" || parte === "plan" ? null : [];
      G[PARTE_A_ESTADO[parte]] = valor ?? vacio;
    }
    if (!G.caso || !G.seg) return;
    refrescar();
  }, (parte, err) => { console.warn(parte, err); if (parte === "caso") aviso(t("No tienes acceso a esta empresa."), true); });
}

/* ------------------------------------------------------------ clics */
document.addEventListener("input", e => {
  const b = e.target.closest("[data-buscar]"); if (!b) return;
  const q = b.value.trim().toLowerCase();
  $$(`#${b.dataset.buscar} > [data-busqueda]`).forEach(el => { el.hidden = q && !el.dataset.busqueda.includes(q); });
});
document.addEventListener("click", async e => {
  const b = e.target.closest("[data-accion], [data-quitar], [data-agregar-correo], [data-revocar], [data-quitar-miembro]"); if (!b) return;
  if (b.dataset.quitar) {
    if (G.caso.personas.length <= 1) return aviso(t("Debe quedar al menos una persona."), true);
    const p = G.caso.personas.find(x => x.id === b.dataset.quitar);
    G.caso.personas = G.caso.personas.filter(x => x.id !== b.dataset.quitar);
    $(`[data-tarjeta="${b.dataset.quitar}"]`).remove();
    $("#resumenDatos").innerHTML = resumenDatos();
    aviso(t("Se quitó a {n}.", { n: p.nombre || t("la persona") }));
    return programar();
  }
  if (b.dataset.agregarCorreo) {
    const email = b.dataset.agregarCorreo, base = email.split("@")[0].replace(/[._-]+/g, " ");
    const nombre = base.replace(/\b\w/g, c => c.toUpperCase());
    G.caso.personas.push(conId({ nombre, email, equipo: "General", salario: 2000, gasto: 0, herramienta: "Claude" }));
    programar();
    aviso(t("{n} quedó en el equipo. Revisa su salario en Datos.", { n: nombre }));
    return render(false);
  }
  if (b.dataset.revocar) {
    try { await accion("revocarToken", { org: G.org, id: b.dataset.revocar }); aviso(t("Token revocado: ya no puede enviar datos.")); }
    catch (err) { aviso(t(err.message), true); }
    return;
  }
  if (b.dataset.quitarMiembro) {
    try { await accion("quitarMiembro", { org: G.org, uid: b.dataset.quitarMiembro }); aviso(t("Se quitó el acceso.")); }
    catch (err) { aviso(t(err.message), true); }
    return;
  }
  const a = b.dataset.accion;
  if (a !== "excel") e.preventDefault();
  if (a === "idioma") {
    cambiarIdioma(lang() === "es" ? "en" : "es");
    render(false);
  } else if (a === "tema") {
    cambiarTema();
    pintarCabecera();
  } else if (a === "entrar") {
    try { await entrarConGoogle(); } catch (err) { if (err.code !== "auth/popup-closed-by-user") aviso(t("No se pudo entrar con Google."), true); }
  } else if (a === "salir") {
    await salir(); location.hash = "";
  } else if (a === "nuevaEmpresa") {
    irA("nuevaEmpresa");
  } else if (a === "agregar") {
    const eq = G.caso.personas[G.caso.personas.length - 1]?.equipo || "General";
    const p = conId({ nombre: "", email: "", equipo: eq, salario: 2000, gasto: 100, herramienta: "Claude" });
    G.caso.personas.push(p);
    $("#listaPersonas").insertAdjacentHTML("beforeend", tarjetaPersona(p));
    $("#resumenDatos").innerHTML = resumenDatos();
    const nueva = $(`[data-tarjeta="${p.id}"]`);
    nueva.scrollIntoView({ behavior: quieto ? "auto" : "smooth", block: "center" });
    $("input", nueva).focus();
    programar();
  } else if (a === "vaciar") {
    G.caso.personas = [conId({ nombre: "", email: G.usuario.email || "", equipo: "General", salario: 2000, gasto: 100, herramienta: "Claude" })];
    G.seg.hechos = {}; guardarSeg();
    programar(); render();
  } else if (a === "excel") {
    descargarExcel();
  } else if (a === "aplicarRecorte") {
    G.seg.recorte = !G.seg.recorte; guardarSeg(); render(false);
    aviso(G.seg.recorte ? t("El seguimiento usa ahora los topes con recorte.") : t("Se quitó el recorte del seguimiento."));
  } else if (a === "quitarRecorte") {
    G.seg.recorte = false; guardarSeg(); render(false);
  } else if (a === "cerrar") {
    cerrarMes();
  } else if (a === "crearToken") {
    b.disabled = true;
    try { G.tokenNuevo = await accion("crearToken", { org: G.org, nombre: "Claude Code de la empresa" }); render(false); aviso(t("Token creado. Cópialo ahora.")); }
    catch (err) { aviso(t(err.message), true); b.disabled = false; }
  } else if (a === "copiarConfig") {
    try { await navigator.clipboard.writeText($("#config").textContent); aviso(t("Configuración copiada.")); } catch (_) { aviso(t("Selecciona el texto y cópialo."), true); }
  } else if (a === "sincronizar") {
    try { const r = await accion("sincronizarAnthropic", { org: G.org }); aviso(r.ok ? t("Facturación actualizada.") : t("No se pudo traer la facturación."), !r.ok); }
    catch (err) { aviso(t(err.message), true); }
  } else if (a === "desconectarAnthropic") {
    try { await accion("guardarClaveAnthropic", { org: G.org, clave: "" }); aviso(t("Se quitó la clave de Anthropic.")); }
    catch (err) { aviso(t(err.message), true); }
  }
});
matchMedia("(prefers-color-scheme: light)").addEventListener("change", pintarCabecera);

/* ------------------------------------------------------------ arranque */
let pararEmpresas = null;
pintarCabecera();
alCambiarSesion(async u => {
  if (pararEmpresas) { pararEmpresas(); pararEmpresas = null; }
  if (G.escucha) { G.escucha.parar(); G.escucha = null; }
  Object.assign(G, { usuario: u || false, empresas: null, org: null, caso: null, seg: null, plan: null });
  render();
  if (!u) return;
  try { await accion("aceptarInvitaciones"); } catch (_) { /* sin invitaciones */ }
  pararEmpresas = escucharMisEmpresas(u.uid, listaEmp => {
    G.empresas = listaEmp.sort((a, b) => String(a.nombre).localeCompare(b.nombre));
    const quiero = G.abrirAlLlegar || G.org || leerLocal(CLAVE_ORG);
    const elegida = listaEmp.find(x => x.id === quiero) || listaEmp[0];
    if (!elegida) { render(); return; }
    if (elegida.id !== G.org) {
      G.abrirAlLlegar = null;
      const h = location.hash.slice(1);
      G.vista = PANTALLAS[h] ? h : "panel";
      abrirEmpresa(elegida.id);
    } else {
      G.empresa = elegida;
    }
  }, err => { console.warn(err); aviso(t("No se pudieron leer tus empresas."), true); });
});
if (LOCAL) console.info("Modo local: usando los emuladores de Firebase.");
