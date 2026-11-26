import { useEffect, useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import { can } from "../../config/roles";
import { useApi } from "../../utils/hooks";
import { shortDate, titleCase } from "../../utils/format";
import { Badge, PageHeader } from "../../components/ui";
import { SelectBox, Tabs } from "../../components/ui/extra";
import { CrudCard } from "../../components/ui/Crud";
import { CalendarSetup } from "../school/Setup";

const person = (u) => `${u.first_name} ${u.last_name}`;
const staffOf = (...roles) => ({ path: "/users/", params: { is_active: true }, label: person, filter: (u) => roles.includes(u.role) });

function SemesterWindows() {
  const { user } = useAuth();
  const manage = can(user, "uni.offerings.manage");
  return (
    <CrudCard title="Registration windows" path="/universities/semesters/" canEdit={manage} canDelete={manage} newLabel="Set up semester"
      subtitle="Course registration, add/drop and grade deadlines for each semester. Students can only register inside the window."
      columns={[{ key: "name", header: "Semester", render: (r) => <><strong>{r.name}</strong> {r.is_current && <Badge tone="success">Current</Badge>}</> },
        { key: "registration", header: "Registration", render: (r) => `${shortDate(r.registration_start)} → ${shortDate(r.registration_end)}` },
        { key: "add_drop_end", header: "Add/drop ends", render: (r) => shortDate(r.add_drop_end) },
        { key: "grades_due", header: "Grades due", render: (r) => shortDate(r.grades_due) },
        { key: "offering_count", header: "Sections", className: "num" }]}
      fields={[
        { key: "period", label: "Semester (from the calendar)", type: "select", required: true, span2: true,
          optionsFrom: { path: "/academic-periods/", params: { kind: "semester" }, label: (r) => `${r.name} (${r.start_date} → ${r.end_date})` } },
        { key: "registration_start", label: "Registration opens", type: "date", required: true },
        { key: "registration_end", label: "Registration closes", type: "date", required: true },
        { key: "add_drop_end", label: "Add/drop ends", type: "date", required: true },
        { key: "grades_due", label: "Grades due", type: "date", required: true },
      ]}
      emptyTitle="No semester set up yet" emptyText="Create the semester on the calendar tab first, then open its registration window here." />
  );
}

function Organisation() {
  const { user } = useAuth();
  const manage = can(user, "uni.programs.manage");
  return (
    <div className="stack">
      <CrudCard title="Faculties" path="/universities/faculties/" canEdit={manage} canDelete={manage} newLabel="New faculty"
        columns={[{ key: "code", header: "Code", render: (r) => <span className="mono">{r.code}</span> }, { key: "name", header: "Faculty" },
          { key: "dean_name", header: "Dean" }, { key: "department_count", header: "Departments", className: "num" }]}
        fields={[{ key: "name", label: "Name", required: true, placeholder: "Faculty of Science" },
          { key: "code", label: "Code", required: true, placeholder: "SCI" },
          { key: "dean", label: "Dean", type: "select", placeholder: "Not assigned", optionsFrom: staffOf("dean") }]} />
      <CrudCard title="Departments" path="/universities/departments/" canEdit={manage} canDelete={manage} newLabel="New department"
        columns={[{ key: "code", header: "Code", render: (r) => <span className="mono">{r.code}</span> }, { key: "name", header: "Department" },
          { key: "faculty_name", header: "Faculty" }, { key: "head_name", header: "Head" }]}
        fields={[{ key: "faculty", label: "Faculty", type: "select", required: true, optionsFrom: { path: "/universities/faculties/", label: (r) => r.name } },
          { key: "name", label: "Name", required: true, placeholder: "Computer Science" },
          { key: "code", label: "Code", required: true, placeholder: "CS" },
          { key: "head", label: "Head of department", type: "select", placeholder: "Not assigned", optionsFrom: staffOf("dept_head") }]} />
    </div>
  );
}

function Programs() {
  const { user } = useAuth();
  const manage = can(user, "uni.programs.manage");
  return (
    <CrudCard title="Degree programmes" path="/universities/programs/" canEdit={manage} canDelete={manage} newLabel="New programme"
      columns={[{ key: "code", header: "Code", render: (r) => <span className="mono">{r.code}</span> },
        { key: "name", header: "Programme", render: (r) => <><strong>{r.name}</strong><div className="muted" style={{ fontSize: "var(--fs-xs)" }}>{r.award} · {r.department_name}</div></> },
        { key: "duration_years", header: "Years", className: "num" }, { key: "total_credits_required", header: "Credits", className: "num" },
        { key: "student_count", header: "Students", className: "num" },
        { key: "is_active", header: "Status", render: (r) => <Badge tone={r.is_active ? "success" : undefined}>{r.is_active ? "Open" : "Closed"}</Badge> }]}
      fields={[{ key: "department", label: "Department", type: "select", required: true, optionsFrom: { path: "/universities/departments/", label: (r) => r.name } },
        { key: "name", label: "Name", required: true, placeholder: "BSc Data Science" },
        { key: "code", label: "Code", required: true, placeholder: "BSC-DS" },
        { key: "award", label: "Award", placeholder: "Bachelor's degree", default: "Bachelor's degree" },
        { key: "duration_years", label: "Duration (years)", type: "number", default: 4, min: 1, max: 8 },
        { key: "total_credits_required", label: "Credits to graduate", type: "number", default: 120, min: 1 },
        { key: "is_active", label: "Open for admissions", type: "checkbox", default: true }]} />
  );
}

function Curricula() {
  const { user } = useAuth();
  const manage = can(user, "uni.programs.manage");
  const [curriculum, setCurriculum] = useState("");
  const { data } = useApi("/universities/curricula/", { page_size: 100 });
  const rows = data?.results || [];
  const first = rows[0]?.id;
  useEffect(() => { if (!curriculum && first) setCurriculum(String(first)); }, [curriculum, first]);
  return (
    <div className="stack">
      <CrudCard title="Curriculum versions" path="/universities/curricula/" canEdit={manage} canDelete={manage} newLabel="New curriculum"
        subtitle="Students follow the curriculum version that was current when they matriculated."
        columns={[{ key: "program_name", header: "Programme" }, { key: "version", header: "Version" },
          { key: "effective_from", header: "Effective", render: (r) => shortDate(r.effective_from) },
          { key: "core_credits", header: "Core credits", className: "num" }, { key: "elective_credits_required", header: "Elective credits", className: "num" },
          { key: "is_current", header: "", render: (r) => r.is_current && <Badge tone="success">Current</Badge> }]}
        fields={[{ key: "program", label: "Programme", type: "select", required: true, optionsFrom: { path: "/universities/programs/", label: (r) => r.name } },
          { key: "version", label: "Version", required: true, placeholder: "2027" },
          { key: "effective_from", label: "Effective from", type: "date", required: true },
          { key: "elective_credits_required", label: "Elective credits required", type: "number", default: 0, min: 0 },
          { key: "is_current", label: "Current version for new students", type: "checkbox", default: true }]} />
      <div className="toolbar">
        <SelectBox id="curriculum-pick" label="Course map for" value={curriculum} onChange={setCurriculum} width={320}
          options={rows.map((c) => ({ value: c.id, label: `${c.program_name} · ${c.version}` }))} />
      </div>
      {curriculum && (
        <CrudCard key={curriculum} title="Curriculum course map" path="/universities/curriculum-courses/" params={{ curriculum }}
          canEdit={manage} canDelete={manage} newLabel="Map course"
          subtitle="Which courses count towards this programme, and when students should normally take them. The degree audit uses this map."
          columns={[{ key: "code", header: "Code", render: (r) => <span className="mono">{r.code}</span> }, { key: "title", header: "Course" },
            { key: "credits", header: "Credits", className: "num" },
            { key: "category", header: "Type", render: (r) => <Badge tone={r.category === "core" ? "brand" : undefined}>{titleCase(r.category)}</Badge> },
            { key: "when", header: "Recommended", render: (r) => `Year ${r.recommended_year}, semester ${r.recommended_semester}` }]}
          fields={[{ key: "curriculum", label: "Curriculum", type: "select", default: curriculum, hidden: () => true, options: [[curriculum, curriculum]] },
            { key: "course", label: "Course", type: "select", required: true, span2: true,
              optionsFrom: { path: "/universities/courses/", label: (r) => `${r.code} · ${r.title} (${r.credit_hours} cr)` } },
            { key: "category", label: "Type", type: "select", required: true, default: "core", options: [["core", "Core"], ["elective", "Elective"]] },
            { key: "recommended_year", label: "Year", type: "number", default: 1, min: 1, max: 8 },
            { key: "recommended_semester", label: "Semester", type: "number", default: 1, min: 1, max: 3 }]}
          deleteConfirm={(r) => `Remove ${r.code} from this curriculum?`} />
      )}
    </div>
  );
}

export default function UniversitySetup() {
  const [tab, setTab] = useState("calendar");
  return (
    <>
      <PageHeader title="Academic setup" description="Calendar and registration windows, faculties and departments, degree programmes and curriculum mapping. Courses and sections live under Programs & courses and Course offerings." />
      <Tabs value={tab} onChange={setTab} label="Setup sections" tabs={[
        { value: "calendar", label: "Calendar" }, { value: "windows", label: "Registration windows" },
        { value: "org", label: "Faculties & departments" }, { value: "programs", label: "Programmes" },
        { value: "curricula", label: "Curricula" },
      ]} />
      {tab === "calendar" && <CalendarSetup childKind="semester" childLabel="Semesters" />}
      {tab === "windows" && <SemesterWindows />}
      {tab === "org" && <Organisation />}
      {tab === "programs" && <Programs />}
      {tab === "curricula" && <Curricula />}
    </>
  );
}
