/* Capa de datos: conexión con Firebase (Auth, Firestore en tiempo real y Functions).
   En localhost usa los emuladores; en producción, el proyecto real. */
import { initializeApp } from "https://www.gstatic.com/firebasejs/13.2.0/firebase-app.js";
import {
  getAuth, connectAuthEmulator, GoogleAuthProvider, signInWithPopup, signOut, onAuthStateChanged,
} from "https://www.gstatic.com/firebasejs/13.2.0/firebase-auth.js";
import {
  initializeFirestore, connectFirestoreEmulator, persistentLocalCache, persistentMultipleTabManager,
} from "https://www.gstatic.com/firebasejs/13.2.0/firebase-firestore.js";
import { getFunctions, connectFunctionsEmulator, httpsCallable } from "https://www.gstatic.com/firebasejs/13.2.0/firebase-functions.js";

// Configuración pública de la app web (no es un secreto: la protegen las reglas de seguridad).
const CONFIG = {
  apiKey: "AIzaSyAtuDE-aumEjRnDFCYQwAuCNy9QyWY3QZs",
  authDomain: "gasto-ia-bajo-control.firebaseapp.com",
  projectId: "gasto-ia-bajo-control",
  storageBucket: "gasto-ia-bajo-control.firebasestorage.app",
  messagingSenderId: "857014032102",
  appId: "1:857014032102:web:8c532ebed91dccd3708d27",
};
export const REGION = "us-east1";
export const LOCAL = ["localhost", "127.0.0.1"].includes(location.hostname);

const app = initializeApp(CONFIG);
export const auth = getAuth(app);
let cache;
try { cache = persistentLocalCache({ tabManager: persistentMultipleTabManager() }); } catch (_) { cache = undefined; }
export const db = initializeFirestore(app, cache && !LOCAL ? { localCache: cache } : {});
export const funciones = getFunctions(app, REGION);

if (LOCAL) {
  connectAuthEmulator(auth, `http://${location.hostname}:9199`, { disableWarnings: true });
  connectFirestoreEmulator(db, location.hostname, 8181);
  connectFunctionsEmulator(funciones, location.hostname, 5101);
}

export const entrarConGoogle = () => signInWithPopup(auth, new GoogleAuthProvider());
export const salir = () => signOut(auth);
export const alCambiarSesion = cb => onAuthStateChanged(auth, cb);

const llamar = httpsCallable(funciones, "app", { timeout: 120000 });
/** Ejecuta una acción del servidor ({accion, ...datos}) y devuelve su resultado. */
export async function accion(nombre, datos = {}) {
  try {
    return (await llamar({ accion: nombre, ...datos })).data;
  } catch (e) {
    throw new Error(e?.message || "No se pudo completar la acción.");
  }
}

/** URL a la que Claude Code manda su telemetría (Claude Code le agrega /v1/logs). */
export const URL_INGESTA = `${location.origin}/otlp`;
