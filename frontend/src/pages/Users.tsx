import { useEffect, useState } from "react";
import api from "../lib/api";
import { apiGet } from "../api/client";

type UserRow = {
  id: number;
  email: string;
  full_name?: string | null;
  roles: string[];
  is_active: boolean;
  is_email_verified: boolean;
};

type CreateForm = {
  email: string;
  full_name: string;
  password: string;
  is_active: boolean;
  roles: { Admin: boolean; User: boolean };
};

export default function Users() {
  const [rows, setRows] = useState<UserRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  // Crear
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState<CreateForm>({
    email: "",
    full_name: "",
    password: "",
    is_active: true,
    roles: { Admin: false, User: true },
  });

  // Editar inline
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editActive, setEditActive] = useState<boolean>(true);
  const [editRoles, setEditRoles] = useState<{ Admin: boolean; User: boolean }>({ Admin: false, User: true });

  async function load() {
    try {
      setLoading(true);
      setErr(null);
      const data = await apiGet<UserRow[]>("/admin/users");
      setRows(data || []);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || "Error al cargar usuarios");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function rolesFromFlags(flags: { Admin: boolean; User: boolean }) {
    const r: string[] = [];
    if (flags.Admin) r.push("Admin");
    if (flags.User) r.push("User");
    return r.length ? r : ["User"];
  }

  // Crear usuario
  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    try {
      await api.post("/admin/users", {
        email: createForm.email.trim().toLowerCase(),
        full_name: createForm.full_name.trim(),
        password: createForm.password,
        roles: rolesFromFlags(createForm.roles),
        is_active: createForm.is_active,
      });
      setShowCreate(false);
      setCreateForm({
        email: "",
        full_name: "",
        password: "",
        is_active: true,
        roles: { Admin: false, User: true },
      });
      await load();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || "No se pudo crear el usuario");
    }
  }

  function beginEdit(u: UserRow) {
    setEditingId(u.id);
    setEditName(u.full_name || "");
    setEditActive(!!u.is_active);
    setEditRoles({ Admin: u.roles.includes("Admin"), User: u.roles.includes("User") });
  }

  async function saveEdit(id: number) {
    try {
      await api.patch(`/admin/users/${id}`, {
        full_name: editName,
        roles: rolesFromFlags(editRoles),
        is_active: editActive,
      });
      setEditingId(null);
      await load();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || "No se pudo actualizar");
    }
  }

  async function setPassword(u: UserRow) {
    const pwd = window.prompt(`Nueva contraseña para ${u.email} (mín. 8)`);
    if (!pwd) return;
    if (pwd.length < 8) {
      alert("La contraseña debe tener al menos 8 caracteres.");
      return;
    }
    try {
      await api.post(`/admin/users/${u.id}/set-password`, { password: pwd });
      alert("Contraseña actualizada.");
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || "No se pudo actualizar la contraseña");
    }
  }

  async function toggleActive(u: UserRow) {
    try {
      await api.patch(`/admin/users/${u.id}`, { is_active: !u.is_active });
      await load();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || "No se pudo cambiar estado");
    }
  }

  async function removeUser(u: UserRow) {
    if (!window.confirm(`¿Desactivar al usuario ${u.email}? (Esto revoca su sesión)`)) return;
    try {
      await api.delete(`/admin/users/${u.id}`); // soft delete (desactiva)
      await load();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || "No se pudo eliminar");
    }
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Usuarios</h1>
        <button
          className="px-3 py-2 rounded-lg border bg-white hover:bg-gray-50 text-sm"
          onClick={() => setShowCreate(s => !s)}
        >
          {showCreate ? "Cerrar" : "Nuevo usuario"}
        </button>
      </div>

      {err && <div className="p-3 rounded-lg bg-red-50 text-red-700 border border-red-200">{err}</div>}

      {/* Crear */}
      {showCreate && (
        <form onSubmit={onCreate} className="rounded-2xl border bg-white p-4 space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="flex flex-col text-sm">
              Email
              <input
                className="border rounded px-3 py-2"
                value={createForm.email}
                onChange={e => setCreateForm(f => ({ ...f, email: e.target.value }))}
                required
                type="email"
              />
            </label>
            <label className="flex flex-col text-sm">
              Nombre
              <input
                className="border rounded px-3 py-2"
                value={createForm.full_name}
                onChange={e => setCreateForm(f => ({ ...f, full_name: e.target.value }))}
              />
            </label>
            <label className="flex flex-col text-sm">
              Contraseña
              <input
                className="border rounded px-3 py-2"
                value={createForm.password}
                onChange={e => setCreateForm(f => ({ ...f, password: e.target.value }))}
                required
                type="password"
                minLength={8}
              />
            </label>
            <div className="flex items-center gap-4">
              <label className="text-sm inline-flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={createForm.roles.Admin}
                  onChange={e => setCreateForm(f => ({ ...f, roles: { ...f.roles, Admin: e.target.checked } }))}
                />
                Admin
              </label>
              <label className="text-sm inline-flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={createForm.roles.User}
                  onChange={e => setCreateForm(f => ({ ...f, roles: { ...f.roles, User: e.target.checked } }))}
                />
                User
              </label>
              <label className="text-sm inline-flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={createForm.is_active}
                  onChange={e => setCreateForm(f => ({ ...f, is_active: e.target.checked }))}
                />
                Activo
              </label>
            </div>
          </div>

          <div className="flex gap-2">
            <button className="bg-blue-600 text-white px-4 py-2 rounded">Crear</button>
            <button type="button" onClick={() => setShowCreate(false)} className="px-4 py-2 rounded border">
              Cancelar
            </button>
          </div>
        </form>
      )}

      {/* Tabla */}
      <div className="overflow-auto rounded-2xl border bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="text-left px-3 py-2">Email</th>
              <th className="text-left px-3 py-2">Nombre</th>
              <th className="text-left px-3 py-2">Roles</th>
              <th className="text-left px-3 py-2">Activo</th>
              <th className="text-left px-3 py-2 w-64">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td className="px-3 py-3 text-gray-500" colSpan={5}>Cargando…</td></tr>
            ) : rows.length === 0 ? (
              <tr><td className="px-3 py-3 text-gray-500" colSpan={5}>Sin usuarios</td></tr>
            ) : (
              rows.map(u => {
                const isEditing = editingId === u.id;
                return (
                  <tr key={u.id} className="odd:bg-white even:bg-gray-50">
                    <td className="px-3 py-2">{u.email}</td>
                    <td className="px-3 py-2">
                      {isEditing ? (
                        <input
                          className="border rounded px-2 py-1 w-56"
                          value={editName}
                          onChange={e => setEditName(e.target.value)}
                        />
                      ) : (
                        u.full_name || ""
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {isEditing ? (
                        <div className="flex items-center gap-3">
                          <label className="inline-flex items-center gap-2 text-xs">
                            <input
                              type="checkbox"
                              checked={editRoles.Admin}
                              onChange={e => setEditRoles(r => ({ ...r, Admin: e.target.checked }))}
                            />
                            Admin
                          </label>
                          <label className="inline-flex items-center gap-2 text-xs">
                            <input
                              type="checkbox"
                              checked={editRoles.User}
                              onChange={e => setEditRoles(r => ({ ...r, User: e.target.checked }))}
                            />
                            User
                          </label>
                        </div>
                      ) : (
                        <div className="flex gap-1">
                          {u.roles.map(r => (
                            <span key={r} className="px-2 py-0.5 text-xs rounded-full border">{r}</span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {isEditing ? (
                        <label className="inline-flex items-center gap-2 text-xs">
                          <input
                            type="checkbox"
                            checked={editActive}
                            onChange={e => setEditActive(e.target.checked)}
                          />
                          Activo
                        </label>
                      ) : (
                        u.is_active ? "Sí" : "No"
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {isEditing ? (
                        <div className="flex gap-2">
                          <button className="bg-blue-600 text-white px-3 py-1 rounded" onClick={() => saveEdit(u.id)}>
                            Guardar
                          </button>
                          <button className="px-3 py-1 rounded border" onClick={() => setEditingId(null)}>
                            Cancelar
                          </button>
                        </div>
                      ) : (
                        <div className="flex flex-wrap gap-2">
                          <button className="px-3 py-1 rounded border" onClick={() => beginEdit(u)}>
                            Editar
                          </button>
                          <button className="px-3 py-1 rounded border" onClick={() => setPassword(u)}>
                            Set password
                          </button>
                          <button
                            className="px-3 py-1 rounded border"
                            onClick={() => toggleActive(u)}
                          >
                            {u.is_active ? "Desactivar" : "Activar"}
                          </button>
                          <button className="px-3 py-1 rounded border text-red-600" onClick={() => removeUser(u)}>
                            Eliminar
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}