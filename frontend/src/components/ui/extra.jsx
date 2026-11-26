import { useState } from "react";
import { Link } from "react-router-dom";
import { LuDownload } from "react-icons/lu";
import { api } from "../../api/client";
import { useApi, useDebounced } from "../../utils/hooks";
import { Alert, Button } from "./index";

/* ---------------- Tabs ---------------- */
export function Tabs({ tabs, value, onChange, label = "Sections" }) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.filter(Boolean).map((t) => (
        <button key={t.value} type="button" role="tab" aria-selected={value === t.value}
          className={`tab${value === t.value ? " tab--active" : ""}`} onClick={() => onChange(t.value)}>
          {t.label}{t.count !== undefined && <span className="tab__count">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

/* ---------------- Action feedback ---------------- */
export function ActionFeedback({ act }) {
  if (act.error) {
    const fields = Object.entries(act.error.fields || {})
      .filter(([k]) => !["missing", "unmet", "missing_prerequisites", "missing_terms"].includes(k));
    const missing = act.error.fields?.missing || act.error.fields?.unmet;
    return (
      <Alert tone="error">
        {act.error.message}
        {fields.length > 0 && (
          <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
            {fields.slice(0, 6).map(([k, v]) => <li key={k}>{k}: {Array.isArray(v) ? v.join(" ") : String(v)}</li>)}
          </ul>
        )}
        {Array.isArray(missing) && missing.length > 1 && (
          <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>{missing.slice(0, 8).map((m) => <li key={m}>{m}</li>)}</ul>
        )}
      </Alert>
    );
  }
  if (act.notice) return <Alert tone="success">{act.notice}</Alert>;
  return null;
}

/* ---------------- Downloads (PDF / CSV behind the API's permission checks) ---------------- */
export function DownloadButton({ path, filename, children = "Download", variant = "secondary", size = "sm", icon = LuDownload }) {
  const [state, setState] = useState({ busy: false, error: null });
  const go = async () => {
    setState({ busy: true, error: null });
    try { await api.download(path, { filename }); setState({ busy: false, error: null }); }
    catch (error) { setState({ busy: false, error }); }
  };
  return (
    <span style={{ display: "inline-flex", flexDirection: "column", gap: 4 }}>
      <Button variant={variant} size={size} icon={icon} onClick={go} disabled={state.busy}>
        {state.busy ? "Preparing…" : children}
      </Button>
      {state.error && <span className="field__error">{state.error.message}</span>}
    </span>
  );
}

/* ---------------- Simple labelled select ---------------- */
export function SelectBox({ id, label, value, onChange, options, placeholder, width = 220, hideLabel = false }) {
  return (
    <span style={{ display: "inline-flex", flexDirection: "column", gap: 4 }}>
      <label htmlFor={id} className={hideLabel ? "sr-only" : "select-label"}>{label}</label>
      <select id={id} className="select" style={{ width }} value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </span>
  );
}

/* ---------------- Student picker (search by name / number) ---------------- */
export function StudentPicker({ value, onChange, label = "Student" }) {
  const [q, setQ] = useState("");
  const search = useDebounced(q);
  const { data } = useApi("/students/", { search, page_size: 8 });
  const rows = data?.results || [];
  return (
    <div className="picker">
      <label htmlFor="student-picker" className="select-label">{label}</label>
      <input id="student-picker" className="input" type="search" placeholder="Search name or ID…" value={q}
        onChange={(e) => setQ(e.target.value)} style={{ width: 280 }} />
      {search && rows.length > 0 && (
        <ul className="picker__list" role="listbox" aria-label="Matching students">
          {rows.map((s) => (
            <li key={s.id}>
              <button type="button" role="option" aria-selected={String(value) === String(s.id)} className="picker__item"
                onClick={() => { onChange(s); setQ(""); }}>
                <strong>{s.first_name} {s.last_name}</strong> <span className="muted mono">{s.student_no}</span>
                <span className="muted"> · {s.level}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ---------------- Weekly timetable grid ---------------- */
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** items: [{ id, day (0=Mon), start_time "08:00:00", end_time, title, sub, room }] */
export function WeekGrid({ items, days = 5, empty = "No classes scheduled." }) {
  if (!items?.length) return <p className="muted" style={{ margin: 0 }}>{empty}</p>;
  const starts = [...new Set(items.map((i) => i.start_time))].sort();
  return (
    <div className="table-wrap">
      <table className="table timetable" aria-label="Weekly timetable">
        <thead>
          <tr><th scope="col">Time</th>{DAYS.slice(0, days).map((d) => <th scope="col" key={d}>{d}</th>)}</tr>
        </thead>
        <tbody>
          {starts.map((start) => (
            <tr key={start}>
              <th scope="row" className="mono">{start.slice(0, 5)}</th>
              {DAYS.slice(0, days).map((_, d) => {
                const here = items.filter((i) => i.day === d && i.start_time === start);
                return (
                  <td key={d}>
                    {here.map((i) => (
                      <div className="slot" key={i.id}>
                        <div className="slot__title">{i.title}</div>
                        {i.sub && <div className="slot__meta">{i.sub}</div>}
                        <div className="slot__meta">{i.start_time.slice(0, 5)}–{i.end_time.slice(0, 5)}{i.room ? ` · ${i.room}` : ""}</div>
                      </div>
                    ))}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---------------- Key/value list ---------------- */
export function KeyValues({ items }) {
  return (
    <dl className="kv">
      {items.filter(Boolean).map(([k, v]) => (
        <div key={k} className="kv__row"><dt>{k}</dt><dd>{v ?? "—"}</dd></div>
      ))}
    </dl>
  );
}

/* ---------------- Small helpers ---------------- */
export function StudentLink({ mode, id, children }) {
  return <Link to={`/${mode}/students/${id}`}>{children}</Link>;
}

export function ProgressBar({ value, max = 100, label }) {
  const pctValue = Math.max(0, Math.min(100, (Number(value) / max) * 100));
  return (
    <div className="hbar__track" role="progressbar" aria-label={label} aria-valuenow={Number(value)} aria-valuemin={0}
      aria-valuemax={max}>
      <div className="hbar__fill" style={{ width: `${pctValue}%` }} />
    </div>
  );
}

/* ---------------- Invitation link (local demo only: emails go to the server console) ---------------- */
export function CopyLink({ href, label = "Copy sign-up link" }) {
  const [copied, setCopied] = useState(false);
  if (!href) return null;
  const copy = async () => {
    try { await navigator.clipboard.writeText(href); setCopied(true); setTimeout(() => setCopied(false), 2000); }
    catch { window.prompt("Copy this link:", href); }
  };
  return <button type="button" className="link-btn" onClick={copy} title={href}>{copied ? "Copied!" : label}</button>;
}
