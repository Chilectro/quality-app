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
  aconex?: string;    // "Cargado" o ""
  status: string;     // "ABIERTO" / "CERRADO" / ""
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
  const [grupoDisc, setGrupoDisc] = useState<string>(""); // "", "obra", "mecanico", "ie"

  const [rows, setRows] = useState<Row[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  const [statusFilter, setStatusFilter] = useState<string>(""); // "", "ABIERTO", "CERRADO"
  const [onlyCargado, setOnlyCargado] = useState<boolean>(false);
  const [onlyErrorSS, setOnlyErrorSS] = useState<boolean>(false);
  const [sinAconex, setSinAconex] = useState<boolean>(false); // NUEVO: Sin cargar Aconex

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
    return () => {
      alive = false;
    };
  }, []);

  async function fetchList(p = 1) {
    setErr(null);
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (subsistema) params.set("subsistema", subsistema);
      if (disciplina) params.set("disciplina", disciplina);
      if (grupoDisc) params.set("grupo", grupoDisc); // NUEVO
      if (q.trim()) params.set("q", q.trim());
      if (statusFilter) params.set("status", statusFilter);
      if (onlyCargado) params.set("cargado", "true");
      if (onlyErrorSS) params.set("error_ss", "true");
      if (sinAconex) params.set("sin_aconex", "true"); // NUEVO
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
    if (grupoDisc) params.set("grupo", grupoDisc); // NUEVO
    if (q.trim()) params.set("q", q.trim());
    if (statusFilter) params.set("status", statusFilter);
    if (onlyCargado) params.set("cargado", "true");
    if (onlyErrorSS) params.set("error_ss", "true");
    if (sinAconex) params.set("sin_aconex", "true"); // NUEVO

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

  function onLimpiar() {
    setDisciplina("");
    setSubsistema("");
    setGrupoDisc("");
    setQ("");
    setStatusFilter("");
    setOnlyCargado(false);
    setOnlyErrorSS(false);
    setSinAconex(false);
    setRows([]);
    setTotal(0);
    setPage(1);
  }

  const canPrev = page > 1;
  const canNext = page * pageSize < total;

  return (
    <div className="h-[calc(100vh-49px)] flex flex-col">
      {/* Layout: Filtros a la izquierda, tabla a la derecha */}
      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-0 h-full overflow-hidden">
        {/* PANEL DE FILTROS (izquierda) */}
        <div className="border-r bg-gray-50 p-4 overflow-y-auto">
          <div className="space-y-4">
            <h2 className="font-semibold text-lg border-b pb-2">Filtros</h2>

          {/* Grupo de Disciplinas (NUEVO) */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Grupo de Disciplinas
            </label>
            <select
              className="w-full border rounded-lg px-3 py-2 bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              value={grupoDisc}
              onChange={(e) => setGrupoDisc(e.target.value)}
            >
              <option value="">— Todos los grupos —</option>
              <option value="obra">Obra civil</option>
              <option value="mecanico">Mecánico Pipping</option>
              <option value="ie">Instrumentación Eléctricos</option>
            </select>
          </div>

          {/* Disciplina individual */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Disciplina específica
            </label>
            <select
              className="w-full border rounded-lg px-3 py-2 bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100"
              value={disciplina}
              onChange={(e) => setDisciplina(e.target.value)}
              disabled={!!grupoDisc}
            >
              <option value="">— Todas —</option>
              {opts.disciplinas.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
            {grupoDisc && (
              <p className="text-xs text-gray-500 mt-1">
                Deshabilitado porque seleccionaste un grupo
              </p>
            )}
          </div>

          {/* Subsistema */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Subsistema
            </label>
            <select
              className="w-full border rounded-lg px-3 py-2 bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              value={subsistema}
              onChange={(e) => setSubsistema(e.target.value)}
            >
              <option value="">— Todos —</option>
              {opts.subsistemas.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>

          {/* Estado */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Estado
            </label>
            <select
              className="w-full border rounded-lg px-3 py-2 bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="">— Todos —</option>
              <option value="ABIERTO">Abiertos</option>
              <option value="CERRADO">Cerrados</option>
            </select>
          </div>

          {/* Búsqueda de texto */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Buscar texto
            </label>
            <input
              className="w-full border rounded-lg px-3 py-2 bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="Código / Descripción / Tag"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>

          {/* Checkboxes */}
          <div className="space-y-3 pt-2 border-t">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                checked={onlyCargado}
                onChange={(e) => {
                  const v = e.target.checked;
                  setOnlyCargado(v);
                  if (v) {
                    setOnlyErrorSS(false);
                    setSinAconex(false);
                  }
                }}
              />
              <span className="text-sm">Solo cargados en Aconex</span>
            </label>

            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                checked={sinAconex}
                onChange={(e) => {
                  const v = e.target.checked;
                  setSinAconex(v);
                  if (v) {
                    setOnlyCargado(false);
                    setOnlyErrorSS(false);
                  }
                }}
              />
              <span className="text-sm">Sin cargar en Aconex</span>
            </label>

            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                checked={onlyErrorSS}
                onChange={(e) => {
                  const v = e.target.checked;
                  setOnlyErrorSS(v);
                  if (v) {
                    setOnlyCargado(false);
                    setSinAconex(false);
                  }
                }}
              />
              <span className="text-sm">Solo Error SS</span>
            </label>
          </div>

          {/* Botones de acción */}
          <div className="space-y-2 pt-3 border-t">
            <button
              onClick={onBuscar}
              disabled={loading}
              className="w-full px-4 py-2.5 rounded-lg bg-black text-white hover:bg-gray-800 disabled:bg-gray-400 font-medium"
            >
              {loading ? "Buscando..." : "Aplicar Filtros"}
            </button>
            <button
              onClick={onLimpiar}
              className="w-full px-4 py-2.5 rounded-lg border bg-white hover:bg-gray-50 text-sm"
            >
              Limpiar filtros
            </button>
          </div>

          {/* Card de resultados */}
          {total > 0 && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mt-4">
              <div className="text-sm text-blue-800 font-medium">
                {fmt(total)} protocolos encontrados
              </div>
              <button
                onClick={onDescargar}
                className="mt-3 w-full px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 text-sm font-medium"
              >
                📥 Exportar a Excel
              </button>
            </div>
          )}
          </div>
        </div>

        {/* TABLA (derecha) */}
        <div className="flex flex-col h-full overflow-hidden bg-white">
          {err && (
            <div className="p-4 bg-red-50 text-red-700 border-b border-red-200">
              {err}
            </div>
          )}

          <div className="flex-1 overflow-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  <th className="text-left px-3 py-3 font-semibold text-gray-700">
                    NÚMERO DE DOCUMENTO
                  </th>
                  <th className="text-left px-3 py-3 font-semibold text-gray-700">
                    REV.
                  </th>
                  <th className="text-left px-3 py-3 font-semibold text-gray-700">
                    DESCRIPCIÓN
                  </th>
                  <th className="text-left px-3 py-3 font-semibold text-gray-700">
                    TAG
                  </th>
                  <th className="text-left px-3 py-3 font-semibold text-gray-700">
                    SUBSISTEMA
                  </th>
                  <th className="text-left px-3 py-3 font-semibold text-gray-700">
                    ACONEX
                  </th>
                  <th className="text-left px-3 py-3 font-semibold text-gray-700">
                    STATUS
                  </th>
                </tr>
              </thead>
              <tbody>
                {!rows.length ? (
                  <tr>
                    <td className="px-3 py-8 text-gray-500 text-center" colSpan={7}>
                      {loading ? "Cargando..." : "No hay datos. Aplica filtros y haz clic en 'Buscar'."}
                    </td>
                  </tr>
                ) : (
                  rows.map((r, i) => {
                    const isCerrado = (r.status || "").toUpperCase() === "CERRADO";
                    const tieneAconex = !!(r.aconex || "").trim();
                    return (
                      <tr key={i} className="odd:bg-white even:bg-gray-50 hover:bg-blue-50">
                        <td className="px-3 py-2 font-mono">{r.document_no}</td>
                        <td className="px-3 py-2">{r.rev}</td>
                        <td className="px-3 py-2">{r.descripcion}</td>
                        <td className="px-3 py-2 font-mono text-xs">{r.tag}</td>
                        <td className="px-3 py-2">{r.subsistema}</td>
                        <td className="px-3 py-2">
                          {tieneAconex ? (
                            <span className="inline-flex items-center px-2 py-1 rounded-full text-xs bg-green-100 text-green-800">
                              ✓ Cargado
                            </span>
                          ) : (
                            <span className="text-gray-400 text-xs">—</span>
                          )}
                        </td>
                        <td className="px-3 py-2">
                          <div className="flex items-center gap-2">
                            <span
                              className={`w-2.5 h-2.5 rounded-full ${
                                isCerrado ? "bg-green-500" : "bg-red-500"
                              }`}
                              title={r.status}
                            />
                            <span className="text-xs">{r.status}</span>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Paginación */}
          {total > 0 && (
            <div className="flex items-center justify-between border-t px-4 py-3 bg-gray-50">
              <div className="text-sm text-gray-600">
                Página {page} de {Math.max(1, Math.ceil(total / pageSize))}
              </div>
              <div className="flex gap-2 items-center">
                <button
                  disabled={!canPrev || loading}
                  onClick={() => fetchList(page - 1)}
                  className={`px-3 py-2 rounded-lg border text-sm ${
                    canPrev && !loading
                      ? "bg-white hover:bg-gray-50"
                      : "bg-gray-100 text-gray-400 cursor-not-allowed"
                  }`}
                >
                  ← Anterior
                </button>
                <select
                  value={pageSize}
                  onChange={(e) => {
                    setPageSize(Number(e.target.value));
                    fetchList(1);
                  }}
                  className="border rounded-lg px-2 py-2 text-sm bg-white"
                >
                  {[25, 50, 100, 200, 500].map((n) => (
                    <option key={n} value={n}>
                      {n}/pág
                    </option>
                  ))}
                </select>
                <button
                  disabled={!canNext || loading}
                  onClick={() => fetchList(page + 1)}
                  className={`px-3 py-2 rounded-lg border text-sm ${
                    canNext && !loading
                      ? "bg-white hover:bg-gray-50"
                      : "bg-gray-100 text-gray-400 cursor-not-allowed"
                  }`}
                >
                  Siguiente →
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
