import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Banner } from "../components/Banner";
import { ApiError } from "../api/client";

const DEMO_EMAIL = import.meta.env.VITE_DEMO_EMAIL as string | undefined;
const DEMO_PASSWORD = import.meta.env.VITE_DEMO_PASSWORD as string | undefined;

export function LoginPage() {
  const { login, isAuthenticated, isLoading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!isLoading && isAuthenticated) {
    const state = location.state as { from?: { pathname?: string } } | null;
    const from = state?.from?.pathname ?? "/";
    return <Navigate to={from} replace />;
  }

  function fillDemoCredentials() {
    if (!DEMO_EMAIL || !DEMO_PASSWORD) return;
    setEmail(DEMO_EMAIL);
    setPassword(DEMO_PASSWORD);
    setError(null);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate("/", { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError("Incorrect email or password.");
      } else {
        setError(err instanceof Error ? err.message : "Login failed.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-screen">
      <div className="login-card">
        <div className="login-brand">
          <img className="brand-mark" src="/apple-touch-icon.png" alt="" width={34} height={34} />
          <div>
            <div className="login-title">SOLGRID</div>
            <div className="login-sub">Tea Energy Intelligence</div>
          </div>
        </div>

        {error && <Banner kind="error">{error}</Banner>}

        <form className="login-form" onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>

        {DEMO_EMAIL && DEMO_PASSWORD && (
          <button type="button" className="demo-creds" onClick={fillDemoCredentials}>
            <span className="demo-creds-label">Demo credentials</span>
            <span className="mono">
              {DEMO_EMAIL} · {DEMO_PASSWORD}
            </span>
          </button>
        )}
      </div>
    </div>
  );
}
