/* Preferencias de quien mira: idioma (español / inglés) y tema (claro / oscuro).
   Se recuerdan en este navegador; si no hay nada guardado, se sigue al sistema. */
import { EN } from "./en.js";

const leer = k => { try { return localStorage.getItem(k); } catch (_) { return null; } };
const guardar = (k, v) => { try { localStorage.setItem(k, v); } catch (_) { /* sin almacenamiento */ } };

let idioma = leer("gia-idioma") || ((navigator.language || "es").toLowerCase().startsWith("es") ? "es" : "en");
export const lang = () => idioma;
export const locale = () => (idioma === "en" ? "en-US" : "es-CO");
export function cambiarIdioma(l) {
  idioma = l === "en" ? "en" : "es";
  guardar("gia-idioma", idioma);
  document.documentElement.lang = idioma;
}
document.documentElement.lang = idioma;

/** Traduce un texto escrito en español. `{clave}` se reemplaza con `vars`. Sin traducción, queda en español. */
export function t(es, vars) {
  let s = idioma === "en" ? (EN[es] ?? es) : es;
  if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
  return s;
}

export function temaActual() {
  const fijo = document.documentElement.dataset.theme;
  if (fijo === "light" || fijo === "dark") return fijo;
  return matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}
export function cambiarTema() {
  const nuevo = temaActual() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = nuevo;
  guardar("gia-tema", nuevo);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = nuevo === "light" ? "#f7f7f8" : "#09090a";
  return nuevo;
}
