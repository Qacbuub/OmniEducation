import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { LuLock, LuPlus, LuSave, LuSend, LuTrash2 } from "react-icons/lu";
import { api } from "../../api/client";
import { useAction, useApi } from "../../utils/hooks";
import { timeAgo, titleCase } from "../../utils/format";
import { Alert, Badge, Button, Card, EmptyState, Field, Modal, PageHeader, Spinner } from "../../components/ui";
import { ActionFeedback, SelectBox } from "../../components/ui/extra";

const KINDS = [["assignment", "Assignment"], ["quiz", "Quiz"], ["midterm", "Midterm"], ["project", "Project"], ["lab", "Lab"], ["exam", "Final exam"]];

function NewAssessment({ offering, used, onClose, onDone }) {
  const [f, setF] = useState({ name: "", kind: "assignment", weight: Math.max(0, 100 - used), max_score: 100, due_date: "" });
  const act = useAction();
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  async function submit(e) {
    e.preventDefault();
    if (await act.run(() => api.post("/universities/assessments/", { ...f, offering, due_date: f.due_date || null }))) onDone();
  }
  return (
    <Modal title="New assessment" onClose={onClose}>
      <form onSubmit={submit} noValidate>
        <ActionFeedback act={act} />
        <div className="form-grid">
          <Field label="Name" className="span-2" error={act.error?.fields?.name?.[0]}>{(a) => <input {...a} className="input" value={f.name} onChange={set("name")} />}</Field>
          <Field label="Type">{(a) => <select {...a} className="select" value={f.kind} onChange={set("kind")}>{KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>}</Field>
          <Field label="Due date">{(a) => <input {...a} className="input" type="date" value={f.due_date} onChange={set("due_date")} />}</Field>
          <Field label="Weight (%)" error={act.error?.fields?.weight?.[0]} hint={`${100 - used}% still unallocated. Weights must total exactly 100% to submit.`}>
            {(a) => <input {...a} className="input" type="number" min="1" max="100" value={f.weight} onChange={set("weight")} />}
          </Field>
          <Field label="Out of" error={act.error?.fields?.max_score?.[0]}>{(a) => <input {...a} className="input" type="number" min="1" value={f.max_score} onChange={set("max_score")} />}</Field>
        </div>
        <div className="form-actions"><Button variant="secondary" onClick={onClose}>Cancel</Button><Button type="submit" disabled={act.busy}>Add assessment</Button></div>
      </form>
    </Modal>
  );
}

/** Spreadsheet-style gradebook. `readOnly` is used by moderators on the approvals screen. */
export function GradebookGrid({ offeringId, readOnly = false, onChanged }) {
  const gb = useApi(`/universities/offerings/${offeringId}/gradebook/`);
  const [scores, setScores] = useState({});
  const [adding, setAdding] = useState(false);
  const act = useAction();
  useEffect(() => {
    if (!gb.data) return;
    const s = {};
    gb.data.rows.forEach((r) => Object.entries(r.scores).forEach(([a, v]) => { s[`${r.registration}:${a}`] = v; }));
    setScores(s);
  }, [gb.data]);
  if (gb.error) return <Alert tone="error">{gb.error.message}</Alert>;
  if (!gb.data) return <Spinner />;
  const d = gb.data;
  const editable = d.can_edit && !readOnly;
  const save = async () => {
    const rows = Object.entries(scores).filter(([, v]) => v !== "" && v !== null && v !== undefined)
      .map(([k, v]) => { const [registration, assessment] = k.split(":"); return { registration: Number(registration), assessment: Number(assessment), score: v }; });
    if (await act.run(() => api.post(`/universities/offerings/${offeringId}/scores/`, { scores: rows }), (r) => `Saved ${r.saved} score(s).`)) gb.reload();
  };
  const submit = async () => {
    if (!window.confirm("Submit final grades for moderation? Scores will lock until the grades are approved or returned.")) return;
    if (await act.run(() => api.post(`/universities/offerings/${offeringId}/submit-grades/`), (r) => `Submitted grades for ${r.submitted} students.`)) { gb.reload(); onChanged?.(); }
  };
  const removeAssessment = async (a) => {
    if (window.confirm(`Delete ${a.name} and its scores?`) && await act.run(() => api.delete(`/universities/assessments/${a.id}/`), "Assessment deleted.") !== undefined) gb.reload();
  };
  const weight = Number(d.weight_total);
  return (
    <>
      <ActionFeedback act={act} />
      <Card title={`${d.offering.course_code}-${d.offering.section} ${d.offering.course_title}`}
        subtitle={`${d.offering.semester_name} · ${d.rows.length} students · weights ${weight}% · grades: ${titleCase(d.state)}`}
        actions={editable && <div className="row-actions">
          <Button size="sm" variant="secondary" icon={LuPlus} onClick={() => setAdding(true)} disabled={weight >= 100}>Assessment</Button>
          <Button size="sm" variant="secondary" icon={LuSave} onClick={save} disabled={act.busy}>Save scores</Button>
          <Button size="sm" icon={LuSend} onClick={submit} disabled={act.busy || weight !== 100}>Submit grades</Button>
        </div>}
        bodyClass="">
        {!editable && !readOnly && (
          <div style={{ padding: "12px 20px 0" }}><Alert tone="info"><LuLock aria-hidden="true" /> Grades are {d.state}. Scores are locked{d.state === "submitted" ? " until a moderator approves or returns them" : ""}.</Alert></div>
        )}
        {d.assessments.length === 0 ? <EmptyState title="No assessments yet">Add assessments whose weights total 100%.</EmptyState> : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Student</th>
                  {d.assessments.map((a) => (
                    <th key={a.id} className="num">
                      {a.name}<div className="muted" style={{ fontWeight: 400, fontSize: "var(--fs-xs)" }}>{a.weight}% · /{a.max_score}
                        {editable && <button type="button" className="link-btn" style={{ marginLeft: 6 }} aria-label={`Delete ${a.name}`} onClick={() => removeAssessment(a)}><LuTrash2 /></button>}</div>
                    </th>
                  ))}
                  <th className="num">Total</th><th>Grade</th><th>Status</th>
                </tr>
              </thead>
              <tbody>
                {d.rows.map((r) => (
                  <tr key={r.registration}>
                    <td><strong>{r.name}</strong><div className="muted mono" style={{ fontSize: "var(--fs-xs)" }}>{r.student_no}</div></td>
                    {d.assessments.map((a) => {
                      const key = `${r.registration}:${a.id}`;
                      return (
                        <td key={a.id} className="num">
                          {editable ? (
                            <input aria-label={`${a.name} score for ${r.name}`} className="input score-input" type="number" min="0" max={a.max_score} step="0.5"
                              value={scores[key] ?? ""} onChange={(e) => setScores((s) => ({ ...s, [key]: e.target.value }))} />
                          ) : (r.scores[a.id] ?? <span className="muted">—</span>)}
                        </td>
                      );
                    })}
                    <td className="num"><strong>{r.total ?? "—"}</strong></td>
                    <td>{r.letter ? <Badge tone={r.letter === "F" ? "danger" : "neutral"}>{r.letter}</Badge> : "—"}</td>
                    <td><Badge>{titleCase(r.grade_status)}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {d.history.length > 0 && (
        <Card title="Moderation history" subtitle="Append-only">
          <ul className="list">
            {d.history.map((h) => (
              <li key={h.id} className="list__item"><span className="list__dot" />
                <div><div className="list__title">{titleCase(h.action)} by {h.actor_name || "—"}</div>
                  <div className="list__meta">{timeAgo(h.created_at)}{h.notes ? ` · ${h.notes}` : ""}</div></div></li>
            ))}
          </ul>
        </Card>
      )}
      {adding && <NewAssessment offering={offeringId} used={weight} onClose={() => setAdding(false)} onDone={() => { setAdding(false); gb.reload(); }} />}
    </>
  );
}

export default function Gradebook() {
  const mine = useApi("/universities/offerings/mine/");
  const [params] = useSearchParams(); // ?offering= when opened from the dashboard
  const [selected, setSelected] = useState(params.get("offering") || "");
  const list = (mine.data || []).filter((o) => o.status !== "cancelled");
  const current = list.filter((o) => o.grade_status !== "approved");
  const chosen = selected || current[0]?.id || list[0]?.id;
  return (
    <>
      <PageHeader title="Gradebook" description="Define weighted assessments, enter scores and submit final grades for moderation." />
      {mine.loading && !mine.data ? <Spinner /> : !list.length ? <Card><EmptyState title="You're not assigned to any sections" /></Card> : (
        <>
          <div className="toolbar">
            <SelectBox id="gb-section" label="Section" value={chosen} onChange={setSelected} width={360}
              options={list.map((o) => ({ value: o.id, label: `${o.course_code}-${o.section} ${o.course_title} · ${o.semester_name} (${titleCase(o.grade_status)})` }))} />
          </div>
          <GradebookGrid key={chosen} offeringId={chosen} onChanged={mine.reload} />
        </>
      )}
    </>
  );
}
