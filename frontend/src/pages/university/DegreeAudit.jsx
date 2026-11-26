import { useState } from "react";
import { LuCircleCheck, LuCircleX } from "react-icons/lu";
import { api } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { can } from "../../config/roles";
import { useAction, useApi } from "../../utils/hooks";
import { money, timeAgo, titleCase } from "../../utils/format";
import { Alert, Badge, Button, Card, EmptyState, PageHeader, Spinner } from "../../components/ui";
import { ActionFeedback, ProgressBar, Tabs } from "../../components/ui/extra";
import { useRecordSubject } from "./Transcript";

function CourseTable({ rows }) {
  return (
    <table className="table">
      <thead><tr><th>Code</th><th>Course</th><th className="num">Credits</th><th>Year</th><th>Status</th><th>Grade</th></tr></thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.course_id}>
            <td className="mono">{r.code}</td><td>{r.title}</td><td className="num">{r.credits}</td><td>Y{r.year} S{r.semester}</td>
            <td><Badge tone={r.status === "completed" ? "success" : r.status === "in_progress" ? "brand" : "neutral"}>{titleCase(r.status)}</Badge></td>
            <td>{r.grade || "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Audit() {
  const { id, picker, self } = useRecordSubject();
  const audit = useApi(id ? `/universities/degree-audit/${id}/` : null);
  const act = useAction();
  const a = audit.data;
  const request = async () => {
    await act.run(() => api.post("/universities/clearances/", self ? {} : { student: a.student_id }),
      "Clearance requested. The registrar will check fees and approve.");
  };
  return (
    <>
      {picker}
      {!id ? <Card><EmptyState title="Choose a student" /></Card> : audit.error ? <Alert tone="error">{audit.error.message}</Alert> : !a ? <Spinner /> : (
        <>
          <ActionFeedback act={act} />
          <div className="grid grid--2">
            <Card title={`${a.name} · ${a.program}`} subtitle={`Curriculum ${a.curriculum || "—"} · ${a.student_no}`}
              actions={<Badge tone={a.eligible ? "success" : "warning"}>{a.eligible ? "Eligible to graduate" : "Not yet eligible"}</Badge>}>
              <div className="stack-sm">
                <div><div className="select-label">Credits {a.credits_earned} of {a.credits_required} ({a.progress_pct}%)</div>
                  <ProgressBar value={a.progress_pct} label="Degree progress" /></div>
                <div>
                  {a.checks.map((c) => (
                    <div className="check" key={c.key}>
                      {c.met ? <LuCircleCheck className="check__icon check__icon--ok" aria-label="Met" /> : <LuCircleX className="check__icon check__icon--no" aria-label="Not met" />}
                      <div><strong>{c.label}</strong><div className="muted">{c.detail}</div></div>
                    </div>
                  ))}
                </div>
                <Button disabled={!a.eligible || act.busy} onClick={request}>Request graduation clearance</Button>
              </div>
            </Card>
            <Card title="Electives" subtitle={`${a.elective_credits_earned} of ${a.elective_credits_required} elective credits (passed courses outside the curriculum count as free electives)`} bodyClass="">
              <CourseTable rows={a.electives} />
            </Card>
            <Card title="Core courses" className="span-2" bodyClass=""><CourseTable rows={a.core} /></Card>
          </div>
        </>
      )}
    </>
  );
}

function Clearances() {
  const { user } = useAuth();
  const { data, loading, reload } = useApi("/universities/clearances/", { page_size: 50 });
  const act = useAction();
  const decide = async (c, clear) => {
    const notes = clear ? "" : window.prompt("Reason for rejecting this clearance:") || "";
    if (!clear && !notes) return;
    if (await act.run(() => api.post(`/universities/clearances/${c.id}/${clear ? "clear" : "reject"}/`, { notes }),
      clear ? `${c.student_name} is cleared to graduate.` : "Clearance rejected.")) reload();
  };
  if (loading && !data) return <Spinner />;
  return (
    <>
      <ActionFeedback act={act} />
      <Card bodyClass="">
        {!data?.results?.length ? <EmptyState title="No clearance requests" /> : (
          <table className="table">
            <thead><tr><th>Student</th><th>Requested</th><th className="num">CGPA</th><th className="num">Credits</th><th className="num">Fee balance at request</th><th>Status</th><th /></tr></thead>
            <tbody>
              {data.results.map((c) => (
                <tr key={c.id}>
                  <td><strong>{c.student_name}</strong> <span className="muted mono">{c.student_no}</span></td><td className="muted">{timeAgo(c.created_at)}</td>
                  <td className="num">{c.audit_snapshot?.cgpa ?? "—"}</td><td className="num">{c.audit_snapshot?.credits_earned ?? "—"}</td>
                  <td className="num" style={{ color: Number(c.finance_balance) > 0 ? "var(--danger)" : undefined }}>{money(c.finance_balance, user.tenant?.currency)}</td>
                  <td><Badge>{c.status}</Badge>{c.notes && <div className="muted" style={{ fontSize: "var(--fs-xs)" }}>{c.notes}</div>}</td>
                  <td className="num">{c.status === "pending" && <div className="row-actions">
                    <Button size="sm" disabled={act.busy} onClick={() => decide(c, true)}>Clear</Button>
                    <Button size="sm" variant="secondary" disabled={act.busy} onClick={() => decide(c, false)}>Reject</Button></div>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      <p className="muted" style={{ fontSize: "var(--fs-sm)" }}>Clearing re-checks the degree audit and refuses students with outstanding fees. Cleared students are marked as graduated.</p>
    </>
  );
}

export default function DegreeAudit() {
  const { user } = useAuth();
  const registrar = can(user, "uni.clearance.manage");
  const [tab, setTab] = useState("audit");
  return (
    <>
      <PageHeader title="Degree audit" description="Progress against the program's curriculum, credits and minimum CGPA, and graduation clearance." />
      {registrar && <Tabs value={tab} onChange={setTab} tabs={[{ value: "audit", label: "Degree audit" }, { value: "clearance", label: "Graduation clearance" }]} />}
      {tab === "audit" ? <Audit /> : <Clearances />}
    </>
  );
}
