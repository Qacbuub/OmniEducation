import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { LuArrowLeft, LuCamera, LuFileText, LuIdCard, LuPencil, LuScrollText, LuTrash2, LuUpload } from "react-icons/lu";
import { api } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { can } from "../../config/roles";
import { useAction, useApi } from "../../utils/hooks";
import { money, shortDate, titleCase } from "../../utils/format";
import { Alert, Badge, Button, Card, EmptyState, Field, Modal, PageHeader, Spinner } from "../../components/ui";
import { ActionFeedback, CopyLink, DownloadButton, KeyValues, Tabs } from "../../components/ui/extra";

const DOC_KINDS = [
  ["supporting", "Supporting document"], ["birth_certificate", "Birth certificate"],
  ["previous_results", "Previous results"], ["other", "Other"],
];

function UploadDocument({ studentId, onClose, onDone }) {
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState("supporting");
  const act = useAction();
  async function submit(e) {
    e.preventDefault();
    const body = new FormData();
    if (file) body.append("file", file);
    body.append("title", title || file?.name || "");
    body.append("kind", kind);
    body.append("student", studentId);
    if (await act.run(() => api.post("/documents/", body))) onDone();
  }
  return (
    <Modal title="Upload document" onClose={onClose}>
      <form onSubmit={submit} noValidate>
        <ActionFeedback act={act} />
        <Field label="File" error={act.error?.fields?.file?.[0]} hint="PDF, PNG, JPG or DOCX, up to the size limit.">
          {(a) => <input {...a} className="input" type="file" accept=".pdf,.png,.jpg,.jpeg,.docx"
            onChange={(e) => setFile(e.target.files[0])} required />}
        </Field>
        <Field label="Title" error={act.error?.fields?.title?.[0]}>
          {(a) => <input {...a} className="input" value={title} onChange={(e) => setTitle(e.target.value)}
            placeholder={file?.name || "e.g. Birth certificate"} />}
        </Field>
        <Field label="Type">
          {(a) => (
            <select {...a} className="select" value={kind} onChange={(e) => setKind(e.target.value)}>
              {DOC_KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          )}
        </Field>
        <div className="form-actions">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" icon={LuUpload} disabled={act.busy || !file}>{act.busy ? "Uploading…" : "Upload"}</Button>
        </div>
      </form>
    </Modal>
  );
}

const EDIT_FIELDS = ["first_name", "middle_name", "last_name", "date_of_birth", "national_id", "gender", "email", "phone", "address"];
const GENDERS = [["female", "Female"], ["male", "Male"], ["other", "Other"], ["undisclosed", "Prefer not to say"]];

function EditStudent({ student, onClose, onDone }) {
  const [form, setForm] = useState(() => Object.fromEntries(EDIT_FIELDS.map((k) => [k, student[k] ?? ""])));
  const act = useAction();
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const err = (k) => act.error?.fields?.[k]?.[0];
  async function submit(e) {
    e.preventDefault();
    const body = { ...form, date_of_birth: form.date_of_birth || null };
    if (await act.run(() => api.patch(`/students/${student.id}/`, body))) onDone();
  }
  const text = (k, label, type = "text", extra = {}) => (
    <Field label={label} error={err(k)} {...extra}>
      {(a) => <input {...a} className="input" type={type} value={form[k]} onChange={set(k)} />}
    </Field>
  );
  return (
    <Modal title="Edit details" onClose={onClose}>
      <form onSubmit={submit} noValidate>
        <ActionFeedback act={act} />
        <div className="form-grid">
          {text("first_name", "First name")}
          {text("middle_name", "Middle name")}
          {text("last_name", "Last name")}
          {text("date_of_birth", "Date of birth", "date")}
          <Field label="Gender" error={err("gender")}>
            {(a) => (
              <select {...a} className="select" value={form.gender} onChange={set("gender")}>
                {GENDERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            )}
          </Field>
          {text("national_id", "ID / birth certificate no.")}
          {text("phone", "Phone", "tel")}
          {text("email", "Email", "email", { className: "span-2" })}
          {text("address", "Address", "text", { className: "span-2" })}
        </div>
        <p className="muted" style={{ fontSize: "var(--fs-xs)" }}>
          Class, grade and status change through class placement, promotion, transfer or withdrawal, not here.
        </p>
        <div className="form-actions">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={act.busy}>{act.busy ? "Saving…" : "Save changes"}</Button>
        </div>
      </form>
    </Modal>
  );
}

/** The student's photo, loaded with the user's token (photos are never public URLs). */
export function StudentAvatar({ student, size = 96 }) {
  const [src, setSrc] = useState(null);
  useEffect(() => {
    if (!student.photo_url) { setSrc(null); return undefined; }
    let url; let alive = true;
    api.blob(student.photo_url.replace(/^\/api/, "")).then((b) => {
      if (!alive) return;
      url = URL.createObjectURL(b);
      setSrc(url);
    }).catch(() => alive && setSrc(null));
    return () => { alive = false; if (url) URL.revokeObjectURL(url); };
  }, [student.photo_url]);
  const initials = `${student.first_name?.[0] || ""}${student.last_name?.[0] || ""}`.toUpperCase();
  return src
    ? <img className="avatar-photo" src={src} alt={`Photo of ${student.first_name} ${student.last_name}`} style={{ width: size, height: size }} />
    : <div className="avatar-photo avatar-photo--empty" style={{ width: size, height: size, fontSize: size / 3 }} aria-label="No photo">{initials}</div>;
}

function PhotoControls({ student, onChanged }) {
  const input = useRef(null);
  const act = useAction();
  async function pick(e) {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    const body = new FormData();
    body.append("photo", file);
    if (await act.run(() => api.post(`/students/${student.id}/photo/`, body), "Photo updated.")) onChanged();
  }
  async function remove() {
    if (!window.confirm("Remove this student's photo?")) return;
    if (await act.run(() => api.delete(`/students/${student.id}/photo/`), "Photo removed.")) onChanged();
  }
  return (
    <div className="stack-sm">
      <input ref={input} type="file" accept="image/jpeg,image/png" hidden onChange={pick} aria-label="Choose a photo" />
      <div className="row-actions" style={{ justifyContent: "flex-start" }}>
        <Button size="sm" variant="secondary" icon={LuCamera} disabled={act.busy} onClick={() => input.current?.click()}>
          {act.busy ? "Uploading…" : student.photo_url ? "Change photo" : "Upload photo"}
        </Button>
        {student.photo_url && <Button size="sm" variant="ghost" icon={LuTrash2} disabled={act.busy} onClick={remove}>Remove</Button>}
      </div>
      <span className="muted" style={{ fontSize: "var(--fs-xs)" }}>JPG or PNG, up to 3 MB. A passport-style photo works best.</span>
      <ActionFeedback act={act} />
    </div>
  );
}

const RELATIONSHIPS = ["mother", "father", "guardian", "grandparent", "sibling", "spouse", "uncle", "aunt", "other"];

/** Say whether the invitation email really went out; show the sign-up link when the server shares it. */
function InviteResult({ result }) {
  if (!result) return null;
  const sent = result.email_sent !== false;
  return (
    <Alert tone={sent ? "success" : "info"}>
      {result.message}
      {result.invite_link && (
        <div style={{ marginTop: 6, fontSize: "var(--fs-xs)" }}>
          {sent ? "For testing, the same sign-up link is also shown here: " : "Sign-up link to share: "}
          <a href={result.invite_link} className="mono" style={{ wordBreak: "break-all" }}>{result.invite_link}</a>{" "}
          <CopyLink href={result.invite_link} label="Copy" />
        </div>
      )}
    </Alert>
  );
}

function ContactForm({ kind, student, onClose, onDone }) {
  const guardian = kind === "guardian";
  const [f, setF] = useState({ first_name: "", last_name: "", name: "", relationship: guardian ? "mother" : "", phone: "", email: "", is_primary: false });
  const act = useAction();
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));
  const err = (k) => act.error?.fields?.[k]?.[0];
  async function submit(e) {
    e.preventDefault();
    const ok = await act.run(async () => {
      if (!guardian) {
        return api.post("/emergency-contacts/", { student: student.id, name: f.name, relationship: f.relationship, phone: f.phone, email: f.email, is_primary: f.is_primary });
      }
      const g = await api.post("/guardians/", { first_name: f.first_name, last_name: f.last_name, phone: f.phone, email: f.email });
      return api.post("/guardian-links/", { guardian: g.id, student: student.id, relationship: f.relationship, is_primary: f.is_primary });
    });
    if (ok) onDone();
  }
  return (
    <Modal title={guardian ? "Add parent / guardian" : "Add emergency contact"} onClose={onClose}>
      <form onSubmit={submit} noValidate>
        <ActionFeedback act={act} />
        <div className="form-grid">
          {guardian ? <>
            <Field label="First name" required error={err("first_name")}>{(a) => <input {...a} className="input" value={f.first_name} onChange={set("first_name")} />}</Field>
            <Field label="Last name" required error={err("last_name")}>{(a) => <input {...a} className="input" value={f.last_name} onChange={set("last_name")} />}</Field>
          </> : (
            <Field label="Full name" required error={err("name")}>{(a) => <input {...a} className="input" value={f.name} onChange={set("name")} />}</Field>
          )}
          <Field label="Relationship" required error={err("relationship")}>
            {(a) => (
              <select {...a} className="select" value={f.relationship} onChange={set("relationship")}>
                <option value="">Choose…</option>
                {RELATIONSHIPS.map((r) => <option key={r} value={r}>{titleCase(r)}</option>)}
              </select>
            )}
          </Field>
          <Field label="Phone" required error={err("phone")}>{(a) => <input {...a} className="input" type="tel" value={f.phone} onChange={set("phone")} />}</Field>
          <Field label="Email" error={err("email")} hint={guardian ? "Needed to invite them to the parent portal." : undefined}>{(a) => <input {...a} className="input" type="email" value={f.email} onChange={set("email")} />}</Field>
          <div className="field"><label className="check"><input type="checkbox" checked={f.is_primary} onChange={set("is_primary")} /> Primary contact</label></div>
        </div>
        {act.error?.fields?.non_field_errors && <p className="field__error">{act.error.fields.non_field_errors.join(" ")}</p>}
        <div className="form-actions">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={act.busy}>{act.busy ? "Saving…" : "Add"}</Button>
        </div>
      </form>
    </Modal>
  );
}

function Contacts({ student: s, isUni, canManage, onChanged }) {
  const [adding, setAdding] = useState(null);
  const [invite, setInvite] = useState(null);
  const act = useAction();
  const removeLink = async (g) => {
    if (window.confirm(`Unlink ${g.name} from ${s.first_name}? They will no longer see this student in the parent portal.`)
      && (await act.run(() => api.delete(`/guardian-links/${g.link_id}/`), "Guardian unlinked.")) !== undefined) onChanged();
  };
  const removeContact = async (c) => {
    if (window.confirm(`Remove ${c.name} as an emergency contact?`)
      && (await act.run(() => api.delete(`/emergency-contacts/${c.id}/`), "Contact removed.")) !== undefined) onChanged();
  };
  const invitePortal = async (path) => {
    setInvite(null);
    const r = await act.run(() => api.post(path, {}));
    if (r) { setInvite(r); onChanged(); }
  };
  return (
    <Card title={isUni ? "Next of kin & emergency contacts" : "Guardians & emergency contacts"}
      actions={canManage && (
        <div className="row-actions">
          <Button size="sm" variant="secondary" onClick={() => setAdding("guardian")}>{isUni ? "Add next of kin" : "Add guardian"}</Button>
          <Button size="sm" variant="secondary" onClick={() => setAdding("contact")}>Add contact</Button>
        </div>
      )}>
      <ActionFeedback act={act} />
      <InviteResult result={invite} />
      <ul className="list">
        {s.guardians.map((g) => (
          <li className="list__item" key={`g${g.link_id}`}>
            <span className="list__dot" />
            <div style={{ flex: 1 }}>
              <div className="list__title">{g.name} {g.is_primary && <Badge tone="brand">Primary</Badge>}</div>
              <div className="list__meta">{titleCase(g.relationship)} · {g.phone || "—"} · {g.email || "no email"}
                {g.has_portal_account ? " · has portal account" : ""}</div>
            </div>
            {canManage && (
              <span className="row-actions">
                {!isUni && !g.has_portal_account && g.email && (
                  <Button size="sm" variant="ghost" disabled={act.busy} onClick={() => invitePortal(`/guardians/${g.id}/portal-account/`)}>Invite to parent portal</Button>
                )}
                <Button size="sm" variant="ghost" icon={LuTrash2} aria-label={`Unlink ${g.name}`} onClick={() => removeLink(g)} />
              </span>
            )}
          </li>
        ))}
        {s.emergency_contacts.map((c) => (
          <li className="list__item" key={`c${c.id}`}>
            <span className="list__dot" />
            <div style={{ flex: 1 }}>
              <div className="list__title">{c.name} {c.is_primary && <Badge tone="brand">Primary</Badge>}</div>
              <div className="list__meta">Emergency contact · {titleCase(c.relationship)} · {c.phone}{c.email ? ` · ${c.email}` : ""}</div>
            </div>
            {canManage && <Button size="sm" variant="ghost" icon={LuTrash2} aria-label={`Remove ${c.name}`} onClick={() => removeContact(c)} />}
          </li>
        ))}
        {!s.guardians.length && !s.emergency_contacts.length && <li className="list__item muted">None recorded.</li>}
      </ul>
      {canManage && !s.has_portal_account && (
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12, marginTop: 8 }}>
          <div className="muted" style={{ fontSize: "var(--fs-xs)", marginBottom: 6 }}>
            {s.first_name} has no {isUni ? "student" : "pupil"} portal account yet{s.email ? "" : " – add an email address first"}.
          </div>
          <Button size="sm" variant="secondary" disabled={act.busy || !s.email} onClick={() => invitePortal(`/students/${s.id}/portal-account/`)}>
            Invite {s.first_name} to the {isUni ? "student" : "pupil"} portal
          </Button>
        </div>
      )}
      {adding && <ContactForm kind={adding} student={s} onClose={() => setAdding(null)} onDone={() => { setAdding(null); onChanged(); }} />}
    </Card>
  );
}

function EndEnrollment({ enrollment, kind, onClose, onDone }) {
  const [form, setForm] = useState({ reason: "", destination: "", effective_date: "" });
  const act = useAction();
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  async function submit(e) {
    e.preventDefault();
    const body = { reason: form.reason, ...(form.effective_date ? { effective_date: form.effective_date } : {}),
      ...(kind === "transfer" ? { destination: form.destination } : {}) };
    if (await act.run(() => api.post(`/enrollments/${enrollment.id}/${kind}/`, body))) onDone();
  }
  return (
    <Modal title={kind === "transfer" ? "Transfer out" : "Withdraw student"} onClose={onClose}>
      <form onSubmit={submit} noValidate>
        <ActionFeedback act={act} />
        <Field label="Reason" error={act.error?.fields?.reason?.[0]}>
          {(a) => <input {...a} className="input" value={form.reason} onChange={set("reason")} required />}
        </Field>
        {kind === "transfer" && (
          <Field label="Destination institution" error={act.error?.fields?.destination?.[0]}>
            {(a) => <input {...a} className="input" value={form.destination} onChange={set("destination")} />}
          </Field>
        )}
        <Field label="Effective date" hint="Defaults to today." error={act.error?.fields?.effective_date?.[0]}>
          {(a) => <input {...a} className="input" type="date" value={form.effective_date} onChange={set("effective_date")} />}
        </Field>
        <div className="form-actions">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="danger" disabled={act.busy}>{act.busy ? "Saving…" : "Confirm"}</Button>
        </div>
      </form>
    </Modal>
  );
}

function SchoolPanel({ id }) {
  const placements = useApi("/schools/placements/", { student: id });
  const attendance = useApi("/schools/attendance/summary/", { student: id });
  const results = useApi("/schools/results/", { student: id });
  const a = attendance.data;
  return (
    <div className="grid grid--2">
      <Card title="Class history">
        <ul className="list">
          {(placements.data?.results || []).map((p) => (
            <li className="list__item" key={p.id}>
              <span className="list__dot" />
              <div>
                <div className="list__title">{p.section_label} · {p.year_name} <Badge>{p.status}</Badge></div>
                <div className="list__meta">{shortDate(p.start_date)} → {p.end_date ? shortDate(p.end_date) : "now"}</div>
              </div>
            </li>
          ))}
          {placements.data?.results?.length === 0 && <li className="list__item muted">Not placed in a class.</li>}
        </ul>
      </Card>
      <Card title="Attendance this term" subtitle={a?.term}>
        {a ? (
          <KeyValues items={[
            ["Attendance rate", a.attendance_rate !== null ? `${a.attendance_rate}%` : "—"],
            ["Present / late", `${a.present} / ${a.late}`],
            ["Absent (unexplained)", a.absent], ["Excused", a.excused],
          ]} />
        ) : <Spinner />}
      </Card>
      <Card title="Term results" className="span-2" bodyClass="">
        <table className="table">
          <thead><tr><th>Term</th><th>Class</th><th className="num">Average</th><th>Grade</th><th className="num">Position</th><th>Status</th><th /></tr></thead>
          <tbody>
            {(results.data?.results || []).map((r) => (
              <tr key={r.id}>
                <td>{r.term_name}</td><td>{r.section_label}</td><td className="num">{r.average}%</td><td>{r.grade}</td>
                <td className="num">{r.position} / {r.class_size}</td><td><Badge>{r.status}</Badge></td>
                <td className="num"><DownloadButton path={`/schools/results/${r.id}/report-card/`}>Report card</DownloadButton></td>
              </tr>
            ))}
            {results.data?.results?.length === 0 && <tr><td colSpan={7} className="muted">No finalized results yet.</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function UniversityPanel({ id }) {
  const standing = useApi("/universities/standings/", { student: id });
  const regs = useApi("/universities/registrations/", { student: id, current: 1 });
  const s = standing.data?.results?.[0];
  return (
    <div className="grid grid--2">
      <Card title="Academic standing" actions={<Link className="btn btn--secondary btn--sm" to={`/university/transcript?student=${id}`}>Transcript</Link>}>
        {s ? (
          <KeyValues items={[
            ["Program", s.program_name], ["Year of study", s.year_of_study], ["Adviser", s.adviser_name],
            ["CGPA", s.cgpa ?? "—"], ["Credits earned", s.credits_earned],
            ["Standing", <Badge key="s">{s.standing === "good" ? "Good standing" : "Probation"}</Badge>],
          ]} />
        ) : standing.loading ? <Spinner /> : <p className="muted">Not matriculated into a program.</p>}
      </Card>
      <Card title="This semester" bodyClass="">
        <table className="table">
          <thead><tr><th>Course</th><th className="num">Credits</th><th>Status</th></tr></thead>
          <tbody>
            {(regs.data?.results || []).map((r) => (
              <tr key={r.id}><td><strong>{r.course_code}</strong> {r.course_title}</td><td className="num">{r.credit_hours}</td><td><Badge>{r.status}</Badge></td></tr>
            ))}
            {regs.data?.results?.length === 0 && <tr><td colSpan={3} className="muted">No registrations.</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

export default function StudentDetail() {
  const { id } = useParams();
  const { user, mode } = useAuth();
  const isUni = mode === "university";
  const [tab, setTab] = useState("overview");
  const [modal, setModal] = useState(null);
  const student = useApi(`/students/${id}/`);
  const enrollments = useApi("/enrollments/", { student: id });
  const docs = useApi("/documents/", { student: id, page_size: 50 });
  const invoices = useApi("/fees/invoices/", { student: id });
  const currency = user.tenant?.currency;

  if (student.error) return <Alert tone="error">{student.error.message}</Alert>;
  if (!student.data) return <Spinner />;
  const s = student.data;
  const active = (enrollments.data?.results || []).find((e) => e.status === "active");
  const canManage = can(user, "students.manage");
  const canDocs = can(user, "documents.manage", "students.manage");

  return (
    <>
      <PageHeader
        eyebrow={<Link to={`/${mode}/students`}><LuArrowLeft aria-hidden="true" /> {isUni ? "Students" : "Pupils"}</Link>}
        title={`${s.first_name} ${s.last_name}`}
        description={`${s.student_no} · ${[s.level, s.section].filter(Boolean).join(" · ") || "—"}`}
        actions={<>
          <DownloadButton path={`/students/${id}/documents/id-card/`} icon={LuIdCard} size={undefined}>ID card</DownloadButton>
          <DownloadButton path={`/students/${id}/documents/enrollment-letter/`} icon={LuFileText} size={undefined}>Enrollment letter</DownloadButton>
          {isUni && <DownloadButton path={`/universities/transcripts/${id}/pdf/`} icon={LuScrollText} size={undefined}>Transcript</DownloadButton>}
        </>}
      />
      <Tabs value={tab} onChange={setTab} label="Student record" tabs={[
        { value: "overview", label: "Overview" },
        { value: "academic", label: isUni ? "Academics" : "Class & results" },
        { value: "documents", label: "Documents", count: docs.data?.count },
        { value: "fees", label: "Fees", count: invoices.data?.count },
      ]} />

      {tab === "overview" && (
        <div className="grid grid--2">
          <Card title="Profile" actions={canManage && (
            <Button size="sm" variant="secondary" icon={LuPencil} onClick={() => setModal("edit")}>Edit details</Button>)}>
            <div className="photo-row">
              <StudentAvatar student={s} />
              {canManage && <PhotoControls student={s} onChanged={student.reload} />}
            </div>
            <KeyValues items={[
              ["Status", <Badge key="st">{s.status}</Badge>], ["Date of birth", shortDate(s.date_of_birth)],
              ["Gender", titleCase(s.gender)], ["ID / certificate no.", s.national_id || "—"], ["Email", s.email], ["Phone", s.phone], ["Address", s.address],
              ["Admitted", shortDate(s.admission_date)], ["Portal account", s.has_portal_account ? "Yes" : "No"],
            ]} />
          </Card>
          <Contacts student={s} isUni={isUni} canManage={canManage} onChanged={student.reload} />
          <Card title="Enrollment history" className="span-2" bodyClass=""
            actions={canManage && active && (
              <div className="row-actions">
                <Button size="sm" variant="secondary" onClick={() => setModal("transfer")}>Transfer out</Button>
                <Button size="sm" variant="danger" onClick={() => setModal("withdraw")}>Withdraw</Button>
              </div>
            )}>
            <table className="table">
              <thead><tr><th>Period</th><th>{isUni ? "Program" : "Grade"}</th><th>{isUni ? "Year" : "Class"}</th><th>Status</th><th>From</th><th>To</th><th>Reason</th></tr></thead>
              <tbody>
                {(enrollments.data?.results || []).map((e) => (
                  <tr key={e.id}>
                    <td>{e.period_name || "—"}</td><td>{e.level_label}</td><td>{e.section_label || "—"}</td>
                    <td><Badge>{e.status}</Badge></td><td>{shortDate(e.start_date)}</td><td>{e.end_date ? shortDate(e.end_date) : "—"}</td>
                    <td className="muted">{e.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      )}

      {tab === "academic" && (isUni ? <UniversityPanel id={id} /> : <SchoolPanel id={id} />)}

      {tab === "documents" && (
        <Card title="Documents" bodyClass=""
          actions={canDocs && <Button size="sm" icon={LuUpload} onClick={() => setModal("upload")}>Upload</Button>}>
          {docs.data?.results?.length ? (
            <table className="table">
              <thead><tr><th>Title</th><th>Type</th><th>Source</th><th>Added</th><th /></tr></thead>
              <tbody>
                {docs.data.results.map((d) => (
                  <tr key={d.id}>
                    <td style={{ fontWeight: 600 }}>{d.title}</td><td>{titleCase(d.kind)}</td>
                    <td className="muted">{d.generated ? "Generated" : `Uploaded by ${d.uploaded_by || "—"}`}</td>
                    <td className="muted">{shortDate(d.created_at)}</td>
                    <td className="num"><DownloadButton path={d.download_url.replace(/^\/api/, "")} filename={d.original_name}>Open</DownloadButton></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <EmptyState title="No documents yet">Uploaded and generated documents appear here.</EmptyState>}
        </Card>
      )}

      {tab === "fees" && (
        <Card title="Invoices" bodyClass="" actions={<Link className="btn btn--secondary btn--sm" to={`/${mode}/fees`}>Fee ledger</Link>}>
          <table className="table">
            <thead><tr><th>Invoice</th><th>Due</th><th className="num">Total</th><th className="num">Paid</th><th className="num">Balance</th><th>Status</th></tr></thead>
            <tbody>
              {(invoices.data?.results || []).map((i) => (
                <tr key={i.id}>
                  <td className="mono">{i.number}</td><td>{shortDate(i.due_date)}</td><td className="num">{money(i.total, currency)}</td>
                  <td className="num">{money(i.amount_paid, currency)}</td><td className="num" style={{ fontWeight: 600 }}>{money(i.balance, currency)}</td>
                  <td><Badge>{i.is_overdue ? "overdue" : i.status}</Badge></td>
                </tr>
              ))}
              {invoices.data?.results?.length === 0 && <tr><td colSpan={6} className="muted">No invoices.</td></tr>}
            </tbody>
          </table>
        </Card>
      )}

      {modal === "edit" && <EditStudent student={s} onClose={() => setModal(null)} onDone={() => { setModal(null); student.reload(); }} />}
      {modal === "upload" && <UploadDocument studentId={id} onClose={() => setModal(null)} onDone={() => { setModal(null); docs.reload(); }} />}
      {(modal === "withdraw" || modal === "transfer") && active && (
        <EndEnrollment enrollment={active} kind={modal} onClose={() => setModal(null)}
          onDone={() => { setModal(null); enrollments.reload(); student.reload(); }} />
      )}
    </>
  );
}
