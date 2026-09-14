import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Banner } from "../components/Banner";
import { ApiError } from "../api/client";

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
          <svg width="30" height="30" viewBox="0 0 30 30" fill="none" aria-hidden="true">
            <circle cx="15" cy="15" r="6.2" fill="#FDB44B" />
            <g stroke="#FDB44B" strokeWidth="1.8" strokeLinecap="round">
              <line x1="15" y1="2.5" x2="15" y2="6" />
              <line x1="15" y1="24" x2="15" y2="27.5" />
              <line x1="2.5" y1="15" x2="6" y2="15" />
              <line x1="24" y1="15" x2="27.5" y2="15" />
              <line x1="6.2" y1="6.2" x2="8.6" y2="8.6" />
              <line x1="21.4" y1="21.4" x2="23.8" y2="23.8" />
              <line x1="23.8" y1="6.2" x2="21.4" y2="8.6" />
              <line x1="8.6" y1="21.4" x2="6.2" y2="23.8" />
            </g>
          </svg>
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
      </div>
    </div>
  );
}
