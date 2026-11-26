import { Link } from "react-router-dom";
import { LuCalendarDays, LuClipboardCheck, LuNotebookPen, LuWallet } from "react-icons/lu";
import { useAuth } from "../../auth/AuthContext";
import { useApi } from "../../utils/hooks";
import { money, shortDate, titleCase } from "../../utils/format";
import { Badge, Card, EmptyState, PageHeader, Spinner } from "../../components/ui";
import { DownloadButton, KeyValues, ProgressBar } from "../../components/ui/extra";

/** Guardian portal (pupils see the same for themselves). Only linked children are ever returned by the API. */
export default function MyChildren() {
  const { user } = useAuth();
  const { data, loading } = useApi("/schools/children/");
  const currency = user.tenant?.currency;
  const pupil = user.role === "pupil";
  return (
    <>
      <PageHeader title={pupil ? "My school" : "My children"}
        description={pupil ? "Your class, attendance, homework and report cards." : "Class, attendance, homework, report cards and fees for each of your children."} />
      {loading && !data ? <Spinner /> : !data?.length ? <Card><EmptyState title="No linked children">Ask the school office to link your account.</EmptyState></Card> : (
        <div className="stack-sm">
          {data.map((c) => (
            <Card key={c.id} title={c.name} subtitle={`${c.class || c.level || "—"} · ${c.student_no}${c.class_teacher ? ` · Class teacher: ${c.class_teacher}` : ""}`}
              actions={<Badge>{c.status}</Badge>}>
              <div className="grid grid--2">
                <div className="stack-sm">
                  <h3 className="card__title" style={{ display: "flex", gap: 8, alignItems: "center" }}><LuClipboardCheck aria-hidden="true" /> Attendance this term</h3>
                  {c.attendance.attendance_rate != null ? <ProgressBar value={c.attendance.attendance_rate} label="Attendance rate" /> : null}
                  <KeyValues items={[["Attendance rate", c.attendance.attendance_rate != null ? `${c.attendance.attendance_rate}%` : "—"],
                    ["Absent / excused", `${c.attendance.absent} / ${c.attendance.excused}`], ["Late", c.attendance.late]]} />
                  {c.recent_absences.length > 0 && (
                    <ul className="list">
                      {c.recent_absences.map((a) => (
                        <li key={a.id} className="list__item"><span className="list__dot" style={{ background: "var(--danger)" }} />
                          <div><div className="list__title">{shortDate(a.date)} · {titleCase(a.status)}{a.lesson_subject ? ` (${a.lesson_subject})` : ""}</div>
                            {a.reason && <div className="list__meta">{a.reason}</div>}</div></li>
                      ))}
                    </ul>
                  )}
                </div>
                <div className="stack-sm">
                  <h3 className="card__title" style={{ display: "flex", gap: 8, alignItems: "center" }}><LuNotebookPen aria-hidden="true" /> Upcoming homework & tests</h3>
                  {c.homework.length === 0 ? <p className="muted" style={{ margin: 0 }}>Nothing due.</p> : (
                    <ul className="list">
                      {c.homework.map((h) => (
                        <li key={h.id} className="list__item"><span className="list__dot" />
                          <div><div className="list__title">{h.subject_name}: {h.name}</div>
                            <div className="list__meta">{titleCase(h.kind)} · due {shortDate(h.due_date)}</div></div></li>
                      ))}
                    </ul>
                  )}
                </div>
                <div className="stack-sm">
                  <h3 className="card__title">Report cards</h3>
                  {c.results.length === 0 ? <p className="muted" style={{ margin: 0 }}>None published yet.</p> : (
                    <table className="table">
                      <thead><tr><th>Term</th><th className="num">Average</th><th>Grade</th><th className="num">Position</th><th /></tr></thead>
                      <tbody>
                        {c.results.map((r) => (
                          <tr key={r.id}><td>{r.term}</td><td className="num">{r.average}%</td><td>{r.grade}</td><td className="num">{r.position}/{r.class_size}</td>
                            <td className="num"><DownloadButton path={`/schools/results/${r.id}/report-card/`}>PDF</DownloadButton></td></tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
                <div className="stack-sm">
                  <h3 className="card__title" style={{ display: "flex", gap: 8, alignItems: "center" }}><LuWallet aria-hidden="true" /> Fees</h3>
                  <p style={{ margin: 0 }}>Balance: <strong style={{ color: Number(c.fee_balance) > 0 ? "var(--danger)" : "var(--success)" }}>{money(c.fee_balance, currency)}</strong></p>
                  <div className="row-actions" style={{ justifyContent: "flex-start" }}>
                    <Link className="btn btn--secondary btn--sm" to="/school/fees">Invoices & payment</Link>
                    <Link className="btn btn--ghost btn--sm" to="/school/timetable"><LuCalendarDays aria-hidden="true" /> Timetable</Link>
                  </div>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
