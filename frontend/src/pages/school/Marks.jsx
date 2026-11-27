import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { LuLock, LuPlus, LuSave } from "react-icons/lu";
import { api } from "../../api/client";
import { useAction, useApi } from "../../utils/hooks";
import { shortDate, titleCase } from "../../utils/format";
import { Alert, Button, Card, EmptyState, PageHeader, Spinner } from "../../components/ui";
import { ActionFeedback, SelectBox, Tabs } from "../../components/ui/extra";
import { NewAssessment } from "./Homework";
import { useClassSubjectTerm } from "./pickers";

function MarkSheet({ assessmentId, onSaved }) {
  const sheet = useApi(`/schools/assessments/${assessmentId}/marks/`);
  const [rows, setRows] = useState([]);
  const act = useAction();
  useEffect(() => { if (sheet.data) setRows(sheet.data.rows.map((r) => ({ ...r, score: r.score ?? "" }))); }, [sheet.data]);
  if (!sheet.data) return <Spinner />;
  const a = sheet.data.assessment;
  const locked = sheet.data.locked;
  const set = (i, k, v) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  const save = async () => {
    const marks = rows.filter((r) => r.score !== "" && r.score !== null).map((r) => ({ student: r.student, score: r.score, remarks: r.remarks || "" }));
    if (await act.run(() => api.post(`/schools/assessments/${a.id}/marks/`, { marks }), (x) => `Saved ${x.saved} mark(s).`)) { sheet.reload(); onSaved?.(); }
  };
  const filled = rows.filter((r) => r.score !== "").length;
  return (
    <Card title={`${a.name} · ${a.section_label} ${a.subject_name}`}
      subtitle={`${titleCase(a.kind)} · out of ${a.max_score} · weight ${a.weight} · due ${shortDate(a.due_date)} · ${filled}/${rows.length} marked`}
      actions={!locked && <Button size="sm" icon={LuSave} disabled={act.busy} onClick={save}>{act.busy ? "Saving…" : "Save marks"}</Button>}
      bodyClass="">
      <div style={{ padding: "0 20px" }}><ActionFeedback act={act} /></div>
      {locked && <div style={{ padding: "12px 20px 0" }}><Alert tone="info"><LuLock aria-hidden="true" /> This term's results are finalized, so marks are locked.</Alert></div>}
      <div className="table-wrap"><table className="table">
        <thead><tr><th>Pupil</th><th className="num">Score / {a.max_score}</th><th className="num">%</th><th>Remark</th></tr></thead>
        <tbody>
          {rows.map((r, i) => {
            const over = r.score !== "" && (Number(r.score) > Number(a.max_score) || Number(r.score) < 0);
            return (
              <tr key={r.student}>
                <td><strong>{r.name}</strong> <span className="muted mono">{r.student_no}</span></td>
                <td className="num">
                  <input aria-label={`Score for ${r.name}`} aria-invalid={over ? "true" : undefined} className="input score-input" type="number"
                    min="0" max={a.max_score} step="0.5" value={r.score} disabled={locked} onChange={(e) => set(i, "score", e.target.value)} />
                  {over && <div className="field__error">0–{a.max_score}</div>}
                </td>
                <td className="num muted">{r.score !== "" ? `${Math.round((100 * Number(r.score)) / Number(a.max_score))}%` : "—"}</td>
                <td><input aria-label={`Remark for ${r.name}`} className="input" style={{ maxWidth: 260 }} value={r.remarks || ""} disabled={locked}
                  onChange={(e) => set(i, "remarks", e.target.value)} /></td>
              </tr>
            );
          })}
        </tbody>
      </table></div>
    </Card>
  );
}

function LiveResults({ section, term }) {
  const { data } = useApi(`/schools/classes/${section.id}/results-preview/`, { term });
  if (!data) return <Spinner />;
  const subjects = data.rows[0]?.subjects || [];
  return (
    <Card title={`${section.label} · ${data.term.name}`} subtitle={`Weighted averages so far · state: ${data.state}`} bodyClass="">
      {data.missing_count > 0 && (
        <div style={{ padding: "12px 20px 0" }}>
          <Alert tone="info">{data.missing_count} mark(s) still missing before the principal can finalize. First: {data.missing[0]}</Alert>
        </div>
      )}
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Pupil</th>{subjects.map((s) => <th key={s.code} className="num">{s.code}</th>)}<th className="num">Average</th><th>Grade</th><th className="num">Pos.</th></tr></thead>
          <tbody>
            {data.rows.map((r) => (
              <tr key={r.student}>
                <td>{r.name}</td>
                {subjects.map((s) => <td key={s.code} className="num">{r.subjects.find((x) => x.code === s.code)?.average ?? "—"}</td>)}
                <td className="num"><strong>{r.average ?? "—"}</strong></td><td>{r.grade || "—"}</td><td className="num">{r.position ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export default function Marks() {
  const [params] = useSearchParams();
  const linked = params.get("assessment");
  const [picked, setPicked] = useState(linked || "");
  const { picker, section, subject, term, loading, select } = useClassSubjectTerm({ onUserChange: () => setPicked(""), initialSection: params.get("section") || "" });
  const [tab, setTab] = useState("enter");
  const [creating, setCreating] = useState(false);
  const list = useApi(section && subject && term ? "/schools/assessments/" : null,
    { section: section?.id, subject: subject?.subject, term, page_size: 100, ordering: "due_date" });
  const items = (list.data?.results || []).filter((a) => Number(a.weight) > 0 || a.marked > 0);
  // Opened from the Homework page: show the linked assessment's class, subject and term.
  const link = useApi(linked ? `/schools/assessments/${linked}/` : null);
  useEffect(() => {
    if (link.data) select({ section: link.data.section, subject: link.data.subject, term: link.data.term });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [link.data]);
  const selectionKey = `${section?.id}-${subject?.subject}-${term}`;
  const chosen = picked || items[0]?.id;
  return (
    <>
      <PageHeader title="Marks entry" description="Enter homework, quiz, test and exam marks. Term scores are weighted automatically; marks lock once results are finalized." />
      {loading ? <Spinner /> : !section ? <Alert tone="info">You don't teach any classes in the current academic year yet. The principal or institution admin assigns teachers on <strong>Academic setup</strong>: the <strong>Classes</strong> tab (class teacher) and <strong>Subject teachers &amp; timetable</strong>. The year and its terms must also be set as current under <strong>Years &amp; terms</strong>.</Alert> : (
        <>
          {picker}
          <Tabs value={tab} onChange={setTab} tabs={[{ value: "enter", label: "Enter marks" }, { value: "results", label: "Live term results" }]} />
          {tab === "enter" && (
            <>
              <div className="toolbar">
                <SelectBox id="pick-assessment" label="Assessment" value={chosen || ""} width={320}
                  options={items.map((a) => ({ value: a.id, label: `${a.name} (${titleCase(a.kind)}, ${a.marked} marked)` }))}
                  onChange={setPicked} />
                <Button variant="secondary" icon={LuPlus} onClick={() => setCreating(true)} disabled={!subject || !term}
                  style={{ alignSelf: "flex-end" }}>New exam or test</Button>
              </div>
              {chosen ? <MarkSheet key={chosen} assessmentId={chosen} onSaved={list.reload} />
                : <Card><EmptyState title="No graded assessments yet"
                    action={<Button icon={LuPlus} onClick={() => setCreating(true)} disabled={!subject || !term}>New exam or test</Button>}>
                    Create the exam, test or quiz for {subject?.subject_name || "this subject"} first, then enter the marks here.
                  </EmptyState></Card>}
              {creating && (
                <NewAssessment section={section} subject={subject} term={term}
                  defaults={{ kind: "exam", weight: 40, max_score: 100, name: "End of term exam" }}
                  onClose={() => setCreating(false)}
                  onDone={(created) => { setCreating(false); list.reload(); if (created?.id) setPicked(created.id); }} />
              )}
            </>
          )}
          {tab === "results" && <LiveResults key={selectionKey} section={section} term={term} />}
        </>
      )}
    </>
  );
}
