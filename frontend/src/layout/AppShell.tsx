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
          <img className="brand-mark" src="/apple-touch-icon.png" alt="" width={32} height={32} />
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
