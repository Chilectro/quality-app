import { useState } from "react";
import api from "../lib/api";

type UpState = {
  loading: boolean;
  progress: number;
  okMsg: string | null;
  errMsg: string | null;
};

export default function Uploads() {
  const [apsaFile, setApsaFile] = useState<File | null>(null);
  const [aconexFile, setAconexFile] = useState<File | null>(null);

  const [apsa, setApsa] = useState<UpState>({ loading: false, progress: 0, okMsg: null, errMsg: null });
  const [aconex, setAconex] = useState<UpState>({ loading: false, progress: 0, okMsg: null, errMsg: null });

  async function upload(
    path: "/admin/upload/apsa" | "/admin/upload/aconex",
    file: File,
    setState: (s: UpState) => void
  ) {
    const fd = new FormData();
    fd.append("file", file);

    setState({ loading: true, progress: 0, okMsg: null, errMsg: null });
    try {
      const res = await api.post(path, fd, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (evt) => {
          if (!evt.total) return;
          const pct = Math.round((evt.loaded * 100) / evt.total);
          setState((s) => ({ ...s, progress: pct }));
        },
      });
      setState({ loading: false, progress: 100, okMsg: `OK: ${res.data?.rows_inserted ?? 0} filas`, errMsg: null });
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e?.message || "Error subiendo archivo";
      setState({ loading: false, progress: 0, okMsg: null, errMsg: detail });
    }
  }

  function Bar({ pct }: { pct: number }) {
    return (
      <div className="w-full bg-gray-200 rounded h-2 overflow-hidden">
        <div className="h-2 bg-blue-600 transition-all" style={{ width: `${pct}%` }} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Cargas (Admin)</h1>

      {/* APSA */}
      <section className="bg-white border rounded p-4 space-y-2">
        <h2 className="font-medium">Subir Log de Protocolos (APSA)</h2>
        <div className="flex items-center gap-2">
          <input
            type="file"
            accept=".xlsx,.xls"
            onChange={(e) => setApsaFile(e.target.files?.[0] || null)}
            disabled={apsa.loading}
          />
          <button
            onClick={() => apsaFile && upload("/admin/upload/apsa", apsaFile, setApsa)}
            className="bg-blue-600 text-white px-3 py-1 rounded disabled:opacity-50"
            disabled={!apsaFile || apsa.loading}
          >
            {apsa.loading ? "Cargando..." : "Subir"}
          </button>
        </div>
        {apsa.loading && <Bar pct={apsa.progress} />}
        {apsa.okMsg && <div className="text-green-700">{apsa.okMsg}</div>}
        {apsa.errMsg && <div className="text-red-700">{apsa.errMsg}</div>}
      </section>

      {/* ACONEX */}
      <section className="bg-white border rounded p-4 space-y-2">
        <h2 className="font-medium">Subir Cargados ACONEX</h2>
        <div className="flex items-center gap-2">
          <input
            type="file"
            accept=".xlsx,.xls,.csv"
            onChange={(e) => setAconexFile(e.target.files?.[0] || null)}
            disabled={aconex.loading}
          />
          <button
            onClick={() => aconexFile && upload("/admin/upload/aconex", aconexFile, setAconex)}
            className="bg-blue-600 text-white px-3 py-1 rounded disabled:opacity-50"
            disabled={!aconexFile || aconex.loading}
          >
            {aconex.loading ? "Cargando..." : "Subir"}
          </button>
        </div>
        {aconex.loading && <Bar pct={aconex.progress} />}
        {aconex.okMsg && <div className="text-green-700">{aconex.okMsg}</div>}
        {aconex.errMsg && <div className="text-red-700">{aconex.errMsg}</div>}
      </section>
    </div>
  );
}
