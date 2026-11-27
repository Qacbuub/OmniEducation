import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { LuGraduationCap, LuLayers, LuPencil, LuScrollText, LuTrendingUp } from "react-icons/lu";
import { api } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { can } from "../../config/roles";
import { useAction, useApi } from "../../utils/hooks";
import { titleCase } from "../../utils/format";
import { Alert, Badge, Button, Card, EmptyState, Field, Modal, PageHeader, Spinner, StatCard } from "../../components/ui";
import { ActionFeedback, DownloadButton, StudentPicker } from "../../components/ui/extra";

/** Resolve whose record to show: the signed-in student, a ?student= id, or a student picked by staff. */
export function useRecordSubject() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const self = user.role === "student";
  const id = self ? "me" : params.get("student");
  const picker = !self && (
    <div className="toolbar">
      <StudentPicker label="Student" value={id} onChange={(s) => setParams({ student: s.id })} />
    </div>
  );
  return { id, picker, self };
}

function Amend({ entry, gradeId, onClose, onDone }) {
  const [total, setTotal] = useState(entry.total_score);
  const [reason, setReason] = useState("");
  const act = useAction();
  async function submit(e) {
    e.preventDefault();
    if (await act.run(() => api.post(`/universities/grades/${gradeId}/amend/`, { total_score: total, reason }))) onDone();
  }
  return (
    <Modal title={`Amend ${entry.course_code} (${entry.semester_name})`} onClose={onClose}>
      <form onSubmit={submit} noValidate>
        <ActionFeedback act={act} />
        <p style={{ marginTop: 0 }}>Current: {entry.total_score}% · {entry.letter}. The original entry is kept and marked as superseded; the change is audited.</p>
        <Field label="Corrected total score (%)" error={act.error?.fields?.total_score?.[0]}>
          {(a) => <input {...a} className="input" type="number" min="0" max="100" step="0.01" value={total} onChange={(e) => setTotal(e.target.value)} />}
        </Field>
        <Field label="Reason (required)" error={act.error?.fields?.reason?.[0]}>
          {(a) => <input {...a} className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Re-mark after appeal" />}
        </Field>
        <div className="form-actions"><Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="danger" disabled={act.busy || !reason.trim()}>Record amendment</Button></div>
      </form>
    </Modal>
  );
}

export default function Transcript() {
  const { user } = useAuth();
  const { id, picker } = useRecordSubject();
  const t = useApi(id ? `/universities/transcripts/${id}/` : null);
  const registrar = can(user, "uni.transcripts.issue");
  const grades = useApi(registrar && t.data ? "/universities/grades/" : null, { registration__student: t.data?.student.id, status: "approved", page_size: 100 });
  const [amend, setAmend] = useState(null);
  const gradeByReg = Object.fromEntries((grades.data?.results || []).map((g) => [g.registration, g.id]));
  const d = t.data;
  return (
    <>
      <PageHeader title="Transcript" description="Approved grades by semester, semester GPA and cumulative GPA (weighted by credit hours)."
        actions={d && <DownloadButton path={`/universities/transcripts/${d.student.id}/pdf/`} icon={LuScrollText} variant="primary" size={undefined}>
          {registrar ? "Official transcript PDF" : "Unofficial transcript PDF"}</DownloadButton>} />
      {picker}
      {!id ? <Card><EmptyState title="Choose a student" /></Card> : t.error ? <Alert tone="error">{t.error.message}</Alert> : !d ? <Spinner /> : (
        <>
          <div className="grid grid--stats" style={{ marginBottom: 16 }}>
            <StatCard icon={LuGraduationCap} label={d.student.name} value={d.student.student_no} delta={d.student.program} />
            <StatCard icon={LuTrendingUp} label="Cumulative GPA" value={d.cgpa ?? "—"} delta={d.student.standing === "probation" ? "Academic probation" : "Good standing"}
              deltaDir={d.student.standing === "probation" ? "down" : "up"} />
            <StatCard icon={LuLayers} label="Credits earned" value={`${d.credits_earned}`} delta={`${d.credits_attempted} attempted`} />
            <StatCard icon={LuScrollText} label="Repeat policy" value={titleCase(d.repeat_policy).replace("Attempt", "attempt")} />
          </div>
          {d.semesters.length === 0 ? <Card><EmptyState title="No approved grades yet" /></Card> : d.semesters.map((s) => (
            <Card key={s.semester_id} title={s.semester} subtitle={`Semester GPA ${s.gpa ?? "—"} · ${s.credits} credits · CGPA to date ${s.cgpa_to_date ?? "—"}`} bodyClass="">
              <div className="table-wrap"><table className="table">
                <thead><tr><th>Code</th><th>Course</th><th className="num">Credits</th><th className="num">Score</th><th>Grade</th><th className="num">Points</th><th /></tr></thead>
                <tbody>
                  {s.entries.map((e) => (
                    <tr key={e.id}>
                      <td className="mono">{e.course_code}</td>
                      <td>{e.course_title}{!e.counts && <> <Badge tone="neutral">Not counted (repeated)</Badge></>}{e.attempt_no > 1 && <> <Badge tone="warning">Attempt {e.attempt_no}</Badge></>}
                        {e.reason && <div className="muted" style={{ fontSize: "var(--fs-xs)" }}>Amended: {e.reason}</div>}</td>
                      <td className="num">{e.credit_hours}</td><td className="num">{e.total_score}</td>
                      <td><Badge tone={e.letter === "F" ? "danger" : "neutral"}>{e.letter}</Badge></td><td className="num">{e.grade_points}</td>
                      <td className="num">{registrar && gradeByReg[e.registration] && (
                        <Button size="sm" variant="ghost" icon={LuPencil} onClick={() => setAmend({ entry: e, gradeId: gradeByReg[e.registration] })}>Amend</Button>)}</td>
                    </tr>
                  ))}
                </tbody>
              </table></div>
            </Card>
          ))}
        </>
      )}
      {amend && <Amend {...amend} onClose={() => setAmend(null)} onDone={() => { setAmend(null); t.reload(); grades.reload(); }} />}
    </>
  );
}
