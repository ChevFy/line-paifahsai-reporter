import { useState } from "react";
import { NavLink, Outlet } from "react-router";
import { AlertCircle, Flame, LogOut } from "lucide-react";
import { useAuth } from "../hooks/useAuth";
import { errorMessage } from "../utils/api-error";

export default function AdminLayout() {
  const { state, signOut } = useAuth();
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState<string | null>(null);
  const username = state.kind === "signed-in" ? state.admin.username : "";

  async function handleSignOut() {
    setIsSigningOut(true);
    setSignOutError(null);
    try {
      await signOut();
    } catch (reason) {
      setSignOutError(errorMessage(reason, "ออกจากระบบไม่สำเร็จ"));
      setIsSigningOut(false);
    }
  }

  return (
    <div className="admin-shell">
      <header className="admin-header">
        <div className="admin-header-inner">
          <div className="brand-icon" aria-hidden="true">
            <Flame size={20} />
          </div>
          <div>
            <h1>ปายฟ้าใส · แอดมิน</h1>
            <p>ระบบแจ้งเหตุไฟป่า อ.ปาย</p>
          </div>
          <nav className="admin-nav" aria-label="เมนูหลัก">
            <NavLink to="/volunteers">จิตอาสา</NavLink>
          </nav>
          <div className="admin-user">
            <span>{username}</span>
            <button
              type="button"
              className="secondary-button"
              onClick={handleSignOut}
              disabled={isSigningOut}
            >
              <LogOut size={16} />
              {isSigningOut ? "กำลังออก..." : "ออกจากระบบ"}
            </button>
          </div>
        </div>
      </header>
      <main className="admin-main">
        {signOutError && (
          <div className="error-box" role="alert">
            <AlertCircle size={16} />
            <p>{signOutError}</p>
          </div>
        )}
        <Outlet />
      </main>
    </div>
  );
}
