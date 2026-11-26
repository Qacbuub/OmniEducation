import { useState } from "react";
import { LuPlus, LuTrash2 } from "react-icons/lu";
import { api } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { can } from "../../config/roles";
import { useAction, useApi } from "../../utils/hooks";
import { shortDate, titleCase } from "../../utils/format";
import { Badge, Button, Card, Field, Modal, PageHeader, Spinner } from "../../components/ui";
import { ActionFeedback, KeyValues, SelectBox } from "../../components/ui/extra";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
export const meetingsText = (o) => o.meetings.map((m) => `${m.day_name} ${m.start_time.slice(0, 5)}–${m.end_time.slice(0, 5)}${m.room ? ` ${m.room}` : ""}`).join(", ");

function SectionForm({ semester, offering, onClose, onDone }) {
  const courses = useApi("/universities/courses/", { page_size: 100, is_active: true });
  const lecturers = useApi("/users/", { role__code: "lecturer", page_size: 100 });
  const [f, setF] = useState(offering ? { course: offering.course, section: offering.section, capacity: offering.capacity, lecturer: offering.lecturer || "", status: offering.status }
    : { course: "", section: "A", capacity: 40, lecturer: "", status: "open" });
  const [meetings, setMeetings] = useState(offering ? offering.meetings.map((m) => ({ ...m, start_time: m.start_time.slice(0, 5), end_time: m.end_time.slice(0, 5) }))
    : [{ day: 0, start_time: "09:00", end_time: "10:30", room: "" }]);
  const act = useAction();
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  const setM = (i, k, v) => setMeetings((ms) => ms.map((m, j) => (j === i ? { ...m, [k]: v } : m)));
  const err = (k) => act.error?.fields?.[k]?.[0];
  async function submit(e) {
    e.preventDefault();
    const body = { ...f, semester, lecturer: f.lecturer || null, meetings: meetings.map((m) => ({ day: Number(m.day), start_time: m.start_time, end_time: m.end_time, room: m.room })) };
    const call = offering ? () => api.patch(`/universities/offerings/${offering.id}/`, body) : () => api.post("/universities/offerings/", body);
    if (await act.run(call)) onDone();
  }
  return (
    <Modal title={offering ? `Edit ${offering.course_code}-${offering.section}` : "New course section"} onClose={onClose}>
      <form onSubmit={submit} noValidate>
        <ActionFeedback act={act} />
        <div className="form-grid">
          <Field label="Course" error={err("course")} className="span-2">
            {(a) => <select {...a} className="select" value={f.course} onChange={set("course")} disabled={Boolean(offering)}>
              <option value="">Choose…</option>
              {(courses.data?.results || []).map((c) => <option key={c.id} value={c.id}>{c.code} {c.title} ({c.credit_hours} cr)</option>)}
            </select>}
          </Field>
          <Field label="Section" error={err("section")}>{(a) => <input {...a} className="input" value={f.section} onChange={set("section")} />}</Field>
          <Field label="Seat capacity" error={err("capacity")}>{(a) => <input {...a} className="input" type="number" min="1" value={f.capacity} onChange={set("capacity")} />}</Field>
          <Field label="Lecturer" error={err("lecturer")}>
            {(a) => <select {...a} className="select" value={f.lecturer} onChange={set("lecturer")}>
              <option value="">Not assigned</option>
              {(lecturers.data?.results || []).map((u) => <option key={u.id} value={u.id}>{u.first_name} {u.last_name}</option>)}
            </select>}
          </Field>
          <Field label="Status">{(a) => <select {...a} className="select" value={f.status} onChange={set("status")}>{["open", "closed", "cancelled"].map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}</select>}</Field>
        </div>
        <fieldset style={{ border: 0, padding: 0, margin: "0 0 12px" }}>
          <legend className="select-label">Weekly meetings · lecturer and room clashes are rejected</legend>
          {meetings.map((m, i) => (
            <div key={i} className="toolbar" style={{ marginBottom: 6 }}>
              <select aria-label="Day" className="select" style={{ width: 90 }} value={m.day} onChange={(e) => setM(i, "day", e.target.value)}>
                {DAYS.map((d, j) => <option key={d} value={j}>{d}</option>)}
              </select>
              <input aria-label="Start time" className="input" type="time" style={{ width: 120 }} value={m.start_time} onChange={(e) => setM(i, "start_time", e.target.value)} />
              <input aria-label="End time" className="input" type="time" style={{ width: 120 }} value={m.end_time} onChange={(e) => setM(i, "end_time", e.target.value)} />
              <input aria-label="Room" className="input" style={{ width: 120 }} placeholder="Room" value={m.room} onChange={(e) => setM(i, "room", e.target.value)} />
              <Button size="sm" variant="ghost" icon={LuTrash2} aria-label="Remove meeting" onClick={() => setMeetings((ms) => ms.filter((_, j) => j !== i))} />
            </div>
          ))}
          <Button size="sm" variant="secondary" icon={LuPlus} onClick={() => setMeetings((ms) => [...ms, { day: 2, start_time: "09:00", end_time: "10:30", room: "" }])}>Add meeting</Button>
        </fieldset>
        <div className="form-actions"><Button variant="secondary" onClick={onClose}>Cancel</Button><Button type="submit" disabled={act.busy || !f.course}>{act.busy ? "Saving…" : "Save section"}</Button></div>
      </form>
    </Modal>
  );
}

export default function Offerings() {
  const { user } = useAuth();
  const semesters = useApi("/universities/semesters/", { page_size: 50 });
  const [semester, setSemester] = useState("");
  const [modal, setModal] = useState(null);
  const list = semesters.data?.results || [];
  const sem = list.find((s) => String(s.id) === String(semester)) || list.find((s) => s.is_current) || list[0];
  const offerings = useApi(sem ? "/universities/offerings/" : null, { semester: sem?.id, page_size: 100 });
  const manage = can(user, "uni.offerings.manage");
  return (
    <>
      <PageHeader title="Course offerings" description="Sections per semester with lecturer, seat capacity and weekly meetings."
        actions={manage && sem && <Button icon={LuPlus} onClick={() => setModal({})}>New section</Button>} />
      {!sem ? <Spinner /> : (
        <>
          <div className="toolbar">
            <SelectBox id="off-sem" label="Semester" value={sem.id} onChange={setSemester} options={list.map((s) => ({ value: s.id, label: s.name }))} width={240} />
          </div>
          <Card title={sem.name} subtitle="Registration window" bodyClass="card__body">
            <KeyValues items={[["Registration opens", shortDate(sem.registration_start)], ["Registration closes", shortDate(sem.registration_end)],
              ["Add/drop deadline", shortDate(sem.add_drop_end)], ["Grades due", shortDate(sem.grades_due)]]} />
          </Card>
          <Card title={`Sections (${offerings.data?.count ?? "…"})`} bodyClass="">
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Section</th><th>Course</th><th className="num">Credits</th><th>Lecturer</th><th>Meetings</th><th className="num">Seats</th><th>Grades</th><th>Status</th>{manage && <th />}</tr></thead>
                <tbody>
                  {(offerings.data?.results || []).map((o) => (
                    <tr key={o.id}>
                      <td className="mono" style={{ fontWeight: 600 }}>{o.course_code}-{o.section}</td><td>{o.course_title}</td><td className="num">{o.credit_hours}</td>
                      <td>{o.lecturer_name || <span className="muted">—</span>}</td><td className="muted" style={{ fontSize: "var(--fs-xs)" }}>{meetingsText(o) || "—"}</td>
                      <td className="num"><span style={{ color: o.seats_left === 0 ? "var(--danger)" : undefined, fontWeight: 600 }}>{o.enrolled}/{o.capacity}</span></td>
                      <td><Badge tone="neutral">{titleCase(o.grade_status)}</Badge></td><td><Badge>{o.status}</Badge></td>
                      {manage && <td className="num"><Button size="sm" variant="secondary" onClick={() => setModal({ offering: o })}>Edit</Button></td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
      {modal && <SectionForm semester={sem.id} offering={modal.offering} onClose={() => setModal(null)} onDone={() => { setModal(null); offerings.reload(); }} />}
    </>
  );
}
