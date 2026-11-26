import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { LuMenu, LuBell, LuLogOut, LuSearch, LuChevronDown, LuUser } from "react-icons/lu";
import { useAuth } from "../../auth/AuthContext";
import { navForUser } from "../../config/navigation";
import { ROLE_LABELS, MODE, modeForUser } from "../../config/roles";
import { useApi } from "../../utils/hooks";
import { fullName, timeAgo } from "../../utils/format";
import { Avatar } from "../ui";
import logo from "../../assets/omniteckno-logo.png";

const MODE_LABEL = { [MODE.PLATFORM]: "Platform administration", [MODE.SCHOOL]: "School (K-12)", [MODE.UNIVERSITY]: "University" };

function Sidebar({ user, mode, onNavigate }) {
  const groups = navForUser(mode, user.role);
  return (
    <aside className="sidebar" aria-label="Main navigation">
      <div className="sidebar__brand">
        <img src={logo} alt="OmniTeckno" />
        <div className="sidebar__product">OmniEducation</div>
      </div>
      <div className="sidebar__tenant">
        <div className="sidebar__tenant-name">{user.tenant?.name || "OmniEducation Platform"}</div>
        <div className="sidebar__tenant-mode">{MODE_LABEL[mode]}</div>
      </div>
      <nav className="sidebar__nav">
        {groups.map((g) => (
          <div className="nav-group" key={g.group}>
            <div className="nav-group__label" id={`nav-${g.group}`}>{g.group}</div>
            <ul role="list" aria-labelledby={`nav-${g.group}`} style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {g.items.map(({ to, label, icon: Icon, end }) => (
                <li key={to}>
                  <NavLink to={to} end={end} className={({ isActive }) => `nav-link${isActive ? " active" : ""}`} onClick={onNavigate}>
                    <Icon aria-hidden="true" />
                    <span>{label}</span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
      <div className="sidebar__footer">© {new Date().getFullYear()} OmniTeckno · An OmniOS company</div>
    </aside>
  );
}

function useClickOutside(ref, onOutside) {
  useEffect(() => {
    const h = (e) => ref.current && !ref.current.contains(e.target) && onOutside();
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [ref, onOutside]);
}

function Notifications({ mode }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useClickOutside(ref, () => setOpen(false));
  // Platform admins have no institution inbox, so the bell stays empty for them.
  const { data } = useApi(mode === MODE.PLATFORM ? null : "/notifications/");
  const items = data?.results || [];
  const unread = data?.unread ?? items.filter((n) => !n.read).length;
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button type="button" className="icon-btn" aria-label={`Notifications, ${unread} unread`} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <LuBell />
        {unread > 0 && <span className="icon-btn__dot" />}
      </button>
      {open && (
        <div className="card" style={{ position: "absolute", right: 0, top: 48, width: 340, zIndex: 30, boxShadow: "var(--shadow)" }}>
          <div className="card__header"><h2 className="card__title">Notifications</h2><span className="badge badge--brand">{unread} new</span></div>
          <ul className="list" style={{ padding: "0 20px", maxHeight: 360, overflowY: "auto" }}>
            {items.length === 0 && <li className="list__item muted">You're all caught up.</li>}
            {items.map((n) => (
              <li className="list__item" key={n.id}>
                <span className="list__dot" style={{ background: n.read ? "var(--border-strong)" : undefined }} />
                <div>
                  <div className="list__title">{n.title}</div>
                  <div className="list__meta">{n.body}</div>
                  <div className="list__meta">{timeAgo(n.created_at)}</div>
                </div>
              </li>
            ))}
          </ul>
          {mode !== MODE.PLATFORM && (
            <div style={{ padding: "10px 20px", borderTop: "1px solid var(--border)" }}>
              <Link to={`/${mode}/notifications`} onClick={() => setOpen(false)}>See all notifications</Link>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function UserMenu({ user, onLogout }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useClickOutside(ref, () => setOpen(false));
  const name = fullName(user);
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button type="button" className="topbar__user btn btn--ghost" style={{ height: 48, padding: "0 8px" }}
        aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <Avatar name={name} />
        <span className="topbar__user-text" style={{ textAlign: "left" }}>
          <span className="topbar__user-name" style={{ display: "block" }}>{name}</span>
          <span className="topbar__user-role">{ROLE_LABELS[user.role]}</span>
        </span>
        <LuChevronDown aria-hidden="true" />
      </button>
      {open && (
        <div className="card" role="menu" style={{ position: "absolute", right: 0, top: 54, width: 240, zIndex: 30, boxShadow: "var(--shadow)", padding: 6 }}>
          <div style={{ padding: "8px 10px 10px", borderBottom: "1px solid var(--border)", marginBottom: 6 }}>
            <div style={{ fontWeight: 600, fontSize: "var(--fs-sm)" }}>{user.email}</div>
            <div className="muted" style={{ fontSize: "var(--fs-xs)" }}>{user.tenant?.name || "Platform"}</div>
          </div>
          <Link role="menuitem" className="btn btn--ghost" style={{ width: "100%", justifyContent: "flex-start" }}
            to={`/${modeForUser(user)}/profile`} onClick={() => setOpen(false)}>
            <LuUser /> My profile
          </Link>
          <button type="button" role="menuitem" className="btn btn--ghost" style={{ width: "100%", justifyContent: "flex-start", color: "var(--danger)" }} onClick={onLogout}>
            <LuLogOut /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}

export default function AppShell() {
  const { user, mode, logout } = useAuth();
  const [navOpen, setNavOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => setNavOpen(false), [location.pathname]);

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className={`shell${navOpen ? " shell--nav-open" : ""}`}>
      <a href="#main" className="skip-link">Skip to main content</a>
      <Sidebar user={user} mode={mode} onNavigate={() => setNavOpen(false)} />
      <div className="backdrop" onClick={() => setNavOpen(false)} aria-hidden="true" />
      <div className="main">
        <header className="topbar">
          <button type="button" className="icon-btn topbar__menu-btn" aria-label="Open navigation" aria-expanded={navOpen} onClick={() => setNavOpen(true)}>
            <LuMenu />
          </button>
          {mode !== MODE.PLATFORM && (
            <form className="topbar__search" role="search" onSubmit={(e) => {
              e.preventDefault();
              const q = new FormData(e.currentTarget).get("q");
              navigate(`/${mode}/students?search=${encodeURIComponent(q || "")}`);
            }}>
              <LuSearch aria-hidden="true" />
              <label htmlFor="global-search" className="sr-only">Search students</label>
              <input id="global-search" name="q" className="input" type="search" placeholder="Search students by name or ID…" />
            </form>
          )}
          <div className="topbar__spacer" />
          <Notifications mode={mode} />
          <UserMenu user={user} onLogout={handleLogout} />
        </header>
        <main id="main" className="content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
