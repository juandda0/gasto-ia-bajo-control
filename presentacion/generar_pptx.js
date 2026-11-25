// Genera presentacion/gasto-ia-bajo-control.pptx (7 diapositivas: avance) y animaciones.json.
// Las animaciones se agregan después con animar_pptx.py (pptxgenjs no las escribe).
// Uso: NODE_PATH=<carpeta con pptxgenjs>/node_modules node generar_pptx.js
const path = require("path");
const fs = require("fs");
const pptxgen = require("pptxgenjs");

const OUT = path.join(__dirname, "gasto-ia-bajo-control.pptx");
const SPEC = path.join(__dirname, "animaciones.json");

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.title = "Gasto en IA bajo control";
pres.author = "Juan Diego Díaz Avendaño";
pres.theme = { headFontFace: "Arial", bodyFontFace: "Arial" };

const K = { ink: "0A0A0A", muted: "6B6B6B", line: "D9D9D9", faint: "F3F3F3", white: "FFFFFF",
  c1: "2F5BD3", c2: "8FA9EE", c3: "E8710A", bad: "D23A2C", c4: "7C4DDB" };
const SANS = "Arial", MONO = "Courier New";

pres.defineSlideMaster({
  title: "OSCURA",
  background: { color: K.ink },
  objects: [
    { placeholder: { options: { name: "tag", type: "body", x: 0.6, y: 2.0, w: 12, h: 0.45, fontFace: MONO, fontSize: 13, color: "9A9A9A", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 2.5, w: 12, h: 1.9, fontFace: SANS, fontSize: 54, bold: true, color: K.white, valign: "top", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.6, y: 4.55, w: 9.5, h: 1.6, fontFace: SANS, fontSize: 20, color: "C8C8C8", valign: "top", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "CLARA",
  background: { color: K.white },
  objects: [
    { placeholder: { options: { name: "tag", type: "body", x: 0.6, y: 0.38, w: 9.8, h: 0.35, fontFace: MONO, fontSize: 12, color: K.muted, margin: 0 }, text: "" } },
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.75, w: 12.1, h: 0.85, fontFace: SANS, fontSize: 32, bold: true, color: K.ink, valign: "top", align: "left", margin: 0 }, text: "" } },
    { text: { text: "Gasto en IA bajo control · Programación Lineal", options: { x: 0.6, y: 7.0, w: 6, h: 0.3, fontFace: SANS, fontSize: 10, color: K.muted, margin: 0 } } },
  ],
  slideNumber: { x: 12.2, y: 7.0, w: 0.5, h: 0.3, fontFace: SANS, fontSize: 10, color: K.muted, align: "right" },
});

/* ---------- utilidades ---------- */
const anim = {};      // número de diapositiva -> grupos de animación
let sn = 0, cnt = 0, currentSec = "";
function seccion(t) { pres.addSection({ title: t }); currentSec = t; }
function nueva(master) {
  sn += 1; cnt = 0; anim[sn] = [];
  return pres.addSlide({ masterName: master, sectionTitle: currentSec });
}
const nm = () => `s${sn}_${++cnt}`;
// grupo: { trigger: "click" | "auto", items: [{ name, eff, delay }] }
function grupo(trigger = "click") { const g = { trigger, items: [] }; anim[sn].push(g); return g; }
function add(g, name, eff = "fade", delay = 0) { g.items.push({ name, eff, delay }); return name; }

function T(s, text, o) {
  const name = nm();
  s.addText(text, Object.assign({ isTextBox: true, fontFace: SANS, fontSize: 14, color: K.ink, margin: 0, valign: "top", objectName: name }, o));
  return name;
}
function R(s, x, y, w, h, fill, lineColor, o = {}) {
  const name = nm();
  s.addShape(pres.shapes.RECTANGLE, { x, y, w, h, objectName: name,
    fill: fill ? { color: fill, transparency: o.transp || 0 } : { type: "none" },
    line: lineColor ? { color: lineColor, width: o.lw || 1 } : { type: "none" } });
  return name;
}
function O(s, cx, cy, d, fill) {
  const name = nm();
  s.addShape(pres.shapes.OVAL, { x: cx - d / 2, y: cy - d / 2, w: d, h: d, fill: { color: fill }, line: { type: "none" }, objectName: name });
  return name;
}
function L(s, x1, y1, x2, y2, color, width = 1.25, o = {}) {
  const name = nm();
  const opt = { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.max(Math.abs(x2 - x1), 0.0001), h: Math.max(Math.abs(y2 - y1), 0.0001),
    line: { color, width, dashType: o.dash || "solid", endArrowType: o.arrow ? "triangle" : undefined }, objectName: name };
  if ((x2 - x1) * (y2 - y1) < 0) opt.flipV = true;
  if (x2 < x1 && y2 === y1) opt.flipH = true;
  if (y2 < y1 && x2 === x1) opt.flipV = true;
  s.addShape(pres.shapes.LINE, opt);
  return name;
}
function header(s, tag, title) {
  s.addText(tag, { placeholder: "tag" });
  s.addText(title, { placeholder: "title" });
}
function flujo(s, n) { // indicador de avance del flujo: 6 tramos
  for (let i = 0; i < 6; i++) R(s, 10.95 + i * 0.3, 0.48, 0.25, 0.07, i < n ? K.ink : K.line);
}
const fmt = (v, d = 0) => v.toLocaleString("es-CO", { minimumFractionDigits: d, maximumFractionDigits: d });
const leyenda = (s, items, y = 6.38, x0 = 5.4, paso = 2.3) => items.forEach((l, i) => {
  R(s, x0 + i * paso, y, 0.16, 0.16, l[1], null);
  T(s, l[0], { x: x0 + 0.24 + i * paso, y: y - 0.05, w: paso - 0.3, h: 0.26, fontSize: 11, color: K.muted });
});

/* ---------- datos del caso (calculados con el código del proyecto) ---------- */
const devs = [
  { n: "Ana", eq: "Backend", herr: "Claude Code (API)", sal: 2400, gasto: 420, r: [3, 1.5, .6], tr: [100, 150], recorte: 250 },
  { n: "Luis", eq: "Backend", herr: "Cursor Teams", sal: 2000, gasto: 180, r: [2.5, 1.25, .5], tr: [100, 150], recorte: 250 },
  { n: "Sara", eq: "Backend", herr: "Cursor Teams", sal: 1700, gasto: 95, r: [2.125, 1.0625, .425], tr: [100, 90], recorte: 100 },
  { n: "Pedro", eq: "Backend", herr: "Claude Code (API)", sal: 1900, gasto: 260, r: [2.375, 1.1875, .475], tr: [100, 150], recorte: 202 },
  { n: "Carla", eq: "Frontend", herr: "Codex (API)", sal: 2200, gasto: 310, r: [2.75, 1.375, .55], tr: [100, 150], recorte: 250 },
  { n: "Diego", eq: "Frontend", herr: "Suscripción personal", sal: 1800, gasto: 60, r: [2.25, 1.125, .45], tr: [100, 150], recorte: 100 },
];
devs.forEach(d => d.tope = d.tr[0] + d.tr[1]);

/* ejes de barras por persona */
function ejes(s, o) {
  const g = Object.assign({ x0: 5.4, x1: 12.6, top: 2.0, bot: 5.7, dec: 0 }, o);
  const Y = v => g.bot - (v / g.max) * (g.bot - g.top);
  g.ticks.forEach(t => {
    L(s, g.x0, Y(t), g.x1, Y(t), K.line, 0.75);
    T(s, fmt(t, g.dec), { x: g.x0 - 0.7, y: Y(t) - 0.12, w: 0.6, h: 0.24, fontFace: MONO, fontSize: 11, color: K.muted, align: "right" });
  });
  T(s, g.label, { x: g.x0 - 0.7, y: g.top - 0.38, w: 3, h: 0.25, fontSize: 11, color: K.muted });
  L(s, g.x0, g.bot, g.x1, g.bot, K.ink, 1);
  const bw = (g.x1 - g.x0) / devs.length;
  devs.forEach((d, i) => T(s, d.n, { x: g.x0 + bw * i, y: g.bot + 0.1, w: bw, h: 0.3, fontSize: 13, align: "center" }));
  return { g, Y, bw };
}

/* ===================== 1. Portada ===================== */
seccion("Inicio");
let s = nueva("OSCURA"), g;
s.addText("PROGRAMACIÓN LINEAL · UNIVERSIDAD DE CÓRDOBA · PROYECTO FINAL", { placeholder: "tag" });
s.addText("Gasto en IA bajo control", { placeholder: "title" });
s.addText("Cuánto debería gastar en inteligencia artificial cada programador, con qué pagarlo y cuándo se está gastando de más.", { placeholder: "body" });
s.addNotes("Presentar el proyecto en una frase: las empresas pagan herramientas de IA por consumo y no saben cuánto gastar por persona. El proyecto lo resuelve con programación lineal usando todos los temas del curso.");

/* ===================== 2. Problema ===================== */
seccion("Problema y propuesta");
s = nueva("CLARA");
header(s, "1 · EL PROBLEMA", "El gasto en IA ya compite con los salarios");
g = grupo("auto");
add(g, R(s, 0.6, 1.85, 5.75, 1.3, null, K.ink, { lw: 1.5 }));
add(g, T(s, "token ≈ kWh", { x: 0.8, y: 2.05, w: 2.4, h: 0.9, fontSize: 28, valign: "middle" }));
add(g, T(s, [{ text: "La IA cobra por tokens", options: { bold: true } }, { text: ", pedazos de texto. Como la luz por kWh, se paga por millón de tokens." }],
  { x: 3.25, y: 2.0, w: 2.95, h: 1.0, fontSize: 13, valign: "middle" }));
add(g, T(s, "LAS EMPRESAS PAGAN DE TRES FORMAS", { x: 0.6, y: 3.4, w: 5.7, h: 0.26, fontFace: MONO, fontSize: 11, color: K.muted }), "fade", 300);
[["Asiento con bolsa incluida", "como un plan pospago"], ["Asiento más consumo", "como un cargo básico"], ["Solo pago por uso", "como el prepago"]].forEach((p, i) => {
  const y = 3.75 + i * 0.5;
  add(g, T(s, p[0], { x: 0.6, y, w: 2.9, h: 0.32, fontSize: 15, bold: true }), "fade", 400 + i * 200);
  add(g, T(s, p[1], { x: 3.5, y: y + 0.02, w: 2.8, h: 0.3, fontSize: 14, color: K.muted }), "fade", 400 + i * 200);
  L(s, 0.6, y + 0.42, 6.35, y + 0.42, K.line, 0.75);
});
const cifras = [
  ["4 meses", "tardó Uber en gastarse su presupuesto de IA para programar de 2026."],
  ["150–250 USD", "al mes gasta en promedio un programador con Claude Code (Anthropic)."],
  ["≈ 2 años", "para que los tokens de un programador igualen un salario promedio (Gartner)."],
  ["67%", "de quienes usan IA en el trabajo entran con cuentas personales (Verizon)."],
];
g = grupo("click");
cifras.forEach((c, i) => {
  const x = 6.85 + (i % 2) * 3.0, y = 1.85 + Math.floor(i / 2) * 1.65;
  add(g, L(s, x, y, x + 2.75, y, K.ink, 1.5), "wiperight", i * 250);
  add(g, T(s, c[0], { x, y: y + 0.12, w: 2.8, h: 0.55, fontSize: 26, bold: true }), "fade", i * 250 + 100);
  add(g, T(s, c[1], { x, y: y + 0.7, w: 2.75, h: 0.85, fontSize: 13, color: "3A3A3A" }), "fade", i * 250 + 200);
});
g = grupo("click");
add(g, R(s, 0.6, 5.4, 12.1, 1.05, K.ink, null));
add(g, T(s, [{ text: "Hoy los topes se ponen a ojo. ", options: { bold: true } },
  { text: "Las plataformas dejan poner límites por persona, pero nadie sabe cuánto poner. Y en las empresas pequeñas hay cuentas personales, claves compartidas y cobros que nadie revisa." }],
  { x: 0.85, y: 5.48, w: 11.6, h: 0.9, fontSize: 15, color: K.white, valign: "middle" }));
T(s, "Uber, Gartner y Verizon: reportes de prensa. Claude Code: documentación oficial de Anthropic.", { x: 0.6, y: 6.6, w: 12, h: 0.26, fontSize: 10, color: K.muted });
s.addNotes("Analogía: el token es como el kilovatio-hora y las formas de pago son como planes de celular. Clic 1: las cifras. Clic 2: el problema de fondo, nadie sabe cuánto debería gastar cada persona.");

/* ===================== 3. Propuesta ===================== */
s = nueva("CLARA");
header(s, "2 · LA PROPUESTA", "Qué entrega y por qué es programación lineal");
const resp = ["Cuánto debe gastar cada programador", "Con qué pagarlo más barato", "Cuándo se está gastando de más", "Cómo ajustar a mitad de mes"];
g = grupo("auto");
resp.forEach((r, i) => {
  const x = 0.6 + i * 3.08;
  add(g, R(s, x, 1.8, 2.85, 1.35, null, K.ink), "fade", i * 200);
  add(g, T(s, "0" + (i + 1), { x: x + 0.22, y: 1.95, w: 1, h: 0.26, fontFace: MONO, fontSize: 11, color: K.muted }), "fade", i * 200);
  add(g, T(s, r, { x: x + 0.22, y: 2.25, w: 2.45, h: 0.75, fontSize: 16, bold: true }), "fade", i * 200);
});
T(s, "EN UN PROBLEMA DE PRODUCCIÓN", { x: 0.6, y: 3.5, w: 5.2, h: 0.26, fontFace: MONO, fontSize: 11, color: K.muted });
T(s, "EN ESTE PROYECTO", { x: 6.6, y: 3.5, w: 6, h: 0.26, fontFace: MONO, fontSize: 11, color: K.muted });
L(s, 0.6, 3.82, 12.7, 3.82, K.ink, 1.25);
const eqv = [
  ["Materia prima disponible", "Presupuesto de IA del mes"],
  ["Productos que se fabrican", "Cada tramo de gasto de cada programador"],
  ["Ganancia por unidad", "Valor de un dólar: horas ahorradas × costo de la hora"],
  ["Capacidad de las máquinas", "Topes: % de la nómina y % del salario de cada uno"],
  ["Pedido mínimo", "Un mínimo para que nadie se quede sin herramientas"],
];
g = grupo("click");
eqv.forEach((e, i) => {
  const y = 3.88 + i * 0.5;
  add(g, T(s, e[0], { x: 0.6, y: y + 0.09, w: 5.2, h: 0.32, fontSize: 15 }), "fade", i * 250);
  add(g, T(s, "→", { x: 5.85, y: y + 0.07, w: 0.6, h: 0.32, fontSize: 16, color: K.muted, align: "center" }), "fade", i * 250);
  add(g, T(s, e[1], { x: 6.6, y: y + 0.09, w: 6.1, h: 0.32, fontSize: 15, bold: true }), "fade", i * 250 + 120);
  L(s, 0.6, y + 0.5, 12.7, y + 0.5, K.line, 0.75);
});
s.addNotes("Arriba, las cuatro respuestas que da la herramienta. El clic conecta con lo que el profesor ya conoce: es un problema de producción con otro nombre. La única idea nueva: los primeros dólares rinden más que los siguientes, por eso el gasto se divide en tramos.");

/* ===================== 4. Ciclo ===================== */
seccion("Cómo lo resolvemos");
s = nueva("CLARA");
header(s, "3 · CÓMO LO RESOLVEMOS", "Cada método del curso alimenta al siguiente");
{
  const u = 0.0108, X = v => 0.6 + v * u, Yc = v => 1.75 + v * u;
  const caja = (gg, x, y, t1, t2, dark) => {
    add(gg, R(s, X(x), Yc(y), 210 * u, 72 * u, dark ? K.ink : K.white, K.ink, { lw: 1.25 }));
    add(gg, T(s, [{ text: t1, options: { bold: true, fontSize: 12.5, breakLine: true } }, { text: t2, options: { fontSize: 11, color: dark ? "C8C8C8" : K.muted } }],
      { x: X(x), y: Yc(y), w: 210 * u, h: 72 * u, align: "center", valign: "middle", color: dark ? K.white : K.ink }));
  };
  const pasosCiclo = [
    { t: "Datos de la empresa", tema: null,
      body: "La empresa pone lo que ya sabe: quiénes son sus programadores, cuánto gana cada uno y cuánto pagó el mes pasado en IA. No necesita saber nada de tokens.",
      sale: "las cifras para plantear los modelos." },
    { t: "Modelo 0: qué plan", tema: "Problema de asignación: método húngaro",
      body: "Cada programador recibe exactamente un asiento o plan: Cursor Teams, Claude Premium, Standard o solo API. Se busca el reparto uno a uno que más le conviene a la empresa.",
      sale: "el plan de cada persona y las bolsas que trae cada asiento." },
    { t: "Modelo 1: cuánto gastar", tema: "Planteamiento, método gráfico y Simplex",
      body: "Reparte el presupuesto entre los programadores para sacar el mayor valor, sin romper las reglas de la empresa. El gráfico lo muestra con dos equipos; Simplex lo resuelve con todos.",
      sale: "un tope de gasto para cada persona." },
    { t: "Modelo 2: con qué pagar", tema: "Método de transporte: noroeste, Vogel y MODI",
      body: "Las formas de pago son los orígenes y los equipos, los destinos. Primero se usan las bolsas de los asientos, después lo que tiene descuento y el resto a precio normal.",
      sale: "el plan de pago más barato y el costo real de cada equipo, que vuelve al Modelo 1." },
    { t: "Indicadores", tema: "Análisis de sensibilidad",
      body: "El precio sombra dice cuánto valor deja un dólar más de presupuesto. Si es casi cero, ya se gasta lo justo. Si alguien pasa su tope, sale una alerta.",
      sale: "indicadores y alertas por persona." },
    { t: "Ajuste a mitad de mes", tema: "Método Dual Simplex",
      body: "Si recortan el presupuesto o alguien se pasa, la solución anterior ya no cumple las reglas. El Dual Simplex la corrige desde ahí, sin resolver todo de nuevo.",
      sale: "topes nuevos para el resto del mes." },
    { t: "El mes siguiente", tema: null,
      body: "La factura real reemplaza lo que se había estimado y el ciclo vuelve a empezar. Cada mes la recomendación sale con mejores datos.",
      sale: "un control del gasto que mejora con el tiempo." },
  ];
  pasosCiclo.forEach((p, i) => p.n = `PASO ${i + 1} DE ${pasosCiclo.length}`);
  const px = 9.15, pw = 3.55;
  const panel = (gg, p, delay = 350) => {
    const ns = [];
    ns.push(T(s, p.n, { x: px, y: 1.85, w: pw, h: 0.26, fontFace: MONO, fontSize: 11, color: K.muted }));
    ns.push(T(s, p.t, { x: px, y: 2.15, w: pw, h: 0.45, fontSize: 20, bold: true }));
    let y = 2.75;
    if (p.tema) {
      ns.push(R(s, px, y, pw, 0.85, K.ink, null));
      ns.push(T(s, [{ text: "TEMA DEL CURSO", options: { fontFace: MONO, fontSize: 10, color: "BBBBBB", breakLine: true } }, { text: p.tema, options: { fontSize: 13, bold: true, color: K.white } }],
        { x: px + 0.15, y: y + 0.08, w: pw - 0.3, h: 0.7, valign: "middle" }));
      y += 1.0;
    }
    ns.push(T(s, p.body, { x: px, y, w: pw, h: 1.6, fontSize: 14 }));
    ns.push(T(s, [{ text: "Resultado: ", options: { bold: true } }, { text: p.sale }], { x: px, y: y + 1.7, w: pw, h: 0.75, fontSize: 13, color: "3A3A3A" }));
    ns.forEach(n => add(gg, n, "fade", delay));
    return ns;
  };
  L(s, 8.85, 1.85, 8.85, 6.55, K.line, 0.75);
  // columnas y filas del diagrama (unidades)
  const c1 = 25, c2 = 275, c3 = 525, r1 = 84, r2 = 264, bw = 210, bh = 72;
  let prev;
  const sale = gg => prev.forEach(n => add(gg, n, "out"));

  g = grupo("auto");
  caja(g, c1, r1, "Datos de la empresa", "salarios y facturas");
  prev = panel(g, pasosCiclo[0], 200);

  g = grupo("click"); sale(g);
  add(g, L(s, X(c1 + bw), Yc(r1 + bh / 2), X(c2), Yc(r1 + bh / 2), K.ink, 1.5, { arrow: true }), "wiperight");
  caja(g, c2, r1, "Modelo 0: qué plan", "método húngaro");
  prev = panel(g, pasosCiclo[1]);

  g = grupo("click"); sale(g);
  add(g, L(s, X(c2 + bw), Yc(r1 + bh / 2), X(c3), Yc(r1 + bh / 2), K.ink, 1.5, { arrow: true }), "wiperight");
  caja(g, c3, r1, "Modelo 1: cuánto gastar", "gráfico y Simplex");
  prev = panel(g, pasosCiclo[2]);

  g = grupo("click"); sale(g);
  add(g, L(s, X(605), Yc(r1 + bh), X(605), Yc(r2), K.ink, 1.5, { arrow: true }), "fade");
  add(g, T(s, "demanda", { x: X(480), y: Yc(196), w: 115 * u, h: 0.24, fontSize: 10.5, color: K.muted, align: "right" }));
  caja(g, c3, r2, "Modelo 2: con qué pagar", "transporte");
  add(g, L(s, X(655), Yc(r2), X(655), Yc(r1 + bh), K.ink, 1.5, { arrow: true }), "fade", 500);
  add(g, T(s, "costo real", { x: X(665), y: Yc(196), w: 90 * u, h: 0.24, fontSize: 10.5, color: K.muted }), "fade", 500);
  prev = panel(g, pasosCiclo[3]);

  g = grupo("click"); sale(g);
  add(g, L(s, X(c3), Yc(r2 + bh / 2), X(c2 + bw), Yc(r2 + bh / 2), K.ink, 1.5, { arrow: true }), "fade");
  caja(g, c2, r2, "Indicadores", "sensibilidad", true);
  prev = panel(g, pasosCiclo[4]);

  g = grupo("click"); sale(g);
  add(g, L(s, X(c2), Yc(r2 + bh / 2), X(c1 + bw), Yc(r2 + bh / 2), K.ink, 1.5, { arrow: true }), "fade");
  caja(g, c1, r2, "Ajuste a mitad de mes", "Dual Simplex");
  prev = panel(g, pasosCiclo[5]);

  g = grupo("click"); sale(g);
  add(g, L(s, X(130), Yc(r2), X(130), Yc(r1 + bh), K.ink, 1.5, { arrow: true }), "fade");
  add(g, T(s, "factura real del mes", { x: X(140), y: Yc(196), w: 130 * u, h: 0.24, fontSize: 10.5, color: K.muted }), "fade", 200);
  prev = panel(g, pasosCiclo[6]);
}
s.addNotes("Cada clic agrega un paso al ciclo y el panel de la derecha explica qué hace, qué tema del curso usa y qué resultado le pasa al siguiente. Leer el panel con palabras propias.");

/* ===================== 5. La idea en un ejemplo ===================== */
seccion("Avance");
s = nueva("CLARA");
header(s, "LA IDEA EN UN EJEMPLO", "Cada dólar de IA rinde menos que el anterior");
T(s, "Ana es programadora y gana 2.400 USD al mes, así que su hora vale 15 USD.", { x: 0.6, y: 1.9, w: 4.3, h: 0.9, fontSize: 17 });
T(s, "Cada dólar de IA le ahorra tiempo, pero cada vez menos.", { x: 0.6, y: 2.95, w: 4.3, h: 0.7, fontSize: 17 });
{
  const x0 = 5.9, x1 = 12.4, top = 2.0, bot = 5.6, max = 3.4;
  const Y = v => bot - v / max * (bot - top);
  [0, 1, 2, 3].forEach(t => {
    L(s, x0, Y(t), x1, Y(t), K.line, 0.75);
    T(s, fmt(t), { x: x0 - 0.55, y: Y(t) - 0.12, w: 0.45, h: 0.24, fontFace: MONO, fontSize: 11, color: K.muted, align: "right" });
  });
  T(s, "valor que produce un dólar", { x: x0 - 0.55, y: 1.6, w: 3, h: 0.25, fontSize: 11, color: K.muted });
  L(s, x0, bot, x1, bot, K.ink, 1);
  L(s, x0, Y(1), x1, Y(1), K.bad, 2.25);
  T(s, "cuesta\n1 dólar", { x: x1 + 0.1, y: Y(1) - 0.24, w: 0.85, h: 0.5, fontSize: 12, bold: true, color: K.bad });
  const barras = [["Primeros 100 USD", 3, "3 USD"], ["Siguientes 150 USD", 1.5, "1,50 USD"], ["Más de 250 USD", 0.6, "0,60 USD"]];
  const bw = (x1 - x0) / 3;
  barras.forEach(([lab, v, txt], i) => {
    T(s, lab, { x: x0 + bw * i, y: bot + 0.1, w: bw, h: 0.3, fontSize: 13, align: "center" });
    const gg = grupo("click"), w = 1.2, x = x0 + bw * i + (bw - w) / 2, col = v >= 1 ? K.c1 : K.c3;
    add(gg, R(s, x, Y(v), w, bot - Y(v), col, null), "wipeup");
    add(gg, T(s, txt, { x: x - 0.3, y: Y(v) - 0.38, w: w + 0.6, h: 0.32, fontSize: 16, bold: true, color: col, align: "center" }), "fade", 400);
  });
}
g = grupo("click");
add(g, R(s, 0.6, 4.1, 4.3, 2.3, K.ink, null));
add(g, T(s, [{ text: "Conviene pagarle hasta 250 USD al mes.", options: { bold: true, breakLine: true } },
  { text: "Después, cada dólar produce menos de lo que cuesta. El modelo hace este cálculo para todos a la vez, respetando el presupuesto y las reglas de la empresa." }],
  { x: 0.85, y: 4.25, w: 3.85, h: 2.0, fontSize: 15, color: K.white, valign: "middle" }));
s.addNotes("Explicar la idea con una sola persona. Clic 1: los primeros 100 dólares rinden 3 por cada dólar. Clic 2: los siguientes 150 rinden 1,50. Clic 3: después de 250, cada dólar rinde 60 centavos, menos de lo que cuesta. Clic 4: la conclusión. Los rendimientos son supuestos del ejemplo.");

/* ===================== 6. ¿Y si Uber...? ===================== */
s = nueva("CLARA");
header(s, "UN CÁLCULO ILUSTRATIVO", "¿Y si Uber hubiera usado esta herramienta?");
T(s, "LO QUE PASÓ", { x: 0.6, y: 1.85, w: 5.3, h: 0.26, fontFace: MONO, fontSize: 11, color: K.muted });
L(s, 0.6, 2.18, 5.9, 2.18, K.ink, 1.25);
g = grupo("auto");
[["5.000", "ingenieros usando Claude Code y Cursor"], ["500–2.000", "USD al mes gastaba cada ingeniero, según lo reportado"], ["4 meses", "le duró el presupuesto de IA de todo 2026: se acabó en abril"]].forEach(([v, t], i) => {
  const y = 2.3 + i * 0.95;
  add(g, T(s, v, { x: 0.6, y, w: 2.5, h: 0.5, fontSize: 26, bold: true }), "fade", i * 300);
  add(g, T(s, t, { x: 3.15, y: y + 0.02, w: 2.75, h: 0.8, fontSize: 14, color: "3A3A3A" }), "fade", i * 300);
  L(s, 0.6, y + 0.88, 5.9, y + 0.88, K.line, 0.75);
});
T(s, "CON NUESTRA HERRAMIENTA", { x: 6.6, y: 1.85, w: 6.1, h: 0.26, fontFace: MONO, fontSize: 11, color: K.muted });
L(s, 6.6, 2.18, 12.7, 2.18, K.ink, 1.25);
const pasosU = [
  ["1", "Al ritmo reportado (punto medio, 1.250 USD): 5.000 × 1.250 = 6,25 millones de USD al mes, unos 75 millones al año."],
  ["2", "En nuestro caso de ejemplo, el 18% del gasto estaba por encima del tope óptimo, y la factura final bajó un 10%."],
  ["3", "Con esos mismos porcentajes, Uber se habría ahorrado:"],
];
pasosU.forEach(([n, t], i) => {
  const gg = grupo("click"), y = 2.3 + i * 0.82;
  add(gg, T(s, n, { x: 6.6, y, w: 0.4, h: 0.4, fontFace: MONO, fontSize: 14, bold: true, color: K.muted }));
  add(gg, T(s, t, { x: 7.05, y, w: 5.65, h: 0.75, fontSize: 15 }));
});
g = grupo("click");
add(g, T(s, "≈ 7 a 14 millones de USD al año", { x: 7.05, y: 4.62, w: 5.65, h: 0.5, fontSize: 24, bold: true, color: K.c1 }));
add(g, R(s, 0.6, 5.5, 12.1, 0.95, K.ink, null), "fade", 500);
add(g, T(s, [{ text: "Y sin un tope igual para todos: ", options: { bold: true } },
  { text: "el programa recorta primero el uso que menos rinde y avisa cada mes, antes de que el presupuesto se acabe." }],
  { x: 0.85, y: 5.55, w: 11.6, h: 0.85, fontSize: 15, color: K.white, valign: "middle" }), "fade", 500);
T(s, "Estimación ilustrativa: no se conoce el presupuesto real de Uber ni cuánto le rinde cada dólar. Cifras de Uber reportadas por The Information y citadas por otros medios.",
  { x: 0.6, y: 6.55, w: 12.1, h: 0.3, fontSize: 10, color: K.muted });
s.addNotes("Lo de la izquierda es lo que se reportó de Uber. A la derecha, un cálculo ilustrativo: no conocemos su presupuesto real, así que tomamos el punto medio del gasto reportado y le aplicamos los porcentajes de nuestro caso de ejemplo. El 10% sale si lo recortado se reinvierte en quienes se quedan cortos; el 18%, si solo se corta el exceso.");

/* ===================== 7. Gracias ===================== */
seccion("Cierre");
s = nueva("OSCURA");
s.addText("GASTO EN IA BAJO CONTROL · PROGRAMACIÓN LINEAL", { placeholder: "tag" });
s.addText([{ text: "Gracias", options: { fontSize: 96 } }], { placeholder: "title" });
s.addText("¿Preguntas?", { placeholder: "body" });
s.addNotes("Si hay tiempo, pedirle al profe: que apruebe el enfoque, que acepte que el valor de un dólar de IA sea un supuesto justificado, y confirmar la fecha de entrega y si el trabajo es individual o en grupo.");

pres.writeFile({ fileName: OUT }).then(() => {
  fs.writeFileSync(SPEC, JSON.stringify(anim, null, 1));
  console.log("ok", OUT, Object.keys(anim).length, "diapositivas");
});
