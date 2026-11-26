import { useState } from "react";
import { LuMegaphone, LuPin, LuPlus, LuTrash2 } from "react-icons/lu";
import { api } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { can, ROLE_LABELS } from "../../config/roles";
import { useAction, useApi } from "../../utils/hooks";
import { timeAgo } from "../../utils/format";
import { Badge, Button, Card, EmptyState, Field, Modal, PageHeader, Spinner } from "../../components/ui";
import { ActionFeedback } from "../../components/ui/extra";

const AUDIENCE = {
  school: ["principal", "class_teacher", "subject_teacher", "finance_officer", "guardian", "pupil"],
  university: ["registrar", "dean", "dept_head", "lecturer", "adviser", "finance_officer", "student"],
};

function NewAnnouncement({ mode, onClose, onDone }) {
  const [form, setForm] = useState({ title: "", body: "", pinned: false, audience_roles: [] });
  const act = useAction();
  const toggle = (r) => setForm((f) => ({ ...f, audience_roles: f.audience_roles.includes(r)
    ? f.audience_roles.filter((x) => x !== r) : [...f.audience_roles, r] }));
  async function submit(e) {
    e.preventDefault();
    if (await act.run(() => api.post("/announcements/", form))) onDone();
  }
  return (
    <Modal title="New announcement" onClose={onClose}>
      <form onSubmit={submit} noValidate>
        <ActionFeedback act={act} />
        <Field label="Title" error={act.error?.fields?.title?.[0]}>
          {(a) => <input {...a} className="input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />}
        </Field>
        <Field label="Message" error={act.error?.fields?.body?.[0]}>
          {(a) => <textarea {...a} className="textarea" rows={5} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} />}
        </Field>
        <fieldset style={{ border: 0, padding: 0, margin: "0 0 16px" }}>
          <legend className="select-label" style={{ marginBottom: 6 }}>Audience (none selected = everyone)</legend>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
            {AUDIENCE[mode].map((r) => (
              <label key={r} style={{ display: "flex", gap: 6, alignItems: "center", fontSize: "var(--fs-sm)" }}>
                <input type="checkbox" checked={form.audience_roles.includes(r)} onChange={() => toggle(r)} /> {ROLE_LABELS[r]}
              </label>
            ))}
          </div>
        </fieldset>
        <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: "var(--fs-sm)" }}>
          <input type="checkbox" checked={form.pinned} onChange={(e) => setForm({ ...form, pinned: e.target.checked })} /> Pin to the top
        </label>
        <div className="form-actions">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={act.busy}>{act.busy ? "Publishing…" : "Publish & notify"}</Button>
        </div>
      </form>
    </Modal>
  );
}

export default function Announcements() {
  const { user, mode } = useAuth();
  const [creating, setCreating] = useState(false);
  const { data, loading, reload } = useApi("/announcements/", { page_size: 50 });
  const act = useAction();
  const manage = can(user, "announcements.manage");
  const items = [...(data?.results || [])].sort((a, b) => Number(b.pinned) - Number(a.pinned));
  const remove = async (a) => {
    if (window.confirm(`Delete "${a.title}"?`) && await act.run(() => api.delete(`/announcements/${a.id}/`), "Announcement deleted.") !== undefined) reload();
  };
  return (
    <>
      <PageHeader title="Announcements" description={`News and notices from ${user.tenant.name}.`}
        actions={manage && <Button icon={LuPlus} onClick={() => setCreating(true)}>New announcement</Button>} />
      <ActionFeedback act={act} />
      {loading && !data ? <Spinner /> : items.length === 0 ? (
        <Card><EmptyState icon={LuMegaphone} title="No announcements yet" /></Card>
      ) : (
        <div className="stack-sm">
          {items.map((a) => (
            <Card key={a.id} title={<span style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
              {a.pinned && <LuPin aria-label="Pinned" />} {a.title}</span>}
              subtitle={`${a.author_name || "Staff"} · ${timeAgo(a.created_at)}`}
              actions={<div className="row-actions">
                {a.audience_roles.length > 0
                  ? a.audience_roles.map((r) => <Badge key={r} tone="neutral">{ROLE_LABELS[r] || r}</Badge>)
                  : <Badge tone="brand">Everyone</Badge>}
                {manage && <Button size="sm" variant="ghost" icon={LuTrash2} aria-label={`Delete ${a.title}`} onClick={() => remove(a)} />}
              </div>}>
              <p style={{ margin: 0, whiteSpace: "pre-line" }}>{a.body}</p>
            </Card>
          ))}
        </div>
      )}
      {creating && <NewAnnouncement mode={mode} onClose={() => setCreating(false)} onDone={() => { setCreating(false); reload(); }} />}
    </>
  );
}
