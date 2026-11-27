import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { LuArrowLeft, LuMailPlus, LuSave, LuTrash2 } from "react-icons/lu";
import { api } from "../../api/client";
import { useAction, useApi } from "../../utils/hooks";
import { shortDate, titleCase } from "../../utils/format";
import { Alert, Badge, Button, Card, Field, PageHeader, Spinner } from "../../components/ui";
import { ActionFeedback, CopyLink, KeyValues } from "../../components/ui/extra";

/** Platform admin: tenant settings (plan, status, contact) and administrator invitations. No student data. */
export default function InstitutionDetail() {
  const { id } = useParams();
  const tenant = useApi(`/tenants/${id}/`);
  const invites = useApi("/platform/invitations/", { page_size: 100 });
  const [f, setF] = useState(null);
  const [email, setEmail] = useState("");
  const save = useAction();
  const invite = useAction();
  useEffect(() => { if (tenant.data) setF({ ...tenant.data }); }, [tenant.data]);
  if (tenant.error) return <Alert tone="error">{tenant.error.message}</Alert>;
  if (!f) return <Spinner />;
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  const err = (k) => save.error?.fields?.[k]?.[0];
  const t = tenant.data;
  const mine = (invites.data?.results || []).filter((i) => String(i.tenant) === String(id));
  async function submit(e) {
    e.preventDefault();
    const body = Object.fromEntries(["name", "status", "plan", "contact_email", "contact_phone", "address", "city", "country", "currency", "timezone",
      "accent_color"].map((k) => [k, f[k]]));
    if (await save.run(() => api.patch(`/tenants/${id}/`, body), "Institution updated.")) tenant.reload();
  }
  async function sendInvite(e) {
    e.preventDefault();
    if (await invite.run(() => api.post(`/tenants/${id}/invite-admin/`, { email }), `Invitation sent to ${email}.`)) { setEmail(""); invites.reload(); }
  }
  return (
    <>
      <PageHeader eyebrow={<Link to="/platform/institutions"><LuArrowLeft aria-hidden="true" /> Institutions</Link>} title={t.name}
        description={`${t.domain} · ${t.type === "university" ? "University" : "School (K-12)"} · created ${shortDate(t.created_at)}`}
        actions={<Badge>{t.status}</Badge>} />
      <div className="grid grid--2">
        <Card title="Tenant settings">
          <form onSubmit={submit} noValidate>
            <ActionFeedback act={save} />
            <div className="form-grid">
              <Field label="Name" error={err("name")} className="span-2">{(a) => <input {...a} className="input" value={f.name} onChange={set("name")} />}</Field>
              <Field label="Status" error={err("status")} hint="Suspended institutions can't sign in.">
                {(a) => <select {...a} className="select" value={f.status} onChange={set("status")}>{["trial", "active", "suspended"].map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}</select>}
              </Field>
              <Field label="Plan">{(a) => <select {...a} className="select" value={f.plan} onChange={set("plan")}>{["Starter", "Standard", "Enterprise"].map((p) => <option key={p}>{p}</option>)}</select>}</Field>
              <Field label="Contact email" error={err("contact_email")}>{(a) => <input {...a} className="input" type="email" value={f.contact_email} onChange={set("contact_email")} />}</Field>
              <Field label="Contact phone">{(a) => <input {...a} className="input" value={f.contact_phone} onChange={set("contact_phone")} />}</Field>
              <Field label="City">{(a) => <input {...a} className="input" value={f.city} onChange={set("city")} />}</Field>
              <Field label="Country">{(a) => <input {...a} className="input" value={f.country} onChange={set("country")} />}</Field>
              <Field label="Currency" error={err("currency")}>{(a) => <input {...a} className="input mono" maxLength={3} value={f.currency} onChange={set("currency")} />}</Field>
              <Field label="Time zone">{(a) => <input {...a} className="input" value={f.timezone} onChange={set("timezone")} />}</Field>
              <Field label="Accent colour" error={err("accent_color")}>{(a) => <input {...a} className="input mono" value={f.accent_color} onChange={set("accent_color")} />}</Field>
              <Field label="Domain">{(a) => <input {...a} className="input mono" value={t.domain} disabled />}</Field>
            </div>
            <div className="form-actions"><Button type="submit" icon={LuSave} disabled={save.busy}>Save settings</Button></div>
          </form>
        </Card>
        <div className="stack-sm">
          <Card title="Usage">
            <KeyValues items={[["Students", t.students], ["Staff", t.staff], ["Plan", t.plan], ["Mode", t.type === "university" ? "University" : "School (K-12)"]]} />
            <p className="muted" style={{ fontSize: "var(--fs-sm)", marginBottom: 0 }}>Platform administrators manage tenants but can't open student records.</p>
          </Card>
          <Card title="Administrator invitations">
            <form onSubmit={sendInvite} noValidate>
              <ActionFeedback act={invite} />
              <Field label="Invite another institution administrator" error={invite.error?.fields?.email?.[0]}>
                {(a) => <input {...a} className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="admin@institution.edu" />}
              </Field>
              <Button type="submit" icon={LuMailPlus} disabled={invite.busy || !email}>Send invitation</Button>
            </form>
            <ul className="list" style={{ marginTop: 12 }}>
              {mine.map((i) => (
                <li key={i.id} className="list__item"><span className="list__dot" />
                  <div><div className="list__title">{i.email} <Badge>{i.status}</Badge></div><div className="list__meta">Expires {shortDate(i.expires_at)} {i.status === "pending" && <CopyLink href={i.invite_link} />}</div></div></li>
              ))}
            </ul>
          </Card>
          <DeleteInstitution tenant={t} />
        </div>
      </div>
    </>
  );
}

/** Permanent removal of an institution and all of its data, confirmed by typing its exact name. */
function DeleteInstitution({ tenant }) {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const del = useAction();
  const navigate = useNavigate();
  const matches = typed.trim() === tenant.name;
  async function remove(e) {
    e.preventDefault();
    const r = await del.run(() => api.delete(`/tenants/${tenant.id}/`, { confirm_name: typed.trim() }));
    if (r) navigate("/platform/institutions", { replace: true, state: { flash: r.message } });
  }
  return (
    <Card title="Delete institution" className="card--danger">
      {!open ? (
        <>
          <p className="muted" style={{ marginTop: 0, fontSize: "var(--fs-sm)" }}>
            Removes {tenant.name} and everything in it: {tenant.students} student{tenant.students === 1 ? "" : "s"}, {tenant.staff} user
            {tenant.staff === 1 ? "" : "s"}, marks, fees and its audit log. To stop access but keep the data, set the status to Suspended instead.
          </p>
          <Button variant="danger" icon={LuTrash2} onClick={() => setOpen(true)}>Delete institution…</Button>
        </>
      ) : (
        <form onSubmit={remove} noValidate>
          <ActionFeedback act={del} />
          <Alert tone="error">This cannot be undone. All of {tenant.name}'s data will be permanently deleted.</Alert>
          <Field label={`Type ${tenant.name} to confirm`} error={del.error?.fields?.confirm_name?.[0]}>
            {(a) => <input {...a} className="input" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />}
          </Field>
          <div className="form-actions" style={{ justifyContent: "flex-start" }}>
            <Button type="submit" variant="danger" icon={LuTrash2} disabled={!matches || del.busy}>
              {del.busy ? "Deleting…" : "Delete permanently"}
            </Button>
            <Button variant="secondary" onClick={() => { setOpen(false); setTyped(""); }} disabled={del.busy}>Cancel</Button>
          </div>
        </form>
      )}
    </Card>
  );
}
