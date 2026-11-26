import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";
import { useApi } from "../../utils/hooks";
import { money } from "../../utils/format";
import { Badge, Card, PageHeader, Spinner } from "../../components/ui";
import { DownloadButton, ProgressBar, SelectBox, Tabs } from "../../components/ui/extra";
import { BarChart, HBarList } from "../../components/ui/charts";

function ClassAttendanceRow({ c, term }) {
  const { data } = useApi("/schools/attendance/summary/", { section: c.id, term });
  return (
    <tr>
      <td><strong>{c.label}</strong></td><td>{c.homeroom_teacher_name || "—"}</td><td className="num">{c.pupil_count}</td>
      <td style={{ width: "40%" }}>{data ? (data.class_rate !== null ? <ProgressBar value={data.class_rate} label={`${c.label} attendance`} /> : "—") : "…"}</td>
      <td className="num">{data?.class_rate != null ? `${data.class_rate}%` : "—"}</td>
    </tr>
  );
}

function SchoolReports() {
  const classes = useApi("/schools/classes/", { current: 1, page_size: 100 });
  const terms = useApi("/academic-periods/", { kind: "term", page_size: 20 });
  const [term, setTerm] = useState("");
  const termList = (terms.data?.results || []).slice().sort((a, b) => a.start_date.localeCompare(b.start_date));
  const activeTerm = term || termList.find((t) => t.is_current)?.id || "";
  const results = useApi(activeTerm ? "/schools/results/" : null, { term: activeTerm, page_size: 100 });
  const { user } = useAuth();
  const passMark = 50;
  const bySection = {};
  (results.data?.results || []).forEach((r) => {
    bySection[r.section_label] ??= { n: 0, sum: 0, pass: 0 };
    bySection[r.section_label].n += 1;
    bySection[r.section_label].sum += Number(r.average);
    bySection[r.section_label].pass += Number(r.average) >= passMark ? 1 : 0;
  });
  return (
    <>
      <div className="toolbar">
        <SelectBox id="rep-term" label="Term" value={activeTerm} onChange={setTerm}
          options={termList.map((t) => ({ value: t.id, label: t.name }))} />
      </div>
      <div className="grid grid--2">
        <Card title="Attendance by class" subtitle="Daily registers for the selected term" bodyClass="" className="span-2">
          {classes.data ? (
            <table className="table">
              <thead><tr><th>Class</th><th>Class teacher</th><th className="num">Pupils</th><th>Attendance</th><th className="num">Rate</th></tr></thead>
              <tbody>{classes.data.results.map((c) => <ClassAttendanceRow key={c.id} c={c} term={activeTerm} />)}</tbody>
            </table>
          ) : <Spinner />}
        </Card>
        <Card title="Results by class" subtitle={`Finalized term results · pass mark ${passMark}%`}>
          {Object.keys(bySection).length ? (
            <BarChart title="Average score by class" format={(v) => `${v}%`} max={100}
              data={Object.entries(bySection).map(([label, s]) => ({ label, value: Math.round(s.sum / s.n) }))} />
          ) : <p className="muted">No finalized results for this term yet. <Link to="/school/report-cards">Report cards →</Link></p>}
        </Card>
        <Card title="Pass rate by class" bodyClass="">
          <table className="table">
            <thead><tr><th>Class</th><th className="num">Pupils</th><th className="num">Average</th><th className="num">Pass rate</th></tr></thead>
            <tbody>
              {Object.entries(bySection).map(([label, s]) => (
                <tr key={label}><td>{label}</td><td className="num">{s.n}</td><td className="num">{(s.sum / s.n).toFixed(1)}%</td>
                  <td className="num">{Math.round((100 * s.pass) / s.n)}%</td></tr>
              ))}
              {!Object.keys(bySection).length && <tr><td colSpan={4} className="muted">—</td></tr>}
            </tbody>
          </table>
        </Card>
      </div>
      <p className="muted" style={{ fontSize: "var(--fs-xs)" }}>{user.tenant.name} · figures update as registers and results are recorded.</p>
    </>
  );
}

function UniversityReports() {
  const dash = useApi("/universities/dashboard/");
  const probation = useApi("/universities/standings/", { standing: "probation", page_size: 100 });
  const d = dash.data;
  return d ? (
    <div className="grid grid--2">
      <Card title="Course demand" subtitle="Registered seats vs capacity, current semester"><HBarList data={d.course_demand} /></Card>
      <Card title="GPA distribution"><BarChart data={d.gpa_distribution} title="CGPA distribution" color="var(--black)" /></Card>
      <Card title="Credit completion by year" subtitle="Average share of program credits earned">
        <BarChart data={d.credit_completion} title="Credit completion" format={(v) => `${v}%`} max={100} />
      </Card>
      <Card title="Enrollment by program"><BarChart data={d.enrollment_by_program} title="Enrollment by program" /></Card>
      <Card title={`Students on academic probation (${probation.data?.count ?? "…"})`} bodyClass="" className="span-2">
        <table className="table">
          <thead><tr><th>Student</th><th>ID</th><th>Program</th><th className="num">Year</th><th className="num">CGPA</th><th>Adviser</th></tr></thead>
          <tbody>
            {(probation.data?.results || []).map((s) => (
              <tr key={s.id}>
                <td><Link to={`/university/students/${s.student}`}>{s.student_name}</Link></td><td className="mono">{s.student_no}</td>
                <td>{s.program_name}</td><td className="num">{s.year_of_study}</td>
                <td className="num"><Badge tone="danger">{s.cgpa}</Badge></td><td>{s.adviser_name || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  ) : <Spinner />;
}

function FinanceSummary() {
  const { data } = useApi("/fees/arrears/");
  if (!data) return <Spinner />;
  return (
    <Card title="Fee collection" subtitle="All issued invoices">
      <div className="grid grid--stats">
        {[["Billed", data.totals.billed], ["Collected", data.totals.collected], ["Outstanding", data.totals.outstanding],
          ["Collection rate", null]].map(([l, v]) => (
          <div key={l}><div className="stat__label">{l}</div><div className="stat__value" style={{ fontSize: "var(--fs-lg)" }}>
            {v !== null ? money(v, data.currency) : `${Math.round((100 * Number(data.totals.collected)) / Math.max(1, Number(data.totals.billed)))}%`}
          </div></div>
        ))}
      </div>
    </Card>
  );
}

export default function Reports() {
  const { mode, user } = useAuth();
  const perms = user.permissions || [];
  const academic = perms.includes("students.view") && perms.includes("reports.view") && !perms.includes("payments.record");
  const finance = perms.includes("fees.view");
  const [tab, setTab] = useState(academic ? "academic" : "finance");
  return (
    <>
      <PageHeader title="Reports" description="Institution-wide figures and exports."
        actions={<DownloadButton path="/students/export/" filename="students.csv" size={undefined}>Students CSV</DownloadButton>} />
      <Tabs value={tab} onChange={setTab} tabs={[academic && { value: "academic", label: "Academic" }, finance && { value: "finance", label: "Finance" }]} />
      {tab === "academic" && (mode === "university" ? <UniversityReports /> : <SchoolReports />)}
      {tab === "finance" && finance && <FinanceSummary />}
    </>
  );
}
