import { Link } from "react-router-dom";
import { LuUsers, LuBookMarked, LuGraduationCap, LuWallet, LuLayers, LuShieldCheck } from "react-icons/lu";
import { useAuth } from "../../auth/AuthContext";
import { useApi } from "../../utils/hooks";
import { compactMoney, number, orDash } from "../../utils/format";
import { ROLE_LABELS } from "../../config/roles";
import { Card, PageHeader, StatCard, Spinner, Alert } from "../../components/ui";
import { BarChart, HBarList } from "../../components/ui/charts";
import PersonalDashboard from "../common/PersonalDashboard";

const MANAGEMENT = ["inst_admin", "registrar", "dean", "dept_head", "finance_officer"];

export default function UniversityDashboard() {
  const { user } = useAuth();
  if (!MANAGEMENT.includes(user.role)) return <PersonalDashboard />;
  return <RegistrarDashboard user={user} />;
}

function RegistrarDashboard({ user }) {
  const { data, loading, error } = useApi("/universities/dashboard/");
  if (loading && !data) return <Spinner />;
  if (error) return <Alert tone="error">{error.message}</Alert>;
  const s = data.stats;

  return (
    <>
      <PageHeader
        eyebrow={data.semester}
        title={`Good day, ${user.first_name}`}
        description={`${ROLE_LABELS[user.role]} overview for ${user.tenant.name}.`}
        actions={<>
          <Link className="btn btn--secondary" to="/university/programs"><LuLayers /> Programs</Link>
          <Link className="btn btn--primary" to="/university/grade-approvals"><LuShieldCheck /> Grade approvals</Link>
        </>}
      />

      <div className="grid grid--stats" style={{ marginBottom: 16 }}>
        <StatCard icon={LuUsers} label="Matriculated students" value={number(s.students)} />
        <StatCard icon={LuBookMarked} label="Course registrations" value={number(s.registrations)} />
        <StatCard icon={LuGraduationCap} label="Average CGPA" value={orDash(s.avg_cgpa, (v) => Number(v).toFixed(2))}
          delta={s.on_probation ? `${s.on_probation} on probation` : undefined} deltaDir="down" />
        <StatCard icon={LuWallet} label="Fee arrears" value={compactMoney(s.fee_arrears, data.currency || "USD")} />
      </div>

      <div className="grid grid--2" style={{ marginBottom: 16 }}>
        <Card title="Enrollment by program" subtitle="Active students this semester">
          <BarChart data={data.enrollment_by_program} title="Enrollment by program" />
        </Card>
        <Card title="GPA distribution" subtitle="Cumulative GPA, all active students">
          <BarChart data={data.gpa_distribution} title="CGPA distribution" color="var(--black)" />
        </Card>
      </div>

      <div className="grid grid--3-1">
        <Card title="Course demand" subtitle="Registered seats vs capacity · black = full">
          <HBarList data={data.course_demand} />
        </Card>
        <Card title="Key dates">
          <ul className="list">
            {data.upcoming.length === 0 && <li className="list__item muted">Nothing scheduled.</li>}
            {data.upcoming.map((u) => (
              <li className="list__item" key={u.title}>
                <span className="list__dot" />
                <div><div className="list__title">{u.title}</div><div className="list__meta">{u.meta}</div></div>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </>
  );
}
