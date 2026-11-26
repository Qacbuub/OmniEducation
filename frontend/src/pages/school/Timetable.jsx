import { useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import { useApi } from "../../utils/hooks";
import { Card, PageHeader, Spinner } from "../../components/ui";
import { SelectBox, WeekGrid } from "../../components/ui/extra";
import { classOptions, useMyClasses } from "./common";

function ClassGrid({ sectionId }) {
  const { data, loading } = useApi(sectionId ? `/schools/classes/${sectionId}/timetable/` : null);
  if (loading && !data) return <Spinner />;
  return <WeekGrid items={(data || []).map((l) => ({ ...l, title: l.subject_name, sub: l.teacher_name }))} />;
}

/** Family view: pick a child, show their class timetable. */
function FamilyTimetable() {
  const kids = useApi("/schools/children/");
  const [child, setChild] = useState("");
  const list = kids.data || [];
  const childId = child || list[0]?.id;
  const placement = useApi(childId ? "/schools/placements/" : null, { student: childId, status: "active" });
  const sectionId = placement.data?.results?.[0]?.section;
  return (
    <>
      {list.length > 1 && (
        <div className="toolbar">
          <SelectBox id="tt-child" label="Child" value={childId} onChange={setChild} options={list.map((c) => ({ value: c.id, label: c.name }))} />
        </div>
      )}
      <Card title={placement.data?.results?.[0]?.section_label ? `${placement.data.results[0].section_label} timetable` : "Timetable"}>
        {sectionId ? <ClassGrid sectionId={sectionId} /> : placement.loading ? <Spinner /> : <p className="muted">Not placed in a class this year.</p>}
      </Card>
    </>
  );
}

function TeacherTimetable() {
  const { data, loading } = useApi("/schools/timetable/mine/");
  if (loading && !data) return <Spinner />;
  return (
    <Card title="My lessons this week">
      <WeekGrid items={(data || []).map((l) => ({ ...l, title: `${l.section_label} · ${l.subject_name}` }))} empty="You have no timetabled lessons." />
    </Card>
  );
}

export default function Timetable() {
  const { user } = useAuth();
  const role = user.role;
  const { classes } = useMyClasses();
  const [section, setSection] = useState("");
  const [view, setView] = useState("mine");
  const family = role === "guardian" || role === "pupil";
  const teacher = role === "class_teacher" || role === "subject_teacher";
  const sectionId = section || classes[0]?.id;
  return (
    <>
      <PageHeader title="Timetable" description="Weekly lessons by class. The server prevents a class, teacher or room being double-booked." />
      {family ? <FamilyTimetable /> : (
        <>
          <div className="toolbar">
            {teacher && <SelectBox id="tt-view" label="View" value={view} onChange={setView}
              options={[{ value: "mine", label: "My lessons" }, { value: "class", label: "A class timetable" }]} />}
            {(!teacher || view === "class") && <SelectBox id="tt-class" label="Class" value={sectionId} onChange={setSection} options={classOptions(classes)} width={160} />}
          </div>
          {teacher && view === "mine" ? <TeacherTimetable /> : (
            <Card title={`${classes.find((c) => c.id === Number(sectionId))?.label || ""} timetable`}>
              {sectionId ? <ClassGrid sectionId={sectionId} /> : <Spinner />}
            </Card>
          )}
        </>
      )}
    </>
  );
}
