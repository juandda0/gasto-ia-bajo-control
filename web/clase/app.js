/* Interfaz del optimizador: cada paso del ciclo es una página con su vista previa y su panel.
   Todo el cálculo lo hace el servidor (Python); aquí solo se dibuja y se anima. */
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const fmt = (v, d = 0) => Number(v).toLocaleString("es-CO", { minimumFractionDigits: d, maximumFractionDigits: d });
  const usd = (v, d = 0) => `${fmt(v, d)} USD`;
  const num = v => (Math.abs(v - Math.round(v)) < 1e-6 ? fmt(v) : fmt(v, 2));
  const quieto = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const E = { caso: null, r: null, pagina: "inicio", paso: { h: 0, s: 0, m: 0, d: 0 }, inicial: "noroeste", z: null, sucio: false };

  const PAGINAS = [
    { id: "inicio", grupo: "Empezar", nombre: "Introducción", ico: "00" },
    { id: "datos", grupo: "Empezar", nombre: "Datos de la empresa", ico: "01" },
    { id: "modelo0", grupo: "El ciclo", nombre: "Modelo 0 · Qué plan", ico: "02", tema: "Problema de asignación · método húngaro" },
    { id: "modelo1", grupo: "El ciclo", nombre: "Modelo 1 · Cuánto usar", ico: "03", tema: "Planteamiento · Simplex" },
    { id: "grafico", grupo: "El ciclo", nombre: "Método gráfico", ico: "04", tema: "Método gráfico" },
    { id: "simplex", grupo: "El ciclo", nombre: "Simplex en tabla", ico: "05", tema: "Método Simplex" },
    { id: "modelo2", grupo: "El ciclo", nombre: "Modelo 2 · Con qué pagar", ico: "06", tema: "Transporte · noroeste, costo mínimo, Vogel y MODI" },
    { id: "sensibilidad", grupo: "El ciclo", nombre: "Sensibilidad", ico: "07", tema: "Análisis de sensibilidad" },
    { id: "dual", grupo: "El ciclo", nombre: "Dual Simplex", ico: "08", tema: "Método Dual Simplex" },
    { id: "resultado", grupo: "Resultado", nombre: "Resultado", ico: "✓" },
  ];

  /* ------------------------------------------------------------ servidor */
  async function resolver() {
    const res = await fetch("/api/resolver", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(E.caso) });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "No se pudo resolver el caso.");
    }
    E.r = await res.json();
    E.sucio = false;
    E.paso = { h: 0, s: 0, m: 0, d: 0 };
    E.z = null;
  }
  async function descargarExcel() {
    const res = await fetch("/api/excel", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(E.caso) });
    if (!res.ok) return aviso("No se pudo generar el Excel con estos datos.", true);
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: "modelos-solver.xlsx" });
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    aviso("Excel descargado: ábrelo y resuelve cada hoja con Solver.");
  }

  /* ------------------------------------------------------------ efectos */
  function aviso(texto, error = false) {
    const el = $("#aviso");
    el.textContent = texto;
    el.classList.toggle("error", error);
    el.classList.add("ver");
    clearTimeout(aviso.t);
    aviso.t = setTimeout(() => el.classList.remove("ver"), 3200);
  }

  // onda de distorsión con aberración cromática; `medio` se ejecuta en el punto más fuerte
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

  // partículas de fondo y estallidos
  const lienzo = $("#particulas"), ctx = lienzo.getContext("2d");
  const motas = [], chispas = [];
  const COLORES = ["#ff5c93", "#ffb547", "#7dffb0", "#4dc3ff", "#a774ff"];
  function medir() { lienzo.width = innerWidth * devicePixelRatio; lienzo.height = innerHeight * devicePixelRatio; }
  addEventListener("resize", medir); medir();
  for (let i = 0; i < 60; i++) motas.push({ x: Math.random(), y: Math.random(), r: Math.random() * 1.2 + 0.3, v: Math.random() * 0.00012 + 0.00004, a: Math.random() * 0.35 + 0.05 });
  function estallido(x, y, n = 46) {
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

  // conteo animado de cifras
  function contar(raiz = document) {
    $$("[data-contar]", raiz).forEach(el => {
      const fin = parseFloat(el.dataset.contar), dec = +(el.dataset.dec || 0), suf = el.dataset.suf || "", pre = el.dataset.pre || "";
      if (quieto) { el.textContent = pre + fmt(fin, dec) + suf; return; }
      const t0 = performance.now(), dur = 1100;
      const paso = ahora => {
        const t = Math.min(1, (ahora - t0) / dur), e = 1 - Math.pow(1 - t, 3);
        el.textContent = pre + fmt(fin * e, dec) + suf;
        if (t < 1) requestAnimationFrame(paso);
      };
      requestAnimationFrame(paso);
    });
  }

  // botones magnéticos
  document.addEventListener("pointermove", e => {
    $$(".btn.primario").forEach(b => {
      const r = b.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      const dx = e.clientX - cx, dy = e.clientY - cy, d = Math.hypot(dx, dy);
      b.style.transform = d < 90 && !quieto ? `translate(${dx * 0.16}px, ${dy * 0.22}px)` : "";
    });
  });

  /* ------------------------------------------------------------ piezas comunes */
  function cabecera(p, descripcion) {
    const i = PAGINAS.findIndex(x => x.id === p.id);
    const ant = PAGINAS[i - 1], sig = PAGINAS[i + 1];
    return `<div class="cab">
      <div class="ico">${p.ico}</div>
      <div><h1>${p.nombre}</h1>${p.tema ? `<span class="tema">${p.tema}</span>` : ""}</div>
      <div class="flechas">
        <button class="btn icono-btn" ${ant ? `data-ir="${ant.id}" aria-label="Anterior: ${ant.nombre}"` : "disabled"}>←</button>
        <button class="btn icono-btn" ${sig ? `data-ir="${sig.id}" aria-label="Siguiente: ${sig.nombre}"` : "disabled"}>→</button>
      </div>
      <p style="grid-column:2/4">${descripcion}</p>
    </div>`;
  }
  function stepper(clave, total, nota) {
    const k = E.paso[clave];
    return `<div class="stepper">
      <button class="btn chico" data-paso="${clave}" data-d="-1" ${k === 0 ? "disabled" : ""}>← Anterior</button>
      <div class="puntos">${Array.from({ length: total }, (_, i) => `<i class="${i === k ? "on" : ""}"></i>`).join("")}</div>
      <button class="btn chico primario" data-paso="${clave}" data-d="1" ${k === total - 1 ? "disabled" : ""}>Siguiente →</button>
      <span class="tenue" style="margin-left:6px">Paso ${k + 1} de ${total}</span>
    </div>${nota ? `<p class="paso-nota" style="margin-top:14px">${nota}</p>` : ""}`;
  }
  const personas = () => E.r.datos.personas;
  const planDe = nombre => E.r.modelo0.asignacion.find(a => a.persona === nombre);

  // barras verticales por persona (SVG)
  function barras({ series, max, etiquetaY = "USD de uso", marcas = [], leyenda = [] }) {
    const W = 720, H = 300, x0 = 54, x1 = 700, y0 = 22, y1 = 250, n = personas().length, bw = (x1 - x0) / n;
    const Y = v => y1 - (v / max) * (y1 - y0);
    const paso = max > 400 ? 100 : max > 150 ? 50 : 25;
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Gráfica por persona">`;
    for (let t = 0; t <= max + 1e-6; t += paso) s += `<line x1="${x0}" x2="${x1}" y1="${Y(t)}" y2="${Y(t)}" stroke="rgba(255,255,255,.06)"/><text x="${x0 - 8}" y="${Y(t) + 4}" text-anchor="end" font-size="11">${fmt(t)}</text>`;
    s += `<text x="${x0 - 46}" y="12" font-size="11">${etiquetaY}</text>`;
    personas().forEach((p, i) => {
      const cx = x0 + bw * i + bw / 2;
      s += `<text x="${cx}" y="${y1 + 20}" text-anchor="middle" font-size="12.5" style="fill:var(--tx)">${p.nombre}</text>`;
      series.forEach((ser, k) => {
        const ancho = Math.min(34, (bw - 22) / series.length), x = cx - (ancho * series.length) / 2 + k * ancho + k * 4 - 2;
        let base = 0;
        ser.partes(p).forEach(([v, color], j) => {
          if (v <= 1e-9) return;
          s += `<rect class="crecer" style="--d:${(i * 0.06 + k * 0.12 + j * 0.15).toFixed(2)}s" x="${x}" y="${Y(base + v)}" width="${ancho}" height="${Y(base) - Y(base + v)}" rx="5" fill="${color}"/>`;
          base += v;
        });
        if (ser.etiqueta) s += `<text class="aparecer" style="--d:${(0.6 + i * 0.06).toFixed(2)}s;fill:var(--tx)" x="${x + ancho / 2}" y="${Y(base) - 7}" text-anchor="middle" font-size="12" font-weight="600">${ser.etiqueta(p)}</text>`;
      });
      marcas.forEach(m => { const v = m.valor(p); if (v == null) return; s += `<line x1="${cx - bw / 2 + 10}" x2="${cx + bw / 2 - 10}" y1="${Y(v)}" y2="${Y(v)}" stroke="${m.color}" stroke-width="2" stroke-dasharray="${m.guiones || ""}"/>`; });
    });
    s += `<line x1="${x0}" x2="${x1}" y1="${y1}" y2="${y1}" stroke="rgba(255,255,255,.25)"/></svg>`;
    const ley = leyenda.map(([t, c, linea]) => `<span style="display:inline-flex;align-items:center;gap:6px;margin-right:16px;font-size:12px;color:var(--tx-2)"><i style="width:${linea ? 14 : 10}px;height:${linea ? 2 : 10}px;border-radius:3px;background:${c};display:inline-block"></i>${t}</span>`).join("");
    return `<div class="svg-box">${s}</div><div style="margin-top:8px">${ley}</div>`;
  }

  /* ------------------------------------------------------------ páginas */
  const PAG = {};

  PAG.inicio = () => `
    <section class="pagina">
      <div class="hero">
        <span class="tema">Programación Lineal · Universidad de Córdoba</span>
        <h1>Gasto en IA <em>bajo control</em></h1>
        <p>Le dice a una empresa qué plan de IA le conviene a cada programador, cuánto debería usar cada uno, con qué pagarlo y cuándo se está gastando de más. Cada paso usa un método del curso y le pasa su resultado al siguiente.</p>
        <div style="display:flex;gap:8px;margin-bottom:28px"><button class="btn primario" data-ir="datos">Empezar con los datos</button><button class="btn" data-ir="resultado">Ver el resultado</button></div>
      </div>
      <div class="zona">
        <div class="vista beam" style="--vel:7s"><span class="etq">ciclo de control mensual · toca un paso</span>${cicloSVG()}</div>
        <div class="panel"><h3>Qué resuelve cada paso</h3>
          <ol class="lista-num">
            <li><span><b>Qué plan</b>Asigna a cada persona un asiento o plan con el método húngaro.</span></li>
            <li><span><b>Cuánto usar</b>Reparte el gasto extra con Simplex, por tramos de rendimiento.</span></li>
            <li><span><b>Con qué pagar</b>Usa primero lo ya pagado: transporte con Vogel y MODI.</span></li>
            <li><span><b>¿Vamos bien?</b>El precio sombra dice cuánto rinde un dólar más.</span></li>
            <li><span><b>Si algo cambia</b>El Dual Simplex corrige los topes sin empezar de cero.</span></li>
          </ol>
        </div>
      </div>
    </section>`;

  function cicloSVG() {
    const caja = (x, y, t1, t2, ir, fuerte) => `<g data-ir="${ir}" style="cursor:pointer">
      <rect x="${x}" y="${y}" width="210" height="72" rx="16" fill="${fuerte ? "rgba(167,116,255,.14)" : "var(--s2)"}" stroke="${fuerte ? "rgba(167,116,255,.6)" : "rgba(255,255,255,.12)"}"/>
      <text x="${x + 105}" y="${y + 31}" text-anchor="middle" font-size="14" font-weight="600" style="fill:var(--tx)">${t1}</text>
      <text x="${x + 105}" y="${y + 51}" text-anchor="middle" font-size="12">${t2}</text></g>`;
    const ruta = "M235 120H275M485 120H525M605 156V264M525 300H485M275 300H235M130 264V156";
    return `<div class="svg-box"><svg viewBox="0 0 760 380" role="img" aria-label="Ciclo de control con seis pasos">
      <path d="${ruta}" stroke="rgba(255,255,255,.35)" stroke-width="1.5" fill="none" class="hormigas"/>
      <path d="M655 264V156" stroke="rgba(255,255,255,.35)" stroke-width="1.5" class="hormigas"/>
      <path id="vuelta" d="M235 120H525V156H605V264H525V300H130V156V120" fill="none"/>
      <circle r="5" fill="#a774ff" style="filter:drop-shadow(0 0 6px #a774ff)"><animateMotion dur="8s" repeatCount="indefinite"><mpath href="#vuelta"/></animateMotion></circle>
      ${caja(25, 84, "Datos de la empresa", "salarios y facturas", "datos")}
      ${caja(275, 84, "Modelo 0: qué plan", "método húngaro", "modelo0")}
      ${caja(525, 84, "Modelo 1: cuánto usar", "gráfico y Simplex", "modelo1")}
      ${caja(525, 264, "Modelo 2: con qué pagar", "transporte · MODI", "modelo2")}
      ${caja(275, 264, "Indicadores", "sensibilidad", "sensibilidad", true)}
      ${caja(25, 264, "Ajuste a mitad de mes", "Dual Simplex", "dual")}
      <text x="597" y="214" text-anchor="end" font-size="11.5">demanda</text>
      <text x="663" y="214" font-size="11.5">costo real</text>
      <text x="142" y="214" font-size="11.5">factura real del mes</text>
    </svg></div>`;
  }

  PAG.datos = p => {
    const c = E.caso, reg = c.reglas;
    const herramientas = ["Claude", "Cursor", "OpenAI", "Ninguna"];
    const filas = c.personas.map((q, i) => `<tr>
      <td><input data-per="${i}" data-campo="nombre" value="${q.nombre}" aria-label="Nombre"></td>
      <td><select data-per="${i}" data-campo="equipo" aria-label="Equipo">${["Backend", "Frontend"].map(e => `<option ${e === q.equipo ? "selected" : ""}>${e}</option>`).join("")}</select></td>
      <td><input data-per="${i}" data-campo="salario" type="number" min="0" step="50" value="${q.salario}" aria-label="Salario"></td>
      <td><input data-per="${i}" data-campo="gasto" type="number" min="0" step="5" value="${q.gasto}" aria-label="Gasto del mes pasado"></td>
      <td><select data-per="${i}" data-campo="herramienta" aria-label="Herramienta">${herramientas.map(h => `<option ${h === q.herramienta ? "selected" : ""}>${h}</option>`).join("")}</select></td></tr>`).join("");
    const nom = c.personas.reduce((s, q) => s + Number(q.salario), 0);
    const control = (id, et, v, min, max, paso, formato) => `<div class="rango"><label for="${id}">${et} <b id="${id}-v">${formato(v)}</b></label><input id="${id}" type="range" min="${min}" max="${max}" step="${paso}" value="${v}"></div>`;
    return `<section class="pagina">${cabecera(p, "La empresa solo pone lo que ya sabe: quién es cada programador, cuánto gana, qué herramienta usa y cuánto pagó el mes pasado. No necesita saber nada de tokens. Cambia lo que quieras y pulsa Optimizar.")}
      <div class="zona">
        <div class="vista" id="vistaDatos"><div class="contenido">
          <span class="etq">programadores</span>
          <div class="tabla-box" style="margin-top:10px"><table>
            <thead><tr><th>Persona</th><th>Equipo</th><th class="num">Salario (USD)</th><th class="num">Gasto mes pasado</th><th>Herramienta actual</th></tr></thead>
            <tbody>${filas}</tbody></table></div>
          <div class="cifras" style="margin-top:18px">
            <div class="cifra"><span>Nómina mensual</span><b>${usd(nom)}</b></div>
            <div class="cifra"><span>Gasto en IA del mes pasado</span><b>${usd(c.personas.reduce((s, q) => s + Number(q.gasto), 0))}</b></div>
            <div class="cifra"><span>Presupuesto de gasto extra</span><b>${usd(reg.presupuesto_pct_nomina * nom)}</b><small>${fmt(reg.presupuesto_pct_nomina * 100)}% de la nómina</small></div>
          </div>
        </div></div>
        <div class="panel">
          <h3>Reglas de la empresa</h3>
          ${control("rPres", "Gasto extra máximo (% de la nómina)", reg.presupuesto_pct_nomina * 100, 1, 15, 0.5, v => `${fmt(v, 1)}%`)}
          ${control("rTope", "Tope por persona (% del salario)", reg.tope_pct_salario * 100, 5, 30, 1, v => `${fmt(v)}%`)}
          ${control("rMin", "Mínimo por persona", reg.minimo, 0, 120, 10, v => usd(v))}
          ${control("rRec", "Recorte a mitad de mes", c.recorte * 100, 5, 50, 5, v => `${fmt(v)}%`)}
          <p>El gasto extra es lo que se paga aparte de las cuotas de los asientos. Lo que cubre la bolsa de un asiento ya está pagado.</p>
          <button class="btn primario beam" id="btnOpt2" style="--vel:2.6s">Optimizar</button>
          <p class="tenue" id="estadoDatos">${E.sucio ? "Hay cambios sin optimizar." : "Los resultados están al día."}</p>
        </div>
      </div></section>`;
  };
  PAG.datos.montar = () => {
    $$("[data-per]").forEach(el => el.addEventListener("change", () => {
      const q = E.caso.personas[+el.dataset.per], campo = el.dataset.campo;
      q[campo] = el.type === "number" ? Number(el.value) : el.value;
      E.sucio = true; $("#estadoDatos").textContent = "Hay cambios sin optimizar.";
    }));
    const unir = (id, aplicar, formato) => {
      const el = $(`#${id}`);
      el.addEventListener("input", () => { $(`#${id}-v`).textContent = formato(+el.value); });
      el.addEventListener("change", () => { aplicar(+el.value); E.sucio = true; $("#estadoDatos").textContent = "Hay cambios sin optimizar."; });
    };
    unir("rPres", v => (E.caso.reglas.presupuesto_pct_nomina = v / 100), v => `${fmt(v, 1)}%`);
    unir("rTope", v => (E.caso.reglas.tope_pct_salario = v / 100), v => `${fmt(v)}%`);
    unir("rMin", v => (E.caso.reglas.minimo = v), v => usd(v));
    unir("rRec", v => (E.caso.recorte = v / 100), v => `${fmt(v)}%`);
    $("#btnOpt2").addEventListener("click", e => optimizar(e.currentTarget, $("#vistaDatos")));
  };

  PAG.modelo0 = p => {
    const m0 = E.r.modelo0, pasos = m0.pasos, k = Math.min(E.paso.h, pasos.length - 1), st = pasos[k];
    const filasC = new Set(st.lineas ? st.lineas.filas : []), colsC = new Set(st.lineas ? st.lineas.columnas : []);
    const asign = st.asignacion || null;
    const tabla = `<table class="matriz"><thead><tr><th>Persona</th>${m0.cupos.map(c => `<th>${c}</th>`).join("")}</tr></thead><tbody>${
      st.matriz.map((fila, i) => `<tr><td>${m0.personas[i]}</td>${fila.map((v, j) => {
        const cls = [];
        if (k > 0 && Math.abs(v) < 1e-6) cls.push("cero");
        if (filasC.has(i) || colsC.has(j)) cls.push("cubierta");
        if (asign && asign[i] === j) cls.push("asignada");
        return `<td class="${cls.join(" ")}">${num(v)}</td>`;
      }).join("")}</tr>`).join("")}</tbody></table>`;
    const lista = m0.asignacion.map(a => `<tr><td>${a.persona}</td><td><span class="estado plan">${a.plan}</span></td><td class="num">${usd(a.costo)}</td></tr>`).join("");
    const tipos = E.caso.planes.map((pl, i) => `<tr><td>${pl.plan}</td>
      <td><input type="number" min="0" step="5" data-plan="${i}" data-campo="cuota" value="${pl.cuota}" aria-label="Cuota de ${pl.plan}"></td>
      <td><input type="number" min="0" step="10" data-plan="${i}" data-campo="bolsa" value="${pl.bolsa}" aria-label="Bolsa de ${pl.plan}"></td>
      <td><input type="number" min="0" step="1" data-plan="${i}" data-campo="cupos" value="${pl.cupos}" aria-label="Cupos de ${pl.plan}"></td></tr>`).join("");
    return `<section class="pagina">${cabecera(p, "Antes de repartir el presupuesto se decide qué asiento o plan recibe cada persona. Cada uno recibe exactamente un plan: es un problema de asignación. Costo = cuota + lo que su uso pase de la bolsa. Quien cambia de herramienta solo aprovecha una parte de la bolsa.")}
      <div class="zona">
        <div class="vista"><div class="contenido">
          <span class="etq">método húngaro · costos en USD al mes</span>
          <div style="margin-top:10px">${stepper("h", pasos.length, `<b>${st.titulo}.</b> ${k === 0 ? "Cada fila es una persona y cada columna un cupo de plan." : st.lineas ? "Las celdas sombreadas son las filas y columnas cubiertas. Si hacen falta menos líneas que personas, se ajusta la matriz." : st.asignacion ? "Se puede asignar una persona por fila y columna sobre los ceros: esa es la asignación óptima." : "Ahora cada fila y cada columna tienen al menos un cero."}`)}</div>
          <div class="tabla-box">${tabla}</div>
        </div></div>
        <div class="panel">
          <h3>Asignación óptima</h3>
          <table><tbody>${lista}</tbody></table>
          <div class="cifras"><div class="cifra"><span>Costo con estos planes</span><b data-contar="${m0.costo}">0</b><small>todo por API: ${usd(m0.costo_todo_api)}</small></div></div>
          <h3>Planes disponibles (supuestos)</h3>
          <div class="tabla-box"><table><thead><tr><th>Plan</th><th class="num">Cuota</th><th class="num">Bolsa</th><th class="num">Cupos</th></tr></thead><tbody>${tipos}</tbody></table></div>
          <button class="btn" id="btnPlanes">Aplicar y optimizar</button>
        </div>
      </div></section>`;
  };
  PAG.modelo0.montar = () => {
    $$("[data-plan]").forEach(el => el.addEventListener("change", () => { E.caso.planes[+el.dataset.plan][el.dataset.campo] = Number(el.value); }));
    $("#btnPlanes").addEventListener("click", e => {
      const cupos = E.caso.planes.reduce((s, x) => s + x.cupos, 0);
      if (cupos !== E.caso.personas.length) return aviso(`Los cupos deben sumar ${E.caso.personas.length}, uno por persona (ahora suman ${cupos}).`, true);
      optimizar(e.currentTarget, $(".vista"), "modelo0");
    });
  };

  PAG.modelo1 = p => {
    const m1 = E.r.modelo1, d = E.r.datos;
    const bolsaU = n => planDe(n).bolsa_usable;
    const fila = q => {
      const uso = m1.topes[q.nombre], ex = m1.extra[q.nombre];
      return `<tr><td>${q.nombre}</td><td><span class="estado plan">${planDe(q.nombre).plan}</span></td><td class="num">${usd(uso)}</td><td class="num">${usd(uso - ex)}</td><td class="num">${usd(ex)}</td><td class="num">${usd(d.reglas.tope_pct_salario * q.salario)}</td></tr>`;
    };
    const max = Math.max(...personas().map(q => d.reglas.tope_pct_salario * q.salario)) * 1.12;
    const extraTotal = Object.values(m1.extra).reduce((a, b) => a + b, 0);
    return `<section class="pagina">${cabecera(p, "Reparte el gasto extra entre los programadores para sacar el mayor valor. Cada dólar rinde menos que el anterior: los primeros 100 USD ahorran 0,2 h por dólar, los 150 siguientes 0,1 h y el resto 0,04 h. Lo que cubre la bolsa del asiento ya está pagado.")}
      <div class="zona">
        <div class="vista"><div class="contenido">
          <span class="etq">uso óptimo de cada persona · resuelto con Simplex (HiGHS)</span>
          <div style="margin-top:12px">${barras({ max, series: [{ partes: q => [[m1.topes[q.nombre] - m1.extra[q.nombre], "rgba(91,140,255,.55)"], [m1.extra[q.nombre], "#a774ff"]], etiqueta: q => fmt(m1.topes[q.nombre]) }],
            marcas: [{ valor: q => d.reglas.tope_pct_salario * q.salario, color: "rgba(255,255,255,.45)", guiones: "4 4" }],
            leyenda: [["Cubierto por la bolsa", "rgba(91,140,255,.55)"], ["Gasto extra", "#a774ff"], ["Tope (15% del salario)", "rgba(255,255,255,.45)", true]] })}</div>
          <div class="tabla-box" style="margin-top:12px"><table><thead><tr><th>Persona</th><th>Plan</th><th class="num">Uso óptimo</th><th class="num">De la bolsa</th><th class="num">Extra</th><th class="num">Tope</th></tr></thead><tbody>${personas().map(fila).join("")}</tbody></table></div>
        </div></div>
        <div class="panel">
          <h3>El modelo</h3>
          <p style="font:12.5px/1.8 var(--m);color:var(--tx)">max Σ r·g − Σ extra<br>uso − extra ≤ bolsa<br>uso ≤ tope · uso ≥ mínimo<br>Σ extra ≤ ${usd(m1.presupuesto)}</p>
          <div class="cifras">
            <div class="cifra"><span>Gasto extra usado</span><b>${usd(extraTotal)}</b><small>de ${usd(m1.presupuesto)}</small></div>
            <div class="cifra"><span>Valor que produce la IA</span><b data-contar="${m1.valor_bruto}">0</b><small>USD de tiempo ahorrado</small></div>
          </div>
          <div class="rango"><label for="pres1">Gasto extra máximo <b id="pres1-v">${fmt(d.reglas.presupuesto_pct_nomina * 100, 1)}%</b></label><input id="pres1" type="range" min="1" max="15" step="0.5" value="${d.reglas.presupuesto_pct_nomina * 100}"></div>
          <p>Mueve el presupuesto y suelta: el modelo se resuelve de nuevo.</p>
        </div>
      </div></section>`;
  };
  PAG.modelo1.montar = () => {
    const el = $("#pres1");
    el.addEventListener("input", () => ($("#pres1-v").textContent = `${fmt(+el.value, 1)}%`));
    el.addEventListener("change", () => { E.caso.reglas.presupuesto_pct_nomina = +el.value / 100; optimizar(null, $(".vista"), "modelo1"); });
  };

  function plano(dv, z, conCamino) {
    const W = 720, H = 400, x0 = 70, x1 = 690, y0 = 24, y1 = 344;
    const maxX = Math.max(dv.tope[0], dv.presupuesto) * 1.1, maxY = Math.max(dv.tope[1], dv.presupuesto) * 1.1;
    const X = v => x0 + (v / maxX) * (x1 - x0), Y = v => y1 - (v / maxY) * (y1 - y0);
    const pasoX = maxX > 1000 ? 200 : 100, pasoY = maxY > 1000 ? 200 : 100;
    let s = `<svg viewBox="0 0 ${W} ${H + 30}" role="img" aria-label="Región factible y recta de Z"><defs><clipPath id="clipPlano"><rect x="${x0}" y="${y0}" width="${x1 - x0}" height="${y1 - y0}"/></clipPath></defs>`;
    for (let t = 0; t <= maxX; t += pasoX) s += `<line x1="${X(t)}" x2="${X(t)}" y1="${y0}" y2="${y1}" stroke="rgba(255,255,255,.05)"/><text x="${X(t)}" y="${y1 + 18}" text-anchor="middle" font-size="11">${fmt(t)}</text>`;
    for (let t = 0; t <= maxY; t += pasoY) s += `<line x1="${x0}" x2="${x1}" y1="${Y(t)}" y2="${Y(t)}" stroke="rgba(255,255,255,.05)"/><text x="${x0 - 8}" y="${Y(t) + 4}" text-anchor="end" font-size="11">${fmt(t)}</text>`;
    const vs = dv.vertices.map(v => [v.x1, v.x2]);
    const cx = vs.reduce((a, v) => a + v[0], 0) / vs.length, cy = vs.reduce((a, v) => a + v[1], 0) / vs.length;
    vs.sort((a, b) => Math.atan2(a[1] - cy, a[0] - cx) - Math.atan2(b[1] - cy, b[0] - cx));
    s += `<polygon class="aparecer" style="--d:.5s" points="${vs.map(v => `${X(v[0])},${Y(v[1])}`).join(" ")}" fill="rgba(91,140,255,.16)" stroke="rgba(91,140,255,.8)" stroke-width="1.5"/>`;
    dv.restricciones.forEach((r, i) => {
      let a, b;
      if (Math.abs(r.a2) < 1e-9) { a = [r.b / r.a1, 0]; b = [r.b / r.a1, maxY]; }
      else if (Math.abs(r.a1) < 1e-9) { a = [0, r.b / r.a2]; b = [maxX, r.b / r.a2]; }
      else { a = [0, r.b / r.a2]; b = [r.b / r.a1, 0]; }
      const l = Math.hypot(X(b[0]) - X(a[0]), Y(b[1]) - Y(a[1]));
      s += `<line class="dibujo" style="--l:${l};--d:${i * 0.12}s" clip-path="url(#clipPlano)" x1="${X(a[0])}" y1="${Y(a[1])}" x2="${X(b[0])}" y2="${Y(b[1])}" stroke="rgba(255,255,255,.55)" stroke-width="1.3"/>`;
      const tx = Math.abs(r.a2) < 1e-9 ? X(a[0]) + 6 : Math.abs(r.a1) < 1e-9 ? x1 - 4 : X(Math.min(b[0], maxX) * 0.5) + 8;
      const ty = Math.abs(r.a2) < 1e-9 ? y0 + 14 : Math.abs(r.a1) < 1e-9 ? Y(a[1]) - 6 : Y((r.b - r.a1 * Math.min(b[0], maxX) * 0.5) / r.a2) - 6;
      s += `<text x="${tx}" y="${ty}" font-size="11" text-anchor="${Math.abs(r.a1) < 1e-9 ? "end" : "start"}">${r.nombre}</text>`;
    });
    vs.forEach(v => (s += `<circle cx="${X(v[0])}" cy="${Y(v[1])}" r="3.5" fill="var(--tx)"/>`));
    if (z != null) {
      const [c1, c2] = dv.c;
      const p1 = [0, z / c2], p2 = [z / c1, 0];
      s += `<line clip-path="url(#clipPlano)" x1="${X(p1[0])}" y1="${Y(p1[1])}" x2="${X(p2[0])}" y2="${Y(p2[1])}" stroke="#ffb547" stroke-width="2.2" stroke-dasharray="7 5" style="filter:drop-shadow(0 0 6px rgba(255,181,71,.6))"/>`;
      s += `<text x="${x1 - 6}" y="${y0 + 14}" text-anchor="end" font-size="12" font-weight="600" style="fill:#ffb547">Z = ${fmt(z)}</text>`;
    }
    const o = dv.optimo;
    if (conCamino) {
      const pts = conCamino.map(q => `${X(q[0])},${Y(q[1])}`).join(" ");
      s += `<polyline points="${pts}" fill="none" stroke="#a774ff" stroke-width="3.5" stroke-linecap="round" style="filter:drop-shadow(0 0 8px rgba(167,116,255,.7))"/>`;
      conCamino.forEach(q => (s += `<circle cx="${X(q[0])}" cy="${Y(q[1])}" r="6" fill="#a774ff"/>`));
    }
    if (z != null && Math.abs(z - o.Z) < 1e-6) s += `<circle cx="${X(o.x1)}" cy="${Y(o.x2)}" r="8" fill="#ffb547" style="filter:drop-shadow(0 0 10px #ffb547)"/><text x="${X(o.x1) + 12}" y="${Y(o.x2) - 10}" font-size="12.5" font-weight="600" style="fill:var(--tx)">Óptimo (${fmt(o.x1)}, ${fmt(o.x2)})</text>`;
    s += `<line x1="${x0}" x2="${x1}" y1="${y1}" y2="${y1}" stroke="rgba(255,255,255,.3)"/><line x1="${x0}" x2="${x0}" y1="${y0}" y2="${y1}" stroke="rgba(255,255,255,.3)"/>`;
    s += `<text x="${(x0 + x1) / 2}" y="${H + 22}" text-anchor="middle" font-size="12" style="fill:var(--tx)">x₁: gasto extra de ${dv.equipos[0]} (USD)</text><text x="${x0}" y="14" font-size="12" style="fill:var(--tx)">x₂: ${dv.equipos[1]}</text></svg>`;
    return `<div class="svg-box">${s}</div>`;
  }

  PAG.grafico = p => {
    const dv = E.r.dos_variables, z = E.z == null ? Math.round(dv.optimo.Z * 0.35) : E.z;
    const vert = [...dv.vertices].sort((a, b) => b.Z - a.Z).map((v, i) => `<tr><td>${v.vertice}</td><td class="num">${fmt(v.x1)}</td><td class="num">${fmt(v.x2)}</td><td class="num ${i === 0 ? "verde" : ""}">${fmt(v.Z)}</td></tr>`).join("");
    return `<section class="pagina">${cabecera(p, `Si se agrupa por equipos y se supone que cada dólar extra rinde siempre lo mismo (${fmt(dv.c[0], 1)} en ${dv.equipos[0]} y ${fmt(dv.c[1], 1)} en ${dv.equipos[1]}), quedan dos variables y el problema cabe en un plano. La zona azul son los repartos que cumplen las reglas; la recta de Z se desplaza hasta el último punto que la toca.`)}
      <div class="zona">
        <div class="vista beam quieto" id="vistaPlano"><div class="contenido"><span class="etq">max Z = ${fmt(dv.c[0], 1)}x₁ + ${fmt(dv.c[1], 1)}x₂</span><div style="margin-top:14px" id="planoBox">${plano(dv, z)}</div></div></div>
        <div class="panel">
          <h3>Recta de Z</h3>
          <div class="rango"><label for="zSl">Valor de Z <b id="zSl-v">${fmt(z)}</b></label><input id="zSl" type="range" min="0" max="${Math.round(dv.optimo.Z * 1.2)}" step="10" value="${z}"></div>
          <button class="btn primario" id="btnOptZ">Llevar al óptimo</button>
          <h3>Vértices de la región</h3>
          <table><thead><tr><th>Vértice</th><th class="num">x₁</th><th class="num">x₂</th><th class="num">Z</th></tr></thead><tbody>${vert}</tbody></table>
          <p>El óptimo siempre está en un vértice: <b style="color:var(--tx)">${dv.equipos[0]} ${fmt(dv.optimo.x1)}, ${dv.equipos[1]} ${fmt(dv.optimo.x2)}, Z = ${fmt(dv.optimo.Z)}</b>.</p>
        </div>
      </div></section>`;
  };
  PAG.grafico.montar = () => {
    const dv = E.r.dos_variables, el = $("#zSl");
    const pintar = v => { E.z = v; $("#zSl-v").textContent = fmt(v); $("#planoBox").innerHTML = plano(dv, v); $("#vistaPlano").classList.toggle("quieto", Math.abs(v - dv.optimo.Z) > 1e-6); };
    el.addEventListener("input", () => pintar(+el.value));
    $("#btnOptZ").addEventListener("click", () => {
      const ini = +el.value, fin = dv.optimo.Z, t0 = performance.now();
      const paso = ahora => { const t = Math.min(1, (ahora - t0) / (quieto ? 1 : 1400)), e = 1 - Math.pow(1 - t, 3), v = t < 1 ? ini + (fin - ini) * e : fin; el.value = v; pintar(v); if (t < 1) requestAnimationFrame(paso); };
      requestAnimationFrame(paso);
    });
  };

  function tablaSimplex(st) {
    const ic = st.entra ? st.columnas.indexOf(st.entra) : -1, ir = st.sale ? st.base.indexOf(st.sale) : -1;
    return `<table class="matriz"><thead><tr><th>Base</th>${st.columnas.map((c, j) => `<th class="${j === ic ? "colpiv" : ""}">${c}</th>`).join("")}${st.razones ? "<th>Razón</th>" : ""}</tr></thead><tbody>${
      st.tabla.map((fila, i) => `<tr class="${i === ir ? "filpiv" : ""}"><td>${st.base[i]}</td>${fila.map((v, j) => `<td class="${j === ic ? "colpiv" : ""} ${i === ir && j === ic ? "pivote" : ""}">${num(v)}</td>`).join("")}${st.razones ? `<td class="tenue">${i < st.razones.length && st.razones[i] != null ? num(st.razones[i]) : "—"}</td>` : ""}</tr>`).join("")}</tbody></table>`;
  }

  PAG.simplex = p => {
    const dv = E.r.dos_variables, S = dv.simplex, k = Math.min(E.paso.s, S.pasos.length - 1), st = S.pasos[k];
    const nota = `${st.nota}.${st.entra ? ` Entra <b>${st.entra}</b> (el z_j − c_j más negativo) y sale <b>${st.sale}</b> (la menor razón).` : ""}`;
    const valorDe = (st, v) => { const i = st.base.indexOf(v); return i < 0 ? 0 : st.tabla[i][st.tabla[i].length - 1]; };
    const camino = S.pasos.slice(0, k + 1).map(q => [S.cambio.x1 + valorDe(q, "y1"), S.cambio.x2 + valorDe(q, "y2")]);
    const zAct = S.cambio.z0 + st.tabla[st.tabla.length - 1][st.tabla[0].length - 1];
    return `<section class="pagina">${cabecera(p, "Simplex no recorre todo el plano: parte de un vértice y se mueve al vecino que más mejora Z, hasta que ninguno mejora. Para empezar en un punto factible, cada variable se escribe como su mínimo más una variable nueva y ≥ 0; así todas las restricciones quedan con ≤ y el origen sirve de inicio.")}
      <div class="zona">
        <div class="vista"><div class="contenido"><span class="etq">tabla Simplex · ${S.cambio.x1 ? `x₁ = ${fmt(S.cambio.x1)} + y1, ` : "x₁ = y1, "}x₂ = ${fmt(S.cambio.x2)} + y2</span>
          <div style="margin-top:10px">${stepper("s", S.pasos.length, nota)}</div>
          <div class="tabla-box">${tablaSimplex(st)}</div>
          <div style="margin-top:16px">${plano(dv, null, camino)}</div>
        </div></div>
        <div class="panel">
          <h3>Solución en este paso</h3>
          <div class="cifras">
            <div class="cifra"><span>x₁ (${dv.equipos[0]})</span><b>${fmt(camino[camino.length - 1][0])}</b></div>
            <div class="cifra"><span>x₂ (${dv.equipos[1]})</span><b>${fmt(camino[camino.length - 1][1])}</b></div>
            <div class="cifra"><span>Z</span><b>${fmt(zAct)}</b><small>${k === S.pasos.length - 1 ? "óptimo" : "todavía mejora"}</small></div>
          </div>
          <h3>Cómo leer la tabla</h3>
          <p>La última fila es z_j − c_j. Mientras haya un valor negativo, Z puede crecer: esa columna entra. La razón Solución / coeficiente decide qué variable sale, para no salirse de la región.</p>
          <p>El camino morado del plano son los vértices que recorre Simplex.</p>
        </div>
      </div></section>`;
  };

  function tablaTransporte(m2, x, opciones = {}) {
    const { ciclo = [], entra = null, reducidos = null } = opciones;
    const signo = {};
    ciclo.forEach((c, k) => (signo[`${c[0]},${c[1]}`] = k % 2 === 0 ? "mas" : "menos"));
    return `<table class="matriz"><thead><tr><th>Fuente de pago</th>${m2.destinos.map(d => `<th>${d}</th>`).join("")}<th>Oferta</th></tr></thead><tbody>${
      m2.origenes.map((o, i) => `<tr><td>${o}</td>${m2.destinos.map((_, j) => {
        const costo = m2.costos[i][j], prohibida = costo >= m2.M - 1e-9, v = x[i][j], cls = [signo[`${i},${j}`] || ""];
        if (prohibida) cls.push("prohibida");
        if (entra && entra[0] === i && entra[1] === j) cls.push("pivote");
        const red = reducidos && reducidos[i][j] != null && !prohibida ? `<span class="costo" style="color:${reducidos[i][j] < -1e-9 ? "var(--rojo)" : "var(--tx-3)"}">${num(reducidos[i][j])}</span>` : "";
        return `<td class="${cls.join(" ")}"><span class="costo">${prohibida ? "M" : num(costo)}</span>${v > 1e-9 ? `<b>${fmt(v)}</b>` : red || "·"}${signo[`${i},${j}`] ? ` <span class="${signo[`${i},${j}`] === "mas" ? "azul" : "rojo"}">${signo[`${i},${j}`] === "mas" ? "+" : "−"}</span>` : ""}</td>`;
      }).join("")}<td class="tenue">${fmt(m2.oferta[i])}</td></tr>`).join("")}
      <tr><td class="tenue">Demanda</td>${m2.demanda.map(d => `<td class="tenue">${fmt(d)}</td>`).join("")}<td></td></tr></tbody></table>`;
  }

  PAG.modelo2 = p => {
    const m2 = E.r.modelo2, k = Math.min(E.paso.m, m2.modi.length - 1), it = m2.modi[k];
    const nombresIni = { noroeste: "Esquina noroeste", costo_minimo: "Costo mínimo", vogel: "Vogel" };
    const maxIni = Math.max(...Object.values(m2.iniciales).map(s => s.costo));
    const barrasIni = Object.entries(m2.iniciales).map(([kk, s]) => `<div style="display:grid;grid-template-columns:110px 1fr 70px;gap:10px;align-items:center;font-size:12.5px"><span>${nombresIni[kk]}</span><span style="height:10px;border-radius:5px;background:var(--s3);overflow:hidden"><i class="crecer" style="display:block;height:100%;width:${(s.costo / maxIni) * 100}%;background:${kk === "noroeste" ? "var(--tx-3)" : "linear-gradient(90deg,#4dc3ff,#a774ff)"};transform-origin:left"></i></span><b class="num" style="text-align:right">${usd(s.costo)}</b></div>`).join("");
    const nota = it.entra ? `Costo actual <b>${usd(it.costo)}</b>. La casilla <b>${m2.origenes[it.entra[0]]} → ${m2.destinos[it.entra[1]]}</b> tiene costo reducido negativo: entra con θ = ${fmt(it.theta)} siguiendo el ciclo + / −.` : `Costo <b>${usd(it.costo)}</b>. Ningún costo reducido es negativo: es el óptimo.`;
    return `<section class="pagina">${cabecera(p, "Las fuentes de pago son los orígenes y los equipos son los destinos. Primero se usan las bolsas de los asientos (costo 0), después la API en batch (mitad de precio, solo para trabajo que puede esperar) y el resto a precio normal. M marca las rutas prohibidas y el destino ficticio absorbe la oferta que sobra.")}
      <div class="zona">
        <div class="vista"><div class="contenido"><span class="etq">MODI desde la esquina noroeste · costo por dólar de uso en la esquina de cada casilla</span>
          <div style="margin-top:10px">${stepper("m", m2.modi.length, nota)}</div>
          <div class="tabla-box">${tablaTransporte(m2, it.asignacion, { ciclo: it.ciclo || [], entra: it.entra, reducidos: it.reducidos })}</div>
          <p class="tenue" style="margin-top:10px">Potenciales: u = (${it.u.map(num).join(", ")}) &nbsp;·&nbsp; v = (${it.v.map(num).join(", ")}). En las casillas vacías se ve el costo reducido c − u − v.</p>
        </div></div>
        <div class="panel">
          <h3>Soluciones iniciales</h3>
          <div class="grupo">${barrasIni}</div>
          <p>Vogel llega al óptimo de una vez${m2.iteraciones_modi_desde_vogel ? ` (MODI hace ${m2.iteraciones_modi_desde_vogel} mejoras)` : ""}; desde la esquina noroeste, MODI necesita ${m2.modi.length - 1} mejoras.</p>
          <div class="cifras"><div class="cifra"><span>Pago por uso del mes</span><b data-contar="${m2.final.costo}" data-suf=" USD">0</b></div></div>
          <h3>Costo real de un dólar más</h3>
          <p>${Object.entries(m2.costo_marginal).map(([e, v]) => `${e}: <b style="color:var(--tx)">${num(v)}</b>`).join(" · ")}. Se lee de los potenciales v de MODI. Vuelve al Modelo 1 y el ciclo ${E.r.ciclo_converge ? "ya no cambia: converge" : "se recalcula"}.</p>
        </div>
      </div></section>`;
  };

  PAG.sensibilidad = p => {
    const m1 = E.r.modelo1, rg = E.r.rango_presupuesto, d = E.r.datos;
    const lo = rg.desde * 0.85, hi = rg.hasta * 1.1, P = v => ((v - lo) / (hi - lo)) * 100;
    const maxB = Math.max(...personas().map(q => Math.max(q.gasto, m1.topes[q.nombre]))) * 1.15;
    const alertas = personas().map(q => { const s = q.gasto - m1.topes[q.nombre]; return `<tr><td>${q.nombre}</td><td class="num">${fmt(q.gasto)} → ${fmt(m1.topes[q.nombre])}</td><td class="num">${s > 1e-6 ? `<span class="estado mal">−${fmt(s)}</span>` : `<span class="estado bien">+${fmt(-s)}</span>`}</td></tr>`; }).join("");
    return `<section class="pagina">${cabecera(p, "Los precios sombra convierten la solución en indicadores para la gerencia. El del presupuesto dice cuánto valor neto deja un dólar más de gasto extra; mientras el presupuesto esté dentro de su rango, ese valor no cambia.")}
      <div class="zona">
        <div class="vista beam" style="--vel:5s"><div class="contenido"><span class="etq">indicador principal</span>
          <div style="display:grid;place-items:center;text-align:center;margin:26px 0 10px">
            <b style="font-size:64px;font-weight:600;letter-spacing:-.04em;line-height:1" data-contar="${m1.precio_sombra.presupuesto}" data-dec="3">0</b>
            <span class="tenue">valor neto de un dólar más de gasto extra</span>
          </div>
          <div style="margin:22px 6px 6px"><div style="position:relative;height:12px;border-radius:6px;background:var(--s3)">
            <i style="position:absolute;left:${P(rg.desde)}%;width:${P(rg.hasta) - P(rg.desde)}%;top:0;bottom:0;border-radius:6px;background:linear-gradient(90deg,#4dc3ff,#a774ff)"></i>
            <i style="position:absolute;left:calc(${P(m1.presupuesto)}% - 2px);top:-6px;width:4px;height:24px;border-radius:2px;background:#fff;box-shadow:0 0 10px #fff"></i></div>
            <div style="display:flex;justify-content:space-between;font-size:12px;margin-top:8px" class="tenue"><span>${usd(rg.desde)}</span><span style="color:var(--tx)">presupuesto actual ${usd(m1.presupuesto)}</span><span>${usd(rg.hasta)}</span></div></div>
          <div style="margin-top:24px">${barras({ max: maxB, series: [{ partes: q => [[Math.min(q.gasto, m1.topes[q.nombre]), "rgba(255,255,255,.25)"], [Math.max(0, q.gasto - m1.topes[q.nombre]), "#ff5a5a"]], etiqueta: q => fmt(q.gasto) }],
            marcas: [{ valor: q => m1.topes[q.nombre], color: "#5b8cff" }], leyenda: [["Gasto del mes pasado", "rgba(255,255,255,.25)"], ["Por encima del tope", "#ff5a5a"], ["Tope óptimo", "#5b8cff", true]] })}</div>
        </div></div>
        <div class="panel">
          <h3>Cómo se lee</h3>
          <p>Un dólar más de gasto extra deja <b style="color:var(--tx)">${num(m1.precio_sombra.presupuesto)}</b> de valor neto. Vale entre ${usd(rg.desde)} y ${usd(rg.hasta)} de presupuesto.</p>
          <p>${m1.precio_sombra.presupuesto > 0.05 ? "Todavía conviene gastar un poco más, pero cada vez rinde menos." : "El presupuesto está casi en su punto justo."}</p>
          <h3>Alertas frente al mes pasado</h3>
          <table><thead><tr><th>Persona</th><th class="num">Gastó → tope</th><th class="num">USD</th></tr></thead><tbody>${alertas}</tbody></table>
        </div>
      </div></section>`;
  };

  PAG.dual = p => {
    const dv = E.r.dos_variables, D = dv.dual_simplex, k = Math.min(E.paso.d, D.pasos.length - 1), st = D.pasos[k];
    const antes = E.r.modelo1, desp = E.r.recorte.modelo1;
    const max = Math.max(...personas().map(q => antes.topes[q.nombre])) * 1.2;
    const nota = `${st.nota}.${st.sale ? ` Sale <b>${st.sale}</b> (la solución negativa) y entra <b>${st.entra}</b> (la menor razón |z_j / a_ij|).` : ""}`;
    return `<section class="pagina">${cabecera(p, `A mitad de mes la gerencia recorta el gasto extra un ${fmt(E.r.datos.recorte * 100)}%. La solución anterior deja de cumplir el presupuesto, pero sigue siendo la mejor en valor: el Dual Simplex la corrige desde ahí, sin resolver todo de nuevo.`)}
      <div class="zona">
        <div class="vista"><div class="contenido"><span class="etq">topes antes y después del recorte · modelo completo con Dual Simplex (HiGHS)</span>
          <div style="margin-top:12px">${barras({ max, series: [{ partes: q => [[antes.topes[q.nombre], "rgba(255,255,255,.18)"]], etiqueta: q => fmt(antes.topes[q.nombre]) }, { partes: q => [[desp.topes[q.nombre], "#a774ff"]], etiqueta: q => fmt(desp.topes[q.nombre]) }],
            leyenda: [["Antes", "rgba(255,255,255,.18)"], ["Después del recorte", "#a774ff"]] })}</div>
          <h3 style="margin:22px 0 10px;font-size:13px;font-weight:500">Vista por equipos en tabla</h3>
          ${stepper("d", D.pasos.length, nota)}
          <div class="tabla-box">${tablaSimplex(st)}</div>
        </div></div>
        <div class="panel">
          <h3>Recorte</h3>
          <div class="rango"><label for="rec">Recorte del presupuesto <b id="rec-v">${fmt(E.r.datos.recorte * 100)}%</b></label><input id="rec" type="range" min="5" max="50" step="5" value="${E.r.datos.recorte * 100}"></div>
          <div class="cifras">
            <div class="cifra"><span>Presupuesto nuevo</span><b>${usd(desp.presupuesto)}</b><small>antes ${usd(antes.presupuesto)}</small></div>
            <div class="cifra"><span>Precio sombra</span><b>${num(desp.precio_sombra.presupuesto)}</b><small>antes ${num(antes.precio_sombra.presupuesto)}</small></div>
            <div class="cifra"><span>Factura nueva</span><b>${usd(E.r.recorte.factura)}</b><small>antes ${usd(E.r.resultado.factura)}</small></div>
          </div>
          <p>Bajan primero los que menos rinden en su último dólar. Que el precio sombra suba quiere decir que cada dólar recortado duele más.</p>
        </div>
      </div></section>`;
  };
  PAG.dual.montar = () => {
    const el = $("#rec");
    el.addEventListener("input", () => ($("#rec-v").textContent = `${fmt(+el.value)}%`));
    el.addEventListener("change", () => { E.caso.recorte = +el.value / 100; optimizar(null, $(".vista"), "dual"); });
  };

  PAG.resultado = p => {
    const R = E.r.resultado, ahorro = R.factura_antes - R.factura;
    const tabla = personas().map(q => { const s = q.gasto - E.r.modelo1.topes[q.nombre]; return `<tr><td>${q.nombre}</td><td><span class="estado plan">${planDe(q.nombre).plan}</span></td><td class="num">${usd(E.r.modelo1.topes[q.nombre])}</td><td class="num tenue">${usd(q.gasto)}</td><td>${s > 1e-6 ? `<span class="estado mal">Bajar ${usd(s)}</span>` : `<span class="estado bien">Puede usar ${usd(-s)} más</span>`}</td></tr>`; }).join("");
    return `<section class="pagina">${cabecera(p, "Lo que recibe la empresa: el plan de cada persona, su tope de uso para configurarlo en la consola de cada proveedor, cómo pagar y cuánto se ahorra.")}
      <div class="zona">
        <div class="vista" id="vistaRes" style="display:grid;gap:22px"><div class="contenido" style="display:grid;gap:22px">
          <div class="recibo beam" style="--vel:4s">
            <div class="check">✓</div>
            <div><span class="tenue">Factura del mes</span><div class="monto" data-contar="${R.factura}" data-suf=" USD">0</div><span class="tenue">antes ${usd(R.factura_antes)}</span></div>
            <div class="filas">
              <div><span>Cuotas de asientos</span><b>${usd(R.cuotas)}</b></div>
              <div><span>Pago por uso</span><b>${usd(R.pago_variable)}</b></div>
              <div><span>Ahorro</span><b class="verde">${usd(ahorro)} · ${fmt((ahorro / R.factura_antes) * 100)}%</b></div>
              <div><span>Valor que produce la IA</span><b>${usd(R.valor)}</b></div>
            </div>
            <button class="btn primario" id="btnExcel2">Descargar Excel</button>
          </div>
          <div class="tabla-box"><table><thead><tr><th>Persona</th><th>Plan</th><th class="num">Tope de uso</th><th class="num">Mes pasado</th><th>Acción</th></tr></thead><tbody>${tabla}</tbody></table></div>
        </div></div>
        <div class="panel">
          <h3>En cifras</h3>
          <div class="cifras">
            <div class="cifra"><span>Valor neto</span><b data-contar="${R.neto}" data-suf=" USD">0</b><small>antes ${usd(R.neto_antes)}</small></div>
            <div class="cifra"><span>Valor de la IA</span><b>+${fmt(((R.valor - R.valor_antes) / R.valor_antes) * 100)}%</b><small>más que el reparto del mes pasado</small></div>
          </div>
          <h3>Comprobaciones</h3>
          <p>El ciclo por etapas da lo mismo que el modelo unido en un solo problema lineal (diferencia ${usd(Math.abs(R.diferencia_con_unido), 2)}).</p>
          <p>El método húngaro coincide con SciPy: ${usd(E.r.modelo0.costo)} y ${usd(E.r.modelo0.costo_scipy)}.</p>
          <p class="tenue">Los salarios, rendimientos y bolsas son supuestos del caso de ejemplo.</p>
        </div>
      </div></section>`;
  };
  PAG.resultado.montar = () => {
    $("#btnExcel2").addEventListener("click", () => ola($(".recibo"), descargarExcel));
    const b = $(".check").getBoundingClientRect();
    setTimeout(() => estallido(b.left + b.width / 2, b.top + b.height / 2, 36), 350);
  };

  /* ------------------------------------------------------------ navegación y render */
  function lado() {
    let html = "", grupo = "";
    PAGINAS.forEach(p => {
      if (p.grupo !== grupo) { grupo = p.grupo; html += `<h6>${grupo}</h6>`; }
      html += `<a data-ir="${p.id}" class="${p.id === E.pagina ? "on" : ""}"><i>${p.ico}</i>${p.nombre}</a>`;
    });
    $("#lado").innerHTML = html;
    $$(".top nav a").forEach(a => a.classList.toggle("on", a.dataset.ir === E.pagina || (a.dataset.ir === "modelo0" && PAGINAS.find(p => p.id === E.pagina)?.grupo === "El ciclo")));
  }
  function render() {
    const p = PAGINAS.find(x => x.id === E.pagina) || PAGINAS[0];
    if (["grafico", "simplex", "dual"].includes(p.id) && !E.r.dos_variables) {
      $("#main").innerHTML = `<section class="pagina">${cabecera(p, "La vista para resolver a mano agrupa a las personas en dos equipos. Con estos datos no hay exactamente dos equipos, así que esta página no aplica; el modelo completo sí se resolvió.")}</section>`;
      lado();
      return;
    }
    $("#main").innerHTML = PAG[p.id](p);
    lado();
    (PAG[p.id].montar || (() => {}))();
    contar($("#main"));
  }
  function ir(id) {
    if (!PAGINAS.some(p => p.id === id)) id = "inicio";
    E.pagina = id;
    if (location.hash !== `#${id}`) history.pushState(null, "", `#${id}`);
    render();
    scrollTo({ top: 0, behavior: quieto ? "auto" : "smooth" });
  }
  addEventListener("popstate", () => { E.pagina = location.hash.slice(1) || "inicio"; render(); });
  document.addEventListener("click", e => {
    const a = e.target.closest("[data-ir]");
    if (a && !a.disabled) { e.preventDefault(); ir(a.dataset.ir); return; }
    const b = e.target.closest("[data-paso]");
    if (b && !b.disabled) {
      const clave = b.dataset.paso;
      E.paso[clave] += +b.dataset.d;
      render();
      const vista = $(".vista");
      if (vista) ola(vista);
    }
  });

  async function optimizar(boton, vista, destino = "resultado") {
    if (optimizar.ocupado) return;
    optimizar.ocupado = true;
    if (boton) boton.disabled = true;
    let error = null;
    const trabajo = resolver().catch(e => (error = e));
    if (vista) await ola(vista, () => {}); else await trabajo;
    await trabajo;
    if (boton) boton.disabled = false;
    optimizar.ocupado = false;
    if (error) return aviso(error.message, true);
    aviso(`Listo: factura de ${usd(E.r.resultado.factura)} al mes.`);
    if (destino === E.pagina) render(); else ir(destino);
    if (boton) { const r = boton.getBoundingClientRect(); estallido(r.left + r.width / 2, r.top + r.height / 2); }
  }
  $("#btnOptimizar").addEventListener("click", e => optimizar(e.currentTarget, $(".vista")));
  $("#btnExcel").addEventListener("click", descargarExcel);

  (async () => {
    try {
      let guardado = null;
      try { guardado = JSON.parse(localStorage.getItem("gasto-ia-v1") || "null"); } catch (_) { /* sin almacenamiento */ }
      E.caso = guardado && guardado.caso ? guardado.caso : await (await fetch("/api/caso")).json();
      await resolver();
      E.pagina = location.hash.slice(1) || "inicio";
      render();
    } catch (e) {
      $("#main").innerHTML = `<p class="error">No se pudo conectar con el servidor: ${e.message}. Ejecuta <code>.venv/bin/uvicorn servidor:app</code> y recarga.</p>`;
    }
  })();
})();
