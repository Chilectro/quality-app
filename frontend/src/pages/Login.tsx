import { useState } from "react";
import type { FormEvent } from "react";
import api from "../lib/api";
import { useAuthStore } from "../store/auth";
import { useNavigate } from "react-router-dom";

export default function Login() {
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAccessToken);

  const [email, setEmail] = useState("rrojasb@acciona.com");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setErr(null);
    setLoading(true);
    try {
      const res = await api.post(
        "/auth/login",
        { email, password },
        {
          // MUY IMPORTANTE para que el navegador guarde la cookie HttpOnly de refresh
          withCredentials: true,
          headers: { Accept: "application/json" },
        }
      );

      const data = res.data as {
        access_token: string;
        email: string;
        name?: string;
        roles?: string[];
      };

      const token = data.access_token;
      const profile = {
        email: data.email,
        name: data.name,
        roles: data.roles ?? [],
      };

      setAuth(token, profile);
      navigate("/");
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || "Error de login";
      setErr(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-sm mx-auto p-6">
      <h1 className="text-xl font-semibold mb-4">Ingreso</h1>
      <form onSubmit={onSubmit} className="space-y-3">
        <div>
          <label className="block text-sm mb-1">Email</label>
          <input
            type="email"
            className="w-full border px-3 py-2 rounded"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="username"
            required
          />
        </div>
        <div>
          <label className="block text-sm mb-1">Contraseña</label>
          <input
            type="password"
            className="w-full border px-3 py-2 rounded"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
            minLength={8}
          />
        </div>
        {err && <p className="text-red-600 text-sm">{err}</p>}
        <button
          disabled={loading}
          className="bg-blue-600 text-white px-4 py-2 rounded disabled:opacity-50"
        >
          {loading ? "Ingresando…" : "Ingresar"}
        </button>
      </form>
    </div>
  );
}