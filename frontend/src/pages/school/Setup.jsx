import { useEffect, useState } from "react";
import { LuCircleCheck } from "react-icons/lu";
import { api } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { can } from "../../config/roles";
import { useAction, useApi } from "../../utils/hooks";
import { shortDate } from "../../utils/format";
import { Badge, Button, PageHeader } from "../../components/ui";
import { ActionFeedback, SelectBox, Tabs } from "../../components/ui/extra";
import { CrudCard } from "../../components/ui/Crud";

const DAYS = [[0, "Monday"], [1, "Tuesday"], [2, "Wednesday"], [3, "Thursday"], [4, "Friday"]];
const teacherName = (u) => `${u.first_name} ${u.last_name}`;
const TEACHING_ROLES = ["class_teacher", "subject_teacher", "principal"];
const TEACHERS = { path: "/users/", params: { is_active: true }, label: teacherName, filter: (u) => TEACHING_ROLES.includes(u.role) };

/** Shared by school and university: academic years plus terms or semesters, with "set current". */
export function CalendarSetup({ childKind, childLabel }) {
  const { user } = useAuth();
  const manage = can(user, "calendar.manage");
  const act = useAction();
  const [version, setVersion] = useState(0);
  const setCurrent = async (row, reload) => {
    if (await act.run(() => api.post(`/academic-periods/${row.id}/set-current/`, {}), `${row.name} is now current.`)) {
      reload(); setVersion((v) => v + 1);
    }
  };
  const currentAction = (row, reload) => manage && !row.is_current && (
    <Button size="sm" variant="ghost" icon={LuCircleCheck} onClick={() => setCurrent(row, reload)}>Make current</Button>
  );
  const period = [
    { key: "name", header: "Name", render: (r) => <><strong>{r.name}</strong> {r.is_current && <Badge tone="success">Current</Badge>}</> },
    { key: "start_date", header: "Starts", render: (r) => shortDate(r.start_date) },
    { key: "end_date", header: "Ends", render: (r) => shortDate(r.end_date) },
  ];
  const dates = [
    { key: "start_date", label: "Start date", type: "date", required: true },
    { key: "end_date", label: "End date", type: "date", required: true },
  ];
  return (
    <div className="stack">
      <ActionFeedback act={act} />
      <CrudCard title="Academic years" path="/academic-periods/" params={{ kind: "academic_year" }} canEdit={manage} canDelete={manage}
        subtitle="The current year is used for new classes, admissions and fee plans."
        newLabel="New year" columns={period} rowActions={currentAction} onChanged={() => setVersion((v) => v + 1)}
        fields={[{ key: "name", label: "Name", required: true, placeholder: "2027" }, ...dates,
          { key: "kind", label: "Kind", type: "select", options: [["academic_year", "Academic year"]], default: "academic_year", hidden: () => true }]}
        emptyTitle="No academic years yet" />
      <CrudCard key={version} title={childLabel} path="/academic-periods/" params={{ kind: childKind }} canEdit={manage} canDelete={manage}
        subtitle={`Each ${childLabel.toLowerCase().replace(/s$/, "")} sits inside an academic year and must fall within its dates.`}
        newLabel={`New ${childLabel.toLowerCase().replace(/s$/, "")}`} rowActions={currentAction}
        columns={[...period, { key: "parent", header: "Year", render: (r) => r.parent_name || "—" }]}
        fields={[
          { key: "parent", label: "Academic year", type: "select", required: true,
            optionsFrom: { path: "/academic-periods/", params: { kind: "academic_year" }, label: (r) => r.name } },
          { key: "name", label: "Name", required: true, placeholder: childKind === "term" ? "Term 1 2027" : "Semester 1 2027/28" },
          ...dates,
          { key: "kind", label: "Kind", type: "select", options: [[childKind, childLabel]], default: childKind, hidden: () => true },
        ]}
        emptyTitle={`No ${childLabel.toLowerCase()} yet`} />
    </div>
  );
}

function Structure() {
  const { user } = useAuth();
  const manage = can(user, "school.classes.manage");
  return (
    <div className="grid grid--2">
      <CrudCard title="Grade levels" path="/schools/grade-levels/" canEdit={manage} canDelete={manage} newLabel="New grade"
        subtitle="Order decides promotion: pupils move to the next grade up."
        columns={[{ key: "order", header: "Order", className: "num" }, { key: "name", header: "Grade" },
          { key: "is_final", header: "Final grade", render: (r) => (r.is_final ? <Badge tone="brand">Graduates</Badge> : "—") }]}
        fields={[{ key: "name", label: "Name", required: true, placeholder: "Grade 7" },
          { key: "order", label: "Order", type: "number", required: true, min: 1 },
          { key: "is_final", label: "Final grade (pupils complete school here)", type: "checkbox", span2: true }]} />
      <CrudCard title="Subjects" path="/schools/subjects/" canEdit={manage} canDelete={manage} newLabel="New subject"
        columns={[{ key: "code", header: "Code", render: (r) => <span className="mono">{r.code}</span> }, { key: "name", header: "Subject" }]}
        fields={[{ key: "name", label: "Name", required: true, placeholder: "Mathematics" },
          { key: "code", label: "Code", required: true, placeholder: "MAT" }]} />
    </div>
  );
}

function ClassesSetup() {
  const { user } = useAuth();
  const manage = can(user, "school.classes.manage");
  return (
    <CrudCard title="Class sections" path="/schools/classes/" params={{ current: 1 }} canEdit={manage} canDelete={manage}
      subtitle="Classes for the current academic year. Assign subject teachers on the Classes page or the next tab."
      newLabel="New class"
      columns={[{ key: "label", header: "Class", render: (r) => <strong>{r.label}</strong> }, { key: "year_name", header: "Year" },
        { key: "homeroom_teacher_name", header: "Class teacher", render: (r) => r.homeroom_teacher_name || <span className="muted">Not assigned</span> },
        { key: "pupil_count", header: "Pupils", className: "num", render: (r) => `${r.pupil_count} / ${r.capacity}` },
        { key: "room", header: "Room" }]}
      fields={[
        { key: "grade_level", label: "Grade", type: "select", required: true, optionsFrom: { path: "/schools/grade-levels/", label: (r) => r.name } },
        { key: "academic_year", label: "Academic year", type: "select", required: true,
          optionsFrom: { path: "/academic-periods/", params: { kind: "academic_year" }, label: (r) => r.name + (r.is_current ? " (current)" : "") } },
        { key: "name", label: "Stream / section", required: true, placeholder: "A" },
        { key: "capacity", label: "Capacity", type: "number", required: true, default: 35, min: 1 },
        { key: "room", label: "Room", placeholder: "Block B, Room 4" },
        { key: "homeroom_teacher", label: "Class teacher", type: "select", placeholder: "Not assigned",
          optionsFrom: { ...TEACHERS, params: { is_active: true, role__code: "class_teacher" } } },
      ]}
      deleteConfirm={(r) => `Delete class ${r.label}? Only empty classes can be deleted.`} />
  );
}

function SectionPicker({ value, onChange }) {
  const { data } = useApi("/schools/classes/", { current: 1, page_size: 100 });
  const options = (data?.results || []).map((c) => ({ value: c.id, label: c.label }));
  const first = options[0]?.value;
  useEffect(() => { if (!value && first) onChange(String(first)); }, [value, first, onChange]);
  return <SelectBox id="setup-class" label="Class" value={value} onChange={onChange} options={options} />;
}

function Allocations() {
  const { user } = useAuth();
  const manage = can(user, "school.classes.manage");
  const [section, setSection] = useState("");
  return (
    <div className="stack">
      <div className="toolbar"><SectionPicker value={section} onChange={setSection} /></div>
      {section && <>
        <CrudCard key={`a${section}`} title="Subjects taught in this class" path="/schools/allocations/" params={{ section }}
          canEdit={manage} canDelete={manage} newLabel="Add subject"
          columns={[{ key: "subject_name", header: "Subject", render: (r) => <strong>{r.subject_name}</strong> },
            { key: "teacher_name", header: "Teacher", render: (r) => r.teacher_name || <span className="muted">Unassigned</span> },
            { key: "weekly_lessons", header: "Lessons / week", className: "num" }]}
          fields={[{ key: "section", label: "Class", type: "select", default: section, hidden: () => true, options: [[section, section]] },
            { key: "subject", label: "Subject", type: "select", required: true, optionsFrom: { path: "/schools/subjects/", label: (r) => r.name } },
            { key: "teacher", label: "Teacher", type: "select", placeholder: "Unassigned", optionsFrom: TEACHERS },
            { key: "weekly_lessons", label: "Lessons per week", type: "number", default: 5, min: 1 }]} />
        <CrudCard key={`t${section}`} title="Weekly timetable" path="/schools/timetable/" params={{ assignment__section: section }}
          canEdit={manage} canDelete={manage} newLabel="Add lesson"
          subtitle="The server rejects a teacher or class booked twice at the same time."
          columns={[{ key: "day_name", header: "Day" }, { key: "period_no", header: "Period", className: "num" },
            { key: "start_time", header: "Time", render: (r) => `${r.start_time.slice(0, 5)}–${r.end_time.slice(0, 5)}` },
            { key: "subject_name", header: "Subject" }, { key: "teacher_name", header: "Teacher" }, { key: "room", header: "Room" }]}
          fields={[
            { key: "assignment", label: "Subject", type: "select", required: true,
              optionsFrom: { path: "/schools/allocations/", params: { section }, label: (r) => `${r.subject_name}${r.teacher_name ? ` · ${r.teacher_name}` : ""}` } },
            { key: "day", label: "Day", type: "select", required: true, options: DAYS },
            { key: "period_no", label: "Period number", type: "number", required: true, min: 1, max: 12 },
            { key: "start_time", label: "Starts", type: "time", required: true },
            { key: "end_time", label: "Ends", type: "time", required: true },
            { key: "room", label: "Room" }]}
          deleteConfirm={(r) => `Remove ${r.subject_name} on ${r.day_name}, period ${r.period_no}?`} />
      </>}
    </div>
  );
}

export default function SchoolSetup() {
  const [tab, setTab] = useState("calendar");
  return (
    <>
      <PageHeader title="Academic setup" description="Academic years and terms, grade levels, subjects, classes, subject teachers and the weekly timetable." />
      <Tabs value={tab} onChange={setTab} label="Setup sections" tabs={[
        { value: "calendar", label: "Years & terms" }, { value: "structure", label: "Grades & subjects" },
        { value: "classes", label: "Classes" }, { value: "allocations", label: "Subject teachers & timetable" },
      ]} />
      {tab === "calendar" && <CalendarSetup childKind="term" childLabel="Terms" />}
      {tab === "structure" && <Structure />}
      {tab === "classes" && <ClassesSetup />}
      {tab === "allocations" && <Allocations />}
    </>
  );
}
