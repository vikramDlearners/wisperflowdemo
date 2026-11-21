import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  ApiError,
  auth,
  getSessionToken,
  login,
  setRole,
  setSessionToken,
  signUp,
  verifyOtp,
  type RoleChoice,
} from "../api";

type Step = "home" | "signup" | "login" | "code" | "role";

const ROLE_OPTIONS: { value: RoleChoice; label: string }[] = [
  { value: "parent", label: "Parent" },
  { value: "caretaker", label: "Caretaker" },
  { value: "hospital", label: "Hospital staff" },
  { value: "child_of_parent", label: "Child of a parent" },
  { value: "others", label: "Others" },
];

export default function Landing() {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>("home");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [selectedRole, setSelectedRole] = useState<RoleChoice | null>(null);
  const [otherRole, setOtherRole] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Returning visitor: if a session token is already stored, check it with the server.
  useEffect(() => {
    if (getSessionToken() == null) return;
    async function restoreSession() {
      try {
        await auth.me();
        navigate("/onboarding/parent");
      } catch {
        // Token is invalid or expired (including 401): forget it and stay on the landing page.
        setSessionToken(null);
      }
    }
    void restoreSession();
  }, [navigate]);

  const errorText = (err: unknown) =>
    err instanceof ApiError ? err.detail : "Something went wrong. Please try again.";

  function goHome() {
    setStep("home");
    setError(null);
    setNotice(null);
    setCode("");
  }

  async function handleSignUp(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await signUp(email, displayName);
      setNotice("We sent a code to your email.");
      setCode("");
      setStep("code");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleLogin(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await login(email);
      setNotice("We sent a code to your email.");
      setCode("");
      setStep("code");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleVerify(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      // verifyOtp stores session_token the same way auth.verify does.
      const session = await verifyOtp(email, code);
      if (session.user.role == null) {
        // New user: ask for their role before entering the app.
        setNotice(null);
        setStep("role");
      } else {
        navigate("/onboarding/parent");
      }
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleSetRole(e: FormEvent) {
    e.preventDefault();
    if (!selectedRole) {
      setError("Please choose your role.");
      return;
    }
    const other = otherRole.trim();
    if (selectedRole === "others" && !other) {
      setError("Please describe your role.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await setRole(selectedRole, selectedRole === "others" ? other : null);
      navigate("/onboarding/parent");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="signin-card landing-page">
      <h1 className="landing-title">CareCircle</h1>

      {error && <p role="alert">{error}</p>}
      {notice && step === "code" && <p>{notice}</p>}

      {step === "home" && (
        <div className="landing-actions">
          <button type="button" className="btn" onClick={() => setStep("signup")}>
            Sign up
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => setStep("login")}>
            Log in
          </button>
        </div>
      )}

      {step === "signup" && (
        <form onSubmit={handleSignUp}>
          <label className="form-field">
            Display name
            <input
              required
              maxLength={255}
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
            />
          </label>
          <label className="form-field">
            Email
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <button type="submit" disabled={loading}>
            {loading ? "Sending code…" : "Send code"}
          </button>
          <button type="button" className="landing-link" onClick={goHome}>
            Back
          </button>
        </form>
      )}

      {step === "login" && (
        <form onSubmit={handleLogin}>
          <label className="form-field">
            Email
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <button type="submit" disabled={loading}>
            {loading ? "Sending code…" : "Send code"}
          </button>
          <button type="button" className="landing-link" onClick={goHome}>
            Back
          </button>
        </form>
      )}

      {step === "code" && (
        <form onSubmit={handleVerify}>
          <label className="form-field">
            6-digit code
            <input
              required
              inputMode="numeric"
              pattern="[0-9]{6}"
              minLength={6}
              maxLength={6}
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            />
          </label>
          <button type="submit" disabled={loading}>
            {loading ? "Verifying…" : "Verify"}
          </button>
          <button type="button" className="landing-link" onClick={goHome}>
            Back
          </button>
        </form>
      )}

      {step === "role" && (
        <form onSubmit={handleSetRole}>
          <fieldset className="role-fieldset">
            <legend>What is your role?</legend>
            {ROLE_OPTIONS.map((opt) => (
              <label key={opt.value} className="role-option">
                <input
                  type="radio"
                  name="role"
                  value={opt.value}
                  checked={selectedRole === opt.value}
                  onChange={() => setSelectedRole(opt.value)}
                />
                {opt.label}
              </label>
            ))}
          </fieldset>
          {selectedRole === "others" && (
            <label className="form-field">
              Please describe your role
              <input
                required
                maxLength={255}
                value={otherRole}
                onChange={(e) => setOtherRole(e.target.value)}
              />
            </label>
          )}
          <button type="submit" disabled={loading}>
            {loading ? "Saving…" : "Continue"}
          </button>
        </form>
      )}

      {loading && <p className="muted">Please wait…</p>}
    </main>
  );
}
