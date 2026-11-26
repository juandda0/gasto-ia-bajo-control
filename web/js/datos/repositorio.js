/* Capa de datos: lectura en tiempo real y escritura de la empresa en Firestore.
   La interfaz no sabe de colecciones ni documentos: solo recibe objetos por callbacks. */
import {
  collection, doc, onSnapshot, query, where, setDoc, orderBy, limit,
} from "https://www.gstatic.com/firebasejs/13.2.0/firebase-firestore.js";
import { db } from "./firebase.js";

const org = id => doc(db, "organizaciones", id);
const estado = (id, nombre) => doc(db, "organizaciones", id, "estado", nombre);

/** Empresas de las que la persona es miembro. */
export function escucharMisEmpresas(uid, cb, error) {
  const q = query(collection(db, "organizaciones"), where("miembrosUid", "array-contains", uid));
  return onSnapshot(q, s => cb(s.docs.map(d => ({ id: d.id, ...d.data() }))), error);
}

/**
 * Escucha todo lo de una empresa y avisa cada cambio con `cb(parte, valor)`.
 * Partes: empresa, caso, seguimiento, plan, gasto (del mes), historial, alertas, conciliacion, tokens.
 * Devuelve una función para dejar de escuchar. `cambiarMes(mes)` re-apunta las lecturas del mes.
 */
export function escucharEmpresa(id, esAdmin, cb, error) {
  const subs = [];
  const fuera = [];
  const on = (ref, parte, mapa) => subs.push(onSnapshot(ref, s => cb(parte, mapa(s)), e => error(parte, e)));
  on(org(id), "empresa", s => (s.exists() ? { id: s.id, ...s.data() } : null));
  on(estado(id, "caso"), "caso", s => (s.exists() ? s.data() : null));
  on(estado(id, "seguimiento"), "seguimiento", s => (s.exists() ? s.data() : null));
  on(estado(id, "plan"), "plan", s => {
    if (!s.exists()) return null;
    const d = s.data();
    let resultado = null;
    try { resultado = d.resultado ? JSON.parse(d.resultado) : null; } catch (_) { resultado = null; }
    return { version: d.version || 0, error: d.error || null, resultado };
  });
  on(query(collection(db, "organizaciones", id, "historial"), orderBy("mes", "desc"), limit(24)), "historial",
    s => s.docs.map(d => d.data()).reverse());
  on(query(collection(db, "organizaciones", id, "alertas"), orderBy("creadaEn", "desc"), limit(30)), "alertas",
    s => s.docs.map(d => ({ id: d.id, ...d.data() })));
  if (esAdmin) on(collection(db, "organizaciones", id, "tokens"), "tokens", s => s.docs.map(d => ({ id: d.id, ...d.data() })));

  let mesActual = null;
  const cambiarMes = mes => {
    if (mes === mesActual) return;
    mesActual = mes;
    fuera.splice(0).forEach(f => f());
    fuera.push(onSnapshot(collection(db, "organizaciones", id, "gasto", mes, "personas"),
      s => cb("gasto", { mes, personas: Object.fromEntries(s.docs.map(d => [d.id, d.data()])) }), e => error("gasto", e)));
    fuera.push(onSnapshot(doc(db, "organizaciones", id, "conciliacion", mes),
      s => cb("conciliacion", s.exists() ? s.data() : null), e => error("conciliacion", e)));
  };
  const parar = () => { subs.forEach(f => f()); fuera.forEach(f => f()); };
  return { parar, cambiarMes };
}

export const guardarCaso = (id, caso) => setDoc(estado(id, "caso"), caso);
export const guardarSeguimiento = (id, seg) => setDoc(estado(id, "seguimiento"), {
  mes: seg.mes, recorte: !!seg.recorte, manual: seg.manual || {}, hechos: seg.hechos || {},
});
