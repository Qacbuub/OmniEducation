import { useEffect, useId, useRef } from "react";
import { LuInbox, LuCircleAlert, LuInfo, LuCircleCheck, LuX } from "react-icons/lu";

/* ---------------- Buttons ---------------- */
export function Button({ variant = "primary", size, block, icon: Icon, children, className = "", ...props }) {
  const cls = ["btn", `btn--${variant}`, size && `btn--${size}`, block && "btn--block", className].filter(Boolean).join(" ");
  return (
    <button type="button" className={cls} {...props}>
      {Icon && <Icon aria-hidden="true" />}
      {children}
    </button>
  );
}

/* ---------------- Layout ---------------- */
export function PageHeader({ eyebrow, title, description, actions }) {
  return (
    <header className="page-header">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="page-header__actions">{actions}</div>}
    </header>
  );
}

export function Card({ title, subtitle, actions, children, bodyClass = "card__body", className = "" }) {
  return (
    <section className={`card ${className}`} aria-label={typeof title === "string" ? title : undefined}>
      {(title || actions) && (
        <div className="card__header">
          <div>
            {title && <h2 className="card__title">{title}</h2>}
            {subtitle && <div className="card__subtitle">{subtitle}</div>}
          </div>
          {actions}
        </div>
      )}
      <div className={bodyClass}>{children}</div>
    </section>
  );
}

export function StatCard({ icon: Icon, label, value, delta, deltaDir = "up" }) {
  return (
    <div className="card stat">
      {Icon && <div className="stat__icon" aria-hidden="true"><Icon /></div>}
      <div>
        <div className="stat__label">{label}</div>
        <div className="stat__value">{value}</div>
        {delta && <div className={`stat__delta stat__delta--${deltaDir}`}>{delta}</div>}
      </div>
    </div>
  );
}

/* ---------------- Feedback ---------------- */
const STATUS_TONE = {
  active: "success", approved: "success", paid: "success", enrolled: "success", present: "success",
  pending: "warning", trial: "warning", partial: "warning", late: "warning", submitted: "brand",
  withdrawn: "neutral", inactive: "neutral", draft: "neutral",
  rejected: "danger", overdue: "danger", absent: "danger", suspended: "danger", probation: "danger",
};
export function Badge({ tone, children }) {
  const t = tone || STATUS_TONE[String(children).toLowerCase()] || "neutral";
  return <span className={`badge badge--${t}`}>{children}</span>;
}

export function Alert({ tone = "info", children }) {
  const Icon = { error: LuCircleAlert, success: LuCircleCheck, info: LuInfo }[tone];
  return (
    <div className={`alert alert--${tone}`} role={tone === "error" ? "alert" : "status"}>
      <Icon aria-hidden="true" />
      <div>{children}</div>
    </div>
  );
}

export function Spinner({ label = "Loading" }) {
  return <div className="spinner" role="status" aria-label={label} />;
}

export function EmptyState({ icon: Icon = LuInbox, title, children, action }) {
  return (
    <div className="empty">
      <Icon aria-hidden="true" />
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action && <div style={{ marginTop: 16 }}>{action}</div>}
    </div>
  );
}

/* ---------------- Forms ---------------- */
export function Field({ label, error, hint, children, className = "", required = false }) {
  const id = useId();
  const describedBy = error ? `${id}-err` : hint ? `${id}-hint` : undefined;
  const child = typeof children === "function"
    ? children({ id, "aria-invalid": error ? "true" : undefined, "aria-describedby": describedBy,
      ...(required ? { "aria-required": "true" } : {}) })
    : children;
  return (
    <div className={`field ${className}`}>
      <label htmlFor={id}>{label}{required && <span className="field__req" aria-hidden="true"> *</span>}</label>
      {child}
      {error ? <span id={`${id}-err`} className="field__error">{error}</span>
        : hint ? <span id={`${id}-hint`} className="field__hint">{hint}</span> : null}
    </div>
  );
}

/* ---------------- Modal ---------------- */
export function Modal({ title, onClose, children }) {
  const ref = useRef(null);
  useEffect(() => {
    const prev = document.activeElement;
    ref.current?.querySelector("input, select, textarea, button")?.focus();
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); prev?.focus?.(); };
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title" ref={ref}>
        <div className="modal__header">
          <h2 id="modal-title" className="card__title">{title}</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close dialog"><LuX /></button>
        </div>
        <div className="modal__body">{children}</div>
      </div>
    </div>
  );
}

/* ---------------- Misc ---------------- */
export function Avatar({ name = "" }) {
  const initials = name.split(" ").filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join("");
  return <span className="avatar" aria-hidden="true">{initials || "?"}</span>;
}

export function PersonCell({ name, sub }) {
  return (
    <div className="person">
      <Avatar name={name} />
      <div>
        <div className="person__name">{name}</div>
        {sub && <div className="person__sub">{sub}</div>}
      </div>
    </div>
  );
}
