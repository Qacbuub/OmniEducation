import { Link } from "react-router-dom";
import { LuBuilding2, LuSchool, LuGraduationCap, LuUsers, LuPlus, LuShieldCheck } from "react-icons/lu";
import { useApi } from "../../utils/hooks";
import { number } from "../../utils/format";
import { Card, PageHeader, StatCard, Spinner, Alert } from "../../components/ui";

export default function PlatformDashboard() {
  const { data, loading, error } = useApi("/platform/stats/");
  if (loading && !data) return <Spinner />;
  if (error) return <Alert tone="error">{error.message}</Alert>;

  return (
    <>
      <PageHeader
        eyebrow="Platform administration"
        title="OmniEducation platform"
        description="Provision institutions, plans, domains and tenant administrators."
        actions={<Link className="btn btn--primary" to="/platform/institutions?new=1"><LuPlus /> New institution</Link>}
      />
      <div className="grid grid--stats" style={{ marginBottom: 16 }}>
        <StatCard icon={LuBuilding2} label="Institutions" value={number(data.institutions)} />
        <StatCard icon={LuSchool} label="Schools (K-12)" value={number(data.schools)} />
        <StatCard icon={LuGraduationCap} label="Universities" value={number(data.universities)} />
        <StatCard icon={LuUsers} label="Active users" value={number(data.active_users)} delta={`${data.pending_invitations} pending invitations`} />
      </div>
      <div className="grid grid--3-1">
        <Card title="Recent platform activity" subtitle="From the audit log" bodyClass="">
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th scope="col">Action</th><th scope="col">Actor</th><th scope="col">Target</th><th scope="col">When</th></tr></thead>
              <tbody>
                {data.recent_activity.map((a) => (
                  <tr key={a.id}>
                    <td><span className="mono">{a.action}</span></td>
                    <td>{a.actor}</td>
                    <td>{a.target}</td>
                    <td className="muted">{a.at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card title="Privacy by design">
          <div style={{ display: "flex", gap: 12 }}>
            <span className="stat__icon"><LuShieldCheck aria-hidden="true" /></span>
            <p className="muted" style={{ fontSize: "var(--fs-sm)" }}>
              Platform administrators manage institutions and their administrators, but cannot browse
              private student records. Every action is written to the audit log.
            </p>
          </div>
        </Card>
      </div>
    </>
  );
}
