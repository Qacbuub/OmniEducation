import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { LuCamera, LuPlus } from "react-icons/lu";
import { api } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { can } from "../../config/roles";
import { useAction, useApi, useDebounced } from "../../utils/hooks";
import { money, shortDate, timeAgo, titleCase } from "../../utils/format";
import { Badge, Button, Card, Field, Modal, PageHeader } from "../../components/ui";
import { DataTable } from "../../components/ui/DataTable";
import { ActionFeedback, CopyLink, KeyValues, SelectBox } from "../../components/ui/extra";
import { StudentAvatar } from "./StudentDetail";

const STATUSES = ["submitted", "under_review", "approved", "offered", "offer_accepted", "offer_declined", "enrolled",
  "rejected", "withdrawn"];
const ACTION_LABEL = {
  under_review: "Start review", approved: "Approve admission", offered: "Make offer", offer_accepted: "Record offer accepted",
  offer_declined: "Record offer declined", rejected: "Reject", withdrawn: "Mark withdrawn",
};
const NEGATIVE = ["rejected", "withdrawn", "offer_declined"];
const CONFIRM = {
  rejected: "Reject this application? The applicant is emailed.",
  withdrawn: "Mark this application as withdrawn? Only do this if the applicant has pulled out.",
  offer_declined: "Record that the applicant declined the offer? This ends the application.",
};

const EMPTY_APPLICANT = {
  first_name: "", middle_name: "", last_name: "", date_of_birth: "", gender: "", national_id: "", email: "", phone: "",
  address: "", target_id: "", intake_period: "", previous_school: "",
  guardian_name: "", guardian_relationship: "", guardian_phone: "", guardian_email: "",
};
// Fields the backend insists on; checked here first so the form can point at every gap at once.
const REQUIRED = ["first_name", "last_name", "date_of_birth", "gender", "email", "phone", "address", "target_id",
  "guardian_name", "guardian_relationship", "guardian_phone"];
const RELATIONSHIPS = ["mother", "father", "guardian", "grandparent", "sibling", "spouse", "uncle", "aunt", "other"];

function NewApplication({ mode, onClose, onDone }) {
  const isUni = mode === "university";
  const targets = useApi(isUni ? "/universities/programs/" : "/schools/grade-levels/", { page_size: 100 });
  const years = useApi("/academic-periods/", { kind: "academic_year", page_size: 20 });
  const [f, setF] = useState(EMPTY_APPLICANT);
  const [missing, setMissing] = useState({});
  const [photo, setPhoto] = useState(null);
  const [preview, setPreview] = useState(null);
  const act = useAction();
  const choosePhoto = (e) => {
    const file = e.target.files[0];
    if (preview) URL.revokeObjectURL(preview);
    setPhoto(file || null);
    setPreview(file ? URL.createObjectURL(file) : null);
  };
  const set = (k) => (e) => { const v = e.target.value; setF((x) => ({ ...x, [k]: v })); setMissing((m) => ({ ...m, [k]: undefined })); };
  const err = (k) => missing[k] || act.error?.fields?.[k]?.[0];
  const options = targets.data?.results || [];
  const kin = isUni ? "Next of kin / emergency contact" : "Parent / guardian";
  async function submit(e) {
    e.preventDefault();
    const gaps = Object.fromEntries(REQUIRED.filter((k) => !String(f[k]).trim()).map((k) => [k, "Required."]));
    setMissing(gaps);
    if (Object.keys(gaps).length) return;
    const target = options.find((o) => String(o.id) === String(f.target_id));
    const body = { ...f, requested_level: target?.name || "", target_id: f.target_id || null, intake_period: f.intake_period || null };
    const created = await act.run(async () => {
      const appRow = await api.post("/admissions/", body);
      if (photo) {
        const form = new FormData();
        form.append("photo", photo);
        try { await api.post(`/admissions/${appRow.id}/photo/`, form); }
        catch (err) { err.message = `The application was saved, but the photo was not: ${err.message}`; throw err; }
      }
      return appRow;
    });
    if (created) onDone();
  }
  const input = (k, label, { type = "text", required = REQUIRED.includes(k), className, placeholder, hint } = {}) => (
    <Field label={label} error={err(k)} required={required} className={className} hint={hint}>
      {(a) => <input {...a} className="input" type={type} value={f[k]} onChange={set(k)} placeholder={placeholder} />}
    </Field>
  );
  const select = (k, label, opts, placeholder = "Choose…") => (
    <Field label={label} error={err(k)} required={REQUIRED.includes(k)}>
      {(a) => (
        <select {...a} className="select" value={f[k]} onChange={set(k)}>
          <option value="">{placeholder}</option>
          {opts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      )}
    </Field>
  );
  const gapCount = Object.values(missing).filter(Boolean).length;
  return (
    <Modal title={isUni ? "New applicant" : "New admission application"} onClose={onClose}>
      <form onSubmit={submit} noValidate>
        <ActionFeedback act={act} />
        {gapCount > 0 && <p className="field__error" role="alert">Fill in the {gapCount} required field{gapCount > 1 ? "s" : ""} marked below.</p>}
        <p className="muted" style={{ fontSize: "var(--fs-xs)", margin: "0 0 8px" }}>Fields marked * are required.</p>

        <h3 className="form-section">{isUni ? "Student" : "Pupil"}</h3>
        <div className="photo-row">
          {preview ? <img className="avatar-photo" src={preview} alt="Selected photo" style={{ width: 84, height: 84 }} />
            : <div className="avatar-photo avatar-photo--empty" style={{ width: 84, height: 84, fontSize: 28 }} aria-hidden="true"><LuCamera /></div>}
          <div className="stack-sm">
            <label className="btn btn--secondary btn--sm" style={{ cursor: "pointer", width: "fit-content" }}>
              <LuCamera aria-hidden="true" /> {photo ? "Change photo" : "Add photo (optional)"}
              <input type="file" accept="image/jpeg,image/png" hidden onChange={choosePhoto} />
            </label>
            <span className="muted" style={{ fontSize: "var(--fs-xs)" }}>JPG or PNG, up to 3 MB. Passport-style works best.</span>
          </div>
        </div>
        <div className="form-grid">
          {input("first_name", "First name")}
          {input("middle_name", "Middle name")}
          {input("last_name", "Last name")}
          {input("date_of_birth", "Date of birth", { type: "date" })}
          {select("gender", "Gender", [["female", "Female"], ["male", "Male"], ["other", "Other"]])}
          {input("national_id", isUni ? "National ID / passport no." : "Birth certificate no.")}
        </div>

        <h3 className="form-section">Contact</h3>
        <div className="form-grid">
          {input("phone", "Phone number", { type: "tel", placeholder: "+255 712 345 678" })}
          {input("email", "Email", { type: "email", hint: isUni ? undefined : "A parent's email is fine for young pupils." })}
          {input("address", "Home address", { className: "span-2" })}
        </div>

        <h3 className="form-section">{isUni ? "Programme" : "Admission"}</h3>
        <div className="form-grid">
          {select("target_id", isUni ? "Programme" : "Grade applied for", options.map((o) => [o.id, o.name]))}
          {select("intake_period", "Intake year", (years.data?.results || []).filter((y) => y.kind === "academic_year").map((y) => [y.id, y.name]), "Current")}
          {input("previous_school", isUni ? "Previous school / college" : "Previous school", { className: "span-2" })}
        </div>

        <h3 className="form-section">{kin}</h3>
        <div className="form-grid">
          {input("guardian_name", "Full name")}
          {select("guardian_relationship", "Relationship", RELATIONSHIPS.map((r) => [r, titleCase(r)]))}
          {input("guardian_phone", "Phone number", { type: "tel", placeholder: "+255 712 345 678" })}
          {input("guardian_email", "Email", { type: "email" })}
        </div>

        <div className="form-actions">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={act.busy}>{act.busy ? "Saving…" : "Submit application"}</Button>
        </div>
      </form>
    </Modal>
  );
}

function Billing({ app, value, onChange }) {
  const opts = useApi(`/admissions/${app.id}/billing-options/`);
  const plans = opts.data?.plans || [];
  const currency = opts.data?.currency;
  const set = (patch) => onChange({ ...value, ...patch });
  const setItem = (i, k, v) => set({ items: value.items.map((it, j) => (j === i ? { ...it, [k]: v } : it)) });
  // Pre-select the plan written for this applicant's grade or programme.
  const best = plans.find((p) => p.matches && p.applies_to) || plans.find((p) => p.matches);
  const bestId = best?.id;
  useEffect(() => {
    if (value.mode === "plan" && !value.plan && bestId) onChange({ ...value, plan: String(bestId) });
  }, [bestId, value, onChange]);
  const chosen = plans.find((p) => String(p.id) === String(value.plan));
  const total = value.items.reduce((t, i) => t + (Number(i.amount) || 0), 0);
  return (
    <fieldset className="billing">
      <legend>First invoice</legend>
      <div className="bill-modes" role="radiogroup" aria-label="How to bill">
        {[["plan", "Bill a fee plan"], ...(opts.data?.can_bill_custom ? [["custom", "One-off amount"]] : []), ["none", "Don't bill now"]].map(([m, l]) => (
          <label key={m} className={`seg__opt ${value.mode === m ? "is-on" : ""}`}>
            <input type="radio" name="billing-mode" value={m} checked={value.mode === m} onChange={() => set({ mode: m })} /> {l}
          </label>
        ))}
      </div>
      {value.mode === "plan" && (
        plans.length === 0 ? <p className="muted">No active fee plans yet. Finance can create one under Fee ledger → Fee plans.</p> : <>
          <SelectBox id="bill-plan" label="Fee plan" value={value.plan || ""} onChange={(v) => set({ plan: v })} width={340}
            options={plans.map((p) => ({ value: p.id, label: `${p.name}${p.applies_to ? ` · ${p.applies_to}` : ""} · ${money(p.total, currency)}${p.matches ? "" : " (other grade)"}` }))} />
          {chosen && <p className="muted" style={{ fontSize: "var(--fs-xs)", margin: "4px 0 0" }}>
            {chosen.items.map((i) => `${i.description} ${money(i.amount, currency)}`).join(" · ")} = <strong>{money(chosen.total, currency)}</strong></p>}
        </>
      )}
      {value.mode === "custom" && (
        <div className="stack-sm">
          {value.items.map((it, i) => (
            <div key={i} className="row-actions" style={{ justifyContent: "flex-start" }}>
              <input className="input" style={{ flex: 2 }} aria-label={`Fee item ${i + 1}`} placeholder="Registration fee" value={it.description}
                onChange={(e) => setItem(i, "description", e.target.value)} />
              <input className="input" style={{ flex: 1, textAlign: "right" }} aria-label={`Amount ${i + 1}`} type="number" min="0" step="0.01"
                placeholder="0" value={it.amount} onChange={(e) => setItem(i, "amount", e.target.value)} />
              {value.items.length > 1 && <Button size="sm" variant="ghost" onClick={() => set({ items: value.items.filter((_, j) => j !== i) })}>Remove</Button>}
            </div>
          ))}
          <div className="row-actions" style={{ justifyContent: "space-between" }}>
            <Button size="sm" variant="secondary" onClick={() => set({ items: [...value.items, { description: "", amount: "" }] })}>Add item</Button>
            <span>Total <strong>{money(total, currency)}</strong></span>
          </div>
        </div>
      )}
      {value.mode !== "none" && (
        <Field label="Due date (optional)" hint="Default: the fee plan's payment terms, or 30 days.">
          {(a) => <input {...a} className="input" type="date" style={{ maxWidth: 200 }} value={value.due_date || ""} onChange={(e) => set({ due_date: e.target.value })} />}
        </Field>
      )}
    </fieldset>
  );
}

function EnrollForm({ app, mode, onDone }) {
  const isUni = mode === "university";
  const classes = useApi(isUni ? null : "/schools/classes/", { current: 1, page_size: 100 });
  const programs = useApi(isUni ? "/universities/programs/" : null, { page_size: 100 });
  const staff = useApi(isUni ? "/users/" : null, { role__code: "adviser", page_size: 100 });
  const [section, setSection] = useState("");
  const [program, setProgram] = useState(app.target_id || "");
  const [adviser, setAdviser] = useState("");
  const [billing, setBilling] = useState({ mode: "plan", plan: "", items: [{ description: "", amount: "" }], due_date: "" });
  const act = useAction();
  const classOptions = (classes.data?.results || [])
    .filter((c) => !app.requested_level || c.grade_name === app.requested_level)
    .map((c) => ({ value: c.id, label: `${c.label} (${c.pupil_count}/${c.capacity})` }));
  const go = async () => {
    const bill = billing.mode === "none" ? { mode: "none" }
      : billing.mode === "plan" ? { mode: "plan", plan: Number(billing.plan) || undefined, due_date: billing.due_date || null }
        : { mode: "custom", items: billing.items, due_date: billing.due_date || null };
    const body = { ...(isUni ? { program: program || undefined, adviser: adviser || undefined } : { section: section || undefined }), billing: bill };
    const r = await act.run(() => api.post(`/admissions/${app.id}/enroll/`, body),
      (x) => `Enrolled with number ${x.student_no}.${x.invoice ? ` Invoice ${x.invoice} issued.` : ""}`);
    if (r) onDone(r);
  };
  return (
    <div className="stack-sm" style={{ borderTop: "1px solid var(--border)", paddingTop: 12 }}>
      <ActionFeedback act={act} />
      <div className="toolbar" style={{ marginBottom: 0 }}>
        {isUni ? <>
          <SelectBox id="enroll-program" label="Program" value={program} onChange={setProgram} placeholder="Match application"
            options={(programs.data?.results || []).map((p) => ({ value: p.id, label: p.name }))} />
          <SelectBox id="enroll-adviser" label="Academic adviser" value={adviser} onChange={setAdviser} placeholder="None"
            options={(staff.data?.results || []).filter((u) => u.role === "adviser").map((u) => ({ value: u.id, label: `${u.first_name} ${u.last_name}` }))} />
        </> : (
          <SelectBox id="enroll-class" label="Class" value={section} onChange={setSection} placeholder="Least-full class automatically"
            options={classOptions} width={260} />
        )}
      </div>
      <Billing app={app} value={billing} onChange={setBilling} />
      {act.error?.fields?.items && <p className="field__error">{[].concat(act.error.fields.items).join(" ")}</p>}
      <div className="form-actions" style={{ marginTop: 0 }}>
        <Button onClick={go} disabled={act.busy}>{act.busy ? "Enrolling…" : isUni ? "Matriculate" : "Enroll pupil"}</Button>
      </div>
    </div>
  );
}

/** Applicant photo: shown in the review, uploadable until the applicant is enrolled. */
function ApplicantPhoto({ app, canEdit, onChanged }) {
  const input = useRef(null);
  const act = useAction();
  const pick = async (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    const body = new FormData();
    body.append("photo", file);
    const r = await act.run(() => api.post(`/admissions/${app.id}/photo/`, body), "Photo saved.");
    if (r) onChanged(r);
  };
  return (
    <div className="photo-row">
      <StudentAvatar student={app} size={84} />
      {canEdit && (
        <div className="stack-sm">
          <input ref={input} type="file" accept="image/jpeg,image/png" hidden onChange={pick} aria-label="Choose a photo" />
          <Button size="sm" variant="secondary" icon={LuCamera} disabled={act.busy} onClick={() => input.current?.click()}>
            {act.busy ? "Uploading…" : app.photo_url ? "Change photo" : "Add photo"}</Button>
          <span className="muted" style={{ fontSize: "var(--fs-xs)" }}>JPG or PNG, up to 3 MB. Becomes the student photo on enrolment.</span>
          <ActionFeedback act={act} />
        </div>
      )}
    </div>
  );
}

function ApplicationDetail({ app: initial, mode, canDecide, onClose, onChanged }) {
  const isUni = mode === "university";
  const [app, setApp] = useState(initial);
  const [notes, setNotes] = useState("");
  const act = useAction();
  // Applicants can answer offers and add documents online while this window is open, so keep it fresh.
  const changedRef = useRef(onChanged);
  changedRef.current = onChanged;
  const statusRef = useRef(initial.status);
  const reload = async () => {
    try {
      const fresh = await api.get(`/admissions/${initial.id}/`);
      setApp(fresh);
      if (fresh.status !== statusRef.current) { statusRef.current = fresh.status; changedRef.current(); }
    } catch { /* keep showing what we have */ }
  };
  useEffect(() => {
    const timer = setInterval(() => { if (document.visibilityState === "visible") reload(); }, 15000);
    return () => clearInterval(timer);
  }, [initial.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const decide = async (status) => {
    // Leaving the workflow is easy to click by mistake, so ask first.
    if (CONFIRM[status] && !window.confirm(CONFIRM[status])) return;
    const r = await act.run(() => api.post(`/admissions/${app.id}/decide/`, { status, notes }), `Status changed to ${titleCase(status)}.`);
    if (r) { setApp(r); statusRef.current = r.status; setNotes(""); onChanged(); } else reload();
  };
  const canEnroll = canDecide && (app.status === "approved" || app.status === "offer_accepted");
  const moves = canDecide ? app.allowed_transitions.filter((s) => s !== "enrolled") : [];
  const forward = moves.filter((s) => !NEGATIVE.includes(s));
  const backward = moves.filter((s) => NEGATIVE.includes(s));
  const steps = isUni ? ["submitted", "under_review", "offered", "offer_accepted", "enrolled"]
    : ["submitted", "under_review", "approved", "enrolled"];
  const at = steps.indexOf(app.status);
  const stepLabel = { submitted: "Submitted", under_review: "Under review", offered: "Offer made", approved: "Approved",
    offer_accepted: "Offer accepted", enrolled: isUni ? "Matriculated" : "Enrolled" };
  const hint = {
    submitted: "Next: start the review.",
    under_review: isUni ? "Next: make an offer (this is the approval step)." : "Next: approve the admission.",
    offered: "Next: record the applicant's answer to the offer.",
    offer_accepted: "Last step: matriculate to create the student record.",
    approved: "Last step: enroll the pupil to create the record and place them in a class.",
    withdrawn: "This application was withdrawn. Reopen it to continue, or leave it closed.",
    rejected: "This application was rejected and is closed.",
    offer_declined: "The applicant declined the offer. The application is closed.",
  }[app.status];
  return (
    <Modal title={`${app.full_name} · ${app.application_no}`} onClose={onClose}>
      <ActionFeedback act={act} />
      <ol className="steps" aria-label="Application progress">
        {steps.map((s, i) => (
          <li key={s} className={at === -1 ? "" : i < at ? "is-done" : i === at ? "is-current" : ""}>{stepLabel[s]}</li>
        ))}
      </ol>
      {hint && <p className="muted" style={{ margin: "8px 0 12px" }}>{hint}</p>}
      <ApplicantPhoto app={app} canEdit={canDecide && app.status !== "enrolled"} onChanged={(r) => { setApp(r); onChanged(); }} />
      <KeyValues items={[
        ["Status", <Badge key="s">{titleCase(app.status)}</Badge>], ["Applying for", app.requested_level],
        ["Date of birth", shortDate(app.date_of_birth)], ["Gender", titleCase(app.gender) || "—"],
        ["ID / certificate no.", app.national_id || "—"], ["Email", app.email], ["Phone", app.phone || "—"],
        ["Address", app.address || "—"], ["Previous school", app.previous_school], ["Source", titleCase(app.source)],
        app.guardian_name && [isUni ? "Next of kin" : "Guardian",
          `${app.guardian_name} (${app.guardian_relationship || "—"}) · ${app.guardian_phone}${app.guardian_email ? ` · ${app.guardian_email}` : ""}`],
        ["Submitted", timeAgo(app.submitted_at)], ["Supporting documents", app.document_count],
        ["Reference code", <span key="r" className="mono">{app.reference_code}</span>],
        app.decision_notes && ["Decision notes", app.decision_notes],
      ]} />
      {app.student_id && (
        <p style={{ marginTop: 12 }}><Link to={`/${mode}/students/${app.student_id}`}>Open the student record →</Link></p>
      )}
      {canEnroll && <EnrollForm app={app} mode={mode} onDone={(r) => { setApp({ ...app, status: "enrolled", student_id: r.student_id }); onChanged(); }} />}
      {moves.length > 0 && (
        <div className="stack-sm" style={{ marginTop: 16, borderTop: "1px solid var(--border)", paddingTop: 12 }}>
          {forward.length > 0 && (
            <Field label="Notes (optional, sent with offers, approvals and rejections)">
              {(a) => <input {...a} className="input" value={notes} onChange={(e) => setNotes(e.target.value)} />}
            </Field>
          )}
          <div className="row-actions" style={{ justifyContent: "space-between" }}>
            <span className="row-actions">
              {forward.map((s) => (
                <Button key={s} size="sm" disabled={act.busy} onClick={() => decide(s)}>
                  {app.status === "withdrawn" && s === "under_review" ? "Reopen application" : ACTION_LABEL[s] || titleCase(s)}
                </Button>
              ))}
            </span>
            <span className="row-actions">
              {backward.map((s) => (
                <Button key={s} size="sm" variant="ghost" disabled={act.busy} onClick={() => decide(s)}>{ACTION_LABEL[s] || titleCase(s)}</Button>
              ))}
            </span>
          </div>
        </div>
      )}
    </Modal>
  );
}

export default function Admissions() {
  const { user, mode } = useAuth();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(null);
  const q = useDebounced(search);
  const { data, loading, error, reload } = useApi("/admissions/", { search: q, status, page });
  const canDecide = can(user, "admissions.manage");
  const statuses = STATUSES.filter((s) => (mode === "university" ? s !== "approved" : !s.startsWith("offer")));
  const columns = [
    { key: "application_no", header: "Application", render: (a) => (
      <button type="button" className="link-btn" onClick={() => setOpen(a)}><span className="mono">{a.application_no}</span></button>) },
    { key: "full_name", header: "Applicant", render: (a) => <strong>{a.full_name}</strong> },
    { key: "requested_level", header: mode === "university" ? "Program" : "Grade" },
    { key: "source", header: "Source", render: (a) => titleCase(a.source) },
    { key: "submitted_at", header: "Submitted", render: (a) => <span className="muted">{timeAgo(a.submitted_at)}</span> },
    { key: "status", header: "Status", render: (a) => <Badge>{titleCase(a.status)}</Badge> },
    { key: "open", header: "", className: "num", render: (a) => <Button size="sm" variant="secondary" onClick={() => setOpen(a)}>Review</Button> },
  ];
  return (
    <>
      <PageHeader title="Admissions" description={mode === "university"
        ? "Applicant → offer → acceptance → matriculation." : "Applicant → review → approved admission → enrolled pupil placed in a class."}
        actions={canDecide && <Button icon={LuPlus} onClick={() => setParams({ new: "1" })}>New application</Button>} />
      <Card bodyClass="">
        <DataTable caption="Applications" columns={columns} data={data} loading={loading} error={error}
          search={search} onSearch={(v) => { setSearch(v); setPage(1); }} searchPlaceholder="Search applicants…"
          filters={<SelectBox id="app-status" label="Status" hideLabel value={status} onChange={(v) => { setStatus(v); setPage(1); }}
            placeholder="All statuses" options={statuses.map((s) => ({ value: s, label: titleCase(s) }))} />}
          page={page} onPage={setPage} />
      </Card>
      <p className="muted" style={{ fontSize: "var(--fs-sm)" }}>
        Applicants can also apply online on your public page{" "}
        <a href={`/apply/${user.tenant.slug}`} target="_blank" rel="noreferrer" className="mono">/apply/{user.tenant.slug}</a>{" "}
        (<CopyLink href={`${window.location.origin}/apply/${user.tenant.slug}`} label="copy link" />) and follow their
        application there with their reference code.
      </p>
      {params.get("new") === "1" && <NewApplication mode={mode} onClose={() => setParams({})} onDone={() => { setParams({}); reload(); }} />}
      {open && <ApplicationDetail app={open} mode={mode} canDecide={canDecide} onClose={() => setOpen(null)} onChanged={reload} />}
    </>
  );
}
