import { useState } from "react";
import api from "../lib/api";

export default function Uploads() {
  const [apsaFile, setApsaFile] = useState<File | null>(null);
  const [aconexFile, setAconexFile] = useState<File | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function upload(path: "/admin/upload/apsa" | "/admin/upload/aconex", file: File) {
    const fd = new FormData();
    fd.append("file", file);
    const res = await api.post(path, fd, { headers: { "Content-Type": "multipart/form-data" } });
    return res.data;
  }

  async function onUploadAPSA() {
    setMsg(null); setErr(null);
    if (!apsaFile) return setErr("Selecciona un archivo APSA");
    try {
      const r = await upload("/admin/upload/apsa", apsaFile);
      setMsg(`APSA OK: ${r.rows_inserted} filas`);
    } catch (e:any) {
      setErr(e?.response?.data?.detail || "Error subiendo APSA");
    }
  }
  async function onUploadAconex() {
    setMsg(null); setErr(null);
    if (!aconexFile) return setErr("Selecciona un archivo ACONEX");
    try {
      const r = await upload("/admin/upload/aconex", aconexFile);
      setMsg(`ACONEX OK: ${r.rows_inserted} filas`);
    } catch (e:any) {
      setErr(e?.response?.data?.detail || "Error subiendo ACONEX");
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Cargas (Admin)</h1>
      {msg && <div className="text-green-700">{msg}</div>}
      {err && <div className="text-red-700">{err}</div>}

      <section className="bg-white border rounded p-4">
        <h2 className="font-medium mb-2">Subir Log de Protocolos (APSA)</h2>
        <input type="file" onChange={e=>setApsaFile(e.target.files?.[0] || null)} />
        <button onClick={onUploadAPSA} className="ml-2 bg-blue-600 text-white px-3 py-1 rounded">Subir</button>
      </section>

      <section className="bg-white border rounded p-4">
        <h2 className="font-medium mb-2">Subir Cargados ACONEX</h2>
        <input type="file" onChange={e=>setAconexFile(e.target.files?.[0] || null)} />
        <button onClick={onUploadAconex} className="ml-2 bg-blue-600 text-white px-3 py-1 rounded">Subir</button>
      </section>
    </div>
  );
}