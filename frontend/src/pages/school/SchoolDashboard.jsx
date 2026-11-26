import { Link } from "react-router-dom";
import { LuUsers, LuClipboardCheck, LuWallet, LuTrendingUp, LuUserPlus, LuFileText } from "react-icons/lu";
import { useAuth } from "../../auth/AuthContext";
import { useApi } from "../../utils/hooks";
import { compactMoney, money, number, orDash, pct } from "../../utils/format";
import { ROLE_LABELS } from "../../config/roles";
import { Card, PageHeader, StatCard, Spinner, Alert } from "../../components/ui";
import { BarChart, LineChart, Donut } from "../../components/ui/charts";
import PersonalDashboard from "../common/PersonalDashboard";

const MANAGEMENT = ["inst_admin", "principal", "registrar", "finance_officer"];

export default function SchoolDashboard() {
  const { user } = useAuth();
  if (!MANAGEMENT.includes(user.role)) return <PersonalDashboard />;
  return <ManagementDashboard user={user} />;
}

function ManagementDashboard({ user }) {
  const { data, loading, error } = useApi("/schools/dashboard/");
  if (loading && !data) return <Spinner />;
  if (error) return <Alert tone="error">{error.message}</Alert>;
  const s = data.stats;
  const cur = data.currency || "KES";

  return (
    <>
      <PageHeader
        eyebrow={data.term}
        title={`Good day, ${user.first_name}`}
        description={`${ROLE_LABELS[user.role]} overview for ${user.tenant.name}.`}
        actions={<>
          <Link className="btn btn--secondary" to="/school/admissions"><LuUserPlus /> New admission</Link>
          <Link className="btn btn--primary" to="/school/report-cards"><LuFileText /> Report cards</Link>
        </>}
      />

      <div className="grid grid--stats" style={{ marginBottom: 16 }}>
        <StatCard icon={LuUsers} label="Enrolled pupils" value={number(s.pupils)} />
        <StatCard icon={LuClipboardCheck} label="Attendance today" value={orDash(s.attendance_today, pct)} />
        <StatCard icon={LuWallet} label="Fees collected" value={compactMoney(s.fees_collected, cur)} delta={`${compactMoney(s.fees_outstanding, cur)} outstanding`} deltaDir="down" />
        <StatCard icon={LuTrendingUp} label="Pass rate (term)" value={orDash(s.pass_rate, pct)} />
      </div>

      <div className="grid grid--3-1" style={{ marginBottom: 16 }}>
        <Card title="Enrollment by grade" subtitle="Active pupils, current academic year">
          <BarChart data={data.enrollment_by_grade} title="Enrollment by grade" />
        </Card>
        <Card title="Fee collection" subtitle="All issued invoices">
          <Donut data={data.fee_collection} title="Fee collection, collected vs outstanding" format={(v) => money(v, cur)} />
        </Card>
      </div>

      <div className="grid grid--2" style={{ marginBottom: 16 }}>
        <Card title="Attendance trend" subtitle="Weekly average, % present">
          <LineChart data={data.attendance_trend} title="Weekly attendance percentage" min={88} max={98} format={(v) => `${v}%`} />
        </Card>
        <Card title="Pass-rate trend" subtitle="Pupils passing all core subjects">
          <BarChart data={data.pass_rate_by_term} title="Pass rate by term" format={(v) => `${v}%`} color="var(--black)" max={100} />
        </Card>
      </div>

      <Card title="Upcoming">
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
    </>
  );
}
