import { useState } from "react";
import { LuPlus } from "react-icons/lu";
import { api } from "../../api/client";
import { useAction, useApi } from "../../utils/hooks";
import { Button, Card, EmptyState, Field, Modal, Spinner } from "./index";
import { ActionFeedback, ConfirmDelete, RowActions } from "./extra";

/**
 * Generic list + create/edit/delete card for simple setup records (grade levels, subjects,
 * faculties, semesters…). The backend does all validation; field errors come back per field.
 *
 * fields: [{ key, label, type: text|number|date|time|select|checkbox|textarea, required, options,
 *            optionsFrom: { path, params, value?, label: (row) => string, filter?: (row) => bool },
 *            hint, span2, default, hidden?: (form) => bool }]
 * columns: [{ key, header, render?(row), className? }]
 */
export function CrudCard({
  title, subtitle, path, params, columns, fields, canEdit = true, canDelete = true, rowActions,
  newLabel = "Add", emptyTitle = "Nothing here yet", emptyText, toBody = (f) => f, onChanged,
  editable = () => true, deleteConfirm = (row) => `Delete ${row.name || row.code || "this record"}?`,
}) {
  const list = useApi(path, { page_size: 100, ...params });
  const [editing, setEditing] = useState(null); // {} for new, row for edit
  const act = useAction();
  const rows = list.data?.results || (Array.isArray(list.data) ? list.data : []);
  const [removing, setRemoving] = useState(null);
  const done = () => { setEditing(null); list.reload(); onChanged?.(); };
  return (
    <Card title={title} subtitle={subtitle} bodyClass=""
      actions={canEdit && <Button size="sm" icon={LuPlus} onClick={() => setEditing({})}>{newLabel}</Button>}>
      <div style={{ padding: act.error || act.notice ? "0 16px" : 0 }}><ActionFeedback act={act} /></div>
      {list.loading && !list.data ? <Spinner /> : rows.length === 0 ? (
        <EmptyState title={emptyTitle}>{emptyText}</EmptyState>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr>{columns.map((c) => <th key={c.key} className={c.className}>{c.header}</th>)}<th className="num">{(canEdit || canDelete) ? "Actions" : ""}</th></tr></thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  {columns.map((c) => <td key={c.key} className={c.className}>{c.render ? c.render(row) : (row[c.key] ?? "—")}</td>)}
                  <td className="num" style={{ whiteSpace: "nowrap" }}>
                    <RowActions name={row.name || row.code || ""} extra={rowActions?.(row, list.reload)}
                      onEdit={canEdit && editable(row) ? () => setEditing(row) : undefined}
                      onDelete={canDelete && editable(row) ? () => setRemoving(row) : undefined} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing && (
        <RecordForm title={`${editing.id ? "Edit" : newLabel} · ${title}`} path={path} record={editing} fields={fields}
          toBody={toBody} onClose={() => setEditing(null)} onDone={done} />
      )}
      {removing && (
        <ConfirmDelete title={`Delete · ${title}`} onConfirm={(reason) => api.delete(`${path}${removing.id}/`, { reason })}
          onClose={(deleted) => { setRemoving(null); if (deleted) { act.say("Deleted."); list.reload(); onChanged?.(); } }}>
          {deleteConfirm(removing)}
        </ConfirmDelete>
      )}
    </Card>
  );
}

function initial(fields, record) {
  return Object.fromEntries(fields.map((f) => {
    const v = record[f.key];
    if (v !== undefined && v !== null) return [f.key, typeof v === "object" && "id" in v ? v.id : v];
    return [f.key, f.default ?? (f.type === "checkbox" ? false : "")];
  }));
}

export function RecordForm({ title, path, record, fields, toBody = (f) => f, onClose, onDone, submitLabel }) {
  const [form, setForm] = useState(() => initial(fields, record));
  const act = useAction();
  const set = (k, v) => setForm((x) => ({ ...x, [k]: v }));
  async function submit(e) {
    e.preventDefault();
    // Empty optional values go to the API as null so foreign keys and dates can be cleared.
    const body = toBody(Object.fromEntries(Object.entries(form).map(([k, v]) => {
      const spec = fields.find((f) => f.key === k);
      if (v === "" && spec?.type !== "text" && spec?.type !== "textarea") return [k, null];
      if (spec?.type === "number" && v !== null && v !== "") return [k, Number(v)];
      return [k, v];
    })));
    const r = await act.run(() => (record.id ? api.patch(`${path}${record.id}/`, body) : api.post(path, body)));
    if (r !== undefined) onDone(r);
  }
  return (
    <Modal title={title} onClose={onClose}>
      <form onSubmit={submit} noValidate>
        <ActionFeedback act={act} />
        <div className="form-grid">
          {fields.filter((f) => !f.hidden?.(form)).map((f) => (
            <FieldInput key={f.key} spec={f} value={form[f.key]} onChange={(v) => set(f.key, v)}
              error={act.error?.fields?.[f.key]?.[0]} form={form} />
          ))}
        </div>
        {act.error?.fields && Object.keys(act.error.fields).some((k) => !fields.some((f) => f.key === k)) && (
          <p className="field__error">{Object.entries(act.error.fields).filter(([k]) => !fields.some((f) => f.key === k))
            .map(([, v]) => [].concat(v).join(" ")).join(" ")}</p>
        )}
        <div className="form-actions">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={act.busy}>{act.busy ? "Saving…" : submitLabel || (record.id ? "Save changes" : "Create")}</Button>
        </div>
      </form>
    </Modal>
  );
}

function FieldInput({ spec, value, onChange, error, form }) {
  const from = spec.optionsFrom;
  const remote = useApi(from ? from.path : null, from ? { page_size: 200, ...(typeof from.params === "function" ? from.params(form) : from.params) } : undefined);
  const options = spec.options
    || (remote.data?.results || (Array.isArray(remote.data) ? remote.data : [])).filter(from?.filter || Boolean).map((r) => [r[from.value || "id"], from.label(r)]);
  const className = spec.span2 ? "span-2" : undefined;
  if (spec.type === "checkbox") {
    return (
      <div className={`field ${className || ""}`}>
        <label className="check"><input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} /> {spec.label}</label>
        {error ? <span className="field__error">{error}</span> : spec.hint && <span className="field__hint">{spec.hint}</span>}
      </div>
    );
  }
  return (
    <Field label={spec.label} error={error} hint={spec.hint} required={spec.required} className={className}>
      {(a) => spec.type === "select" ? (
        <select {...a} className="select" value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
          <option value="">{spec.placeholder || "Choose…"}</option>
          {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      ) : spec.type === "textarea" ? (
        <textarea {...a} className="input" rows={3} value={value ?? ""} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <input {...a} className="input" type={spec.type || "text"} value={value ?? ""} step={spec.step}
          min={spec.min} max={spec.max} placeholder={spec.placeholder} onChange={(e) => onChange(e.target.value)} />
      )}
    </Field>
  );
}
