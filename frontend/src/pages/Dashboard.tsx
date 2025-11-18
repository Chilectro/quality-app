// src/pages/Dashboard.tsx
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { apiGet } from "../api/client";
// import StatCard from "../components/StatCard";
import { useAuthStore } from "../store/auth";

type Cards = {
  universo: number;
  abiertos: number;
  cerrados: number;
  aconex_cargados: number;
  aconex_validos?: number;
  aconex_invalidos?: number;
  aconex_error_ss?: number;
};

type DisciplinaRow = {
  disciplina: string;
  universo: number;
  abiertos: number;
  cerrados: number;
  aconex: number;
};

type GrupoRow = {
  grupo: string;
  universo: number;
  abiertos: number;
  cerrados: number;
  aconex: number;
};

type SubRow = {
  subsistema: string;
  universo: number;
  abiertos: number;
  cerrados: number;
  pendiente_cierre: number;
  cargado_aconex: number;
  pendiente_aconex: number;
};

type DupRow = {
  document_no: string;
  count: number;
};

type ChangesSummary = {
  has_previous: boolean;
  new_loaded_at?: string | null;
  prev_loaded_at?: string | null;
  changed_count?: number;
};

const fmt = (n: number | null | undefined) => (n ?? 0).toLocaleString("es-CL");

// Componente de Progress Bar
function ProgressBar({ value, max, color = "blue" }: { value: number; max: number; color?: string }) {
  const percentage = max > 0 ? Math.round((value / max) * 100) : 0;

  const colorClasses = {
    blue: "bg-blue-400",
    green: "bg-green-400",
    red: "bg-red-400",
    yellow: "bg-yellow-400",
    purple: "bg-purple-400",
  }[color] || "bg-blue-400";

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-gray-600">
        <span>{fmt(value)}</span>
        <span>{percentage}%</span>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
        <div
          className={`h-full ${colorClasses} transition-all duration-500 ease-out`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}

// Componente de Card Premium
function MetricCard({
  title,
  value,
  icon,
  gradient,
  subtitle,
  progressBar,
}: {
  title: string;
  value: string | number;
  icon: string;
  gradient: string;
  subtitle?: string;
  progressBar?: { value: number; max: number; color: string };
}) {
  return (
    <div className={`rounded-2xl p-6 text-white shadow-lg hover:shadow-xl transition-all duration-300 hover:-translate-y-1 ${gradient}`}>
      <div className="flex items-start justify-between mb-3">
        <div className="text-3xl">{icon}</div>
        <div className="text-right">
          <div className="text-3xl font-bold">{value}</div>
          <div className="text-sm opacity-90">{title}</div>
        </div>
      </div>
      {subtitle && <div className="text-xs opacity-80 mt-2">{subtitle}</div>}
      {progressBar && (
        <div className="mt-4">
          <ProgressBar {...progressBar} />
        </div>
      )}
    </div>
  );
}

function Table({
  columns,
  rows,
}: {
  columns: { key: string; label: string; className?: string; render?: (value: any, row: any) => ReactNode }[];
  rows: any[];
}) {
  return (
    <div className="overflow-auto rounded-2xl border bg-white shadow-sm">
      <table className="min-w-full text-sm">
        <thead className="bg-gradient-to-r from-gray-50 to-gray-100 sticky top-0 z-10">
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={`text-left px-4 py-3 font-semibold text-gray-700 ${c.className ?? ""}`}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td className="px-4 py-8 text-gray-500 text-center" colSpan={columns.length}>
                Sin datos
              </td>
            </tr>
          ) : (
            rows.map((r, i) => (
              <tr key={i} className="border-b border-gray-100 hover:bg-blue-50 transition-colors">
                {columns.map((c) => (
                  <td key={c.key} className={`px-4 py-3 ${c.className ?? ""}`}>
                    {c.render ? c.render(r[c.key], r) : r[c.key]}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function ExportCSVButton<T>({ rows, filename }: { rows: T[]; filename: string }) {
  const onExport = () => {
    if (!rows?.length) return;
    const headers = Object.keys(rows[0] as any);
    const csv = [
      headers.join(";"),
      ...rows.map((r: any) => headers.map((h) => (r[h] ?? "")).join(";")),
    ].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename.endsWith(".csv") ? filename : `${filename}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <button onClick={onExport} className="px-4 py-2 rounded-lg bg-gradient-to-r from-blue-400/90 to-blue-500/90 text-white text-sm hover:from-blue-500/90 hover:to-blue-600/90 shadow-md hover:shadow-lg transition-all">
      📥 Exportar CSV
    </button>
  );
}

export default function Dashboard() {
  const [loading, setLoading] = useState(true);
  const [cards, setCards] = useState<Cards | null>(null);
  const [discRows, setDiscRows] = useState<DisciplinaRow[]>([]);
  const [grpRows, setGrpRows] = useState<GrupoRow[]>([]);
  const [tab, setTab] = useState<"obra" | "mecanico" | "ie" | "general">("obra");
  const [subsObra, setSubsObra] = useState<SubRow[] | null>(null);
  const [subsMec, setSubsMec] = useState<SubRow[] | null>(null);
  const [subsIE, setSubsIE] = useState<SubRow[] | null>(null);
  const [dupRows, setDupRows] = useState<DupRow[]>([]);
  const [chg, setChg] = useState<ChangesSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showDownloads, setShowDownloads] = useState(false);

  const token = useAuthStore((s) => s.accessToken);
  const API_URL = import.meta.env.VITE_API_URL as string;

  const downloadSSErrorsCsv = async () => {
    try {
      const url = `${API_URL}/export/aconex-ss-errors.csv`;
      const res = await fetch(url, {
        method: "GET",
        headers: { Authorization: `Bearer ${token}` },
        credentials: "include",
      });
      if (!res.ok) throw new Error("No se pudo descargar la lista de errores de SS");
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "aconex_ss_errors.csv";
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e: any) {
      setError(e?.message || "Error al descargar errores de SS");
    }
  };

  const downloadUnmatchedCsv = async (strict = false) => {
    try {
      const url = `${API_URL}/aconex/unmatched.csv?strict=${strict ? "true" : "false"}`;
      const res = await fetch(url, {
        method: "GET",
        headers: { Authorization: `Bearer ${token}` },
        credentials: "include",
      });
      if (!res.ok) throw new Error("No se pudo descargar el CSV");
      const blob = await res.blob();
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = strict ? "aconex_unmatched_strict.csv" : "aconex_unmatched.csv";
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (e: any) {
      setError(e?.message || "Error al descargar CSV de no-match");
    }
  };

  const downloadDuplicatesCsv = async (strict = false) => {
    try {
      const url = `${API_URL}/aconex/duplicates.csv?strict=${strict ? "true" : "false"}`;
      const res = await fetch(url, {
        method: "GET",
        headers: { Authorization: `Bearer ${token}` },
        credentials: "include",
      });
      if (!res.ok) throw new Error("No se pudo descargar el CSV de duplicados");
      const blob = await res.blob();
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = strict ? "aconex_duplicados_strict.csv" : "aconex_duplicados.csv";
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (e: any) {
      setError(e?.message || "Error al descargar CSV de duplicados");
    }
  };

  const downloadChangesCsv = async () => {
    try {
      const res = await fetch(`${API_URL}/metrics/subsistemas/changes.csv`, {
        method: "GET",
        headers: { Authorization: `Bearer ${token}` },
        credentials: "include",
      });
      if (!res.ok) throw new Error("No se pudo descargar el CSV de cambios");
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "cambios_subsistemas.csv";
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e: any) {
      setError(e?.message || "Error al descargar cambios");
    }
  };

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        setLoading(true);
        const [c, d, g, dup, cs] = await Promise.all([
          apiGet<Cards>("/metrics/cards"),
          apiGet<DisciplinaRow[]>("/metrics/disciplinas"),
          apiGet<GrupoRow[]>("/metrics/grupos"),
          apiGet<DupRow[]>("/aconex/duplicates"),
          apiGet<ChangesSummary>("/metrics/changes/summary"),
        ]);
        if (!alive) return;
        setCards(c);
        setDiscRows(d);
        setGrpRows(g);
        setDupRows(dup || []);
        setChg(cs || null);
      } catch (e: any) {
        setError(e?.message || "Error al cargar métricas");
      } finally {
        setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        if (tab === "obra" && !subsObra) {
          const rows = await apiGet<SubRow[]>("/metrics/subsistemas?group=obra");
          if (alive) setSubsObra(rows);
        }
        if (tab === "mecanico" && !subsMec) {
          const rows = await apiGet<SubRow[]>("/metrics/subsistemas?group=mecanico");
          if (alive) setSubsMec(rows);
        }
        if (tab === "ie" && !subsIE) {
          const rows = await apiGet<SubRow[]>("/metrics/subsistemas?group=ie");
          if (alive) setSubsIE(rows);
        }
        if (tab === "general") {
          const promises: Promise<void>[] = [];
          if (!subsObra) {
            promises.push(apiGet<SubRow[]>("/metrics/subsistemas?group=obra").then((rows) => { if (alive) setSubsObra(rows); }));
          }
          if (!subsMec) {
            promises.push(apiGet<SubRow[]>("/metrics/subsistemas?group=mecanico").then((rows) => { if (alive) setSubsMec(rows); }));
          }
          if (!subsIE) {
            promises.push(apiGet<SubRow[]>("/metrics/subsistemas?group=ie").then((rows) => { if (alive) setSubsIE(rows); }));
          }
          if (promises.length) await Promise.all(promises);
        }
      } catch (e: any) {
        setError(e?.message || "Error al cargar subsistemas");
      }
    })();
    return () => {
      alive = false;
    };
  }, [tab, subsObra, subsMec, subsIE]);

  const aggregatedGeneral = useMemo<SubRow[]>(() => {
    const sources: SubRow[][] = [subsObra ?? [], subsMec ?? [], subsIE ?? []];
    const map = new Map<string, SubRow>();
    for (const arr of sources) {
      for (const r of arr) {
        const key = r.subsistema || "";
        if (!map.has(key)) {
          map.set(key, {
            subsistema: key,
            universo: 0,
            abiertos: 0,
            cerrados: 0,
            pendiente_cierre: 0,
            cargado_aconex: 0,
            pendiente_aconex: 0,
          });
        }
        const acc = map.get(key)!;
        acc.universo += Number(r.universo) || 0;
        acc.abiertos += Number(r.abiertos) || 0;
        acc.cerrados += Number(r.cerrados) || 0;
        acc.pendiente_cierre += Number(r.pendiente_cierre) || 0;
        acc.cargado_aconex += Number(r.cargado_aconex) || 0;
        acc.pendiente_aconex += Number(r.pendiente_aconex) || 0;
      }
    }
    return Array.from(map.values());
  }, [subsObra, subsMec, subsIE]);

  const currentSubs = useMemo(() => {
    if (tab === "obra") return subsObra ?? [];
    if (tab === "mecanico") return subsMec ?? [];
    if (tab === "ie") return subsIE ?? [];
    return aggregatedGeneral;
  }, [tab, subsObra, subsMec, subsIE, aggregatedGeneral]);

  const orderedSubs = useMemo(() => {
    const arr = [...currentSubs];
    arr.sort((a, b) =>
      (a.subsistema || "").localeCompare(b.subsistema || "", undefined, {
        numeric: true,
        sensitivity: "base",
      })
    );
    return arr;
  }, [currentSubs]);

  const { doc_keys_con_duplicados, duplicados_extras } = useMemo(() => {
    const rows = dupRows || [];
    let keys = 0;
    let extras = 0;
    for (const r of rows) {
      const c = Number(r.count) || 0;
      if (c >= 2) {
        keys += 1;
        extras += c - 1;
      }
    }
    return { doc_keys_con_duplicados: keys, duplicados_extras: extras };
  }, [dupRows]);

  const universo = cards?.universo || 0;
  const abiertos = cards?.abiertos || 0;
  const cerrados = cards?.cerrados || 0;
  const porcentajeCerrado = universo > 0 ? Math.round((cerrados / universo) * 100) : 0;
  const porcentajeAbierto = universo > 0 ? Math.round((abiertos / universo) * 100) : 0;

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      {/* Hero Section */}
      <div className="bg-gradient-to-r from-blue-400/90 via-blue-500/90 to-indigo-500/90 text-white px-6 py-8 shadow-lg">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-3xl font-bold mb-2">Dashboard de Calidad</h1>
              <p className="text-blue-100">Monitoreo en tiempo real de protocolos APSA y Aconex</p>
            </div>
            <div className="relative">
              <button
                onClick={() => setShowDownloads(!showDownloads)}
                className="px-4 py-2 bg-white/20 hover:bg-white/30 rounded-lg backdrop-blur-sm transition-all flex items-center gap-2"
              >
                📦 Descargas
                <span className="text-xs">{showDownloads ? "▲" : "▼"}</span>
              </button>

              {showDownloads && (
                <div className="absolute right-0 mt-2 w-64 bg-white rounded-lg shadow-xl p-3 z-10 text-gray-700 text-sm">
                  <div className="space-y-2">
                    <button onClick={() => downloadUnmatchedCsv(false)} className="w-full text-left px-3 py-2 hover:bg-gray-100 rounded">
                      📄 No-match (CSV)
                    </button>
                    <button onClick={() => downloadUnmatchedCsv(true)} className="w-full text-left px-3 py-2 hover:bg-gray-100 rounded">
                      📄 No-match estricto
                    </button>
                    <button onClick={() => downloadDuplicatesCsv(false)} className="w-full text-left px-3 py-2 hover:bg-gray-100 rounded">
                      📄 Duplicados (CSV)
                    </button>
                    <button onClick={() => downloadDuplicatesCsv(true)} className="w-full text-left px-3 py-2 hover:bg-gray-100 rounded">
                      📄 Duplicados estrictos
                    </button>
                    <button onClick={downloadSSErrorsCsv} className="w-full text-left px-3 py-2 hover:bg-gray-100 rounded">
                      📄 Errores de SS
                    </button>
                    {chg?.has_previous && (
                      <button onClick={downloadChangesCsv} className="w-full text-left px-3 py-2 hover:bg-gray-100 rounded">
                        📄 Cambios entre cargas
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {/* Banner de cambios */}
        {chg?.has_previous && (chg.changed_count ?? 0) > 0 && (
          <div className="bg-gradient-to-r from-amber-50 to-yellow-50 border border-amber-200 rounded-xl p-4 shadow-sm">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="text-2xl">⚠️</div>
                <div>
                  <div className="font-semibold text-amber-900">
                    {chg.changed_count} subsistema(s) con cambios detectados
                  </div>
                  {chg.prev_loaded_at && chg.new_loaded_at && (
                    <div className="text-xs text-amber-700 mt-1">
                      {new Date(chg.prev_loaded_at).toLocaleString()} → {new Date(chg.new_loaded_at).toLocaleString()}
                    </div>
                  )}
                </div>
              </div>
              <button
                onClick={downloadChangesCsv}
                className="px-3 py-2 bg-amber-400/90 hover:bg-amber-500/90 text-white rounded-lg text-sm transition-colors"
              >
                Descargar cambios
              </button>
            </div>
          </div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 shadow-sm">
            {error}
          </div>
        )}

        {/* Métricas Principales - Hero Cards */}
        <section>
          <h2 className="text-xl font-semibold text-gray-800 mb-4 flex items-center gap-2">
            <span className="text-2xl">📊</span>
            Métricas Principales
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <MetricCard
              title="Total Protocolos"
              value={fmt(universo)}
              icon="📋"
              gradient="bg-gradient-to-br from-blue-300/80 to-blue-400/80"
              subtitle="Universo completo de protocolos"
            />
            <MetricCard
              title="Protocolos Cerrados"
              value={fmt(cerrados)}
              icon="✅"
              gradient="bg-gradient-to-br from-green-300/80 to-green-400/80"
              subtitle={`${porcentajeCerrado}% del total`}
              progressBar={{ value: cerrados, max: universo, color: "green" }}
            />
            <MetricCard
              title="Protocolos Abiertos"
              value={fmt(abiertos)}
              icon="⚠️"
              gradient="bg-gradient-to-br from-red-300/80 to-red-400/80"
              subtitle={`${porcentajeAbierto}% del total`}
              progressBar={{ value: abiertos, max: universo, color: "red" }}
            />
          </div>
        </section>

        {/* Métricas Aconex */}
        <section>
          <h2 className="text-xl font-semibold text-gray-800 mb-4 flex items-center gap-2">
            <span className="text-2xl">🔗</span>
            Análisis Aconex
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricCard
              title="Total Cargado"
              value={fmt(cards?.aconex_cargados)}
              icon="📥"
              gradient="bg-gradient-to-br from-indigo-300/80 to-indigo-400/80"
            />
            <MetricCard
              title="Válidos (match)"
              value={fmt(cards?.aconex_validos)}
              icon="✓"
              gradient="bg-gradient-to-br from-emerald-300/80 to-emerald-400/80"
            />
            <MetricCard
              title="Inválidos (sin match)"
              value={fmt(cards?.aconex_invalidos)}
              icon="✗"
              gradient="bg-gradient-to-br from-orange-300/80 to-orange-400/80"
            />
            <MetricCard
              title="Error de SS"
              value={fmt(cards?.aconex_error_ss)}
              icon="⚡"
              gradient="bg-gradient-to-br from-purple-300/80 to-purple-400/80"
            />
          </div>
        </section>

        {/* Duplicados */}
        <section>
          <h2 className="text-xl font-semibold text-gray-800 mb-4 flex items-center gap-2">
            <span className="text-2xl">🔄</span>
            Duplicados en Aconex
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <MetricCard
              title="Claves duplicadas"
              value={fmt(doc_keys_con_duplicados)}
              icon="🔑"
              gradient="bg-gradient-to-br from-pink-300/80 to-rose-400/80"
              subtitle="Documentos con el mismo número"
            />
            <MetricCard
              title="Registros extras"
              value={fmt(duplicados_extras)}
              icon="📑"
              gradient="bg-gradient-to-br from-fuchsia-300/80 to-fuchsia-400/80"
              subtitle="Filas duplicadas a revisar"
            />
          </div>
        </section>

        {/* Grupos */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-gray-800 flex items-center gap-2">
              <span className="text-2xl">👥</span>
              Por Grupo
            </h2>
            <ExportCSVButton rows={grpRows} filename="grupos.csv" />
          </div>
          <Table
            columns={[
              { key: "grupo", label: "Grupo", className: "font-semibold" },
              { key: "universo", label: "Universo", render: (v) => <span className="font-mono">{fmt(v)}</span> },
              { key: "abiertos", label: "Abiertos", render: (v) => <span className="text-red-600 font-semibold">{fmt(v)}</span> },
              { key: "cerrados", label: "Cerrados", render: (v) => <span className="text-green-600 font-semibold">{fmt(v)}</span> },
              { key: "aconex", label: "Aconex", render: (v) => <span className="font-mono">{fmt(v)}</span> },
            ]}
            rows={grpRows}
          />
        </section>

        {/* Disciplinas */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-gray-800 flex items-center gap-2">
              <span className="text-2xl">🎯</span>
              Por Disciplina
            </h2>
            <ExportCSVButton rows={discRows} filename="disciplinas.csv" />
          </div>
          <Table
            columns={[
              { key: "disciplina", label: "Disciplina", className: "w-28 font-mono font-semibold" },
              { key: "universo", label: "Universo", render: (v) => <span className="font-mono">{fmt(v)}</span> },
              { key: "abiertos", label: "Abiertos", render: (v) => <span className="text-red-600 font-semibold">{fmt(v)}</span> },
              { key: "cerrados", label: "Cerrados", render: (v) => <span className="text-green-600 font-semibold">{fmt(v)}</span> },
              { key: "aconex", label: "Aconex", render: (v) => <span className="font-mono">{fmt(v)}</span> },
            ]}
            rows={discRows}
          />
        </section>

        {/* Subsistemas con tabs */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <div className="flex gap-2">
              <button
                className={`px-4 py-2 rounded-lg font-medium transition-all ${
                  tab === "obra"
                    ? "bg-gradient-to-r from-blue-400/90 to-blue-500/90 text-white shadow-md"
                    : "bg-white text-gray-700 hover:bg-gray-50 border"
                }`}
                onClick={() => setTab("obra")}
              >
                🏗️ Obra civil
              </button>
              <button
                className={`px-4 py-2 rounded-lg font-medium transition-all ${
                  tab === "mecanico"
                    ? "bg-gradient-to-r from-blue-400/90 to-blue-500/90 text-white shadow-md"
                    : "bg-white text-gray-700 hover:bg-gray-50 border"
                }`}
                onClick={() => setTab("mecanico")}
              >
                ⚙️ Mecánico Pipping
              </button>
              <button
                className={`px-4 py-2 rounded-lg font-medium transition-all ${
                  tab === "ie"
                    ? "bg-gradient-to-r from-blue-400/90 to-blue-500/90 text-white shadow-md"
                    : "bg-white text-gray-700 hover:bg-gray-50 border"
                }`}
                onClick={() => setTab("ie")}
              >
                ⚡ I&amp;E
              </button>
              <button
                className={`px-4 py-2 rounded-lg font-medium transition-all ${
                  tab === "general"
                    ? "bg-gradient-to-r from-blue-400/90 to-blue-500/90 text-white shadow-md"
                    : "bg-white text-gray-700 hover:bg-gray-50 border"
                }`}
                onClick={() => setTab("general")}
                title="Suma Obra + Mecánico + I&E por subsistema"
              >
                📊 General
              </button>
            </div>
            <ExportCSVButton rows={orderedSubs} filename={`subsistemas_${tab}.csv`} />
          </div>

          <Table
            columns={[
              { key: "subsistema", label: "Subsistema", className: "w-52 font-semibold" },
              { key: "universo", label: "Universo", render: (v) => <span className="font-mono">{fmt(v)}</span> },
              { key: "abiertos", label: "Abiertos", render: (v) => <span className="text-red-600 font-semibold">{fmt(v)}</span> },
              { key: "cerrados", label: "Cerrados", render: (v) => <span className="text-green-600 font-semibold">{fmt(v)}</span> },
              { key: "pendiente_cierre", label: "Pend. Cierre", render: (v) => <span className="text-orange-600">{fmt(v)}</span> },
              { key: "cargado_aconex", label: "Carg. Aconex", render: (v) => <span className="text-blue-600">{fmt(v)}</span> },
              { key: "pendiente_aconex", label: "Pend. Aconex", render: (v) => <span className="text-purple-600 font-semibold">{fmt(v)}</span> },
            ]}
            rows={orderedSubs}
          />
        </section>

        {loading && (
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-blue-500 border-t-transparent"></div>
            <p className="mt-4 text-gray-600">Cargando métricas...</p>
          </div>
        )}
      </div>
    </div>
  );
}
