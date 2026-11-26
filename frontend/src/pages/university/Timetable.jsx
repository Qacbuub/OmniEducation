import { useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import { can } from "../../config/roles";
import { useApi } from "../../utils/hooks";
import { Card, PageHeader, Spinner } from "../../components/ui";
import { StudentPicker, WeekGrid } from "../../components/ui/extra";

/** Student: own timetable. Lecturer: sections they teach. Registrar/adviser: any student's timetable. */
export default function UniTimetable() {
  const { user } = useAuth();
  const [student, setStudent] = useState(null);
  const lookup = can(user, "students.view", "uni.registration.approve") && user.role !== "student";
  const params = student ? { student: student.id } : undefined;
  const { data, loading } = useApi(!lookup || student || user.role === "lecturer" ? "/universities/timetable/" : null, params);
  return (
    <>
      <PageHeader title={user.role === "lecturer" ? "My teaching timetable" : "Timetable"}
        description={data?.semester ? `${data.semester.name}${data.owner ? ` · ${data.owner}` : ""}` : "Weekly class meetings this semester."} />
      {lookup && <div className="toolbar"><StudentPicker label="Show a student's timetable" value={student?.id} onChange={setStudent} /></div>}
      <Card>
        {loading && !data ? <Spinner /> : !data ? <p className="muted">Choose a student.</p> : (
          <WeekGrid days={6} items={data.meetings.map((m) => ({ ...m, title: `${m.course_code}-${m.section}`, sub: m.course_title }))}
            empty="No registered classes this semester." />
        )}
      </Card>
    </>
  );
}
