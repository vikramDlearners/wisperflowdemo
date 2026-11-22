import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { acceptParentInvite } from "../api";

// Parent-facing sign-in via a one-time link: /parent/accept-invite?token=...
export default function ParentAcceptInvite() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get("token") ?? "";
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    // The invite token is single-use; guard against a second call from StrictMode remounts.
    if (started.current) return;
    started.current = true;

    if (!token) {
      setError("This sign-in link is missing its token.");
      return;
    }

    acceptParentInvite(token)
      .then(() => navigate("/parent/chat", { replace: true }))
      .catch(() => {
        setError("This sign-in link is invalid or has expired. Ask your family member to send a new one.");
      });
  }, [token, navigate]);

  if (error) {
    return (
      <main className="signin-card">
        <h1>Sign-in link not valid</h1>
        <p role="alert">{error}</p>
        <Link to="/signin">Go to sign in</Link>
      </main>
    );
  }

  return (
    <main className="signin-card">
      <p role="status">Signing you in…</p>
    </main>
  );
}
