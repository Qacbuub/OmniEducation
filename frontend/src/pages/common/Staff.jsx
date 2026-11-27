import { useState } from "react";
import { LuMailPlus, LuTrash2 } from "react-icons/lu";
import { api } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { can, ROLE_LABELS } from "../../config/roles";
import { useAction, useApi, useDebounced } from "../../utils/hooks";
import { shortDate } from "../../utils/format";
import { Alert, Badge, Button, Card, Field, Modal, PageHeader, PersonCell } from "../../components/ui";
import { DataTable } from "../../components/ui/DataTable";
import { ActionFeedback, ConfirmDelete, CopyLink, RowActions, Tabs } from "../../components/ui/extra";
import { RecordForm } from "../../components/ui/Crud";

const STAFF_FIELDS = [
  { key: "first_name", label: "First name", required: true },
  { key: "last_name", label: "Last name", required: true },
  { key: "email", label: "Contact email", type: "text" },
  { key: "phone", label: "Phone", type: "text" },
  { key: "job_title", label: "Job title", type: "text" },
  { key: "department", label: "Department", type: "text" },
  { key: "hire_date", label: "Hire date", type: "date" },
  { key: "status", label: "Status", type: "select", required: true,
    options: [["active", "Active"], ["on_leave", "On leave"], ["left", "Left"]] },
];

const STAFF_ROLES = {
  school: ["inst_admin", "principal", "registrar", "class_teacher", "subject_teacher", "finance_officer"],
  university: ["inst_admin", "registrar", "dean", "dept_head", "lecturer", "adviser", "finance_officer"],
};

function InviteStaff({ mode, onClose, onDone }) {
  const [form, setForm] = useState({ email: "", first_name: "", last_name: "", role: mode === "school" ? "class_teacher" : "lecturer" });
  const act = useAction();
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const err = (k) => act.error?.fields?.[k]?.[0];
  async function submit(e) {
    e.preventDefault();
    if (await act.run(() => api.post("/invitations/", form))) onDone(form.email);
  }
  return (
    <Modal title="Invite a staff member" onClose={onClose}>
      <form onSubmit={submit} noValidate>
        <ActionFeedback act={act} />
        <div className="form-grid">
          <Field label="First name" error={err("first_name")}>{(a) => <input {...a} className="input" value={form.first_name} onChange={set("first_name")} />}</Field>
          <Field label="Last name" error={err("last_name")}>{(a) => <input {...a} className="input" value={form.last_name} onChange={set("last_name")} />}</Field>
          <Field label="Email" error={err("email")} className="span-2">{(a) => <input {...a} className="input" type="email" value={form.email} onChange={set("email")} required />}</Field>
          <Field label="Role" error={err("role")} className="span-2" hint="The role decides what they can see and do.">
            {(a) => (
              <select {...a} className="select" value={form.role} onChange={set("role")}>
                {STAFF_ROLES[mode].map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
              </select>
            )}
          </Field>
        </div>
        <div className="form-actions">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" icon={LuMailPlus} disabled={act.busy}>{act.busy ? "Sending…" : "Send invitation"}</Button>
        </div>
      </form>
    </Modal>
  );
}

export default function Staff() {
  const { user, mode } = useAuth();
  const [tab, setTab] = useState("staff");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [inviting, setInviting] = useState(false);
  const q = useDebounced(search);
  const staff = useApi("/staff/", { search: q, page });
  const manage = can(user, "staff.manage");
  const invites = useApi(manage ? "/invitations/" : "/staff/", { page_size: 50 });
  const act = useAction();
  const [notice, setNotice] = useState(null);
  const [editing, setEditing] = useState(null);
  const [removing, setRemoving] = useState(null);

  const columns = [
    { key: "name", header: "Name", render: (s) => <PersonCell name={`${s.first_name} ${s.last_name}`} sub={s.account_email || s.email} /> },
    { key: "staff_no", header: "Staff no.", render: (s) => <span className="mono">{s.staff_no}</span> },
    { key: "job_title", header: "Job title" },
    { key: "role", header: "Role", render: (s) => s.role ? ROLE_LABELS[s.role] : <span className="muted">No account</span> },
    { key: "hire_date", header: "Hired", render: (s) => shortDate(s.hire_date) },
    { key: "status", header: "Status", render: (s) => <Badge>{s.status}</Badge> },
    ...(manage ? [{ key: "actions", header: "Actions", className: "num", render: (s) => (
      <RowActions name={`${s.first_name} ${s.last_name}`} onEdit={() => setEditing(s)}
        onDelete={s.account_email === user.email ? undefined : () => setRemoving(s)} />
    ) }] : []),
  ];
  const revoke = async (inv) => {
    if (window.confirm(`Cancel the invitation for ${inv.email}?`) &&
      await act.run(() => api.delete(`/invitations/${inv.id}/`), "Invitation cancelled.") !== undefined) invites.reload();
  };

  return (
    <>
      <PageHeader title="Staff" description="Staff profiles, roles and invitations."
        actions={manage && <Button icon={LuMailPlus} onClick={() => setInviting(true)}>Invite staff</Button>} />
      <ActionFeedback act={act} />
      {notice && <Alert tone="success">{notice}</Alert>}
      {editing && (
        <RecordForm title={`Edit · ${editing.first_name} ${editing.last_name}`} path="/staff/" record={editing} fields={STAFF_FIELDS}
          onClose={() => setEditing(null)} onDone={() => { setEditing(null); setNotice("Staff details saved."); staff.reload(); }} />
      )}
      {removing && (
        <ConfirmDelete title={`Delete ${removing.first_name} ${removing.last_name}`} confirmLabel="Delete staff member"
          onConfirm={(reason) => api.delete(`/staff/${removing.id}/`, { reason })}
          onClose={(deleted) => { if (deleted) { setNotice(`${removing.first_name} ${removing.last_name} was deleted.`); staff.reload(); } setRemoving(null); }}>
          <p style={{ marginTop: 0 }}>This removes the staff profile ({removing.staff_no}) and {removing.account_email ? `the sign-in ${removing.account_email}` : "the profile's details"}.
            Classes and sections they teach become unassigned; marks and records they entered stay.</p>
          <p className="muted" style={{ fontSize: "var(--fs-sm)", marginBottom: 0 }}>To keep the history of who did what, set the status to Left instead.</p>
        </ConfirmDelete>
      )}
      {manage && <Tabs value={tab} onChange={setTab} tabs={[{ value: "staff", label: "Staff", count: staff.data?.count },
        { value: "invites", label: "Invitations", count: invites.data?.count }]} />}
      {tab === "staff" ? (
        <Card bodyClass="">
          <DataTable caption="Staff" columns={columns} data={staff.data} loading={staff.loading} error={staff.error}
            search={search} onSearch={(v) => { setSearch(v); setPage(1); }} searchPlaceholder="Search staff…" page={page} onPage={setPage} />
        </Card>
      ) : (
        <Card bodyClass="">
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Email</th><th>Name</th><th>Role</th><th>Status</th><th>Expires</th><th /></tr></thead>
            <tbody>
              {(invites.data?.results || []).map((i) => (
                <tr key={i.id}>
                  <td>{i.email}</td><td>{[i.first_name, i.last_name].filter(Boolean).join(" ") || "—"}</td><td>{i.role_name}</td>
                  <td><Badge>{i.status}</Badge></td><td className="muted">{shortDate(i.expires_at)}</td>
                  <td className="num" style={{ whiteSpace: "nowrap" }}>
                    {i.status === "pending" && <CopyLink href={i.invite_link} />}
                    {i.status === "pending" && <Button size="sm" variant="ghost" icon={LuTrash2} onClick={() => revoke(i)}>Cancel</Button>}
                  </td>
                </tr>
              ))}
              {invites.data?.results?.length === 0 && <tr><td colSpan={6} className="muted">No invitations.</td></tr>}
            </tbody>
          </table></div>
        </Card>
      )}
      {inviting && <InviteStaff mode={mode} onClose={() => setInviting(false)}
        onDone={(email) => { setInviting(false); act.clear(); invites.reload(); setTab("invites"); setNotice(`Invitation sent to ${email}.`); }} />}
    </>
  );
}

