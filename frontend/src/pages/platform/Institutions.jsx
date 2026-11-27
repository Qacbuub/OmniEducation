import { useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { LuPlus, LuSchool, LuGraduationCap } from "react-icons/lu";
import { api } from "../../api/client";
import { useApi, useDebounced } from "../../utils/hooks";
import { Alert, Badge, Button, Card, Field, Modal, PageHeader } from "../../components/ui";
import { shortDate } from "../../utils/format";
import { DataTable } from "../../components/ui/DataTable";

const EMPTY = { name: "", slug: "", type: "school", city: "", country: "", plan: "Starter", admin_email: "" };

function CreateInstitution({ onClose, onCreated }) {
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const set = (k) => (e) => {
    const v = e.target.value;
    setForm((f) => ({
      ...f, [k]: v,
      // Suggest a short name from the institution name until the user edits it.
      ...(k === "name" && f.slug === slugify(f.name) ? { slug: slugify(v) } : {}),
    }));
  };
  const err = (k) => error?.fields?.[k]?.[0];

  async function submit(e) {
    e.preventDefault();
    setSaving(true); setError(null);
    try {
      const t = await api.post("/tenants/", form);
      onCreated(t);
    } catch (ex) { setError(ex); } finally { setSaving(false); }
  }

  return (
    <Modal title="Create institution" onClose={onClose}>
      <form onSubmit={submit} noValidate>
        {error && <Alert tone="error">{error.message}</Alert>}
        <fieldset style={{ border: 0, padding: 0, margin: "0 0 16px" }}>
          <legend style={{ fontWeight: 600, fontSize: "var(--fs-sm)", marginBottom: 8 }}>Institution mode</legend>
          <div className="grid grid--2" style={{ gap: 10 }}>
            {[["school", "School (K-12)", "Grades, terms, report cards", LuSchool], ["university", "University", "Courses, credits, transcripts", LuGraduationCap]].map(([v, label, sub, Icon]) => (
              <label key={v} className="card" style={{ padding: 14, cursor: "pointer", display: "flex", gap: 10, alignItems: "flex-start",
                borderColor: form.type === v ? "var(--brand)" : undefined, boxShadow: form.type === v ? "0 0 0 1px var(--brand)" : undefined }}>
                <input type="radio" name="type" value={v} checked={form.type === v} onChange={set("type")} style={{ marginTop: 4 }} />
                <span>
                  <span style={{ display: "flex", gap: 6, alignItems: "center", fontWeight: 600 }}><Icon aria-hidden="true" /> {label}</span>
                  <span className="muted" style={{ fontSize: "var(--fs-xs)" }}>{sub}</span>
                </span>
              </label>
            ))}
          </div>
          {err("type") && <span className="field__error">{err("type")}</span>}
        </fieldset>
        <div className="form-grid">
          <Field label="Institution name" error={err("name")} className="span-2">
            {(a) => <input {...a} className="input" value={form.name} onChange={set("name")} required />}
          </Field>
          <Field label="Short name" error={err("slug")} hint={`Workspace: ${form.slug || "short-name"}.omniedu.app`}>
            {(a) => <input {...a} className="input mono" value={form.slug} onChange={set("slug")} required />}
          </Field>
          <Field label="Plan">
            {(a) => (
              <select {...a} className="select" value={form.plan} onChange={set("plan")}>
                <option>Starter</option><option>Standard</option><option>Enterprise</option>
              </select>
            )}
          </Field>
          <Field label="City">{(a) => <input {...a} className="input" value={form.city} onChange={set("city")} />}</Field>
          <Field label="Country">{(a) => <input {...a} className="input" value={form.country} onChange={set("country")} />}</Field>
          <Field label="Institution administrator email" error={err("admin_email")} hint="We'll email them an invitation to set their password." className="span-2">
            {(a) => <input {...a} className="input" type="email" value={form.admin_email} onChange={set("admin_email")} required />}
          </Field>
        </div>
        <div className="form-actions">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={saving}>{saving ? "Creating…" : "Create & send invitation"}</Button>
        </div>
      </form>
    </Modal>
  );
}

const slugify = (s) => s.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 30);

export default function Institutions() {
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [type, setType] = useState("");
  const [page, setPage] = useState(1);
  const location = useLocation();
  const [notice, setNotice] = useState(location.state?.flash || null); // e.g. "X and all of its data were deleted."
  const q = useDebounced(search);
  const { data, loading, error, reload } = useApi("/tenants/", { search: q, type, page });
  const creating = params.get("new") === "1";
  const closeCreate = () => setParams({}, { replace: true });

  const columns = [
    { key: "name", header: "Institution", render: (t) => (
      <div><Link to={`/platform/institutions/${t.id}`} style={{ fontWeight: 600 }}>{t.name}</Link><div className="muted mono" style={{ fontSize: "var(--fs-xs)" }}>{t.domain}</div></div>
    )},
    { key: "type", header: "Mode", render: (t) => <Badge tone={t.type === "university" ? "dark" : "brand"}>{t.type === "university" ? "University" : "School"}</Badge> },
    { key: "location", header: "Location", render: (t) => [t.city, t.country].filter(Boolean).join(", ") || "—" },
    { key: "plan", header: "Plan" },
    { key: "students", header: "Students", className: "num" },
    { key: "status", header: "Status", render: (t) => <Badge>{t.status}</Badge> },
    { key: "created_at", header: "Created", render: (t) => <span className="muted">{shortDate(t.created_at)}</span> },
  ];

  return (
    <>
      <PageHeader
        eyebrow="Platform"
        title="Institutions"
        description="Each institution is an isolated tenant with its own data, branding and settings."
        actions={<Button icon={LuPlus} onClick={() => setParams({ new: "1" })}>New institution</Button>}
      />
      {notice && <Alert tone="success">{notice}</Alert>}
      <Card bodyClass="">
        <DataTable
          caption="Institutions"
          columns={columns} data={data} loading={loading} error={error}
          search={search} onSearch={(v) => { setSearch(v); setPage(1); }} searchPlaceholder="Search institutions…"
          filters={
            <>
              <label className="sr-only" htmlFor="type-filter">Filter by mode</label>
              <select id="type-filter" className="select" style={{ width: 180 }} value={type} onChange={(e) => { setType(e.target.value); setPage(1); }}>
                <option value="">All modes</option><option value="school">Schools</option><option value="university">Universities</option>
              </select>
            </>
          }
          page={page} onPage={setPage}
        />
      </Card>
      {creating && (
        <CreateInstitution onClose={closeCreate} onCreated={(t) => {
          closeCreate();
          setNotice(`${t.name} was created. An invitation was sent to its administrator.`);
          reload();
        }} />
      )}
    </>
  );
}
