// src/pages/Dashboard.tsx
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { apiGet } from "../api/client";
import StatCard from "../components/StatCard";
import { useAuthStore } from "../store/auth";

type Cards = {
  universo: number;
  abiertos: number;
  cerrados: number;
  aconex_cargados: number;   // total cargados (filas crudas del log)
  aconex_validos?: number;   // con match
  aconex_invalidos?: number; // sin match
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

// Duplicados Aconex (por Document No normalizado)
type DupRow = {
  document_no: string;
  count: number; // repeticiones del mismo document_no (normalizado)
};

// Resumen de cambios (última vs anterior)
type ChangesSummary = {
  has_previous: boolean;
  new_loaded_at?: string | null;
  prev_loaded_at?: string | null;
  changed_count?: number;
};

const fmt = (n: number | null | undefined) => (n ?? 0).toLocaleString("es-CL");

function Table({
  columns,
  rows,
}: {
  columns: { key: string; label: string; className?: string; render?: (value: any, row: any) => ReactNode }[];
  rows: any[];
}) {
  return (
    <div className="overflow-auto rounded-2xl border bg-white">
      <table className="min-w-full text-sm">
        <thead className="bg-gray-50 sticky top-0 z-10">
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={`text-left px-3 py-2 font-medium text-gray-600 ${c.className ?? ""}`}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td className="px-3 py-4 text-gray-500" colSpan={columns.length}>
                Sin datos
              </td>
            </tr>
          ) : (
            rows.map((r, i) => (
              <tr key={i} className="odd:bg-white even:bg-gray-50">
                {columns.map((c) => (
                  <td key={c.key} className={`px-3 py-2 ${c.className ?? ""}`}>
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
    <button onClick={onExport} className="px-3 py-2 rounded-lg bg-gray-800 text-white text-sm hover:bg-black">
      Exportar CSV
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

  // Descarga CSV de "Aconex sin match"
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

  // Descarga CSV de "Aconex duplicados"
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

  // Descarga CSV de "Cambios por subsistema" (último vs anterior)
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

  // Carga inicial: tarjetas, disciplinas, grupos, duplicados, resumen de cambios
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

  // Lazy load de subsistemas por tab (incluye "general": trae lo que falte)
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
          // Trae lo que falte de los tres para poder agregar
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

  // Agregado "General": suma por subsistema las métricas de obra + mecánico + I&E
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
    // general
    return aggregatedGeneral;
  }, [tab, subsObra, subsMec, subsIE, aggregatedGeneral]);

  // Ordenar por 'subsistema' (alfanumérico)
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

  // Métricas de duplicados (mini-cards)
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

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="text-xl font-semibold">Dashboard</div>
        <div className="flex items-center gap-2">
          {/* No-match */}
          <button
            onClick={() => downloadUnmatchedCsv(false)}
            className="px-3 py-2 rounded-lg border bg-white hover:bg-gray-50 text-sm"
            title="Descargar Aconex sin match (normalizado)"
          >
            Descargar no-match (CSV)
          </button>
          <button
            onClick={() => downloadUnmatchedCsv(true)}
            className="px-3 py-2 rounded-lg border bg-white hover:bg-gray-50 text-sm"
            title="Descargar Aconex sin match (estricto, sin normalización)"
          >
            No-match estricto (CSV)
          </button>

          {/* Duplicados */}
          <button
            onClick={() => downloadDuplicatesCsv(false)}
            className="px-3 py-2 rounded-lg border bg-white hover:bg-gray-50 text-sm"
            title="Descargar Aconex duplicados (normalizado)"
          >
            Duplicados (CSV)
          </button>
          <button
            onClick={() => downloadDuplicatesCsv(true)}
            className="px-3 py-2 rounded-lg border bg-white hover:bg-gray-50 text-sm"
            title="Descargar Aconex duplicados (estricto, sin normalización)"
          >
            Duplicados estrictos (CSV)
          </button>
        </div>
      </div>

      {/* Banner de cambios detectados (última vs anterior) */}
      {chg?.has_previous && (chg.changed_count ?? 0) > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 px-3 py-2 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-sm">
          <div>
            <strong>{chg.changed_count}</strong> subsistema(s) con cambios desde la última carga.
            {chg.prev_loaded_at && chg.new_loaded_at && (
              <span className="ml-2">
                ({new Date(chg.prev_loaded_at).toLocaleString()} → {new Date(chg.new_loaded_at).toLocaleString()})
              </span>
            )}
          </div>
          <button
            onClick={downloadChangesCsv}
            className="px-2 py-1 rounded-md border bg-white hover:bg-gray-50"
            title="Descargar detalle de cambios"
          >
            Descargar cambios (CSV)
          </button>
        </div>
      )}

      {error ? (
        <div className="p-3 rounded-lg bg-red-50 text-red-700 border border-red-200">{error}</div>
      ) : null}

      {/* Tarjetas de totales */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-4">
        <StatCard title="Universo Protocolos" value={fmt(cards?.universo)} />
        <StatCard title="Abiertos" value={fmt(cards?.abiertos)} />
        <StatCard title="Cerrados" value={fmt(cards?.cerrados)} />
        <StatCard title="Cargado Aconex (total)" value={fmt(cards?.aconex_cargados)} />
        <StatCard title="Aconex válidos (match)" value={fmt(cards?.aconex_validos)} />
        <StatCard title="Aconex inválidos (sin match)" value={fmt(cards?.aconex_invalidos)} />
      </div>

      {/* Análisis Aconex — Duplicados */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-medium">Análisis Aconex — Duplicados</h3>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-2 gap-4">
          <StatCard title="Claves con duplicados (Doc No)" value={fmt(doc_keys_con_duplicados)} />
          <StatCard title="Registros extra por duplicados" value={fmt(duplicados_extras)} />
        </div>
      </section>

      {/* Análisis Aconex — Errores de SS */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-medium">Análisis Aconex — Errores de SS</h3>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-2 gap-4">
          <StatCard title="Protocolos con Error de SS" value={fmt(cards?.aconex_error_ss)} />
          <div className="rounded-2xl border bg-white p-4 flex items-center justify-between">
            <div>
              <div className="text-sm text-gray-500">Descargar</div>
              <div className="text-base font-medium">Lista de errores de SS</div>
            </div>
            <button
              onClick={downloadSSErrorsCsv}
              className="px-3 py-2 rounded-lg border bg-white hover:bg-gray-50 text-sm"
            >
              Descargar (CSV)
            </button>
          </div>
        </div>
      </section>

      {/* Disciplinas */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-medium">Por disciplina</h3>
          <ExportCSVButton rows={discRows} filename="disciplinas.csv" />
        </div>
        <Table
          columns={[
            { key: "disciplina", label: "Disciplina", className: "w-28" },
            { key: "universo", label: "Universo", render: (v) => fmt(v) },
            { key: "abiertos", label: "Abiertos", render: (v) => fmt(v) },
            { key: "cerrados", label: "Cerrados", render: (v) => fmt(v) },
            { key: "aconex", label: "Aconex", render: (v) => fmt(v) },
          ]}
          rows={discRows}
        />
      </section>

      {/* Grupos */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-medium">Por grupo</h3>
          <ExportCSVButton rows={grpRows} filename="grupos.csv" />
        </div>
        <Table
          columns={[
            { key: "grupo", label: "Grupo" },
            { key: "universo", label: "Universo", render: (v) => fmt(v) },
            { key: "abiertos", label: "Abiertos", render: (v) => fmt(v) },
            { key: "cerrados", label: "Cerrados", render: (v) => fmt(v) },
            { key: "aconex", label: "Aconex", render: (v) => fmt(v) },
          ]}
          rows={grpRows}
        />
      </section>

      {/* Subsistemas con tabs (orden alfabético) */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex gap-2">
            <button
              className={`px-3 py-2 rounded-lg border ${tab === "obra" ? "bg-black text-white" : "bg-white"}`}
              onClick={() => setTab("obra")}
            >
              Obra civil
            </button>
            <button
              className={`px-3 py-2 rounded-lg border ${tab === "mecanico" ? "bg-black text-white" : "bg-white"}`}
              onClick={() => setTab("mecanico")}
            >
              Mecánico Pipping
            </button>
            <button
              className={`px-3 py-2 rounded-lg border ${tab === "ie" ? "bg-black text-white" : "bg-white"}`}
              onClick={() => setTab("ie")}
            >
              I&amp;E
            </button>
            <button
              className={`px-3 py-2 rounded-lg border ${tab === "general" ? "bg-black text-white" : "bg-white"}`}
              onClick={() => setTab("general")}
              title="Suma Obra + Mecánico + I&E por subsistema"
            >
              General
            </button>
          </div>
          <ExportCSVButton rows={orderedSubs} filename={`subsistemas_${tab}.csv`} />
        </div>

        <Table
          columns={[
            { key: "subsistema", label: "Subsistema", className: "w-52" },
            { key: "universo", label: "Universo", render: (v) => fmt(v) },
            { key: "abiertos", label: "Abiertos", render: (v) => fmt(v) },
            { key: "cerrados", label: "Cerrados", render: (v) => fmt(v) },
            { key: "pendiente_cierre", label: "Pend. Cierre", render: (v) => fmt(v) },
            { key: "cargado_aconex", label: "Carg. Aconex", render: (v) => fmt(v) },
            { key: "pendiente_aconex", label: "Pend. Aconex", render: (v) => fmt(v) },
          ]}
          rows={orderedSubs}
        />
      </section>

      {loading ? <div className="text-sm text-gray-500">Cargando métricas…</div> : null}
    </div>
  );
}
