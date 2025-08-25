import axios from "axios";
import type { InternalAxiosRequestConfig } from "axios";
import { useAuthStore } from "../store/auth";

// BACKENDS
const RENDER_BACKEND = "https://quality-app-ufxj.onrender.com";
const LOCAL_BACKEND  = "http://127.0.0.1:8000";

function pickBase(): string {
  // 1) Variables de entorno (ambos nombres soportados)
  const env =
    (import.meta as any)?.env?.VITE_API_URL ??
    (import.meta as any)?.env?.VITE_API_BASE_URL ??
    "";

  const fromEnv = String(env || "").trim();
  if (fromEnv) return fromEnv.replace(/\/+$/, "");

  // 2) Detección por hostname en runtime (por si falla la env)
  const host = (typeof window !== "undefined" && window.location.hostname) || "";
  if (host.includes("onrender.com") || host.includes("pages.dev")) {
    return RENDER_BACKEND;
  }

  // 3) Desarrollo local
  return LOCAL_BACKEND;
}

export const BASE = pickBase();

const api = axios.create({
  baseURL: BASE,
  withCredentials: true,
  headers: { Accept: "application/json" },
});

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    const h: any = config.headers ?? {};
    if (typeof h.set === "function") {
      h.set("Authorization", `Bearer ${token}`);
    } else {
      h["Authorization"] = `Bearer ${token}`;
    }
    config.headers = h;
  }
  return config;
});

let refreshing: Promise<string | null> | null = null;

async function doRefresh(): Promise<string | null> {
  try {
    // Usa SIEMPRE la misma instancia para respetar baseURL y cookies
    const res = await api.post("/auth/refresh", {});
    const token = res.data?.access_token as string;
    useAuthStore.getState().setAccessToken(token, {
      email: res.data?.email,
      name: res.data?.name,
      roles: res.data?.roles || [],
    });
    return token || null;
  } catch {
    useAuthStore.getState().logout();
    return null;
  }
}

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const original: any = error?.config;
    if (error?.response?.status === 401 && original && !original._retry) {
      original._retry = true;
      refreshing = refreshing ?? doRefresh();
      const newTok = await refreshing;
      refreshing = null;
      if (newTok) {
        const h: any = original.headers ?? {};
        if (typeof h.set === "function") {
          h.set("Authorization", `Bearer ${newTok}`);
        } else {
          h["Authorization"] = `Bearer ${newTok}`);
        }
        original.headers = h;
        return api(original);
      }
    }
    return Promise.reject(error);
  }
);

export default api;