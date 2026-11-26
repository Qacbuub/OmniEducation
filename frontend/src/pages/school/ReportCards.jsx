import { useEffect, useState } from "react";
import { LuFileCheck, LuLockOpen, LuSend } from "react-icons/lu";
import { api } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { can } from "../../config/roles";
import { useAction, useApi } from "../../utils/hooks";
import { shortDate } from "../../utils/format";
import { Alert, Badge, Button, Card, EmptyState, PageHeader, Spinner } from "../../components/ui";
import { ActionFeedback, DownloadButton, SelectBox } from "../../components/ui/extra";
import { classOptions, termOptions, useMyClasses, useTerms } from "./common";

function RemarkInput({ result, field, label, onSaved }) {
  const [value, setValue] = useState(result[field] || "");
  const [state, setState] = useState("");
  useEffect(() => setValue(result[field] || ""), [result, field]);
  const save = async () => {
    if (value === (result[field] || "")) return;
    setState("saving");
    try { await api.patch(`/schools/results/${result.id}/`, { [field]: value }); setState("saved"); onSaved?.(); }
    catch (e) { setState(e.message); }
  };
  return (
    <div>
      <input aria-label={`${label} for ${result.student_name}`} className="input" value={value} onChange={(e) => setValue(e.target.value)} onBlur={save} />
      {state && <div className={state === "saved" || state === "saving" ? "field__hint" : "field__error"}>{state === "saving" ? "Saving…" : state === "saved" ? "Saved" : state}</div>}
    </div>
  );
}

function StaffView() {
  const { user } = useAuth();
  const { classes, loading } = useMyClasses();
  const { terms, current } = useTerms();
  const [section, setSection] = useState("");
  const [term, setTerm] = useState("");
  const sec = classes.find((c) => String(c.id) === String(section)) || classes[0];
  const termId = term || current?.id;
  const preview = useApi(sec && termId ? `/schools/classes/${sec.id}/results-preview/` : null, { term: termId });
  const results = useApi(sec && termId ? "/schools/results/" : null, { section: sec?.id, term: termId, page_size: 100 });
  const act = useAction();
  const principal = can(user, "school.results.publish");
  const homeroom = sec?.homeroom_teacher === user.id;
  const state = preview.data?.state;
  const reload = () => { preview.reload(); results.reload(); };
  const run = async (what, msg) => { if (await act.run(() => api.post(`/schools/results/${what}/`, { section: sec.id, term: termId }), msg)) reload(); };
  if (loading) return <Spinner />;
  if (!sec) return <Alert tone="info">You have no classes this year.</Alert>;
  const rows = (results.data?.results || []).slice().sort((a, b) => (a.position || 99) - (b.position || 99));
  return (
    <>
      <div className="toolbar">
        <SelectBox id="rc-class" label="Class" value={sec.id} onChange={setSection} options={classOptions(classes)} width={150} />
        <SelectBox id="rc-term" label="Term" value={termId || ""} onChange={setTerm} options={termOptions(terms)} width={170} />
      </div>
      <ActionFeedback act={act} />
      <Card title={`${sec.label} · ${preview.data?.term.name || ""}`}
        subtitle={state === "published" ? "Published: families can see these report cards."
          : state === "finalized" ? "Finalized: marks are locked. Add remarks, then publish."
            : state === "open" ? `Open: ${preview.data.missing_count} mark(s) still missing.` : "…"}
        actions={principal && state && (
          <div className="row-actions">
            {state === "open" && <Button size="sm" icon={LuFileCheck} disabled={act.busy || preview.data.missing_count > 0}
              onClick={() => run("finalize", "Results finalized. Marks are now locked.")}>Finalize results</Button>}
            {state === "finalized" && <>
              <Button size="sm" variant="secondary" icon={LuLockOpen} disabled={act.busy} onClick={() => run("reopen", "Results reopened for corrections.")}>Reopen</Button>
              <Button size="sm" icon={LuSend} disabled={act.busy} onClick={() => run("publish", "Report cards published. Guardians and pupils have been notified.")}>Publish report cards</Button>
            </>}
          </div>
        )}
        bodyClass="">
        {state === "open" && preview.data.missing_count > 0 && (
          <div style={{ padding: "12px 20px 0" }}>
            <Alert tone="info">
              Finalizing needs every mark. Missing: {preview.data.missing.slice(0, 4).join("; ")}{preview.data.missing_count > 4 ? ` and ${preview.data.missing_count - 4} more` : ""}.
            </Alert>
          </div>
        )}
        {state === "open" ? (
          <EmptyState title="Not finalized yet">Live averages are on the Marks entry page. Report cards are created when the principal finalizes the term.</EmptyState>
        ) : rows.length === 0 ? <Spinner /> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th className="num">Pos.</th><th>Pupil</th><th className="num">Average</th><th>Grade</th><th className="num">Days present/absent</th><th>Class teacher's remark</th><th>Principal's remark</th><th /></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td className="num">{r.position}</td><td><strong>{r.student_name}</strong></td>
                    <td className="num">{r.average}%</td><td><Badge tone={r.grade === "E" ? "danger" : "neutral"}>{r.grade}</Badge></td>
                    <td className="num">{r.days_present} / {r.days_absent}</td>
                    <td style={{ minWidth: 200 }}>{state === "finalized" && (homeroom || principal)
                      ? <RemarkInput result={r} field="teacher_remark" label="Class teacher's remark" /> : r.teacher_remark || "—"}</td>
                    <td style={{ minWidth: 200 }}>{state === "finalized" && principal
                      ? <RemarkInput result={r} field="principal_remark" label="Principal's remark" /> : r.principal_remark || "—"}</td>
                    <td className="num"><DownloadButton path={`/schools/results/${r.id}/report-card/`}>Report card</DownloadButton></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}

function FamilyView() {
  const { data, loading } = useApi("/schools/results/", { page_size: 100 });
  if (loading && !data) return <Spinner />;
  const rows = data?.results || [];
  if (!rows.length) return <Card><EmptyState title="No report cards published yet">You'll be notified when the school publishes them.</EmptyState></Card>;
  const byChild = {};
  rows.forEach((r) => { (byChild[r.student_name] ??= []).push(r); });
  return Object.entries(byChild).map(([name, list]) => (
    <Card key={name} title={name} bodyClass="">
      <table className="table">
        <thead><tr><th>Term</th><th>Class</th><th className="num">Average</th><th>Grade</th><th className="num">Position</th><th>Subjects</th><th>Published</th><th /></tr></thead>
        <tbody>
          {list.map((r) => (
            <tr key={r.id}>
              <td><strong>{r.term_name}</strong></td><td>{r.section_label}</td><td className="num">{r.average}%</td><td>{r.grade}</td>
              <td className="num">{r.position} of {r.class_size}</td>
              <td className="muted" style={{ fontSize: "var(--fs-xs)" }}>{r.subjects.map((s) => `${s.code} ${s.grade}`).join(" · ")}</td>
              <td className="muted">{shortDate(r.published_at)}</td>
              <td className="num"><DownloadButton path={`/schools/results/${r.id}/report-card/`}>Report card PDF</DownloadButton></td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  ));
}

export default function ReportCards() {
  const { user } = useAuth();
  const family = user.role === "guardian" || user.role === "pupil";
  return (
    <>
      <PageHeader title="Report cards" description={family ? "Published term report cards." :
        "Finalize a class's term results (marks lock), add remarks, then publish report cards to families."} />
      {family ? <div className="stack-sm"><FamilyView /></div> : <StaffView />}
    </>
  );
}
