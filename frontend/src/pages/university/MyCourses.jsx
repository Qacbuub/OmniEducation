import { Link } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";
import { useApi } from "../../utils/hooks";
import { shortDate, titleCase } from "../../utils/format";
import { Alert, Badge, Card, EmptyState, PageHeader, Spinner } from "../../components/ui";
import { ProgressBar } from "../../components/ui/extra";

const GRADE_STATUS = {
  in_progress: ["In progress", undefined], draft: ["Being marked", undefined], submitted: ["Submitted for approval", "warning"],
  returned: ["Under review", "warning"], approved: ["Final", "success"],
};

/** A student's courses this semester: every assessment, their mark and the running total. */
export default function MyCourses() {
  const { mode } = useAuth();
  const { data, loading, error } = useApi("/universities/registrations/coursework/", { student: "me" });
  if (error) return <Alert tone="error">{error.message}</Alert>;
  const courses = data?.courses || [];
  return (
    <>
      <PageHeader title="My courses & marks" description={`${data?.semester?.name || "This semester"}: your marks as lecturers enter them. Letter grades appear once the department approves them; then they go on your transcript.`} />
      {loading && !data ? <Spinner /> : courses.length === 0 ? (
        <Card><EmptyState title="You have no courses this semester">Add courses under <Link to={`/${mode}/registration`}>Course registration</Link>.</EmptyState></Card>
      ) : (
        <div className="grid grid--2">
          {courses.map((c) => {
            const [label, tone] = GRADE_STATUS[c.grade_status] || [titleCase(c.grade_status), undefined];
            return (
              <Card key={c.registration} bodyClass=""
                title={<>{c.course_code} · {c.course_title}</>}
                subtitle={`${c.credit_hours} credits · section ${c.section} · ${c.lecturer || "lecturer to be announced"}${
                  c.attendance?.rate != null ? ` · attendance ${c.attendance.rate}% (${c.attendance.absences} absent of ${c.attendance.sessions} classes)` : ""}`}
                actions={c.status === "pending" ? <Badge tone="warning">Awaiting adviser approval</Badge>
                  : c.letter ? <Badge tone="success">Grade {c.letter} · {c.grade_points} pts</Badge> : <Badge tone={tone}>{label}</Badge>}>
                <div style={{ padding: "0 16px 12px" }}>
                  <ProgressBar value={Number(c.earned) || 0}
                    label={c.percent_so_far != null
                      ? `${c.earned} of ${c.weight_marked} marks so far (${c.percent_so_far}%) · ${c.weight_total}% of the course is assessed`
                      : "No marks entered yet"} />
                </div>
                {c.assessments.length === 0 ? <p className="muted" style={{ padding: "0 16px 16px" }}>Your lecturer hasn't set up assessments yet.</p> : (
                  <div className="table-wrap"><table className="table">
                    <thead><tr><th>Assessment</th><th className="num">Weight</th><th>Due</th><th className="num">Score</th></tr></thead>
                    <tbody>
                      {c.assessments.map((a) => (
                        <tr key={a.id}>
                          <td>{a.name} <span className="muted">· {titleCase(a.kind)}</span></td>
                          <td className="num">{Number(a.weight)}%</td>
                          <td>{a.due_date ? shortDate(a.due_date) : "—"}</td>
                          <td className="num">{a.score != null ? <strong>{Number(a.score)} / {Number(a.max_score)}</strong> : <span className="muted">—</span>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table></div>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </>
  );
}
