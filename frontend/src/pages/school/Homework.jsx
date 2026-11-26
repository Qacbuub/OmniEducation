import { useState } from "react";
import { Link } from "react-router-dom";
import { LuNotebookPen, LuPlus, LuTrash2 } from "react-icons/lu";
import { api } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { can } from "../../config/roles";
import { useAction, useApi } from "../../utils/hooks";
import { shortDate, titleCase } from "../../utils/format";
import { Alert, Badge, Button, Card, EmptyState, Field, Modal, PageHeader, Spinner } from "../../components/ui";
import { ActionFeedback, Tabs } from "../../components/ui/extra";
import { today } from "./common";
import { useClassSubjectTerm } from "./pickers";

const KINDS = [["homework", "Homework"], ["quiz", "Quiz"], ["test", "Class test"], ["project", "Project"], ["exam", "Exam"]];

function NewAssessment({ section, subject, term, onClose, onDone }) {
  const [f, setF] = useState({ name: "", kind: "homework", weight: 10, max_score: 20, due_date: "", description: "" });
  const act = useAction();
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  const err = (k) => act.error?.fields?.[k]?.[0];
  async function submit(e) {
    e.preventDefault();
    const body = { ...f, section: section.id, subject: subject.subject, term, due_date: f.due_date || null };
    if (await act.run(() => api.post("/schools/assessments/", body))) onDone();
  }
  return (
    <Modal title={`New assessment · ${section.label} ${subject.subject_name}`} onClose={onClose}>
      <form onSubmit={submit} noValidate>
        <ActionFeedback act={act} />
        <div className="form-grid">
          <Field label="Title" error={err("name")} className="span-2">{(a) => <input {...a} className="input" value={f.name} onChange={set("name")} placeholder="e.g. Fractions worksheet" />}</Field>
          <Field label="Type">{(a) => <select {...a} className="select" value={f.kind} onChange={set("kind")}>{KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>}</Field>
          <Field label="Due date" error={err("due_date")}>{(a) => <input {...a} className="input" type="date" value={f.due_date} onChange={set("due_date")} />}</Field>
          <Field label="Weight" error={err("weight")} hint="Share of the subject's term score. 0 = ungraded practice.">
            {(a) => <input {...a} className="input" type="number" min="0" max="100" value={f.weight} onChange={set("weight")} />}
          </Field>
          <Field label="Out of" error={err("max_score")}>{(a) => <input {...a} className="input" type="number" min="1" value={f.max_score} onChange={set("max_score")} />}</Field>
          <Field label="Instructions for pupils" className="span-2">{(a) => <textarea {...a} className="textarea" rows={3} value={f.description} onChange={set("description")} />}</Field>
        </div>
        <div className="form-actions">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={act.busy}>{act.busy ? "Saving…" : "Create & notify families"}</Button>
        </div>
      </form>
    </Modal>
  );
}

function TeacherView() {
  const { picker, section, subject, term, loading } = useClassSubjectTerm();
  const [creating, setCreating] = useState(false);
  const list = useApi(section && subject && term ? "/schools/assessments/" : null,
    { section: section?.id, subject: subject?.subject, term, page_size: 100, ordering: "due_date" });
  const act = useAction();
  const remove = async (a) => {
    if (window.confirm(`Delete "${a.name}" and any marks entered for it?`) &&
      await act.run(() => api.delete(`/schools/assessments/${a.id}/`), "Assessment deleted.") !== undefined) list.reload();
  };
  if (loading) return <Spinner />;
  if (!section) return <Alert tone="info">You don't teach any classes this year.</Alert>;
  const items = list.data?.results || [];
  const weight = items.reduce((s, a) => s + Number(a.weight), 0);
  return (
    <>
      {picker}
      <ActionFeedback act={act} />
      <Card title={`${section.label} · ${subject?.subject_name || ""}`}
        subtitle={`${items.length} assessments · graded weights total ${weight} (scores are scaled to 100%)`}
        actions={subject && <Button size="sm" icon={LuPlus} onClick={() => setCreating(true)}>New homework / test</Button>} bodyClass="">
        {items.length === 0 ? <EmptyState icon={LuNotebookPen} title="Nothing set yet for this term" /> : (
          <table className="table">
            <thead><tr><th>Title</th><th>Type</th><th>Due</th><th className="num">Weight</th><th className="num">Out of</th><th className="num">Marked</th><th /></tr></thead>
            <tbody>
              {items.map((a) => (
                <tr key={a.id}>
                  <td><strong>{a.name}</strong>{a.description && <div className="muted" style={{ fontSize: "var(--fs-xs)" }}>{a.description}</div>}</td>
                  <td><Badge tone="neutral">{titleCase(a.kind)}</Badge></td><td>{shortDate(a.due_date)}</td>
                  <td className="num">{Number(a.weight) ? a.weight : <span className="muted">ungraded</span>}</td><td className="num">{a.max_score}</td>
                  <td className="num">{a.marked}/{section.pupil_count}</td>
                  <td className="num"><div className="row-actions">
                    <Link className="btn btn--secondary btn--sm" to={`/school/marks?assessment=${a.id}`}>Enter marks</Link>
                    <Button size="sm" variant="ghost" icon={LuTrash2} aria-label={`Delete ${a.name}`} onClick={() => remove(a)} />
                  </div></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      {creating && <NewAssessment section={section} subject={subject} term={term} onClose={() => setCreating(false)}
        onDone={() => { setCreating(false); list.reload(); }} />}
    </>
  );
}

function FamilyView() {
  const { data, loading } = useApi("/schools/assessments/", { page_size: 100, ordering: "due_date" });
  const [tab, setTab] = useState("upcoming");
  const now = today();
  const all = data?.results || [];
  const items = all.filter((a) => (tab === "upcoming" ? (a.due_date || "") >= now : (a.due_date || "") < now));
  if (loading && !data) return <Spinner />;
  return (
    <>
      <Tabs value={tab} onChange={setTab} tabs={[{ value: "upcoming", label: "Upcoming" }, { value: "past", label: "Past" }]} />
      {items.length === 0 ? <Card><EmptyState icon={LuNotebookPen} title={tab === "upcoming" ? "Nothing due" : "Nothing yet"} /></Card> : (
        <Card bodyClass="">
          <table className="table">
            <thead><tr><th>Due</th><th>Class</th><th>Subject</th><th>Title</th><th>Type</th></tr></thead>
            <tbody>
              {(tab === "past" ? items.slice().reverse() : items).map((a) => (
                <tr key={a.id}>
                  <td className="mono">{shortDate(a.due_date)}</td><td>{a.section_label}</td><td>{a.subject_name}</td>
                  <td><strong>{a.name}</strong>{a.description && <div className="muted" style={{ fontSize: "var(--fs-xs)" }}>{a.description}</div>}</td>
                  <td><Badge tone="neutral">{titleCase(a.kind)}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}

export default function Homework() {
  const { user } = useAuth();
  const teacher = can(user, "school.marks.enter");
  return (
    <>
      <PageHeader title="Homework & assessments" description={teacher
        ? "Set homework, quizzes, tests, projects and exams. Families are notified when you set work."
        : "Homework, tests and exams set for your class."} />
      {teacher ? <TeacherView /> : <FamilyView />}
    </>
  );
}
