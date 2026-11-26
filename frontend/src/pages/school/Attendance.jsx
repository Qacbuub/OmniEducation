import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { LuCheckCheck, LuSave } from "react-icons/lu";
import { api } from "../../api/client";
import { useAction, useApi } from "../../utils/hooks";
import { Alert, Badge, Button, Card, EmptyState, PageHeader, Spinner } from "../../components/ui";
import { ActionFeedback, ProgressBar, SelectBox, Tabs } from "../../components/ui/extra";
import { classOptions, termOptions, today, useMyClasses, useTerms } from "./common";

const STATUSES = [["present", "Present"], ["late", "Late"], ["absent", "Absent"], ["excused", "Excused"]];

function StatusPicker({ name, value, onChange }) {
  return (
    <div className="seg" role="radiogroup" aria-label={name}>
      {STATUSES.map(([v, l]) => (
        <label key={v} className={`${value === v ? "on " : ""}${v}`}>
          <input type="radio" name={name} value={v} checked={value === v} onChange={() => onChange(v)} />
          <span>{l}</span>
        </label>
      ))}
    </div>
  );
}

function Register({ classes }) {
  const [params] = useSearchParams(); // ?section= when opened from the dashboard
  const [section, setSection] = useState(params.get("section") || "");
  const [date, setDate] = useState(today());
  const [lesson, setLesson] = useState("");
  // Class teachers start on their own homeroom; everyone else on the first class.
  const sectionId = section || (classes.find((c) => c.is_homeroom) || classes[0])?.id;
  const sheet = useApi(sectionId ? "/schools/attendance/sheet/" : null, { section: sectionId, date, lesson: lesson || undefined });
  const [rows, setRows] = useState([]);
  const act = useAction();
  useEffect(() => { if (sheet.data) setRows(sheet.data.rows.map((r) => ({ ...r }))); }, [sheet.data]);
  const set = (i, k, v) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  const save = async () => {
    const records = rows.filter((r) => r.status).map((r) => ({ student: r.student, status: r.status, reason: r.reason || "" }));
    const res = await act.run(() => api.post("/schools/attendance/register/", { section: sectionId, date, lesson: lesson || null, records }),
      (x) => `Saved ${x.saved} record(s). ${x.absent ? `${x.absent} absent — guardians have been notified.` : "No absences."}`);
    if (res) sheet.reload();
  };
  const d = sheet.data;
  const unmarked = rows.filter((r) => !r.status).length;
  return (
    <>
      <div className="toolbar">
        <SelectBox id="att-class" label="Class" value={sectionId} onChange={(v) => { setSection(v); setLesson(""); }} options={classOptions(classes)} width={160} />
        <span style={{ display: "inline-flex", flexDirection: "column", gap: 4 }}>
          <label htmlFor="att-date" className="select-label">Date</label>
          <input id="att-date" className="input" type="date" value={date} max={today()} onChange={(e) => { setDate(e.target.value); setLesson(""); }} />
        </span>
        <SelectBox id="att-lesson" label="Register" value={lesson} onChange={setLesson} placeholder="Daily register" width={260}
          options={(d?.lessons_today || []).map((l) => ({ value: l.id, label: `P${l.period_no} ${l.start_time.slice(0, 5)} · ${l.subject_name}` }))} />
      </div>
      <ActionFeedback act={act} />
      {!d ? <Spinner /> : (
        <Card title={`${d.section.label} · ${lesson && d.lesson ? `${d.lesson.subject_name} lesson` : "Daily register"} · ${date}`}
          subtitle={d.can_record ? `${rows.length} pupils${unmarked ? ` · ${unmarked} not marked yet` : ""}`
            : "You can view this register but only the class teacher (daily) or the lesson's teacher can record it."}
          actions={d.can_record && <div className="row-actions">
            <Button size="sm" variant="secondary" icon={LuCheckCheck} onClick={() => setRows((rs) => rs.map((r) => ({ ...r, status: r.status || "present" })))}>Mark rest present</Button>
            <Button size="sm" icon={LuSave} disabled={act.busy || rows.every((r) => !r.status)} onClick={save}>{act.busy ? "Saving…" : "Save register"}</Button>
          </div>}
          bodyClass="">
          {rows.length === 0 ? <EmptyState title="No pupils in this class" /> : (
            <table className="table">
              <thead><tr><th>Pupil</th><th>Status</th><th>Reason (for absences)</th></tr></thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={r.student}>
                    <td><strong>{r.name}</strong> <span className="muted mono">{r.student_no}</span></td>
                    <td>{d.can_record ? <StatusPicker name={`status-${r.student}`} value={r.status} onChange={(v) => set(i, "status", v)} />
                      : r.status ? <Badge>{r.status}</Badge> : <span className="muted">—</span>}</td>
                    <td>{(r.status === "absent" || r.status === "excused") && d.can_record ? (
                      <input aria-label={`Reason for ${r.name}`} className="input" style={{ maxWidth: 280 }} value={r.reason || ""}
                        placeholder={r.status === "excused" ? "Required, e.g. medical" : "Optional"} onChange={(e) => set(i, "reason", e.target.value)} />
                    ) : <span className="muted">{r.reason}</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      )}
    </>
  );
}

function Summary({ classes }) {
  const { terms, current } = useTerms();
  const [section, setSection] = useState("");
  const [term, setTerm] = useState("");
  const sectionId = section || classes[0]?.id;
  const termId = term || current?.id;
  const { data } = useApi(sectionId && termId ? "/schools/attendance/summary/" : null, { section: sectionId, term: termId });
  return (
    <>
      <div className="toolbar">
        <SelectBox id="sum-class" label="Class" value={sectionId} onChange={setSection} options={classOptions(classes)} width={160} />
        <SelectBox id="sum-term" label="Term" value={termId} onChange={setTerm} options={termOptions(terms)} width={180} />
      </div>
      {!data ? <Spinner /> : (
        <Card title={`Attendance summary · ${data.term}`} subtitle={`Class attendance rate ${data.class_rate ?? "—"}%`} bodyClass="">
          <table className="table">
            <thead><tr><th>Pupil</th><th className="num">Days</th><th className="num">Present</th><th className="num">Late</th><th className="num">Absent</th><th className="num">Excused</th><th>Rate</th></tr></thead>
            <tbody>
              {data.rows.map((r) => (
                <tr key={r.student}>
                  <td>{r.name}</td><td className="num">{r.days_recorded}</td><td className="num">{r.present}</td><td className="num">{r.late}</td>
                  <td className="num" style={{ color: r.absent >= 3 ? "var(--danger)" : undefined, fontWeight: r.absent >= 3 ? 700 : undefined }}>{r.absent}</td>
                  <td className="num">{r.excused}</td>
                  <td style={{ width: "25%" }}>{r.attendance_rate != null ? <ProgressBar value={r.attendance_rate} label={`${r.name} attendance`} /> : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}

export default function Attendance() {
  const { classes, loading } = useMyClasses();
  const [tab, setTab] = useState("register");
  return (
    <>
      <PageHeader title="Attendance" description="Daily registers by the class teacher, per-lesson attendance by subject teachers. Guardians are notified of unexplained absences." />
      <Tabs value={tab} onChange={setTab} tabs={[{ value: "register", label: "Take attendance" }, { value: "summary", label: "Summaries" }]} />
      {loading && !classes.length ? <Spinner /> : !classes.length ? <Alert tone="info">You have no classes this year.</Alert>
        : tab === "register" ? <Register classes={classes} /> : <Summary classes={classes} />}
    </>
  );
}
