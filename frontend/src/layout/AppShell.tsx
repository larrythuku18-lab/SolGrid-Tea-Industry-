import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const NAV_ITEMS = [
  {
    to: "/",
    label: "Overview",
    icon: (
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="3" y="3" width="7" height="9" rx="1" />
        <rect x="14" y="3" width="7" height="5" rx="1" />
        <rect x="14" y="12" width="7" height="9" rx="1" />
        <rect x="3" y="16" width="7" height="5" rx="1" />
      </svg>
    ),
  },
  {
    to: "/ledger",
    label: "Ledger",
    icon: (
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M4 4h16v16H4z" />
        <path d="M8 9h8M8 13h8M8 17h5" />
      </svg>
    ),
  },
  {
    to: "/benchmark",
    label: "Benchmark",
    icon: (
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M3 3v18h18" />
        <path d="M7 15l4-5 3 3 5-7" />
      </svg>
    ),
  },
  {
    to: "/scenarios",
    label: "Scenarios",
    icon: (
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8a7 7 0 0 1-10 10z" />
        <path d="M2 22c1.5-3 4-5 6-7" />
      </svg>
    ),
  },
];

function initials(name: string | null): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  return parts
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

export function AppShell() {
  const { me, logout } = useAuth();

  return (
    <div className="app">
      <aside className="rail">
        <div className="brand">
          <span aria-hidden="true">
            <svg width="30" height="30" viewBox="0 0 30 30" fill="none">
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
          </span>
          <div>
            <div className="brand-name">SOLGRID</div>
            <div className="brand-sub">Tea Energy</div>
          </div>
        </div>

        <nav className="nav" aria-label="Primary">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === "/"}>
              {item.icon}
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="rail-foot">
          <div className="acct">
            <div className="acct-badge">{initials(me?.organization_name ?? null)}</div>
            <div>
              <div className="acct-name">{me?.organization_name ?? "—"}</div>
              <div className="acct-role">{me?.role}</div>
            </div>
          </div>
          <button type="button" className="logout-btn" onClick={logout}>
            Sign out
          </button>
        </div>
      </aside>

      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
