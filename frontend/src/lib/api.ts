import axios from "axios";
import type { InternalAxiosRequestConfig } from "axios";
import { useAuthStore } from "../store/auth";

const BASE = (import.meta.env.VITE_API_URL as string) ?? "http://127.0.0.1:8000";

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
      refreshing = refreshing ?? doRefresh();
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

export default api;