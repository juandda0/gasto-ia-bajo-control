/* Capa de dominio del navegador: fechas del mes, gasto por persona y lectura de CSV.
   Funciones puras: no tocan la pantalla ni Firebase. */

export function hoyEn(zona = "America/Bogota") {
  const p = Object.fromEntries(new Intl.DateTimeFormat("en-CA", { timeZone: zona, year: "numeric", month: "2-digit", day: "2-digit" })
    .formatToParts(new Date()).map(x => [x.type, x.value]));
  return { mes: `${p.year}-${p.month}`, dia: +p.day };
}
export const diasDe = m => { const [a, b] = m.split("-").map(Number); return new Date(a, b, 0).getDate(); };
export const nombreMes = (m, locale = "es-CO") => {
  const [a, b] = m.split("-").map(Number);
  const t = new Date(a, b - 1, 1).toLocaleDateString(locale, { month: "long", year: "numeric" });
  return t[0].toUpperCase() + t.slice(1);
};
/** Día del mes del seguimiento: hoy si es el mes en curso; el último si ya terminó (falta cerrarlo). */
export function diaDelMes(mes, zona) {
  const hoy = hoyEn(zona);
  if (mes === hoy.mes) return hoy.dia;
  return mes < hoy.mes ? diasDe(mes) : 1;
}

/**
 * Gasto automático por persona: lo que reportó Claude con su id, más lo que llegó a nombre de su
 * correo antes de que la agregaran al equipo. Lo que no es de nadie queda en `sinAsignar`.
 */
export function repartirGasto(personas, gastoMes) {
  const porId = {}, porDia = {}, sinAsignar = [];
  const ids = new Set(personas.map(p => p.id));
  const porCorreo = Object.fromEntries(personas.filter(p => p.email).map(p => [String(p.email).toLowerCase(), p.id]));
  let ultimo = null;
  for (const [clave, fila] of Object.entries(gastoMes || {})) {
    const usd = Number(fila.usd) || 0;
    const dueño = ids.has(clave) ? clave : porCorreo[String(fila.email || "").toLowerCase()];
    if (dueño) porId[dueño] = (porId[dueño] || 0) + usd;
    else sinAsignar.push({ clave, email: fila.email || "", usd });
    for (const [d, v] of Object.entries(fila.porDia || {})) porDia[+d] = (porDia[+d] || 0) + (Number(v) || 0);
    const t = fila.ultimo?.toDate ? fila.ultimo.toDate() : null;
    if (t && (!ultimo || t > ultimo)) ultimo = t;
  }
  sinAsignar.sort((a, b) => b.usd - a.usd);
  return { porId, porDia, sinAsignar, ultimo };
}

/** Lee un CSV simple (coma o punto y coma, con encabezado) y devuelve personas. */
export function leerCsv(texto) {
  const lineas = texto.replace(/^﻿/, "").split(/\r?\n/).filter(l => l.trim());
  if (lineas.length < 2) return [];
  const sep = (lineas[0].match(/;/g) || []).length > (lineas[0].match(/,/g) || []).length ? ";" : ",";
  const partir = l => {
    const out = []; let cur = "", q = false;
    for (let i = 0; i < l.length; i++) {
      const c = l[i];
      if (c === '"') { if (q && l[i + 1] === '"') { cur += '"'; i++; } else q = !q; }
      else if (c === sep && !q) { out.push(cur); cur = ""; }
      else cur += c;
    }
    out.push(cur);
    return out.map(x => x.trim());
  };
  const sinTilde = s => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const cab = partir(lineas[0]).map(sinTilde);
  const col = (...nombres) => cab.findIndex(c => nombres.some(n => c.includes(n)));
  const i = { nombre: col("nombre", "name"), email: col("correo", "email", "mail"), equipo: col("equipo", "team", "area"),
    salario: col("salario", "sueldo", "salary"), herramienta: col("herramienta", "tool"), gasto: col("gasto", "spend") };
  const herramientas = { claude: "Claude", cursor: "Cursor", openai: "OpenAI", chatgpt: "OpenAI", gemini: "Gemini" };
  const num = v => Math.max(0, Number(String(v || "").replace(/[^\d.,-]/g, "").replace(/\.(?=\d{3}(\D|$))/g, "").replace(",", ".")) || 0);
  return lineas.slice(1).map(partir).map(f => ({
    nombre: i.nombre >= 0 ? f[i.nombre] : "",
    email: i.email >= 0 ? String(f[i.email] || "").toLowerCase() : "",
    equipo: i.equipo >= 0 ? f[i.equipo] || "General" : "General",
    salario: i.salario >= 0 ? num(f[i.salario]) : 2000,
    herramienta: herramientas[sinTilde(i.herramienta >= 0 ? f[i.herramienta] || "" : "")] || (i.herramienta >= 0 && f[i.herramienta] ? "Ninguna" : "Claude"),
    gasto: i.gasto >= 0 ? num(f[i.gasto]) : 0,
  })).filter(p => p.nombre || p.email);
}

export const PLANTILLA_CSV = "nombre,correo,equipo,salario,herramienta,gasto\nAna Pérez,ana@empresa.com,Backend,2400,Claude,420\n";
