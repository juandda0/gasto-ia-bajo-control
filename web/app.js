/* App para empresas: la empresa pone sus datos y recibe su plan; durante el mes le hace
   seguimiento. Todo el cálculo (asignación, Simplex, transporte, sensibilidad, Dual Simplex)
   lo hace el servidor; aquí solo se habla en lenguaje de negocio.
   Los datos se guardan en este navegador (localStorage). */
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const fmt = (v, d = 0) => Number(v).toLocaleString("es-CO", { minimumFractionDigits: d, maximumFractionDigits: d });
  const usd = (v, d = 0) => `${fmt(v, d)} USD`;
  const esc = t => String(t).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const quieto = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const CLAVE = "gasto-ia-v1";
  const HERRAMIENTAS = ["Claude", "Cursor", "OpenAI", "Gemini", "Ninguna"];
  const COLOR_AVATAR = ["#ff9ec0", "#ffd08a", "#a6ffc9", "#9fdcff", "#cdb2ff", "#ffb8a0"];

  const G = { caso: null, r: null, error: null, calculando: false, vista: "plan", ejemplo: false,
    seg: null, hist: [], hechos: {}, confirmarCierre: false };

  /* ------------------------------------------------------------ guardar y cargar */
  function guardar() {
    try { localStorage.setItem(CLAVE, JSON.stringify({ caso: G.caso, seg: G.seg, hist: G.hist, hechos: G.hechos, ejemplo: G.ejemplo })); } catch (_) { /* sin almacenamiento */ }
  }
  function leerGuardado() {
    try { return JSON.parse(localStorage.getItem(CLAVE) || "null"); } catch (_) { return null; }
  }
  const mesActual = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; };
  const nombreMes = m => { const [a, b] = m.split("-").map(Number); const t = new Date(a, b - 1, 1).toLocaleDateString("es-CO", { month: "long", year: "numeric" }); return t[0].toUpperCase() + t.slice(1); };
  const diasDe = m => { const [a, b] = m.split("-").map(Number); return new Date(a, b, 0).getDate(); };
  const siguienteMes = m => { const [a, b] = m.split("-").map(Number); return b === 12 ? `${a + 1}-01` : `${a}-${String(b + 1).padStart(2, "0")}`; };
  const nuevoSeg = mes => ({ mes, gastado: {}, recorte: false, dia: mes === mesActual() ? new Date().getDate() : 1 });
  let siguienteId = 1;
  const conId = p => (p.id ? p : { ...p, id: `p${siguienteId++}` });

  /* ------------------------------------------------------------ servidor */
  function paraEnviar() {
    // nombres únicos y no vacíos; números válidos
    const vistos = {};
    const personas = G.caso.personas.map((p, i) => {
      let nombre = String(p.nombre || "").trim() || `Persona ${i + 1}`;
      if (vistos[nombre]) nombre = `${nombre} ${++vistos[nombre]}`; else vistos[nombre] = 1;
      const n = v => Math.max(0, Number(v) || 0);
      return { ...p, nombre, equipo: String(p.equipo || "").trim() || "General", salario: n(p.salario), gasto: n(p.gasto) };
    });
    return { ...G.caso, personas, recorte: G.caso.recorte };
  }
  async function calcular() {
    const pedido = (calcular.n = (calcular.n || 0) + 1);
    G.calculando = true; pintarEstado();
    try {
      const res = await fetch("/api/resolver", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(paraEnviar()) });
      const cuerpo = await res.json().catch(() => ({}));
      if (pedido !== calcular.n) return false; // llegó otra versión más nueva
      if (!res.ok) throw new Error(String(cuerpo.detail || "No se pudo calcular el plan.").replace("No se pudo resolver con estos datos: ", ""));
      G.r = cuerpo; G.error = null;
      return true;
    } catch (e) {
      if (pedido === calcular.n) G.error = e.message;
      return false;
    } finally {
      if (pedido === calcular.n) { G.calculando = false; pintarEstado(); }
    }
  }
  let temporizador = null;
  function programar(despues) {
    guardar();
    clearTimeout(temporizador);
    G.calculando = true; pintarEstado();
    temporizador = setTimeout(async () => { const ok = await calcular(); if (despues) despues(ok); }, 650);
  }
  async function descargarExcel() {
    const res = await fetch("/api/excel", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(paraEnviar()) });
    if (!res.ok) return aviso("No se pudo generar el Excel con estos datos.", true);
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: "plan-gasto-ia.xlsx" });
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    aviso("Excel descargado.");
  }

  /* ------------------------------------------------------------ efectos */
  function aviso(texto, error = false) {
    const el = $("#aviso");
    el.textContent = texto;
    el.classList.toggle("error", error);
    el.classList.add("ver");
    clearTimeout(aviso.t);
    aviso.t = setTimeout(() => el.classList.remove("ver"), 3000);
  }
  function ola(el, medio) {
    // refresco suave: se atenúa el contenido y pasa un brillo; `medio` se ejecuta a mitad
    return new Promise(listo => {
      if (!el) return listo();
      if (!el.querySelector(":scope > .barrido")) el.insertAdjacentHTML("beforeend", '<div class="barrido"></div>');
      el.classList.remove("refresco"); void el.offsetWidth; el.classList.add("refresco");
      const dur = quieto ? 1 : 750;
      setTimeout(() => medio && medio(), dur * 0.35);
      setTimeout(() => { el.classList.remove("refresco"); listo(); }, dur);
    });
  }
  const lienzo = $("#particulas"), ctx = lienzo.getContext("2d");
  const motas = [], chispas = [];
  const COLORES = ["#ff5c93", "#ffb547", "#7dffb0", "#4dc3ff", "#a774ff"];
  function medir() { lienzo.width = innerWidth * devicePixelRatio; lienzo.height = innerHeight * devicePixelRatio; }
  addEventListener("resize", medir); medir();
  for (let i = 0; i < (innerWidth < 760 ? 28 : 56); i++) motas.push({ x: Math.random(), y: Math.random(), r: Math.random() * 1.2 + 0.3, v: Math.random() * 0.00012 + 0.00004, a: Math.random() * 0.35 + 0.05 });
  function estallido(x, y, n = 40) {
    if (quieto) return;
    for (let i = 0; i < n; i++) {
      const ang = Math.random() * Math.PI * 2, vel = Math.random() * 5 + 1.5;
      chispas.push({ x, y, vx: Math.cos(ang) * vel, vy: Math.sin(ang) * vel - 2, vida: 1, c: COLORES[i % COLORES.length], r: Math.random() * 2.2 + 1 });
    }
  }
  function animarParticulas() {
    const W = lienzo.width, H = lienzo.height, k = devicePixelRatio;
    ctx.clearRect(0, 0, W, H);
    for (const m of motas) {
      m.y -= m.v; if (m.y < 0) { m.y = 1; m.x = Math.random(); }
      ctx.fillStyle = `rgba(255,255,255,${m.a})`; ctx.beginPath(); ctx.arc(m.x * W, m.y * H, m.r * k, 0, 7); ctx.fill();
    }
    for (let i = chispas.length - 1; i >= 0; i--) {
      const c = chispas[i];
      c.x += c.vx; c.y += c.vy; c.vy += 0.12; c.vx *= 0.985; c.vida -= 0.016;
      if (c.vida <= 0) { chispas.splice(i, 1); continue; }
      ctx.globalAlpha = c.vida; ctx.fillStyle = c.c; ctx.shadowColor = c.c; ctx.shadowBlur = 10;
      ctx.beginPath(); ctx.arc(c.x * k, c.y * k, c.r * k, 0, 7); ctx.fill();
      ctx.globalAlpha = 1; ctx.shadowBlur = 0;
    }
    requestAnimationFrame(animarParticulas);
  }
  if (!quieto) requestAnimationFrame(animarParticulas);
  function contar(raiz = document) {
    $$("[data-contar]", raiz).forEach(el => {
      const fin = parseFloat(el.dataset.contar), dec = +(el.dataset.dec || 0), suf = el.dataset.suf || "";
      const desde = parseFloat(el.dataset.desde || 0);
      if (quieto) { el.innerHTML = fmt(fin, dec) + suf; return; }
      const t0 = performance.now(), dur = 1000;
      const paso = ahora => {
        const t = Math.min(1, (ahora - t0) / dur), e = 1 - Math.pow(1 - t, 3);
        el.innerHTML = fmt(desde + (fin - desde) * e, dec) + suf;
        if (t < 1) requestAnimationFrame(paso);
      };
      requestAnimationFrame(paso);
    });
  }
  function centro(el) { const b = el.getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2]; }

  /* ------------------------------------------------------------ datos derivados del plan */
  const P = () => G.r.datos.personas; // personas con los nombres con los que se calculó
  const asig = nombre => G.r.modelo0.asignacion.find(a => a.persona === nombre);
  const topes = () => (G.seg && G.seg.recorte ? G.r.recorte.modelo1.topes : G.r.modelo1.topes);
  const iniciales = n => n.split(/\s+/).map(x => x[0] || "").join("").slice(0, 2).toUpperCase();
  const colorDe = id => COLOR_AVATAR[(parseInt(String(id).replace(/\D/g, ""), 10) || 0) % COLOR_AVATAR.length];
  function donde(p, plan) {
    if (!plan) return "";
    if (plan.plan !== "Solo API") return `${plan.plan} · límite en su panel`;
    return p.herramienta === "Ninguna" ? "Pago por uso · la API que elija" : `Pago por uso · API de ${p.herramienta}`;
  }
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
    const m2 = G.r.modelo2, i = m2.origenes.indexOf("API en batch");
    if (i < 0) return { total: 0, equipos: [] };
    let total = 0; const eqs = [];
    m2.destinos.forEach((d, j) => { if (d !== "Ficticio" && m2.final.asignacion[i][j] > 1e-6) { total += m2.final.asignacion[i][j]; eqs.push(d); } });
    return { total, equipos: eqs };
  }

  /* ------------------------------------------------------------ pantalla 1: tus datos */
  function campoNumero(id, campo, etq, valor, sufijo = "USD") {
    return `<label class="campo"><span>${etq}</span><span class="con-sufijo"><input type="number" inputmode="decimal" min="0" step="10" data-id="${id}" data-campo="${campo}" value="${esc(valor)}"><b>${sufijo}</b></span></label>`;
  }
  function tarjetaPersona(p) {
    const eqs = [...new Set(G.caso.personas.map(x => x.equipo).filter(Boolean))];
    return `<div class="tarjeta persona" data-tarjeta="${p.id}">
      <div class="cab">
        <span class="avatar" style="background:${colorDe(p.id)}">${esc(iniciales(p.nombre || "?"))}</span>
        <label class="campo"><input data-id="${p.id}" data-campo="nombre" value="${esc(p.nombre)}" placeholder="Nombre" aria-label="Nombre" autocomplete="off"></label>
        <button class="btn fantasma icono" data-quitar="${p.id}" aria-label="Quitar a ${esc(p.nombre || "esta persona")}" title="Quitar">✕</button>
      </div>
      <div class="rejilla">
        <label class="campo"><span>Equipo</span><input data-id="${p.id}" data-campo="equipo" value="${esc(p.equipo)}" list="equipos" autocomplete="off"></label>
        <label class="campo"><span>Herramienta que usa</span><select data-id="${p.id}" data-campo="herramienta">${HERRAMIENTAS.map(h => `<option ${h === p.herramienta ? "selected" : ""}>${h}</option>`).join("")}</select></label>
        ${campoNumero(p.id, "salario", "Salario al mes", p.salario)}
        ${campoNumero(p.id, "gasto", "Gastó en IA el mes pasado", p.gasto)}
      </div>
      <datalist id="equipos">${eqs.map(e => `<option value="${esc(e)}">`).join("")}</datalist>
    </div>`;
  }
  function resumenDatos() {
    const ps = G.caso.personas, nom = ps.reduce((s, p) => s + (Number(p.salario) || 0), 0), gas = ps.reduce((s, p) => s + (Number(p.gasto) || 0), 0);
    return `<span><b>${ps.length}</b> ${ps.length === 1 ? "persona" : "personas"}</span><span>Nómina <b>${usd(nom)}</b></span><span>Gastaron en IA <b>${usd(gas)}</b>${nom ? ` · ${fmt((gas / nom) * 100, 1)} % de la nómina` : ""}</span>`;
  }
  function deslizador(id, etq, valor, min, max, paso, formato, ayuda) {
    return `<div class="rango"><label for="${id}">${etq} <b id="${id}-v">${formato(valor)}</b></label><input id="${id}" type="range" min="${min}" max="${max}" step="${paso}" value="${valor}">${ayuda ? `<small>${ayuda}</small>` : ""}</div>`;
  }
  function pantallaDatos() {
    const reg = G.caso.reglas;
    return `<section class="pantalla">
      <div class="titulo">
        <h1>Tu equipo y lo que gastó en IA el mes pasado</h1>
        <p>Con el salario, la herramienta y el gasto del mes pasado de cada programador armamos el plan. No hace falta saber nada de tokens.</p>
        ${G.ejemplo ? `<p style="margin-top:12px;font-size:13.5px"><span class="chip ojo">Datos de ejemplo</span> Cámbialos por los tuyos o <a href="#" data-accion="vaciar">empieza en blanco</a>.</p>` : ""}
      </div>
      <div class="lista dos" id="listaPersonas">${G.caso.personas.map(tarjetaPersona).join("")}</div>
      <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap"><button class="btn" data-accion="agregar">＋ Agregar programador</button></div>
      <div class="resumen-datos" id="resumenDatos">${resumenDatos()}</div>
      <div class="seccion">
        <details class="avanzado">
          <summary><span><b style="font-weight:600">Reglas de la empresa</b><br><span class="tenue" style="font-size:13px">Opcional · ya vienen con valores recomendados</span></span></summary>
          <div class="dentro">
            ${deslizador("rPres", "Gasto extra máximo", reg.presupuesto_pct_nomina * 100, 1, 15, 0.5, v => `${fmt(v, 1)} % de la nómina`, "Lo que se paga aparte de las cuotas de los asientos.")}
            ${deslizador("rTope", "Tope por persona", reg.tope_pct_salario * 100, 5, 30, 1, v => `${fmt(v)} % del salario`, "Nadie usa más que esto en IA.")}
            ${deslizador("rMin", "Mínimo por persona", reg.minimo, 0, 150, 10, v => usd(v), "Nadie se queda sin IA.")}
          </div>
        </details>
      </div>
      <div class="accion"><div class="dentro">
        <a class="btn primario ancho beam" style="--vel:3s" href="#plan" id="verPlan">Ver mi plan →</a>
        <div class="nota" id="notaEstado"></div>
      </div></div>
    </section>`;
  }
  function montarDatos() {
    const lista = $("#listaPersonas");
    lista.addEventListener("input", e => {
      const el = e.target.closest("[data-campo]"); if (!el) return;
      const p = G.caso.personas.find(x => x.id === el.dataset.id); if (!p) return;
      p[el.dataset.campo] = el.type === "number" ? (el.value === "" ? "" : Number(el.value)) : el.value;
      if (el.dataset.campo === "nombre") $(`[data-tarjeta="${p.id}"] .avatar`).textContent = iniciales(p.nombre || "?");
      $("#resumenDatos").innerHTML = resumenDatos();
      G.ejemplo = false;
      programar();
    });
    lista.addEventListener("change", e => { if (e.target.tagName === "SELECT") e.target.dispatchEvent(new Event("input", { bubbles: true })); });
    const unir = (id, aplicar, formato) => {
      const el = $(`#${id}`);
      el.addEventListener("input", () => { $(`#${id}-v`).textContent = formato(+el.value); });
      el.addEventListener("change", () => { aplicar(+el.value); programar(); });
    };
    unir("rPres", v => (G.caso.reglas.presupuesto_pct_nomina = v / 100), v => `${fmt(v, 1)} % de la nómina`);
    unir("rTope", v => (G.caso.reglas.tope_pct_salario = v / 100), v => `${fmt(v)} % del salario`);
    unir("rMin", v => (G.caso.reglas.minimo = v), v => usd(v));
  }

  /* ------------------------------------------------------------ pantalla 2: tu plan */
  function tareasDelPlan() {
    const r = G.r, mes = G.seg.mes, t = [];
    const grupos = {};
    r.modelo0.asignacion.forEach(a => { (grupos[a.plan] = grupos[a.plan] || []).push(a); });
    Object.entries(grupos).forEach(([plan, xs]) => {
      if (xs[0].cuota > 0) t.push({ k: `asiento-${plan}`, b: `Contrata ${xs.length} ${xs.length === 1 ? "asiento" : "asientos"} de ${plan}`, s: `${usd(xs[0].cuota * xs.length)} al mes · para ${xs.map(x => x.persona).join(", ")}` });
    });
    if (grupos["Solo API"]) t.push({ k: "api", b: `Deja a ${grupos["Solo API"].map(x => x.persona).join(", ")} con pago por uso`, s: "No les conviene un asiento: pagan solo lo que usan." });
    t.push({ k: "topes", b: "Pon un límite de gasto a cada persona", s: "En el panel de cada herramienta. Los valores están en «Por persona»." });
    const bt = flujoBatch();
    if (bt.total > 0) t.push({ k: "batch", b: `Manda ${usd(bt.total)} de trabajo que pueda esperar a la API en batch`, s: `Pruebas, documentación o revisiones de la noche de ${bt.equipos.join(" y ")}: cuesta la mitad.` });
    const tp = r.modelo1.topes;
    const altos = P().filter(p => p.gasto - tp[p.nombre] > 0.5).map(p => p.nombre);
    if (altos.length) t.push({ k: "altos", b: `Habla con ${altos.join(", ")}`, s: "El mes pasado gastaron más que su tope. Lo que recortan es lo que menos les rendía." });
    const bajos = P().filter(p => tp[p.nombre] - p.gasto > 20).map(p => p.nombre);
    if (bajos.length) t.push({ k: "bajos", b: `Anima a ${bajos.join(", ")} a usar más la IA`, s: "Tienen espacio y cada dólar ahí rinde más que en otros." });
    return t.map(x => ({ ...x, k: `${mes}:${x.k}` }));
  }
  function filaPlan(p) {
    const tp = G.r.modelo1.topes[p.nombre], a = asig(p.nombre), dif = p.gasto - tp;
    const max = Math.max(tp, p.gasto, 1);
    const chip = dif > 0.5 ? `<span class="chip mal">Bajar ${usd(dif)}</span>` : dif < -0.5 ? `<span class="chip bien">Puede usar ${usd(-dif)} más</span>` : `<span class="chip ok">Justo</span>`;
    const c = G.caso.personas.find(x => x.id === p.id) || p;
    return `<div class="tarjeta fila-persona">
      <div class="arriba">
        <span class="avatar" style="background:${colorDe(p.id)}">${esc(iniciales(p.nombre))}</span>
        <div class="nombre"><b>${esc(p.nombre)}</b><span>${esc(donde(p, a))}</span></div>
        <div class="tope"><b>${usd(tp)}</b><span>tope al mes</span></div>
      </div>
      <div class="barra" aria-label="Mes pasado ${usd(p.gasto)} contra tope ${usd(tp)}"><i class="lleno ${dif > 0.5 ? "mal" : ""}" style="width:${(Math.min(p.gasto, max) / max) * 100}%"></i><i class="marca-tope" style="left:calc(${(tp / max) * 100}% - 1px)"></i></div>
      <div class="leyenda-barra"><span>Mes pasado ${usd(p.gasto)}</span><span>Tope ${usd(tp)}</span></div>
      <div class="linea-chips"><span class="chip plan">${esc(a ? a.plan : "")}</span>${chip}<button class="btn fantasma chico" data-editar="${p.id}" style="margin-left:auto">Editar</button></div>
      <div class="editar" id="ed-${p.id}" hidden>
        <div class="rejilla">
          ${campoNumero(p.id, "gasto", "Gastó el mes pasado", c.gasto)}
          ${campoNumero(p.id, "salario", "Salario al mes", c.salario)}
          <label class="campo"><span>Herramienta</span><select data-id="${p.id}" data-campo="herramienta">${HERRAMIENTAS.map(h => `<option ${h === c.herramienta ? "selected" : ""}>${h}</option>`).join("")}</select></label>
          <label class="campo"><span>Equipo</span><input data-id="${p.id}" data-campo="equipo" value="${esc(c.equipo)}"></label>
        </div>
      </div>
    </div>`;
  }
  function pantallaPlan() {
    if (!G.r) return `<section class="pantalla"><div class="titulo"><h1>Tu plan</h1><p>${G.error ? `<span class="rojo">${esc(G.error)}</span>` : "Calculando…"}</p></div>${G.error ? `<a class="btn" href="#datos">Revisar los datos</a>` : ""}</section>`;
    const r = G.r, R = r.resultado, ahorro = R.factura_antes - R.factura;
    const hAhora = P().reduce((s, p) => s + horas(r, p.nombre), 0), hAntes = P().reduce((s, p) => s + horasCon(r, p.gasto), 0);
    const ps = r.modelo1.precio_sombra.presupuesto, rg = r.rango_presupuesto, reg = r.datos.reglas;
    const rec = r.recorte.modelo1, cambios = P().filter(p => Math.abs(rec.topes[p.nombre] - r.modelo1.topes[p.nombre]) > 0.5);
    const tareas = tareasDelPlan();
    const textoPresupuesto = ps > 0.005
      ? `Subir el presupuesto <b>100 USD</b> te dejaría unos <b>${usd(ps * 100)}</b> más de valor neto. Vale mientras el gasto extra esté entre ${usd(rg.desde)} y ${usd(rg.hasta)}.`
      : `Ya tienes presupuesto de sobra: subirlo no aporta nada. Podrías bajar el gasto extra hasta <b>${usd(rg.desde)}</b> sin perder valor.`;
    return `<section class="pantalla">
      ${G.error ? `<p class="rojo" style="margin:0 0 12px">${esc(G.error)} Se muestra el último plan que sí se pudo calcular.</p>` : ""}
      <div class="columnas">
        <div class="col">
          <div class="tarjeta factura beam" style="--vel:4.5s" id="factura"><div class="contenido">
            <div class="etq">Factura de IA de ${esc(nombreMes(G.seg.mes).toLowerCase())}</div>
            <div class="monto"><span data-contar="${R.factura}" data-desde="${R.factura_antes}">${fmt(R.factura)}</span> <small>USD</small></div>
            <div class="tenue" style="font-size:13.5px">antes ${usd(R.factura_antes)}</div>
            <div class="insignia ${ahorro < 0 ? "mala" : ""}">${ahorro >= 0 ? `Ahorras ${usd(ahorro)} · ${fmt((ahorro / Math.max(R.factura_antes, 1)) * 100)} %` : `Sube ${usd(-ahorro)}, pero rinde más`}</div>
            <div class="mini-cifras">
              <div><span>Tiempo que ahorra la IA</span><b>${fmt(hAhora)} h</b><span>antes ${fmt(hAntes)} h</span></div>
              <div><span>Valor neto</span><b>${usd(R.neto)}</b><span>antes ${usd(R.neto_antes)}</span></div>
              <div><span>Cuotas fijas</span><b>${usd(R.cuotas)}</b><span>+ ${usd(R.pago_variable)} por uso</span></div>
            </div>
          </div></div>
          <div class="acciones-plan">
            <a class="btn primario ancho solo-escritorio" href="#seguimiento">Hacerle seguimiento al mes →</a>
            <div class="secundarias"><a class="btn" href="/clase/#modelo0">Ver el cálculo paso a paso</a><button class="btn fantasma" data-accion="excel">Descargar Excel</button></div>
            <p>Calculado con programación lineal: método húngaro, Simplex, método gráfico, transporte con Vogel y MODI, sensibilidad y Dual Simplex.</p>
          </div>
          <div class="seccion"><h2>Qué hacer este mes <span>${tareas.filter(t => G.hechos[t.k]).length} de ${tareas.length}</span></h2>
            <div class="tareas">${tareas.map(t => `<label class="tarea ${G.hechos[t.k] ? "hecha" : ""}"><input type="checkbox" data-tarea="${esc(t.k)}" ${G.hechos[t.k] ? "checked" : ""}><div><b>${esc(t.b)}</b><span>${esc(t.s)}</span></div></label>`).join("")}</div>
          </div>
        </div>
        <div class="col">
          <div class="seccion"><h2>Por persona</h2><div class="lista" id="listaPlan">${P().map(filaPlan).join("")}</div></div>
          <div class="seccion"><h2>¿Y si cambio el presupuesto?</h2>
            <div class="tarjeta indicador">
              ${deslizador("pPres", "Gasto extra máximo", reg.presupuesto_pct_nomina * 100, 1, 15, 0.5, v => `${fmt(v, 1)} % · ${usd((v / 100) * r.datos.nomina)}`)}
              <p style="margin:0;color:var(--tx-2);font-size:14px">${textoPresupuesto}</p>
            </div>
          </div>
          <div class="seccion"><h2>Si recortan el presupuesto a mitad de mes</h2>
            <div class="tarjeta indicador">
              ${deslizador("pRec", "Recorte", r.datos.recorte * 100, 5, 50, 5, v => `${fmt(v)} %`)}
              <div class="cambios">
                ${cambios.length ? cambios.map(p => `<div><span>${esc(p.nombre)}</span><span>${usd(r.modelo1.topes[p.nombre])} → <b>${usd(rec.topes[p.nombre])}</b></span></div>`).join("") : `<div><span>Nadie cambia</span><span>el presupuesto sobraba</span></div>`}
                <div><span>Factura nueva</span><b>${usd(r.recorte.factura)}</b></div>
              </div>
              <p style="margin:0;color:var(--tx-3);font-size:13px">Bajan primero los que menos rinden en su último dólar; el resto no se toca.</p>
              <button class="btn" data-accion="aplicarRecorte">${G.seg.recorte ? "Recorte aplicado en el seguimiento ✓" : "Aplicar este recorte en el seguimiento"}</button>
            </div>
          </div>
        </div>
      </div>
      <div class="accion solo-movil"><div class="dentro"><a class="btn primario ancho" href="#seguimiento">Hacerle seguimiento al mes →</a><div class="nota" id="notaEstado"></div></div></div>
    </section>`;
  }
  function montarPlan() {
    const lista = $("#listaPlan");
    if (!lista) return;
    lista.addEventListener("click", e => {
      const b = e.target.closest("[data-editar]"); if (!b) return;
      const ed = $(`#ed-${b.dataset.editar}`); ed.hidden = !ed.hidden; b.textContent = ed.hidden ? "Editar" : "Listo";
      if (!ed.hidden) ed.querySelector("input").focus();
    });
    lista.addEventListener("change", e => {
      const el = e.target.closest("[data-campo]"); if (!el) return;
      const p = G.caso.personas.find(x => x.id === el.dataset.id); if (!p) return;
      p[el.dataset.campo] = el.type === "number" ? Number(el.value) || 0 : el.value;
      G.ejemplo = false;
      recalcularConOnda();
    });
    $$(".tarea input").forEach(c => c.addEventListener("change", () => {
      G.hechos[c.dataset.tarea] = c.checked; guardar();
      c.closest(".tarea").classList.toggle("hecha", c.checked);
      if (c.checked) estallido(...centro(c), 18);
      const tareas = tareasDelPlan();
      $(".seccion h2 span").textContent = `${tareas.filter(t => G.hechos[t.k]).length} de ${tareas.length}`;
    }));
    const unir = (id, aplicar, formato) => {
      const el = $(`#${id}`);
      el.addEventListener("input", () => { $(`#${id}-v`).textContent = formato(+el.value); });
      el.addEventListener("change", () => { aplicar(+el.value); recalcularConOnda(); });
    };
    unir("pPres", v => (G.caso.reglas.presupuesto_pct_nomina = v / 100), v => `${fmt(v, 1)} % · ${usd((v / 100) * G.r.datos.nomina)}`);
    unir("pRec", v => (G.caso.recorte = v / 100), v => `${fmt(v)} %`);
    const b = $("#factura .insignia");
    if (b && !montarPlan.yaFesteje) { montarPlan.yaFesteje = true; setTimeout(() => estallido(...centro(b), 30), 500); }
  }
  async function recalcularConOnda() {
    guardar();
    clearTimeout(temporizador);
    const antes = G.r && G.r.resultado.factura;
    const trabajo = calcular();
    await ola($("#factura"));
    const ok = await trabajo;
    if (G.vista === "plan") {
      const y = scrollY;
      render(false);
      scrollTo(0, y);
      if (ok && antes != null) aviso(`Plan recalculado: ${usd(G.r.resultado.factura)} al mes.`);
    }
  }

  /* ------------------------------------------------------------ pantalla 3: seguimiento */
  function estadoDe(p) {
    const t = topes()[p.nombre], g = G.seg.gastado[p.id], dias = diasDe(G.seg.mes), dia = Math.max(1, Math.min(G.seg.dia, dias));
    if (g == null || g === "") return { t, g: 0, proy: 0, clase: "", chip: `<span class="chip">Sin dato</span>`, nivel: 0 };
    const proy = (g / dia) * dias;
    if (g > t + 0.5) return { t, g, proy, clase: "mal", chip: `<span class="chip mal">Se pasó ${usd(g - t)}</span>`, nivel: 2 };
    if (proy > t + 0.5) return { t, g, proy, clase: "ojo", chip: `<span class="chip ojo">A este ritmo llega a ${usd(proy)}</span>`, nivel: 1 };
    return { t, g, proy, clase: "", chip: `<span class="chip bien">Va bien</span>`, nivel: 0 };
  }
  function barraSeg(p) {
    const s = estadoDe(p), max = Math.max(s.t, s.g, s.proy, 1);
    return `<div class="barra"><i class="lleno ${s.clase}" style="width:${(s.g / max) * 100}%"></i>${s.proy > 0 ? `<i class="proy" style="left:calc(${(Math.min(s.proy, max) / max) * 100}% - 1px)" title="Proyección a fin de mes"></i>` : ""}<i class="marca-tope" style="left:calc(${(s.t / max) * 100}% - 1px)"></i></div>
      <div class="leyenda-barra"><span>Lleva ${usd(s.g)}${s.proy > 0 ? ` · cierra en ~${usd(s.proy)}` : ""}</span><span>Tope ${usd(s.t)}</span></div>`;
  }
  function totalesSeg() {
    const ps = P(), tp = topes();
    const g = ps.reduce((s, p) => s + (Number(G.seg.gastado[p.id]) || 0), 0), t = ps.reduce((s, p) => s + tp[p.nombre], 0);
    const dias = diasDe(G.seg.mes), dia = Math.max(1, Math.min(G.seg.dia, dias));
    const alertas = ps.filter(p => estadoDe(p).nivel > 0).length;
    return { g, t, proy: (g / dia) * dias, alertas };
  }
  function pintarTotales() {
    const T = totalesSeg(), el = $("#totalesSeg");
    if (!el) return;
    el.innerHTML = `<div><span>Uso hasta hoy</span><b>${usd(T.g)}</b><span>de ${usd(T.t)} en topes</span></div>
      <div><span>Cierre estimado</span><b class="${T.proy > T.t + 0.5 ? "ambar" : ""}">${usd(T.proy)}</b><span>al ritmo actual</span></div>
      <div><span>Alertas</span><b class="${T.alertas ? "rojo" : "verde"}">${T.alertas}</b><span>${T.alertas ? "personas a revisar" : "todo en orden"}</span></div>`;
    pintarFlujo();
  }
  function pantallaSeguimiento() {
    if (!G.r) return pantallaPlan();
    const dias = diasDe(G.seg.mes);
    const filas = P().map(p => {
      const a = asig(p.nombre), v = G.seg.gastado[p.id];
      return `<div class="tarjeta fila-persona" data-seg="${p.id}">
        <div class="arriba">
          <span class="avatar" style="background:${colorDe(p.id)}">${esc(iniciales(p.nombre))}</span>
          <div class="nombre"><b>${esc(p.nombre)}</b><span>${esc(donde(p, a))}</span></div>
          <label class="campo" style="width:128px"><span class="con-sufijo"><input type="number" inputmode="decimal" min="0" step="5" data-gastado="${p.id}" value="${v == null ? "" : esc(v)}" placeholder="0" aria-label="Lo que lleva gastado ${esc(p.nombre)}"><b>USD</b></span></label>
        </div>
        <div class="b">${barraSeg(p)}</div>
        <div class="linea-chips e">${estadoDe(p).chip}</div>
      </div>`;
    }).join("");
    const hist = G.hist.slice(-6).reverse();
    const maxH = Math.max(1, ...hist.map(h => Math.max(h.antes, h.real)));
    return `<section class="pantalla">
      <div class="titulo">
        <h1>Gasto de ${esc(nombreMes(G.seg.mes).split(" ")[0].toLowerCase())}, persona por persona</h1>
        <p>Copia lo que lleva cada uno según el panel de su herramienta. Con eso calculamos cómo cerrará el mes y avisamos antes de que alguien se pase.</p>
      </div>
      <div class="columnas">
        <div class="col">
          <div class="tarjeta" id="tarjetaMes"><div class="contenido" style="display:grid;gap:14px">
            <div class="mes"><b>${esc(nombreMes(G.seg.mes))}</b>${G.seg.recorte ? `<button class="chip ojo" data-accion="quitarRecorte" style="border:0;cursor:pointer">Con recorte del ${fmt(G.r.datos.recorte * 100)} % ✕</button>` : ""}</div>
            ${deslizador("sDia", "Vamos en el día", G.seg.dia, 1, dias, 1, v => `${v} de ${dias}`)}
            <div class="mini-cifras" id="totalesSeg"></div>
          </div></div>
          <div class="seccion"><h2>Por persona</h2><div class="lista" id="listaSeg">${filas}</div></div>
        </div>
        <div class="col">
          <div class="seccion"><h2>Cerrar el mes</h2>
            <div class="tarjeta" style="display:grid;gap:12px">
              <p style="margin:0;color:var(--tx-2);font-size:14px">Cuando termine el mes, lo que gastó cada persona pasa a ser su dato del mes pasado y se calcula el plan del siguiente. Así el plan se ajusta solo, mes a mes.</p>
              <button class="btn ${G.confirmarCierre ? "primario" : ""}" data-accion="cerrar">${G.confirmarCierre ? "Toca otra vez para confirmar" : `Cerrar ${esc(nombreMes(G.seg.mes))} y planear el siguiente`}</button>
            </div>
          </div>
          ${hist.length ? `<div class="seccion"><h2>Meses anteriores</h2><div class="tarjeta historial">${hist.map(h => `<div class="h"><span>${esc(nombreMes(h.mes))}</span><b>${usd(h.real)}</b><div class="barra"><i class="lleno ${h.real > h.plan + 0.5 ? "ojo" : ""}" style="width:${(h.real / maxH) * 100}%"></i><i class="marca-tope" style="left:calc(${(Math.min(h.plan, maxH) / maxH) * 100}% - 1px)"></i></div><small class="tenue" style="grid-column:1/3">Uso real ${usd(h.real)} · topes ${usd(h.plan)} · antes del plan se gastaba ${usd(h.antes)}</small></div>`).join("")}</div></div>` : ""}
        </div>
      </div>
      <div class="accion"><div class="dentro"><a class="btn ancho" href="#plan">← Ver el plan</a><div class="nota" id="notaEstado"></div></div></div>
    </section>`;
  }
  function montarSeguimiento() {
    const lista = $("#listaSeg"); if (!lista) return;
    pintarTotales();
    lista.addEventListener("input", e => {
      const el = e.target.closest("[data-gastado]"); if (!el) return;
      const id = el.dataset.gastado;
      if (el.value === "") delete G.seg.gastado[id]; else G.seg.gastado[id] = Math.max(0, Number(el.value) || 0);
      G.seg.registro = G.seg.registro || {};
      G.seg.registro[G.seg.dia] = P().reduce((s2, x) => s2 + (Number(G.seg.gastado[x.id]) || 0), 0);
      guardar();
      const p = P().find(x => x.id === id), fila = $(`[data-seg="${id}"]`);
      $(".b", fila).innerHTML = barraSeg(p);
      $(".e", fila).innerHTML = estadoDe(p).chip;
      pintarTotales();
    });
    const dia = $("#sDia");
    dia.addEventListener("input", () => {
      G.seg.dia = +dia.value; $("#sDia-v").textContent = `${dia.value} de ${diasDe(G.seg.mes)}`;
      P().forEach(p => { const f = $(`[data-seg="${p.id}"]`); $(".b", f).innerHTML = barraSeg(p); $(".e", f).innerHTML = estadoDe(p).chip; });
      pintarTotales();
    });
    dia.addEventListener("change", guardar);
  }
  async function cerrarMes(boton) {
    if (!G.confirmarCierre) { G.confirmarCierre = true; render(false); setTimeout(() => { if (G.confirmarCierre) { G.confirmarCierre = false; if (G.vista === "seguimiento") render(false); } }, 5000); return; }
    G.confirmarCierre = false;
    const tp = topes();
    const real = P().reduce((s, p) => s + (Number(G.seg.gastado[p.id]) || 0), 0);
    G.hist.push({ mes: G.seg.mes, real, plan: P().reduce((s, p) => s + tp[p.nombre], 0), antes: G.r.resultado.factura_antes, factura: G.r.resultado.factura });
    G.caso.personas.forEach(p => { if (G.seg.gastado[p.id] != null) p.gasto = Number(G.seg.gastado[p.id]) || 0; });
    G.seg = nuevoSeg(siguienteMes(G.seg.mes));
    G.ejemplo = false;
    guardar();
    const xy = boton ? centro(boton) : [innerWidth / 2, innerHeight / 2];
    await calcular();
    estallido(...xy, 50);
    aviso(`Listo: plan de ${nombreMes(G.seg.mes)} calculado con el gasto real.`);
    location.hash = "#panel";
  }


  /* ------------------------------------------------------------ pantalla 0: panel principal */
  function graficaMes() {
    // uso acumulado del mes contra la suma de topes, con la proyección al cierre
    const dias = diasDe(G.seg.mes), T = totalesSeg(), reg = G.seg.registro || {};
    const W = 340, H = 150, x0 = 30, x1 = 330, y0 = 12, y1 = 124;
    const puntos = Object.entries(reg).map(([d, v]) => [+d, v]).filter(([d]) => d <= G.seg.dia).sort((a, b) => a[0] - b[0]);
    if (!puntos.length || puntos[puntos.length - 1][0] !== G.seg.dia) puntos.push([G.seg.dia, T.g]);
    const max = Math.max(T.t, T.proy, 1) * 1.12;
    const X = d => x0 + ((d - 0) / dias) * (x1 - x0), Y = v => y1 - (v / max) * (y1 - y0);
    const real = [[0, 0], ...puntos].map(([d, v]) => `${X(d).toFixed(1)},${Y(v).toFixed(1)}`).join(" ");
    const pasa = T.proy > T.t + 0.5;
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Uso acumulado del mes contra los topes">
      <defs><linearGradient id="gReal" x1="0" x2="1"><stop offset="0" stop-color="#4dc3ff"/><stop offset="1" stop-color="#a774ff"/></linearGradient>
      <linearGradient id="gArea" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#a774ff" stop-opacity=".28"/><stop offset="1" stop-color="#a774ff" stop-opacity="0"/></linearGradient></defs>`;
    [0, 0.5, 1].forEach(f => { const v = max * f; s += `<line x1="${x0}" x2="${x1}" y1="${Y(v)}" y2="${Y(v)}" stroke="rgba(255,255,255,.06)"/><text x="${x0 - 6}" y="${Y(v) + 4}" text-anchor="end" font-size="9">${fmt(v)}</text>`; });
    s += `<line x1="${x0}" x2="${x1}" y1="${Y(T.t)}" y2="${Y(T.t)}" stroke="#fff" stroke-opacity=".7" stroke-dasharray="3 4"/><text x="${x1}" y="${Y(T.t) - 5}" text-anchor="end" font-size="9.5" style="fill:#fff">topes ${usd(T.t)}</text>`;
    s += `<polygon points="${X(0)},${y1} ${real} ${X(puntos[puntos.length - 1][0])},${y1}" fill="url(#gArea)"/>`;
    s += `<polyline points="${real}" fill="none" stroke="url(#gReal)" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round" class="trazo"/>`;
    if (T.g > 0) s += `<line x1="${X(G.seg.dia)}" y1="${Y(T.g)}" x2="${X(dias)}" y2="${Y(T.proy)}" stroke="${pasa ? "#ffb547" : "#8db0ff"}" stroke-width="1.8" stroke-dasharray="4 4"/><circle cx="${X(dias)}" cy="${Y(T.proy)}" r="3.5" fill="${pasa ? "#ffb547" : "#8db0ff"}"/>`;
    s += `<circle cx="${X(G.seg.dia)}" cy="${Y(T.g)}" r="4.5" fill="#fff"/>`;
    s += `<text x="${x0}" y="${H - 4}" font-size="9">día 1</text><text x="${x1}" y="${H - 4}" text-anchor="end" font-size="9">día ${dias}</text></svg>`;
    return s;
  }
  function graficaMeses() {
    const filas = G.hist.slice(-5).map(h => ({ mes: h.mes, antes: h.antes, con: h.factura }));
    filas.push({ mes: G.seg.mes, antes: G.r.resultado.factura_antes, con: G.r.resultado.factura, actual: true });
    const max = Math.max(1, ...filas.map(f => Math.max(f.antes, f.con)));
    return `<div class="meses">${filas.map(f => `<div class="m ${f.actual ? "actual" : ""}">
      <div class="col-barras"><i class="b-antes" style="height:${(f.antes / max) * 100}%" title="Sin el plan ${usd(f.antes)}"></i><i class="b-con" style="height:${(f.con / max) * 100}%" title="Con el plan ${usd(f.con)}"></i></div>
      <span>${esc(nombreMes(f.mes).split(" ")[0].slice(0, 3))}</span></div>`).join("")}</div>
      <div class="leyenda"><span><i style="background:rgba(255,255,255,.22)"></i>Gasto del mes anterior</span><span><i style="background:linear-gradient(#a774ff,#4dc3ff)"></i>Factura con el plan</span></div>`;
  }
  function pantallaPanel() {
    if (!G.r) return pantallaPlan();
    const R = G.r.resultado, T = totalesSeg(), tp = topes(), ahorro = R.factura_antes - R.factura;
    const ahorroTotal = G.hist.reduce((s, h) => s + (h.antes - h.factura), 0) + ahorro;
    const hAhora = P().reduce((s, p) => s + horas(G.r, p.nombre), 0);
    const anotados = P().filter(p => G.seg.gastado[p.id] != null).length;
    const alertas = P().map(p => ({ p, s: estadoDe(p) })).filter(x => x.s.nivel > 0).sort((a, b) => b.s.nivel - a.s.nivel);
    const tareas = tareasDelPlan(), hechas = tareas.filter(t => G.hechos[t.k]).length;
    const eqs = [...new Set(P().map(p => p.equipo))].map(eq => {
      const gente = P().filter(p => p.equipo === eq);
      return { eq, t: gente.reduce((s, p) => s + tp[p.nombre], 0), g: gente.reduce((s, p) => s + (Number(G.seg.gastado[p.id]) || 0), 0), n: gente.length };
    });
    const pct = T.t ? (T.g / T.t) * 100 : 0;
    return `<section class="pantalla">
      <div class="titulo">
        <h1>${esc(nombreMes(G.seg.mes).split(" ")[0])}${anotados ? ` va en ${usd(T.g)} de ${usd(T.t)}` : `: factura estimada de ${usd(R.factura)}`}</h1>
        <p>${alertas.length ? `${alertas.length === 1 ? "Una persona va" : `${alertas.length} personas van`} camino de pasarse de su tope.` : anotados ? "Nadie va camino de pasarse de su tope." : "Anota el gasto del mes para ver cómo va cada persona."} ${ahorro > 0 ? `Con el plan pagas ${usd(ahorro)} menos que el mes pasado.` : ""}</p>
      </div>
      <div class="kpis">
        <a class="tarjeta kpi beam" style="--vel:5s" href="#plan"><span>Factura estimada</span><b><span data-contar="${R.factura}" data-desde="${R.factura_antes}">${fmt(R.factura)}</span> <small>USD</small></b><em>antes ${usd(R.factura_antes)}</em></a>
        <a class="tarjeta kpi" href="#seguimiento"><span>Uso hasta hoy</span><b><span data-contar="${T.g}">${fmt(T.g)}</span> <small>USD</small></b><div class="barra fina"><i class="lleno ${T.proy > T.t + 0.5 ? "ojo" : ""}" style="width:${Math.min(100, pct)}%"></i></div><em>${fmt(pct)} % de los topes · día ${G.seg.dia}</em></a>
        <a class="tarjeta kpi" href="#plan"><span>Ahorro ${G.hist.length ? "acumulado" : "del mes"}</span><b class="verde"><span data-contar="${ahorroTotal}">${fmt(ahorroTotal)}</span> <small>USD</small></b><em>${fmt((ahorro / Math.max(R.factura_antes, 1)) * 100)} % menos este mes</em></a>
        <a class="tarjeta kpi" href="#plan"><span>Tiempo que ahorra la IA</span><b><span data-contar="${hAhora}">${fmt(hAhora)}</span> <small>h</small></b><em>valor ${usd(R.valor)}</em></a>
      </div>
      <div class="columnas">
        <div class="col">
          <div class="seccion"><h2>Gasto del mes <a href="#seguimiento" class="enlace">Anotar gasto →</a></h2>
            <div class="tarjeta">
              ${anotados ? graficaMes() : `<div class="vacio"><b>Aún no has anotado el gasto de este mes</b><span>Toma 1 minuto: copia lo que muestra el panel de cada herramienta.</span><a class="btn chico" href="#seguimiento">Anotar ahora</a></div>`}
              ${anotados ? `<div class="leyenda-barra" style="margin-top:6px"><span>${anotados} de ${P().length} personas con dato</span><span class="${T.proy > T.t + 0.5 ? "ambar" : ""}">Cierre estimado ${usd(T.proy)}</span></div>` : ""}
            </div>
          </div>
          <div class="seccion"><h2>Por equipo</h2>
            <div class="tarjeta lista">${eqs.map(e => { const max = Math.max(e.t, e.g, 1); return `<div style="display:grid;gap:6px">
              <div class="leyenda-barra" style="color:var(--tx-2)"><span><b style="color:var(--tx);font-weight:600">${esc(e.eq)}</b> · ${e.n} ${e.n === 1 ? "persona" : "personas"}</span><span>${usd(e.g)} de ${usd(e.t)}</span></div>
              <div class="barra"><i class="lleno ${e.g > e.t + 0.5 ? "mal" : ""}" style="width:${(e.g / max) * 100}%"></i><i class="marca-tope" style="left:calc(${(e.t / max) * 100}% - 1px)"></i></div></div>`; }).join("")}</div>
          </div>
        </div>
        <div class="col">
          <div class="seccion"><h2>Alertas <span>${alertas.length}</span></h2>
            <div class="lista">${alertas.length ? alertas.map(({ p, s }) => `<a class="tarjeta alerta-fila" href="#seguimiento"><span class="avatar" style="background:${colorDe(p.id)}">${esc(iniciales(p.nombre))}</span><div><b>${esc(p.nombre)}</b><span>${s.nivel === 2 ? `Se pasó: lleva ${usd(s.g)} de ${usd(s.t)}` : `A este ritmo cierra en ${usd(s.proy)} (tope ${usd(s.t)})`}</span></div><i class="punto ${s.nivel === 2 ? "mal" : "ojo"}"></i></a>`).join("")
              : `<div class="tarjeta vacio"><b>${anotados ? "Todo en orden" : "Sin alertas por ahora"}</b><span>${anotados ? "Nadie va camino de pasarse de su tope." : "Aparecen cuando anotes el gasto del mes."}</span></div>`}</div>
          </div>
          <div class="seccion"><h2>Mes a mes</h2><div class="tarjeta">${graficaMeses()}</div></div>
          <div class="seccion"><h2>Qué hacer este mes <a href="#plan" class="enlace">Ver plan →</a></h2>
            <a class="tarjeta progreso" href="#plan"><div class="leyenda-barra" style="color:var(--tx-2)"><span>${hechas} de ${tareas.length} tareas hechas</span><span>${fmt((hechas / Math.max(tareas.length, 1)) * 100)} %</span></div><div class="barra fina"><i class="lleno" style="width:${(hechas / Math.max(tareas.length, 1)) * 100}%"></i></div>
              ${tareas.filter(t => !G.hechos[t.k]).slice(0, 2).map(t => `<span class="sig">○ ${esc(t.b)}</span>`).join("")}</a>
          </div>
        </div>
      </div>
      <div class="accion"><div class="dentro"><a class="btn primario ancho" href="#seguimiento">Anotar el gasto de hoy</a><div class="nota" id="notaEstado"></div></div></div>
    </section>`;
  }
  function montarPanel() {}

  /* ------------------------------------------------------------ navegación */
  const PANTALLAS = { panel: [pantallaPanel, montarPanel], datos: [pantallaDatos, montarDatos], plan: [pantallaPlan, montarPlan], seguimiento: [pantallaSeguimiento, montarSeguimiento] };
  function pintarEstado() {
    const el = $("#notaEstado"); if (!el) return;
    el.classList.toggle("error", !!G.error && !G.calculando);
    if (G.calculando) el.textContent = "Calculando el plan…";
    else if (G.error) el.textContent = G.error;
    else if (G.r && G.vista === "datos") el.textContent = `Plan listo: ${usd(G.r.resultado.factura)} al mes (antes ${usd(G.r.resultado.factura_antes)})`;
    else el.textContent = "Se guarda solo en este navegador.";
    const cta = $("#verPlan"); if (cta) cta.classList.toggle("cargando", G.calculando);
  }
  // estado del flujo: qué paso está listo, cuál es el actual y qué líneas se llenan
  function pintarFlujo() {
    const hecho = {
      panel: !!G.r,
      datos: !!(G.caso && G.caso.personas.length),
      plan: !!G.r && !G.error,
      seguimiento: !!(G.seg && Object.keys(G.seg.gastado).length),
    };
    const alertas = G.r && G.seg ? totalesSeg().alertas : 0;
    $$(".pasos .paso").forEach(el => {
      const p = el.dataset.p;
      el.classList.toggle("on", p === G.vista);
      el.classList.toggle("hecho", hecho[p]);
      el.classList.toggle("alerta", p === "seguimiento" && alertas > 0);
      const a = el.querySelector("a");
      if (p === G.vista) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    $('[data-linea="plan"]').classList.toggle("lleno", hecho.datos && hecho.plan);
    $('[data-linea="seguimiento"]').classList.toggle("lleno", hecho.plan && hecho.seguimiento);
  }
  function render(animar = true) {
    const [pintar, montar] = PANTALLAS[G.vista];
    $("#app").innerHTML = pintar();
    if (!animar) { const s = $(".pantalla"); if (s) s.style.animation = "none"; }
    pintarFlujo();
    montar();
    contar($("#app"));
    pintarEstado();
    if (G.r && G.seg) { const T = totalesSeg(); pintarFlujo(); }
  }
  async function irA(vista) {
    if (!PANTALLAS[vista]) vista = "panel";
    if (vista !== "datos" && (G.calculando || temporizador)) { clearTimeout(temporizador); temporizador = null; await calcular(); }
    G.vista = vista;
    G.confirmarCierre = false;
    render();
    scrollTo({ top: 0, behavior: "auto" });
  }
  addEventListener("hashchange", () => irA(location.hash.slice(1)));
  document.addEventListener("click", async e => {
    const b = e.target.closest("[data-accion], [data-quitar]"); if (!b) return;
    if (b.dataset.quitar) {
      if (G.caso.personas.length <= 1) return aviso("Debe quedar al menos una persona.", true);
      const p = G.caso.personas.find(x => x.id === b.dataset.quitar);
      G.caso.personas = G.caso.personas.filter(x => x.id !== b.dataset.quitar);
      $(`[data-tarjeta="${b.dataset.quitar}"]`).remove();
      $("#resumenDatos").innerHTML = resumenDatos();
      aviso(`Se quitó a ${p.nombre || "la persona"}.`);
      return programar();
    }
    const a = b.dataset.accion;
    if (a !== "excel") e.preventDefault();
    if (a === "agregar") {
      const eq = G.caso.personas[G.caso.personas.length - 1]?.equipo || "General";
      const p = conId({ nombre: "", equipo: eq, salario: 2000, gasto: 100, herramienta: "Claude" });
      G.caso.personas.push(p);
      $("#listaPersonas").insertAdjacentHTML("beforeend", tarjetaPersona(p));
      $("#resumenDatos").innerHTML = resumenDatos();
      const nueva = $(`[data-tarjeta="${p.id}"]`);
      nueva.scrollIntoView({ behavior: quieto ? "auto" : "smooth", block: "center" });
      $("input", nueva).focus();
      programar();
    } else if (a === "vaciar") {
      G.caso.personas = [conId({ nombre: "", equipo: "General", salario: 2000, gasto: 100, herramienta: "Claude" })];
      G.ejemplo = false; G.seg = nuevoSeg(mesActual()); G.hist = []; G.hechos = {};
      render(); programar();
    } else if (a === "excel") {
      descargarExcel();
    } else if (a === "aplicarRecorte") {
      G.seg.recorte = !G.seg.recorte; guardar(); render(false);
      aviso(G.seg.recorte ? "El seguimiento usa ahora los topes con recorte." : "Se quitó el recorte del seguimiento.");
    } else if (a === "quitarRecorte") {
      G.seg.recorte = false; guardar(); render(false);
    } else if (a === "cerrar") {
      cerrarMes(b);
    }
  });

  /* ------------------------------------------------------------ arranque */
  (async () => {
    try {
      const guardado = leerGuardado();
      if (guardado && guardado.caso) {
        Object.assign(G, { caso: guardado.caso, seg: guardado.seg, hist: guardado.hist || [], hechos: guardado.hechos || {}, ejemplo: !!guardado.ejemplo });
      } else {
        G.caso = await (await fetch("/api/caso")).json();
        G.ejemplo = true;
      }
      G.caso.personas.forEach(p => { const k = parseInt(String(p.id || "").replace(/\D/g, ""), 10); if (k >= siguienteId) siguienteId = k + 1; });
      G.caso.personas = G.caso.personas.map(conId);
      if (!G.seg) G.seg = nuevoSeg(mesActual());
      guardar();
      await calcular();
      const h = location.hash.slice(1);
      G.vista = PANTALLAS[h] ? h : (G.ejemplo ? "datos" : "panel");
      if (!h) history.replaceState(null, "", `#${G.vista}`);
      render();
    } catch (e) {
      $("#app").innerHTML = `<p class="rojo">No se pudo conectar con el servidor: ${esc(e.message)}. Ejecuta <code>.venv/bin/uvicorn servidor:app --port 8765</code> y recarga.</p>`;
    }
  })();
})();
