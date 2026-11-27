import { useEffect, useState } from "react";
import { LuCheckCheck, LuSave } from "react-icons/lu";
import { api } from "../../api/client";
import { useAction, useApi } from "../../utils/hooks";
import { titleCase } from "../../utils/format";
import { Badge, Button, Card, EmptyState, PageHeader, Spinner } from "../../components/ui";
import { ActionFeedback, SelectBox } from "../../components/ui/extra";
import { StatusPicker } from "../school/Attendance";
import { today } from "../school/common";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** One section's register for one day: mark each registered student, see their attendance rate so far. */
function Register({ offering }) {
  const [date, setDate] = useState(today());
  const sheet = useApi(`/universities/offerings/${offering.id}/attendance/`, { date });
  const [rows, setRows] = useState([]);
  const act = useAction();
  useEffect(() => { if (sheet.data) setRows(sheet.data.rows.map((r) => ({ ...r }))); }, [sheet.data]);
  const set = (i, k, v) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  const save = async () => {
    const records = rows.filter((r) => r.status).map((r) => ({ registration: r.registration, status: r.status, note: r.note || "" }));
    const res = await act.run(() => api.post(`/universities/offerings/${offering.id}/attendance/`, { date, records }), (x) => {
      const absent = x.rows.filter((r) => r.status === "absent").length;
      return `Attendance for ${date} saved.${absent ? ` ${absent} absent — they were notified.` : ""}`;
    });
    if (res) sheet.reload();
  };
  const d = sheet.data;
  const unmarked = rows.filter((r) => !r.status).length;
  const meetsOn = (d?.meeting_days || []).map((n) => DAYS[n]).join(", ");
  return (
    <>
      <div className="toolbar">
        <span style={{ display: "inline-flex", flexDirection: "column", gap: 4 }}>
          <label htmlFor="ua-date" className="select-label">Class date</label>
          <input id="ua-date" className="input" type="date" value={date} max={today()} onChange={(e) => setDate(e.target.value)} />
        </span>
        {d?.recent_dates?.length > 0 && (
          <SelectBox id="ua-recent" label="Recorded classes" value="" placeholder="Open a recorded class…" width={220}
            options={d.recent_dates.map((x) => ({ value: x, label: x }))} onChange={(v) => v && setDate(v)} />
        )}
      </div>
      <ActionFeedback act={act} />
      {!d ? <Spinner /> : (
        <Card title={`${offering.course_code}-${offering.section} · ${date}`}
          subtitle={`${rows.length} students${meetsOn ? ` · meets ${meetsOn}` : ""}${d.recorded ? " · already recorded (saving updates it)" : unmarked ? ` · ${unmarked} not marked yet` : ""}`}
          actions={d.can_edit && rows.length > 0 && <div className="row-actions">
            <Button size="sm" variant="secondary" icon={LuCheckCheck} onClick={() => setRows((rs) => rs.map((r) => ({ ...r, status: r.status || "present" })))}>Mark rest present</Button>
            <Button size="sm" icon={LuSave} disabled={act.busy || rows.every((r) => !r.status)} onClick={save}>{act.busy ? "Saving…" : "Save attendance"}</Button>
          </div>}
          bodyClass="">
          {rows.length === 0 ? <EmptyState title="No approved students in this section yet">Students appear here once their registration is approved.</EmptyState> : (
            <div className="table-wrap"><table className="table">
              <thead><tr><th>Student</th><th>Status</th><th>Note</th><th className="num">Attendance so far</th></tr></thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={r.registration}>
                    <td><strong>{r.name}</strong> <span className="muted mono">{r.student_no}</span></td>
                    <td>{d.can_edit ? <StatusPicker name={`status-${r.registration}`} value={r.status} onChange={(v) => set(i, "status", v)} />
                      : r.status ? <Badge>{titleCase(r.status)}</Badge> : <span className="muted">—</span>}</td>
                    <td>{d.can_edit && r.status && r.status !== "present" ? (
                      <input aria-label={`Note for ${r.name}`} className="input" style={{ maxWidth: 240 }} value={r.note || ""}
                        placeholder={r.status === "excused" ? "e.g. medical certificate" : "Optional"} onChange={(e) => set(i, "note", e.target.value)} />
                    ) : <span className="muted">{r.note}</span>}</td>
                    <td className="num">{r.rate == null ? <span className="muted">—</span> : (
                      <span title={`${r.sessions} classes recorded, ${r.absences} absent`}>
                        <Badge tone={r.rate < 75 ? "danger" : "success"}>{r.rate}%</Badge> <span className="muted">{r.absences} abs.</span>
                      </span>
                    )}</td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          )}
        </Card>
      )}
    </>
  );
}

export default function UniversityAttendance() {
  const mine = useApi("/universities/offerings/mine/", { current: 1 }); // only the semester set as current
  const [selected, setSelected] = useState("");
  const list = (mine.data || []).filter((o) => o.status !== "cancelled");
  const chosen = list.find((o) => String(o.id) === String(selected)) || list[0];
  return (
    <>
      <PageHeader title="Class attendance" description="Record who attended each class meeting. Absent students are notified; excused absences don't lower the attendance rate." />
      {mine.loading && !mine.data ? <Spinner /> : !chosen ? <Card><EmptyState title="You're not assigned to any sections">
        You have no sections in the current semester. The registrar or department head assigns lecturers on
        <strong> Course offerings</strong>, for the semester set as current.
      </EmptyState></Card> : (
        <>
          <div className="toolbar">
            <SelectBox id="ua-section" label="Section" value={chosen.id} onChange={setSelected} width={360}
              options={list.map((o) => ({ value: o.id, label: `${o.course_code}-${o.section} ${o.course_title} · ${o.semester_name}` }))} />
          </div>
          <Register key={chosen.id} offering={chosen} />
        </>
      )}
    </>
  );
}
