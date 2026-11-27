import { useState } from "react";
import { LuBookMarked, LuCalendarClock, LuCheck, LuGauge, LuGraduationCap, LuX } from "react-icons/lu";
import { api } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { can } from "../../config/roles";
import { useAction, useApi, useDebounced } from "../../utils/hooks";
import { shortDate, timeAgo } from "../../utils/format";
import { Alert, Badge, Button, Card, EmptyState, PageHeader, Spinner, StatCard } from "../../components/ui";
import { ActionFeedback, StudentPicker, Tabs } from "../../components/ui/extra";
import { meetingsText } from "./Offerings";

/** Registration workspace for one student (the signed-in student, or one chosen by an adviser/registrar). */
function StudentRegistration({ studentId, name }) {
  const params = studentId ? { student: studentId } : { student: "me" };
  const summary = useApi("/universities/registrations/summary/", params);
  const mine = useApi("/universities/registrations/", { ...(studentId ? { student: studentId } : {}), current: 1, page_size: 50 });
  const [search, setSearch] = useState("");
  const q = useDebounced(search);
  const offerings = useApi("/universities/offerings/", { current: 1, search: q, page_size: 100, status: "open" });
  const courses = useApi("/universities/courses/", { page_size: 100 });
  const act = useAction();
  const s = summary.data;
  const prereqs = Object.fromEntries((courses.data?.results || []).map((c) => [c.id, c.prerequisites.map((p) => p.code)]));
  const active = (mine.data?.results || []).filter((r) => r.status === "pending" || r.status === "approved");
  const taken = new Set(active.map((r) => r.course_code));
  const reload = () => { summary.reload(); mine.reload(); offerings.reload(); };
  const register = async (o) => {
    const body = { offering: o.id, ...(studentId ? { student: studentId } : {}) };
    if (await act.run(() => api.post("/universities/registrations/", body),
      (r) => `${o.course_code} ${r.status === "pending" ? "requested – waiting for adviser approval" : "registered"}.`)) reload();
  };
  const drop = async (r) => {
    if (window.confirm(`Drop ${r.course_code}?`) && await act.run(() => api.post(`/universities/registrations/${r.id}/drop/`, {}), `${r.course_code} dropped.`)) reload();
  };
  if (summary.error) return <Alert tone="error">{summary.error.message}</Alert>;
  if (!s) return <Spinner />;
  return (
    <>
      <div className="grid grid--stats" style={{ marginBottom: 16 }}>
        <StatCard icon={LuGauge} label="Credit load" value={`${s.credits} / ${s.max_credits}`}
          delta={s.below_minimum ? `Below the ${s.min_credits}-credit minimum` : "Within limits"} deltaDir={s.below_minimum ? "down" : "up"} />
        <StatCard icon={LuCalendarClock} label="Add/drop deadline" value={shortDate(s.semester.add_drop_end)}
          delta={s.window_open ? "Window open" : "Window closed"} deltaDir={s.window_open ? "up" : "down"} />
        <StatCard icon={LuGraduationCap} label="CGPA" value={s.cgpa ?? "—"} delta={s.standing === "probation" ? "Academic probation" : "Good standing"}
          deltaDir={s.standing === "probation" ? "down" : "up"} />
        <StatCard icon={LuBookMarked} label="Pending approval" value={s.pending} />
      </div>
      <ActionFeedback act={act} />
      <Card title={`${name ? `${name} · ` : ""}${s.semester.name} registrations`} bodyClass="">
        {active.length === 0 ? <EmptyState title="No courses yet">Pick sections from the list below.</EmptyState> : (
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Course</th><th className="num">Credits</th><th>Section</th><th>Lecturer</th><th>Status</th><th>Attempt</th><th /></tr></thead>
            <tbody>
              {active.map((r) => (
                <tr key={r.id}>
                  <td><strong className="mono">{r.course_code}</strong> {r.course_title}</td><td className="num">{r.credit_hours}</td><td>{r.section}</td>
                  <td>{r.lecturer_name || "—"}</td><td><Badge>{r.status}</Badge>{r.decision_notes && <div className="muted" style={{ fontSize: "var(--fs-xs)" }}>{r.decision_notes}</div>}</td>
                  <td>{r.attempt_no > 1 ? <Badge tone="warning">Repeat #{r.attempt_no}</Badge> : "1st"}</td>
                  <td className="num">{s.add_drop_open && <Button size="sm" variant="ghost" onClick={() => drop(r)} disabled={act.busy}>Drop</Button>}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </Card>
      <Card title="Open sections" subtitle="The server checks prerequisites, seats, timetable clashes, the credit limit and the add/drop window." bodyClass="">
        <div className="table-toolbar">
          <div className="topbar__search" style={{ maxWidth: 320 }}>
            <label className="sr-only" htmlFor="sec-search">Search sections</label>
            <input id="sec-search" className="input" type="search" placeholder="Search course code or title…" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
        </div>
        {!offerings.data ? <Spinner /> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Section</th><th>Course</th><th className="num">Credits</th><th>Prerequisites</th><th>Meetings</th><th className="num">Seats left</th><th /></tr></thead>
              <tbody>
                {offerings.data.results.map((o) => (
                  <tr key={o.id}>
                    <td className="mono" style={{ fontWeight: 600 }}>{o.course_code}-{o.section}</td><td>{o.course_title}<div className="muted" style={{ fontSize: "var(--fs-xs)" }}>{o.lecturer_name || ""}</div></td>
                    <td className="num">{o.credit_hours}</td>
                    <td>{(prereqs[o.course] || []).map((p) => <Badge key={p} tone="neutral">{p}</Badge>)}{!(prereqs[o.course] || []).length && <span className="muted">None</span>}</td>
                    <td className="muted" style={{ fontSize: "var(--fs-xs)" }}>{meetingsText(o)}</td>
                    <td className="num" style={{ color: o.seats_left === 0 ? "var(--danger)" : undefined, fontWeight: 600 }}>{o.seats_left === 0 ? "Full" : o.seats_left}</td>
                    <td className="num">{taken.has(o.course_code) ? <Badge tone="success">Registered</Badge>
                      : o.seats_left === 0 ? <span className="muted" title="No seats left in this section">Full</span>
                      : <Button size="sm" disabled={act.busy || !s.window_open} onClick={() => register(o)}>Register</Button>}</td>
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

function Approvals() {
  const { data, loading, reload } = useApi("/universities/registrations/", { status: "pending", current: 1, page_size: 100 });
  const [notes, setNotes] = useState({});
  const act = useAction();
  const decide = async (r, approve) => {
    if (await act.run(() => api.post(`/universities/registrations/${r.id}/${approve ? "approve" : "reject"}/`, { notes: notes[r.id] || "" }),
      `${r.student_name}: ${r.course_code} ${approve ? "approved" : "rejected"}.`)) reload();
  };
  if (loading && !data) return <Spinner />;
  const rows = data?.results || [];
  return (
    <>
      <ActionFeedback act={act} />
      <Card title={`Waiting for approval (${rows.length})`} subtitle="Advisers see their own advisees; the registrar sees everyone." bodyClass="">
        {rows.length === 0 ? <EmptyState title="Nothing waiting" /> : (
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Student</th><th>Course</th><th className="num">Credits</th><th>Requested</th><th>Note to student</th><th /></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td><strong>{r.student_name}</strong> <span className="muted mono">{r.student_no}</span></td>
                  <td><span className="mono">{r.course_code}-{r.section}</span> {r.course_title}</td><td className="num">{r.credit_hours}</td>
                  <td className="muted">{timeAgo(r.created_at)}</td>
                  <td><input aria-label={`Note for ${r.student_name}`} className="input" style={{ maxWidth: 220 }} value={notes[r.id] || ""}
                    onChange={(e) => setNotes((n) => ({ ...n, [r.id]: e.target.value }))} /></td>
                  <td className="num"><div className="row-actions">
                    <Button size="sm" icon={LuCheck} disabled={act.busy} onClick={() => decide(r, true)}>Approve</Button>
                    <Button size="sm" variant="secondary" icon={LuX} disabled={act.busy} onClick={() => decide(r, false)}>Reject</Button>
                  </div></td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </Card>
    </>
  );
}

function OnBehalf() {
  const [student, setStudent] = useState(null);
  return (
    <>
      <div className="toolbar"><StudentPicker label="Student" value={student?.id} onChange={setStudent} /></div>
      {student ? <StudentRegistration key={student.id} studentId={student.id} name={`${student.first_name} ${student.last_name}`} />
        : <Card><EmptyState title="Choose a student">Registrations you make for a student are approved immediately.</EmptyState></Card>}
    </>
  );
}

export default function Registration() {
  const { user } = useAuth();
  const staff = can(user, "uni.registration.approve");
  const [tab, setTab] = useState("approvals");
  return (
    <>
      <PageHeader title="Course registration" description={staff
        ? "Approve students' course requests, or register courses on a student's behalf."
        : "Add and drop courses for this semester. Requests go to your academic adviser for approval."} />
      {staff ? (
        <>
          <Tabs value={tab} onChange={setTab} tabs={[{ value: "approvals", label: "Approvals" }, { value: "student", label: "Register a student" }]} />
          {tab === "approvals" ? <Approvals /> : <OnBehalf />}
        </>
      ) : <StudentRegistration />}
    </>
  );
}
