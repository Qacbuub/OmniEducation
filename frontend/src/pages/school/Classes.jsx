import { useState } from "react";
import { Link } from "react-router-dom";
import { LuUserPlus } from "react-icons/lu";
import { api } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { can } from "../../config/roles";
import { useAction, useApi } from "../../utils/hooks";
import { Badge, Button, Card, EmptyState, PageHeader, Spinner } from "../../components/ui";
import { ActionFeedback, SelectBox, StudentPicker, Tabs, WeekGrid } from "../../components/ui/extra";
import { useMyClasses } from "./common";

function Roster({ section }) {
  const { data, loading } = useApi(`/schools/classes/${section.id}/roster/`);
  if (loading && !data) return <Spinner />;
  const pupils = data?.pupils || [];
  return pupils.length === 0 ? <EmptyState title="No pupils in this class yet" /> : (
    <table className="table">
      <thead><tr><th>Pupil</th><th>Admission no.</th><th>Guardian</th><th>Today</th><th className="num">Term attendance</th><th className="num">Absences</th></tr></thead>
      <tbody>
        {pupils.map((p) => (
          <tr key={p.id}>
            <td><Link to={`/school/students/${p.id}`}>{p.first_name} {p.last_name}</Link></td>
            <td className="mono">{p.student_no}</td>
            <td>{p.guardian || "—"}{p.guardian_phone && <div className="muted" style={{ fontSize: "var(--fs-xs)" }}>{p.guardian_phone}</div>}</td>
            <td>{p.today ? <Badge>{p.today}</Badge> : <span className="muted">Not taken</span>}</td>
            <td className="num">{p.term_attendance_rate != null ? `${p.term_attendance_rate}%` : "—"}</td>
            <td className="num" style={{ color: p.term_absences >= 3 ? "var(--danger)" : undefined }}>{p.term_absences}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Subjects({ section, onChanged }) {
  const { user } = useAuth();
  const manage = can(user, "school.classes.manage");
  const teachers = useApi(manage ? "/users/" : null, { page_size: 100, is_active: true });
  const act = useAction();
  const options = (teachers.data?.results || []).filter((u) => ["class_teacher", "subject_teacher", "principal"].includes(u.role))
    .map((u) => ({ value: u.id, label: `${u.first_name} ${u.last_name}` }));
  const assign = async (a, teacher) => {
    if (await act.run(() => api.patch(`/schools/allocations/${a.id}/`, { teacher: teacher || null }), `${a.subject_name} teacher updated.`)) onChanged();
  };
  const classTeachers = (teachers.data?.results || []).filter((u) => u.role === "class_teacher")
    .map((u) => ({ value: u.id, label: `${u.first_name} ${u.last_name}` }));
  const setHomeroom = async (teacher) => {
    if (await act.run(() => api.patch(`/schools/classes/${section.id}/`, { homeroom_teacher: teacher || null }), "Class teacher updated.")) onChanged();
  };
  return (
    <>
      <ActionFeedback act={act} />
      {manage && (
        <div className="toolbar">
          <SelectBox id={`homeroom-${section.id}`} label="Class teacher" value={section.homeroom_teacher || ""}
            placeholder="Not assigned" options={classTeachers} onChange={setHomeroom} width={260} />
        </div>
      )}
      <table className="table">
        <thead><tr><th>Subject</th><th>Code</th><th>Teacher</th><th className="num">Lessons / week</th></tr></thead>
        <tbody>
          {section.assignments.map((a) => (
            <tr key={a.id}>
              <td><strong>{a.subject_name}</strong></td><td className="mono">{a.subject_code}</td>
              <td>{manage ? (
                <SelectBox id={`t-${a.id}`} label={`${a.subject_name} teacher`} hideLabel value={a.teacher || ""} placeholder="Unassigned"
                  options={options} onChange={(v) => assign(a, v)} />
              ) : a.teacher_name || "—"}</td>
              <td className="num">{a.weekly_lessons}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function ClassTimetable({ section }) {
  const { data } = useApi(`/schools/classes/${section.id}/timetable/`);
  return <WeekGrid items={(data || []).map((l) => ({ ...l, title: l.subject_name, sub: l.teacher_name }))} />;
}

function PlacePupil({ section, onDone }) {
  const [student, setStudent] = useState(null);
  const act = useAction();
  const place = async () => {
    const r = await act.run(() => api.post(`/schools/classes/${section.id}/place/`, { student: student.id }),
      `${student.first_name} ${student.last_name} placed in ${section.label}.`);
    if (r) { setStudent(null); onDone(); }
  };
  return (
    <div className="stack-sm">
      <ActionFeedback act={act} />
      <div className="toolbar" style={{ marginBottom: 0 }}>
        <StudentPicker label="Pupil to place or move" value={student?.id} onChange={setStudent} />
        {student && <span>Selected: <strong>{student.first_name} {student.last_name}</strong> ({student.level} {student.section})</span>}
        <Button icon={LuUserPlus} disabled={!student || act.busy} onClick={place}>Place in {section.label}</Button>
      </div>
      <p className="muted" style={{ fontSize: "var(--fs-sm)", margin: 0 }}>Moving a pupil keeps their previous class in their history. Full classes are refused.</p>
    </div>
  );
}

export default function Classes() {
  const { user } = useAuth();
  const { classes, loading, reload, all } = useMyClasses();
  const [selected, setSelected] = useState(null);
  const [tab, setTab] = useState("roster");
  const section = classes.find((c) => c.id === selected) || classes[0];
  const manage = can(user, "school.classes.manage");
  return (
    <>
      <PageHeader title="Classes & roster" description={all ? "Every class this academic year, with rosters, subject teachers and timetables."
        : "The classes you teach this year."} />
      {loading && !classes.length ? <Spinner /> : !section ? <Card><EmptyState title="No classes yet" /></Card> : (
        <div className="grid grid--3-1" style={{ gridTemplateColumns: "260px 1fr" }}>
          <Card title="Classes" bodyClass="">
            <ul className="list" style={{ padding: "0 12px" }}>
              {classes.map((c) => (
                <li key={c.id} className="list__item" style={{ padding: 0 }}>
                  <button type="button" className={`picker__item${c.id === section.id ? " is-active" : ""}`}
                    aria-current={c.id === section.id ? "true" : undefined} onClick={() => { setSelected(c.id); setTab("roster"); }}>
                    <strong>{c.label}</strong>
                    <span className="muted"> · {c.pupil_count}/{c.capacity}{c.is_homeroom ? " · your homeroom" : ""}</span>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
          <Card title={`${section.label} · ${section.year_name}`}
            subtitle={`Class teacher: ${section.homeroom_teacher_name || "not assigned"} · ${section.pupil_count} of ${section.capacity} places · ${section.room || "no room"}`}
            bodyClass="card__body">
            <Tabs value={tab} onChange={setTab} tabs={[
              { value: "roster", label: "Roster", count: section.pupil_count }, { value: "subjects", label: "Subjects & teachers" },
              { value: "timetable", label: "Timetable" }, manage && { value: "place", label: "Place a pupil" },
            ]} />
            {tab === "roster" && <Roster key={`${section.id}-${section.pupil_count}`} section={section} />}
            {tab === "subjects" && <Subjects section={section} onChanged={reload} />}
            {tab === "timetable" && <ClassTimetable key={section.id} section={section} />}
            {tab === "place" && <PlacePupil section={section} onDone={reload} />}
          </Card>
        </div>
      )}
    </>
  );
}
