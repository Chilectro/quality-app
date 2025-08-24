// src/api/client.ts
import axios from "axios";
import type { InternalAxiosRequestConfig, AxiosResponse } from "axios";
import { useAuthStore } from "../store/auth";

const BASE = (import.meta.env.VITE_API_URL as string) ?? "http://127.0.0.1:8000";

const api = axios.create({
  baseURL: BASE,
  withCredentials: true, // necesario para enviar/recibir la cookie de refresh
  headers: { Accept: "application/json" },
});

// --- Authorization en cada request ---
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

// --- Refresh automático con cookie y reintento 1 vez ---
let refreshing: Promise<string | null> | null = null;

async function refreshToken(): Promise<string | null> {
  try {
    const res = await axios.post(`${BASE}/auth/refresh`, {}, { withCredentials: true });
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
      refreshing = refreshing ?? refreshToken();
      const newTok = await refreshing;
      refreshing = null;
      if (newTok) {
        const h: any = original.headers ?? {};
        if (typeof h.set === "function") {
          h.set("Authorization", `Bearer ${newTok}`);
        } else {
          h["Authorization"] = `Bearer ${newTok}`;
        }
        original.headers = h;
        return api(original);
      }
    }
    return Promise.reject(error);
  }
);

// --- Helpers que usa tu Dashboard ---
export async function apiGet<T = any>(url: string, config?: any): Promise<T> {
  const res: AxiosResponse<T> = await api.get(url, config);
  return res.data;
}

export async function apiPost<T = any>(url: string, data?: any, config?: any): Promise<T> {
  const res: AxiosResponse<T> = await api.post(url, data, config);
  return res.data;
}

export default api;