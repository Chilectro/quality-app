import { Routes, Route, Navigate, Link, useLocation } from "react-router-dom";
import Login from "./pages/Login"
import Dashboard from "./pages/Dashboard";
import Uploads from "./pages/Uploads";
import Users from "./pages/Users";
import { useAuthStore } from "./store/auth";
import type { ReactNode } from "react";
import LogProtocolos from "./pages/LogProtocolos";

function Protected({ children, role }: { children: ReactNode; role?: "Admin" | "User" }) {


  const { isAuthenticated, hasRole } = useAuthStore();
  if (!isAuthenticated()) return <Navigate to="/login" replace />;
  if (role && !hasRole(role)) return <Navigate to="/" replace />;
  return children;
}

export default function App() {
  const { isAuthenticated, logout, profile } = useAuthStore();
  const location = useLocation();

  // LogProtocolos necesita full width sin padding
  const isFullWidthPage = location.pathname === "/log-protocolos";

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <header className="bg-white border-b">
        <div className={`${isFullWidthPage ? 'w-full px-6' : 'max-w-6xl mx-auto px-4'} py-3 flex items-center gap-4`}>
          <Link to="/" className="font-semibold">QualityApp</Link>
          {isAuthenticated() && (
            <>
              <Link to="/" className="text-sm">Dashboard</Link>
              <Link to="/log-protocolos" className="px-3 py-2 rounded-lg hover:bg-gray-100"> Log Protocolos</Link>
              <Link to="/uploads" className="text-sm">Cargas</Link>
              {profile?.roles?.includes("Admin") && (
                <Link to="/admin/users" className="text-sm">Usuarios</Link>
              )}
              <div className="ml-auto flex items-center gap-3">
                <span className="text-sm">{profile?.name} ({profile?.email})</span>
                <button onClick={logout} className="text-sm text-red-600">Salir</button>
              </div>
            </>
          )}
        </div>
      </header>

      <main className={isFullWidthPage ? "" : "max-w-6xl mx-auto px-4 py-6"}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={
            <Protected><Dashboard /></Protected>
          } />
          <Route path="/log-protocolos" element={<Protected><LogProtocolos /></Protected>} />
          <Route path="/uploads" element={
            <Protected role="Admin"><Uploads /></Protected>
          } />
          <Route path="/admin/users" element={
            <Protected role="Admin"><Users /></Protected>
          } />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}