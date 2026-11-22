import { useEffect, useRef, useState, type ClipboardEvent, type FormEvent, type KeyboardEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import "../auth.css";
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

// Sign up / log in with an emailed 6-digit code, then (new users) pick a role.
// Steps: login | signup -> code -> role -> /onboarding/parent (parents: /parent/chat)

type Step = "login" | "signup" | "code" | "role";

const ROLE_OPTIONS: { value: RoleChoice; label: string; hint: string; icon: string }[] = [
  { value: "child_of_parent", label: "Son or daughter", hint: "Caring for a parent", icon: "👪" },
  { value: "parent", label: "Parent", hint: "Receiving care", icon: "🧓" },
  { value: "caretaker", label: "Caretaker", hint: "Home nurse or helper", icon: "🤝" },
  { value: "hospital", label: "Hospital staff", hint: "Doctor or care team", icon: "🩺" },
  { value: "others", label: "Someone else", hint: "Tell us your role", icon: "✳" },
];

const CODE_LENGTH = 6;
const RESEND_SECONDS = 30;

export default function Landing() {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>("login");
  const [codeFrom, setCodeFrom] = useState<"login" | "signup">("login");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [digits, setDigits] = useState<string[]>(Array(CODE_LENGTH).fill(""));
  const [selectedRole, setSelectedRole] = useState<RoleChoice | null>(null);
  const [otherRole, setOtherRole] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [resendIn, setResendIn] = useState(0);
  const digitRefs = useRef<(HTMLInputElement | null)[]>([]);

  const code = digits.join("");

  // Returning visitor: if a session token is already stored, check it with the server.
  useEffect(() => {
    if (getSessionToken() == null) return;
    async function restoreSession() {
      try {
        const me = await auth.me();
        navigate(me.role === "parent" ? "/parent/chat" : "/onboarding/parent");
      } catch {
        // Token is invalid or expired (including 401): forget it and stay here.
        setSessionToken(null);
      }
    }
    void restoreSession();
  }, [navigate]);

  // Countdown for "Resend code".
  useEffect(() => {
    if (resendIn <= 0) return;
    const t = window.setTimeout(() => setResendIn((s) => s - 1), 1000);
    return () => window.clearTimeout(t);
  }, [resendIn]);

  // Focus the first code box when the code step opens.
  useEffect(() => {
    if (step === "code") digitRefs.current[0]?.focus();
  }, [step]);

  const errorText = (err: unknown) =>
    err instanceof ApiError ? err.detail : "Something went wrong. Please check your connection and try again.";

  function switchTo(next: "login" | "signup") {
    setStep(next);
    setError(null);
    setNotice(null);
  }

  function openCodeStep(from: "login" | "signup") {
    setCodeFrom(from);
    setDigits(Array(CODE_LENGTH).fill(""));
    setNotice(null);
    setResendIn(RESEND_SECONDS);
    setStep("code");
  }

  async function handleSignUp(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await signUp(email.trim(), displayName.trim());
      openCodeStep("signup");
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
      await login(email.trim());
      openCodeStep("login");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }

  // After sign-up the account exists, so a new code always comes from the login endpoint.
  async function handleResend() {
    setError(null);
    setNotice(null);
    try {
      await login(email.trim());
      setDigits(Array(CODE_LENGTH).fill(""));
      setNotice("A new code is on its way.");
      setResendIn(RESEND_SECONDS);
      digitRefs.current[0]?.focus();
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function verify(fullCode: string) {
    setLoading(true);
    setError(null);
    try {
      // verifyOtp stores session_token the same way auth.verify does.
      const session = await verifyOtp(email.trim(), fullCode);
      if (session.user.role == null) {
        setNotice(null);
        setStep("role");
      } else {
        // Parents go straight to their check-in chat; everyone else to onboarding.
        navigate(session.user.role === "parent" ? "/parent/chat" : "/onboarding/parent");
      }
    } catch (err) {
      setError(errorText(err));
      setDigits(Array(CODE_LENGTH).fill(""));
      digitRefs.current[0]?.focus();
    } finally {
      setLoading(false);
    }
  }

  function handleVerify(e: FormEvent) {
    e.preventDefault();
    if (code.length === CODE_LENGTH) void verify(code);
  }

  function setDigit(index: number, raw: string) {
    const value = raw.replace(/\D/g, "");
    if (value.length > 1) {
      fillFrom(index, value);
      return;
    }
    const next = [...digits];
    next[index] = value;
    setDigits(next);
    if (value && index < CODE_LENGTH - 1) digitRefs.current[index + 1]?.focus();
    if (value && next.every(Boolean)) void verify(next.join(""));
  }

  function fillFrom(index: number, value: string) {
    const next = [...digits];
    for (let i = 0; i < value.length && index + i < CODE_LENGTH; i++) next[index + i] = value[i];
    setDigits(next);
    const last = Math.min(index + value.length, CODE_LENGTH) - 1;
    digitRefs.current[Math.min(last + 1, CODE_LENGTH - 1)]?.focus();
    if (next.every(Boolean)) void verify(next.join(""));
  }

  function onDigitKey(index: number, e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Backspace" && !digits[index] && index > 0) {
      digitRefs.current[index - 1]?.focus();
    } else if (e.key === "ArrowLeft" && index > 0) {
      digitRefs.current[index - 1]?.focus();
    } else if (e.key === "ArrowRight" && index < CODE_LENGTH - 1) {
      digitRefs.current[index + 1]?.focus();
    }
  }

  function onDigitPaste(index: number, e: ClipboardEvent<HTMLInputElement>) {
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "");
    if (!pasted) return;
    e.preventDefault();
    fillFrom(index, pasted);
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
      navigate(selectedRole === "parent" ? "/parent/chat" : "/onboarding/parent");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }

  const accountExists = step === "signup" && error?.toLowerCase().includes("already exists");

  return (
    <div className="au">
      {/* Brand panel */}
      <aside className="au-brand" aria-hidden="true">
        <Link to="/" className="au-logo" tabIndex={-1}>
          <span className="au-logo-mark">✳</span>
          CareCircle
        </Link>

        <div className="au-brand-body">
          <h2>Care for your parents together, even from afar.</h2>
          <p>Medicines, reminders and voice check-ins for the whole family, in English, தமிழ் and हिन्दी.</p>

          <div className="au-demo">
            <div className="au-demo-head">
              <span className="au-demo-mic">🎙</span>
              <div>
                <strong>Good morning, Appa</strong>
                <span>8:00 AM · Amlodipine 5 mg</span>
              </div>
            </div>
            <div className="au-bubble au-bubble-user">“நான் மாத்திரை சாப்பிட்டேன்.”</div>
            <div className="au-bubble au-bubble-app">✓ Marked as taken. Meera and Rahul were updated.</div>
          </div>
        </div>

        <ul className="au-points">
          <li>No passwords: sign in with an email code</li>
          <li>Every family member sees the same care plan</li>
        </ul>
      </aside>

      {/* Form panel */}
      <main className="au-main">
        <div className="au-top">
          <Link to="/" className="au-home">
            ← Home
          </Link>
          <Link to="/" className="au-logo au-logo-mobile">
            <span className="au-logo-mark">✳</span>
            CareCircle
          </Link>
        </div>

        <div className="au-card">
          {(step === "login" || step === "signup") && (
            <>
              <h1>{step === "login" ? "Welcome back" : "Create your account"}</h1>
              <p className="au-sub">
                {step === "login"
                  ? "Enter your email and we'll send you a 6-digit code."
                  : "Start your family's care circle in under a minute."}
              </p>

              <div className="au-tabs" role="tablist" aria-label="Choose">
                <button
                  type="button"
                  role="tab"
                  aria-selected={step === "login"}
                  className={step === "login" ? "is-active" : ""}
                  onClick={() => switchTo("login")}
                >
                  Log in
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={step === "signup"}
                  className={step === "signup" ? "is-active" : ""}
                  onClick={() => switchTo("signup")}
                >
                  Sign up
                </button>
              </div>

              {error && (
                <div role="alert" className="au-alert">
                  <span>{error}</span>
                  {accountExists && (
                    <button type="button" className="au-link" onClick={() => switchTo("login")}>
                      Log in instead
                    </button>
                  )}
                </div>
              )}

              <form onSubmit={step === "login" ? handleLogin : handleSignUp} className="au-form">
                {step === "signup" && (
                  <label className="au-field">
                    <span>Your name</span>
                    <input
                      required
                      maxLength={255}
                      autoComplete="name"
                      placeholder="e.g. Meera Rao"
                      value={displayName}
                      onChange={(e) => setDisplayName(e.target.value)}
                    />
                  </label>
                )}
                <label className="au-field">
                  <span>Email address</span>
                  <input
                    type="email"
                    required
                    autoComplete="email"
                    inputMode="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </label>
                <button type="submit" className="au-btn" disabled={loading}>
                  {loading ? <span className="au-spinner" aria-hidden="true" /> : null}
                  {loading ? "Sending code…" : "Send code"}
                </button>
              </form>

              <p className="au-foot">
                {step === "login" ? "New to CareCircle? " : "Already have an account? "}
                <button type="button" className="au-link" onClick={() => switchTo(step === "login" ? "signup" : "login")}>
                  {step === "login" ? "Create an account" : "Log in"}
                </button>
              </p>
            </>
          )}

          {step === "code" && (
            <form onSubmit={handleVerify}>
              <span className="au-icon" aria-hidden="true">✉</span>
              <h1>Check your email</h1>
              <p className="au-sub">
                We sent a 6-digit code to <strong>{email}</strong>.
              </p>

              {error && (
                <div role="alert" className="au-alert">
                  <span>{error}</span>
                </div>
              )}
              {notice && (
                <p role="status" className="au-notice">
                  {notice}
                </p>
              )}

              <div className="au-otp" role="group" aria-label="6-digit code">
                {digits.map((d, i) => (
                  <input
                    key={i}
                    ref={(el) => {
                      digitRefs.current[i] = el;
                    }}
                    value={d}
                    inputMode="numeric"
                    autoComplete={i === 0 ? "one-time-code" : "off"}
                    maxLength={CODE_LENGTH}
                    aria-label={`Digit ${i + 1}`}
                    disabled={loading}
                    onChange={(e) => setDigit(i, e.target.value)}
                    onKeyDown={(e) => onDigitKey(i, e)}
                    onPaste={(e) => onDigitPaste(i, e)}
                    onFocus={(e) => e.target.select()}
                  />
                ))}
              </div>

              <button type="submit" className="au-btn" disabled={loading || code.length < CODE_LENGTH}>
                {loading ? <span className="au-spinner" aria-hidden="true" /> : null}
                {loading ? "Verifying…" : "Verify and continue"}
              </button>

              <div className="au-code-links">
                <button type="button" className="au-link" onClick={handleResend} disabled={resendIn > 0 || loading}>
                  {resendIn > 0 ? `Resend code in ${resendIn}s` : "Resend code"}
                </button>
                <button type="button" className="au-link au-muted-link" onClick={() => switchTo(codeFrom)}>
                  Use a different email
                </button>
              </div>
            </form>
          )}

          {step === "role" && (
            <form onSubmit={handleSetRole}>
              <span className="au-icon" aria-hidden="true">👋</span>
              <h1>One last thing</h1>
              <p className="au-sub">How are you part of the care circle?</p>

              {error && (
                <div role="alert" className="au-alert">
                  <span>{error}</span>
                </div>
              )}

              <fieldset className="au-roles">
                <legend className="au-sr">Your role</legend>
                {ROLE_OPTIONS.map((opt) => (
                  <label key={opt.value} className={`au-role${selectedRole === opt.value ? " is-selected" : ""}`}>
                    <input
                      type="radio"
                      name="role"
                      value={opt.value}
                      checked={selectedRole === opt.value}
                      onChange={() => {
                        setSelectedRole(opt.value);
                        setError(null);
                      }}
                    />
                    <span className="au-role-icon" aria-hidden="true">
                      {opt.icon}
                    </span>
                    <span className="au-role-text">
                      <strong>{opt.label}</strong>
                      <span>{opt.hint}</span>
                    </span>
                    <span className="au-role-check" aria-hidden="true">✓</span>
                  </label>
                ))}
              </fieldset>

              {selectedRole === "others" && (
                <label className="au-field">
                  <span>Please describe your role</span>
                  <input
                    required
                    maxLength={255}
                    placeholder="e.g. Neighbour, family friend"
                    value={otherRole}
                    onChange={(e) => setOtherRole(e.target.value)}
                  />
                </label>
              )}

              <button type="submit" className="au-btn" disabled={loading}>
                {loading ? <span className="au-spinner" aria-hidden="true" /> : null}
                {loading ? "Saving…" : "Continue"}
              </button>
            </form>
          )}
        </div>

        <p className="au-legal">Your family's health information is only shared with people you invite.</p>
      </main>
    </div>
  );
}
