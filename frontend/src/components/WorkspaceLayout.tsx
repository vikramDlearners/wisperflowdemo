import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import "../parent-profile.css";
import "../workspace.css";
import { auth, getProfile, type UserOut } from "../api";
import LogoutButton from "./LogoutButton";

// Family workspace shell: sidebar navigation + top bar. Uses the pp- styles
// from parent-profile.css so it matches the Parent profile page.

export type WorkspacePage =
  | "overview"
  | "parent-profile"
  | "medicines"
  | "activity"
  | "tasks"
  | "appointments"
  | "records"
  | "timeline"
  | "members"
  | "manage-profile"
  | "notifications";

const ROLE_LABELS: Record<string, string> = {
  parent: "Parent",
  caretaker: "Caretaker",
  hospital: "Hospital staff",
  manager: "Manager",
  others: "Member",
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
}

interface NavItem {
  key: WorkspacePage;
  icon: string;
  label: string;
  to: string | null; // null while the family is unknown: shown disabled
}

interface WorkspaceLayoutProps {
  /** null when the user has no family yet: family links are shown disabled. */
  familyId: string | null;
  current: WorkspacePage;
  title: string;
  children: ReactNode;
}

export default function WorkspaceLayout({ familyId, current, title, children }: WorkspaceLayoutProps) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [parentName, setParentName] = useState<string | null>(null);
  // Sidebar drawer state for tablet/mobile widths (always visible on desktop).
  const [navOpen, setNavOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    setNavOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!navOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setNavOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [navOpen]);

  useEffect(() => {
    let active = true;
    auth
      .me()
      .then((me) => active && setUser(me))
      .catch(() => undefined);
    getProfile()
      .then((p) => active && setParentName(p.parent_full_name))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  const fam = (path: string) => (familyId ? `/family/${familyId}${path}` : null);
  const workspace: NavItem[] = [
    { key: "overview", icon: "⌂", label: "Overview", to: fam("") },
    { key: "parent-profile", icon: "♡", label: "Parent profile", to: "/parent-profile" },
    { key: "medicines", icon: "▤", label: "Medicines", to: fam("/medicines") },
    { key: "activity", icon: "◉", label: "CareVoice activity", to: fam("/activity") },
    { key: "tasks", icon: "☷", label: "Tasks", to: fam("/tasks") },
    { key: "appointments", icon: "▦", label: "Appointments", to: fam("/appointments") },
    { key: "records", icon: "▧", label: "Records", to: fam("/records") },
  ];
  const settings: NavItem[] = [
    { key: "members", icon: "♙", label: "Family members", to: fam("/members") },
    { key: "manage-profile", icon: "✎", label: "Manage Profile", to: fam("/manage-profile") },
    { key: "notifications", icon: "⚙", label: "Notification settings", to: fam("/notifications") },
  ];

  const renderNav = (items: NavItem[]) =>
    items.map((item) =>
      item.to ? (
        <Link
          key={item.key}
          to={item.to}
          className={`pp-nav-item${item.key === current ? " is-current" : ""}`}
          aria-current={item.key === current ? "page" : undefined}
        >
          <span className="pp-nav-icon" aria-hidden="true">{item.icon}</span>
          {item.label}
        </Link>
      ) : (
        <span key={item.key} className="pp-nav-item is-disabled" title="Create a family first">
          <span className="pp-nav-icon" aria-hidden="true">{item.icon}</span>
          {item.label}
        </span>
      ),
    );

  const parent = parentName?.trim() || "Your parent";
  const userName = user?.display_name ?? "You";
  const userRole = (user?.role && ROLE_LABELS[user.role]) || "Family member";

  return (
    <div className={`pp ws${navOpen ? " ws-nav-open" : ""}`}>
      <div className="ws-backdrop" onClick={() => setNavOpen(false)} aria-hidden="true" />
      <aside className="pp-sidebar" id="ws-sidebar" aria-label="Sidebar">
        <div className="pp-brand">
          <span className="pp-brand-mark" aria-hidden="true">✳</span>
          <div>
            <div className="pp-brand-name">CareCircle</div>
            <div className="pp-brand-tag">Family care, together</div>
          </div>
        </div>

        <nav aria-label="Workspace">
          <p className="pp-nav-heading">Workspace</p>
          {renderNav(workspace)}
          <p className="pp-nav-heading">Settings</p>
          {renderNav(settings)}
        </nav>

        <div className="pp-family">
          <p className="pp-nav-heading">Your family</p>
          <div className="pp-person">
            <span className="pp-avatar pp-avatar-green">{initials(parent)}</span>
            <div>
              <div className="pp-person-name">{parent}</div>
              <div className="pp-person-sub">Care profile</div>
            </div>
          </div>
          <div className="pp-person">
            <span className="pp-avatar pp-avatar-warm">{initials(userName)}</span>
            <div>
              <div className="pp-person-name">{userName}</div>
              <div className="pp-person-sub">{userRole}</div>
            </div>
          </div>
          <LogoutButton />
        </div>
      </aside>

      <div className="pp-main">
        <header className="pp-topbar">
          <button
            type="button"
            className="ws-menu"
            aria-label={navOpen ? "Close menu" : "Open menu"}
            aria-expanded={navOpen}
            aria-controls="ws-sidebar"
            onClick={() => setNavOpen((o) => !o)}
          >
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
          </button>
          <nav className="pp-breadcrumb" aria-label="Breadcrumb">
            <span>CareCircle</span>
            <span aria-hidden="true">/</span>
            <strong>{title}</strong>
          </nav>
          <label className="pp-search">
            <span aria-hidden="true">⌕</span>
            <input type="search" placeholder="Search records, tasks..." aria-label="Search records and tasks" />
          </label>
          <button type="button" className="pp-bell ws-bell" aria-label="Notifications">
            <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
              <path
                d="M6 9a6 6 0 1 1 12 0c0 5 2 6.5 2 6.5H4S6 14 6 9Zm4.3 9.5a1.8 1.8 0 0 0 3.4 0"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span className="ws-bell-dot" />
          </button>
          <div className="pp-user ws-user">
            <span className="pp-avatar pp-avatar-warm">{initials(userName)}</span>
            <div className="ws-user-text">
              <div className="pp-person-name">{userName}</div>
              <div className="pp-person-sub">{userRole}</div>
            </div>
          </div>
        </header>

        {children}
      </div>
    </div>
  );
}
