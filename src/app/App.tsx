import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { AlertCircle, Loader2 } from "lucide-react";
import AdminLayout from "./components/AdminLayout";
import RequireAuth from "./components/RequireAuth";
import { AuthProvider } from "./hooks/AuthProvider";
import { useAuth } from "./hooks/useAuth";
import LoginPage from "./pages/LoginPage";
import VolunteersPage from "./pages/VolunteersPage";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AdminApp />
      </BrowserRouter>
    </AuthProvider>
  );
}

export function AdminApp() {
  const { state, retry } = useAuth();

  if (state.kind === "checking") {
    return (
      <main className="status-page">
        <p className="loading-text" role="status">
          <Loader2 className="spin" size={16} />
          กำลังตรวจสอบการเข้าสู่ระบบ...
        </p>
      </main>
    );
  }

  if (state.kind === "error") {
    return (
      <main className="status-page">
        <div className="error-box" role="alert">
          <AlertCircle size={16} />
          <p>{state.message}</p>
        </div>
        <button type="button" className="primary-button" onClick={retry}>
          ลองอีกครั้ง
        </button>
      </main>
    );
  }

  return <AdminRoutes />;
}

export function AdminRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <AdminLayout />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/volunteers" replace />} />
        <Route path="volunteers" element={<VolunteersPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
