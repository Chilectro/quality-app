// src/pages/LogProtocolos.tsx
import { useEffect, useState } from "react";
import { apiGet } from "../api/client";
import { useAuthStore } from "../store/auth";

type Options = {
  disciplinas: string[];
  subsistemas: string[];
};

type Row = {
  document_no: string;
  rev: string; // "0"
  descripcion: string;
  tag: string;
  subsistema: string;
};

type ListResponse = {
  rows: Row[];
  total: number;
  page: number;
  page_size: number;
};

const fmt = (n: number) => n.toLocaleString("es-CL");

export default function LogProtocolos() {
  const [opts, setOpts] = useState<Options>({ disciplinas: [], subsistemas: [] });
  const [disciplina, setDisciplina] = useState<string>("");
  const [subsistema, setSubsistema] = useState<string>("");
  const [q, setQ] = useState<string>("");

  const [rows, setRows] = useState<Row[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const token = useAuthStore((s) => s.accessToken);
  const API_URL = import.meta.env.VITE_API_URL as string;

  // cargar opciones
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const o = await apiGet<Options>("/apsa/options");
        if (!alive) return;
        setOpts(o);
      } catch (e: any) {
        setErr(e?.message || "Error cargando opciones");
      }
    })();
    return () => { alive = false; };
  }, []);

  async function fetchList(p = 1) {
    setErr(null);
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (subsistema) params.set("subsistema", subsistema);
      if (disciplina) params.set("disciplina", disciplina);
      if (q.trim()) params.set("q", q.trim());
      params.set("page", String(p));
      params.set("page_size", String(pageSize));

      const data = await apiGet<ListResponse>(`/apsa/list?${params.toString()}`);
      setRows(data.rows || []);
      setTotal(data.total || 0);
      setPage(data.page || p);
    } catch (e: any) {
      setErr(e?.message || "Error al buscar protocolos");
    } finally {
      setLoading(false);
    }
  }

  function onBuscar() {
    fetchList(1);
  }

  function onDescargar() {
    const params = new URLSearchParams();
    if (subsistema) params.set("subsistema", subsistema);
    if (disciplina) params.set("disciplina", disciplina);
    if (q.trim()) params.set("q", q.trim());

    const url = `${API_URL}/export/apsa.csv?${params.toString()}`;
    fetch(url, { headers: { Authorization: `Bearer ${token}` }, credentials: "include" })
      .then((res) => {
        if (!res.ok) throw new Error("No se pudo descargar");
        return res.blob();
      })
      .then((blob) => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "log_protocolos.csv";
        a.click();
        URL.revokeObjectURL(a.href);
      })
      .catch((e) => setErr(e?.message || "Error al descargar"));
  }

  const canPrev = page > 1;
  const canNext = page * pageSize < total;

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-xl font-semibold">Log Protocolos</h1>

      {/* Filtros */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
        <div>
          <label className="block text-sm text-gray-600 mb-1">Subsistema</label>
          <select className="w-full border rounded-lg px-3 py-2"
                  value={subsistema}
                  onChange={(e) => setSubsistema(e.target.value)}>
            <option value="">— Todos —</option>
            {opts.subsistemas.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm text-gray-600 mb-1">Disciplina</label>
          <select className="w-full border rounded-lg px-3 py-2"
                  value={disciplina}
                  onChange={(e) => setDisciplina(e.target.value)}>
            <option value="">— Todas —</option>
            {opts.disciplinas.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm text-gray-600 mb-1">Buscar (código / descripción / tag)</label>
          <input className="w-full border rounded-lg px-3 py-2"
                 placeholder="ej: 5620-S01 / VÁLVULA / PRC..."
                 value={q}
                 onChange={(e) => setQ(e.target.value)} />
        </div>

        <div className="flex gap-2">
          <button onClick={onBuscar}
                  className="px-4 py-2 rounded-lg bg-black text-white">
            {loading ? "Buscando..." : "Buscar"}
          </button>
          <button onClick={onDescargar}
                  className="px-4 py-2 rounded-lg border bg-white hover:bg-gray-50">
            Descargar Excel
          </button>
        </div>
      </div>

      {/* Estado / errores */}
      <div className="text-sm text-gray-500">
        {total ? <>Resultado: <b>{fmt(total)}</b> filas</> : null}
      </div>
      {err ? <div className="p-3 rounded-lg bg-red-50 text-red-700 border border-red-200">{err}</div> : null}

      {/* Tabla */}
      <div className="overflow-auto rounded-2xl border bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="text-left px-3 py-2">NÚMERO DE DOCUMENTO ACONEX</th>
              <th className="text-left px-3 py-2">REV.</th>
              <th className="text-left px-3 py-2">DESCRIPCIÓN</th>
              <th className="text-left px-3 py-2">TAG</th>
              <th className="text-left px-3 py-2">SUBSISTEMA</th>
            </tr>
          </thead>
          <tbody>
            {!rows.length ? (
              <tr><td className="px-3 py-4 text-gray-500" colSpan={5}>Sin datos</td></tr>
            ) : rows.map((r, i) => (
              <tr key={i} className="odd:bg-white even:bg-gray-50">
                <td className="px-3 py-2">{r.document_no}</td>
                <td className="px-3 py-2">{r.rev}</td>
                <td className="px-3 py-2">{r.descripcion}</td>
                <td className="px-3 py-2">{r.tag}</td>
                <td className="px-3 py-2">{r.subsistema}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Paginación */}
      <div className="flex items-center justify-between">
        <div className="text-sm text-gray-500">
          Página {page} de {Math.max(1, Math.ceil(total / pageSize))}
        </div>
        <div className="flex gap-2">
          <button
            disabled={!canPrev || loading}
            onClick={() => fetchList(page - 1)}
            className={`px-3 py-2 rounded-lg border ${canPrev ? "bg-white hover:bg-gray-50" : "bg-gray-100 text-gray-400 cursor-not-allowed"}`}
          >
            ← Anterior
          </button>
          <button
            disabled={!canNext || loading}
            onClick={() => fetchList(page + 1)}
            className={`px-3 py-2 rounded-lg border ${canNext ? "bg-white hover:bg-gray-50" : "bg-gray-100 text-gray-400 cursor-not-allowed"}`}
          >
            Siguiente →
          </button>
          <select
            value={pageSize}
            onChange={(e) => { setPageSize(Number(e.target.value)); fetchList(1); }}
            className="border rounded-lg px-2 py-2 text-sm"
          >
            {[25, 50, 100, 200, 500].map((n) => <option key={n} value={n}>{n}/página</option>)}
          </select>
        </div>
      </div>
    </div>
  );
}