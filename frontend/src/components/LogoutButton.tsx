import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { auth } from "../api";

// Signs the user out via POST /api/auth/logout, then returns to the sign-in page.
// auth.logout() always clears the stored session token, even when the request fails
// (e.g. 401 because the session already ended, or no network), so the user is
// signed out on this device in every case.

interface LogoutButtonProps {
  className?: string;
  /** Optional translated labels; default to English. */
  label?: string;
  busyLabel?: string;
}

export default function LogoutButton({ className = "", label = "Log out", busyLabel = "Signing out…" }: LogoutButtonProps) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);

  async function handleLogout() {
    setBusy(true);
    try {
      await auth.logout();
    } catch {
      // Token is already cleared by auth.logout(); nothing else to do.
    } finally {
      navigate("/start", { replace: true });
    }
  }

  return (
    <button
      type="button"
      className={`logout-btn ${className}`.trim()}
      onClick={handleLogout}
      disabled={busy}
    >
      <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
        <path
          d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 16l-4-4 4-4M6 12h10"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {busy ? busyLabel : label}
    </button>
  );
}
