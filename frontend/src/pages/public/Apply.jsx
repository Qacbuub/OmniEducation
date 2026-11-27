import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  LuArrowLeft, LuCamera, LuCheck, LuFileUp, LuGraduationCap, LuMapPin, LuSchool, LuSearch, LuSend, LuX,
} from "react-icons/lu";
import { api } from "../../api/client";
import logo from "../../assets/omniteckno-logo.png";
import { Alert, Badge, Button, Card, EmptyState, Field, Spinner } from "../../components/ui";
import { ActionFeedback } from "../../components/ui/extra";
import { shortDate, titleCase } from "../../utils/format";
import { useAction, useApi } from "../../utils/hooks";

/* Public admission pages (no sign-in): choose an institution, apply, then follow the application with the
   private reference code: status, photo, supporting documents, and accepting a university offer. */

function PublicLayout({ children }) {
  return (
    <div className="public">
      <header className="public__bar">
        <Link to="/apply" className="public__brand"><img src={logo} alt="OmniTeckno" /><span>OmniEducation admissions</span></Link>
        <Link to="/login" className="public__signin">Staff and student sign in</Link>
      </header>
      <main className="public__main" id="main">{children}</main>
    </div>
  );
}

function InstitutionHeader({ inst, subtitle }) {
  const Icon = inst.type === "university" ? LuGraduationCap : LuSchool;
  return (
    <div className="public__inst" style={{ borderTopColor: inst.accent_color || "var(--brand)" }}>
      {inst.logo ? <img src={inst.logo} alt="" className="public__inst-logo" />
        : <div className="public__inst-logo public__inst-logo--icon" aria-hidden="true"><Icon /></div>}
      <div>
        <h1>{inst.name}</h1>
        <p className="muted">{subtitle}</p>
        {(inst.contact_email || inst.contact_phone) && (
          <p className="muted public__contact">Questions? {[inst.contact_email, inst.contact_phone].filter(Boolean).join(" · ")}</p>
        )}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- /apply */
export function ApplyIndex() {
  const list = useApi("/public/institutions/");
  const [ref, setRef] = useState({ slug: "", code: "" });
  const navigate = useNavigate();
  const items = list.data || [];
  return (
    <PublicLayout>
      <div className="public__intro">
        <h1>Apply online</h1>
        <p className="muted">Choose the school or university you want to apply to. You don't need an account.</p>
      </div>
      {list.loading ? <Spinner /> : list.error ? <Alert tone="error">{list.error.message}</Alert> : items.length === 0 ? (
        <EmptyState title="No institutions are accepting applications">Please check again later.</EmptyState>
      ) : (
        <ul className="public__grid">
          {items.map((i) => {
            const Icon = i.type === "university" ? LuGraduationCap : LuSchool;
            return (
              <li key={i.slug}>
                <Link to={`/apply/${i.slug}`} className="public__card">
                  <Icon aria-hidden="true" />
                  <strong>{i.name}</strong>
                  <span className="muted">{i.type === "university" ? "University" : "School (K-12)"}</span>
                  {(i.city || i.country) && <span className="muted"><LuMapPin aria-hidden="true" /> {[i.city, i.country].filter(Boolean).join(", ")}</span>}
                </Link>
              </li>
            );
          })}
        </ul>
      )}
      <Card title="Already applied?" subtitle="Check your status with the reference code you received.">
        <form className="public__lookup" onSubmit={(e) => { e.preventDefault(); if (ref.slug && ref.code.trim()) navigate(`/apply/${ref.slug}/status?ref=${encodeURIComponent(ref.code.trim())}`); }}>
          <Field label="Institution">
            {(a) => (
              <select {...a} className="select" value={ref.slug} onChange={(e) => setRef({ ...ref, slug: e.target.value })}>
                <option value="">Choose…</option>
                {items.map((i) => <option key={i.slug} value={i.slug}>{i.name}</option>)}
              </select>
            )}
          </Field>
          <Field label="Reference code">
            {(a) => <input {...a} className="input" value={ref.code} onChange={(e) => setRef({ ...ref, code: e.target.value })} placeholder="e.g. 3F9A1C27B0" autoComplete="off" />}
          </Field>
          <Button type="submit" icon={LuSearch} disabled={!ref.slug || !ref.code.trim()}>Check status</Button>
        </form>
      </Card>
    </PublicLayout>
  );
}

/* ---------------------------------------------------------------- /apply/:slug */
const EMPTY = {
  first_name: "", middle_name: "", last_name: "", date_of_birth: "", gender: "", national_id: "", email: "", phone: "",
  address: "", target_id: "", intake_period: "", previous_school: "",
  guardian_name: "", guardian_relationship: "", guardian_phone: "", guardian_email: "",
};
const REQUIRED = ["first_name", "last_name", "date_of_birth", "gender", "email", "phone", "address", "target_id",
  "guardian_name", "guardian_relationship", "guardian_phone"];
const RELATIONSHIPS = ["mother", "father", "guardian", "grandparent", "sibling", "spouse", "uncle", "aunt", "other"];

export function ApplyForm() {
  const { slug } = useParams();
  const info = useApi(`/public/${slug}/apply/`);
  const [f, setF] = useState(EMPTY);
  const [missing, setMissing] = useState({});
  const [done, setDone] = useState(null);
  const act = useAction();

  if (info.loading) return <PublicLayout><Spinner /></PublicLayout>;
  if (info.error || !info.data) {
    return (
      <PublicLayout>
        <EmptyState title="Institution not found" action={<Link to="/apply" className="btn btn--secondary">See all institutions</Link>}>
          This application page does not exist or is not open.
        </EmptyState>
      </PublicLayout>
    );
  }
  const inst = info.data;
  const isUni = inst.type === "university";
  const kin = isUni ? "Next of kin / emergency contact" : "Parent / guardian";

  if (done) {
    const statusUrl = `/apply/${slug}/status?ref=${done.reference_code}`;
    return (
      <PublicLayout>
        <InstitutionHeader inst={inst} subtitle="Application received" />
        <Card>
          <Alert tone="success">Thank you, {f.first_name}. Your application <strong>{done.application_no}</strong> was sent to {inst.name}.</Alert>
          <p>Your private reference code:</p>
          <p className="public__code" aria-label="Reference code">{done.reference_code}</p>
          <p className="muted">Write it down or keep this page. You need it to check your status, add your photo and documents
            {isUni ? ", and accept your offer" : ""}. {f.email && <>We also emailed it to <strong>{f.email}</strong>.</>}</p>
          <div className="form-actions" style={{ justifyContent: "flex-start" }}>
            <Link to={statusUrl} className="btn btn--primary"><LuFileUp aria-hidden="true" /> Add photo and documents</Link>
          </div>
        </Card>
      </PublicLayout>
    );
  }

  const set = (k) => (e) => { const v = e.target.value; setF((x) => ({ ...x, [k]: v })); setMissing((m) => ({ ...m, [k]: undefined })); };
  const err = (k) => missing[k] || act.error?.fields?.[k]?.[0];
  async function submit(e) {
    e.preventDefault();
    const gaps = Object.fromEntries(REQUIRED.filter((k) => !String(f[k]).trim()).map((k) => [k, "Required."]));
    setMissing(gaps);
    if (Object.keys(gaps).length) {
      document.getElementById("apply-gaps")?.focus();
      return;
    }
    const target = inst.options.find((o) => String(o.id) === String(f.target_id));
    const body = { ...f, requested_level: target?.name || "", target_id: f.target_id || null, intake_period: f.intake_period || null };
    const res = await act.run(() => api.post(`/public/${slug}/apply/`, body));
    if (res) { setDone(res); window.scrollTo(0, 0); }
  }
  const input = (k, label, { type = "text", className, placeholder, hint, autoComplete } = {}) => (
    <Field label={label} error={err(k)} required={REQUIRED.includes(k)} className={className} hint={hint}>
      {(a) => <input {...a} className="input" type={type} value={f[k]} onChange={set(k)} placeholder={placeholder} autoComplete={autoComplete} />}
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
    <PublicLayout>
      <p><Link to="/apply"><LuArrowLeft aria-hidden="true" /> All institutions</Link></p>
      <InstitutionHeader inst={inst} subtitle={isUni ? "Undergraduate application" : "Admission application"} />
      <Card>
        <form onSubmit={submit} noValidate>
          <ActionFeedback act={act} />
          {gapCount > 0 && <p id="apply-gaps" tabIndex={-1} className="field__error" role="alert">Fill in the {gapCount} required field{gapCount > 1 ? "s" : ""} marked below.</p>}
          <p className="muted" style={{ fontSize: "var(--fs-xs)", margin: "0 0 8px" }}>
            Fields marked * are required. You can add a photo and supporting documents after you submit.
          </p>

          <h2 className="form-section">{isUni ? "Applicant" : "Pupil"}</h2>
          <div className="form-grid">
            {input("first_name", "First name", { autoComplete: isUni ? "given-name" : "off" })}
            {input("middle_name", "Middle name")}
            {input("last_name", "Last name", { autoComplete: isUni ? "family-name" : "off" })}
            {input("date_of_birth", "Date of birth", { type: "date" })}
            {select("gender", "Gender", [["female", "Female"], ["male", "Male"], ["other", "Other"]])}
            {input("national_id", isUni ? "National ID / passport no." : "Birth certificate no.")}
          </div>

          <h2 className="form-section">Contact</h2>
          <div className="form-grid">
            {input("phone", "Phone number", { type: "tel", placeholder: "+255 712 345 678", autoComplete: "tel" })}
            {input("email", "Email", { type: "email", autoComplete: "email", hint: isUni ? "We send your reference code here." : "A parent's email is fine. We send the reference code here." })}
            {input("address", "Home address", { className: "span-2", autoComplete: "street-address" })}
          </div>

          <h2 className="form-section">{isUni ? "Programme" : "Admission"}</h2>
          <div className="form-grid">
            {select("target_id", isUni ? "Programme" : "Grade applied for", inst.options.map((o) => [o.id, o.code ? `${o.name} (${o.code})` : o.name]))}
            {select("intake_period", "Intake", inst.intakes.map((y) => [y.id, y.name]), "Next available")}
            {input("previous_school", isUni ? "Previous school / college" : "Previous school", { className: "span-2" })}
          </div>

          <h2 className="form-section">{kin}</h2>
          <div className="form-grid">
            {input("guardian_name", "Full name")}
            {select("guardian_relationship", "Relationship", RELATIONSHIPS.map((r) => [r, titleCase(r)]))}
            {input("guardian_phone", "Phone number", { type: "tel", placeholder: "+255 712 345 678" })}
            {input("guardian_email", "Email", { type: "email" })}
          </div>

          <div className="form-actions">
            <Button type="submit" icon={LuSend} disabled={act.busy}>{act.busy ? "Sending…" : "Submit application"}</Button>
          </div>
        </form>
      </Card>
    </PublicLayout>
  );
}

/* ---------------------------------------------------------------- /apply/:slug/status?ref=… */
const STATUS_TEXT = {
  submitted: "Received. The admissions office will review it soon.",
  under_review: "Under review by the admissions office.",
  approved: "Approved! The school will contact you about enrolment.",
  offered: "You have an offer of admission. Please accept or decline it below.",
  offer_accepted: "Offer accepted. The registrar will complete your matriculation.",
  offer_declined: "You declined the offer.",
  enrolled: "Enrolled. Welcome! You will receive sign-in details from the institution.",
  rejected: "Not successful this time. The institution may tell you more by email.",
  withdrawn: "This application was withdrawn.",
};
const DOC_KINDS = [["supporting", "Supporting document"], ["birth_certificate", "Birth certificate"],
  ["previous_results", "Previous results"], ["other", "Other"]];

export function ApplicationStatus() {
  const { slug } = useParams();
  const [params, setParams] = useSearchParams();
  const ref = params.get("ref") || "";
  const [code, setCode] = useState(ref);
  const [app, setApp] = useState(null);
  const [lookup, setLookup] = useState({ loading: Boolean(ref), error: null });
  const act = useAction();
  const [docKind, setDocKind] = useState("supporting");
  const [file, setFile] = useState(null);
  const [fileKey, setFileKey] = useState(0);
  const [confirming, setConfirming] = useState(null); // "accept" | "decline" while asking "are you sure?"

  useEffect(() => {
    if (!ref) { setApp(null); return; }
    setLookup({ loading: true, error: null });
    api.get(`/public/${slug}/applications/${encodeURIComponent(ref)}/`)
      .then((d) => { setApp(d); setLookup({ loading: false, error: null }); })
      .catch((error) => { setApp(null); setLookup({ loading: false, error }); });
  }, [slug, ref]);

  const base = `/public/${slug}/applications/${encodeURIComponent(ref)}/`;
  const isUni = app?.institution?.type === "university";
  const steps = isUni ? ["submitted", "under_review", "offered", "offer_accepted", "enrolled"]
    : ["submitted", "under_review", "approved", "enrolled"];
  const at = app ? steps.indexOf(app.status) : -1;

  async function uploadPhoto(e) {
    const photo = e.target.files[0];
    e.target.value = "";
    if (!photo) return;
    const form = new FormData();
    form.append("photo", photo);
    const res = await act.run(() => api.post(base + "photo/", form), "Photo added.");
    if (res) setApp(res);
  }
  async function uploadDoc(e) {
    e.preventDefault();
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    form.append("kind", docKind);
    form.append("title", file.name);
    const res = await act.run(() => api.post(base + "documents/", form), `${file.name} uploaded.`);
    if (res) { setApp((a) => ({ ...a, document_count: a.document_count + 1 })); setFile(null); setFileKey((k) => k + 1); }
  }
  async function respond(decision) {
    setConfirming(null);
    const res = await act.run(() => api.post(base + "respond/", { decision }),
      decision === "accept" ? "Offer accepted. Congratulations!" : "Offer declined.");
    if (res) setApp(res);
  }

  return (
    <PublicLayout>
      <p><Link to="/apply"><LuArrowLeft aria-hidden="true" /> All institutions</Link></p>
      {app && <InstitutionHeader inst={app.institution} subtitle="Application status" />}
      {!app && (
        <Card title="Check your application" subtitle="Enter the reference code you received when you applied.">
          <form className="public__lookup" onSubmit={(e) => { e.preventDefault(); if (code.trim()) setParams({ ref: code.trim() }); }}>
            <Field label="Reference code" error={lookup.error ? (lookup.error.status === 404 ? "No application matches this code." : lookup.error.message) : undefined}>
              {(a) => <input {...a} className="input" value={code} onChange={(e) => setCode(e.target.value)} autoComplete="off" />}
            </Field>
            <Button type="submit" icon={LuSearch} disabled={!code.trim() || lookup.loading}>{lookup.loading ? "Checking…" : "Check status"}</Button>
          </form>
        </Card>
      )}
      {app && (
        <div className="stack">
          <Card title={`${app.full_name} · ${app.application_no}`} subtitle={`${app.requested_level} · applied ${shortDate(app.submitted_at)}`}
            actions={<Badge tone={["rejected", "withdrawn", "offer_declined"].includes(app.status) ? "danger" : undefined}>{titleCase(app.status)}</Badge>}>
            <ActionFeedback act={act} />
            {at >= 0 && (
              <ol className="steps" aria-label="Application progress">
                {steps.map((s, i) => (
                  <li key={s} className={i < at ? "is-done" : i === at ? "is-current" : ""} aria-current={i === at ? "step" : undefined}>
                    {i < at && <LuCheck aria-hidden="true" />} {titleCase(s === "offer_accepted" ? "accepted" : s)}
                  </li>
                ))}
              </ol>
            )}
            <p>{STATUS_TEXT[app.status] || titleCase(app.status)}</p>
            {app.can_respond && !confirming && (
              <div className="form-actions" style={{ justifyContent: "flex-start" }}>
                <Button icon={LuCheck} onClick={() => setConfirming("accept")} disabled={act.busy}>Accept offer</Button>
                <Button variant="secondary" icon={LuX} onClick={() => setConfirming("decline")} disabled={act.busy}>Decline</Button>
              </div>
            )}
            {app.can_respond && confirming && (
              <div className="public__confirm" role="group" aria-label="Confirm your answer">
                <p><strong>{confirming === "accept"
                  ? `Accept the offer from ${app.institution.name} for ${app.requested_level}?`
                  : "Decline this offer? You cannot undo this online."}</strong></p>
                <div className="form-actions" style={{ justifyContent: "flex-start" }}>
                  <Button variant={confirming === "accept" ? "primary" : "danger"} onClick={() => respond(confirming)} disabled={act.busy}>
                    {act.busy ? "Sending…" : confirming === "accept" ? "Yes, accept" : "Yes, decline"}
                  </Button>
                  <Button variant="secondary" onClick={() => setConfirming(null)} disabled={act.busy}>Cancel</Button>
                </div>
              </div>
            )}
          </Card>

          {app.can_upload && (
            <Card title="Photo and documents" subtitle="You can add these until a decision is made.">
              <div className="photo-row">
                <div className="avatar-photo avatar-photo--empty" style={{ width: 64, height: 64, fontSize: 22 }} aria-hidden="true">
                  {app.has_photo ? <LuCheck /> : <LuCamera />}
                </div>
                <div className="public__photo-text">
                  <label className="btn btn--secondary btn--sm" style={{ cursor: "pointer", width: "fit-content" }}>
                    <LuCamera aria-hidden="true" /> {app.has_photo ? "Replace photo" : "Add passport photo"}
                    <input type="file" accept="image/jpeg,image/png" hidden onChange={uploadPhoto} />
                  </label>
                  <span className="muted" style={{ fontSize: "var(--fs-xs)" }}>
                    {app.has_photo ? "Photo received." : "JPG or PNG, up to 3 MB."}
                  </span>
                </div>
              </div>
              <form className="public__upload" onSubmit={uploadDoc}>
                <Field label="Document type">
                  {(a) => (
                    <select {...a} className="select" value={docKind} onChange={(e) => setDocKind(e.target.value)}>
                      {DOC_KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                    </select>
                  )}
                </Field>
                <Field label="File" hint="PDF, Word, JPG or PNG, up to 5 MB.">
                  {(a) => <input {...a} key={fileKey} type="file" className="input" accept=".pdf,.docx,.jpg,.jpeg,.png" onChange={(e) => setFile(e.target.files[0] || null)} />}
                </Field>
                <Button type="submit" icon={LuFileUp} disabled={!file || act.busy}>Upload</Button>
              </form>
              <p className="muted" style={{ fontSize: "var(--fs-xs)" }}>
                {app.document_count ? `${app.document_count} document${app.document_count > 1 ? "s" : ""} received.` : "No documents yet."}
              </p>
            </Card>
          )}
          <p className="muted" style={{ fontSize: "var(--fs-xs)" }}>
            Keep your reference code private: anyone with it can see this page. <Link to={`/apply/${slug}/status`} onClick={() => { setApp(null); setCode(""); }}>Check another code</Link>
          </p>
        </div>
      )}
    </PublicLayout>
  );
}
