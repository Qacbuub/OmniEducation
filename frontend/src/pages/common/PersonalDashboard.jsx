import { Link } from "react-router-dom";
import {
  LuBookOpen, LuCalendarDays, LuClipboardCheck, LuGraduationCap, LuListChecks, LuNotebookPen, LuTrendingUp, LuUsers, LuWallet,
} from "react-icons/lu";
import { useAuth } from "../../auth/AuthContext";
import { navForUser } from "../../config/navigation";
import { ROLE_LABELS, ROLES as R } from "../../config/roles";
import { useApi } from "../../utils/hooks";
import { money, shortDate, timeAgo } from "../../utils/format";
import { Badge, Card, EmptyState, PageHeader, Spinner, StatCard } from "../../components/ui";
import { ProgressBar } from "../../components/ui/extra";

const todayIndex = () => (new Date().getDay() + 6) % 7; // Mon = 0 … Sun = 6
const todayISO = () => new Date().toISOString().slice(0, 10);
const hhmm = (t) => (t || "").slice(0, 5);

/* ---------------------------------------------------------------- shared widgets */
function TodayClasses({ items, empty = "No classes today." }) {
  const today = (items || []).filter((m) => m.day === todayIndex()).sort((a, b) => a.start_time.localeCompare(b.start_time));
  return (
    <Card title="Today" subtitle={new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}>
      {!items ? <Spinner /> : today.length === 0 ? <p className="muted">{empty}</p> : (
        <ul className="list">
          {today.map((m) => (
            <li className="list__item" key={m.id}>
              <span className="list__dot" />
              <div>
                <div className="list__title">{hhmm(m.start_time)}–{hhmm(m.end_time)} · {m.title}</div>
                <div className="list__meta">{[m.sub, m.room].filter(Boolean).join(" · ")}</div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Announcements() {
  const { mode } = useAuth();
  const ann = useApi("/announcements/", { page_size: 4 });
  const notes = useApi("/notifications/", { page_size: 4 });
  const items = [
    ...(ann.data?.results || []).map((a) => ({ key: `a${a.id}`, title: a.title, body: a.body, at: a.created_at, pinned: a.pinned })),
    ...(notes.data?.results || []).filter((n) => n.kind !== "announcement").map((n) => ({ key: `n${n.id}`, title: n.title, body: n.body, at: n.created_at, unread: !n.read_at })),
  ].sort((a, b) => (b.pinned - a.pinned) || String(b.at).localeCompare(String(a.at))).slice(0, 6);
  return (
    <Card title="Announcements & notifications" actions={<Link to={`/${mode}/announcements`} className="btn btn--ghost btn--sm">All</Link>}>
      {ann.loading && !ann.data ? <Spinner /> : items.length === 0 ? <p className="muted">Nothing new.</p> : (
        <ul className="list">
          {items.map((n) => (
            <li className="list__item" key={n.key}>
              <span className="list__dot" />
              <div>
                <div className="list__title">{n.title} {n.pinned && <Badge tone="brand">Pinned</Badge>} {n.unread && <Badge tone="warning">New</Badge>}</div>
                <div className="list__meta">{n.body?.slice(0, 140)}{n.at ? ` · ${timeAgo(n.at)}` : ""}</div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function QuickLinks() {
  const { user, mode } = useAuth();
  const links = navForUser(mode, user.role).flatMap((g) => g.items).filter((i) => !i.end);
  return (
    <Card title="Quick links">
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(170px, 1fr))", gap: 10 }}>
        {links.map(({ to, label, icon: Icon }) => (
          <Link key={to + label} to={to} className="card" style={{ padding: 12, display: "flex", gap: 10, alignItems: "center", color: "var(--text)", textDecoration: "none" }}>
            <span className="stat__icon" style={{ width: 32, height: 32 }}><Icon aria-hidden="true" /></span>
            <span style={{ fontWeight: 600, fontSize: "var(--fs-sm)" }}>{label}</span>
          </Link>
        ))}
      </div>
    </Card>
  );
}

function FeeBalance({ invoices, currency }) {
  const open = (invoices || []).filter((i) => Number(i.balance) > 0 && i.status !== "void");
  const due = open.reduce((s, i) => s + Number(i.balance), 0);
  return <StatCard icon={LuWallet} label={open.some((i) => i.is_overdue) ? "Fee balance (overdue)" : "Fee balance"} value={invoices ? money(due, currency) : "…"} />;
}

/* ---------------------------------------------------------------- university student */
function StudentHome() {
  const { user, mode } = useAuth();
  const standing = useApi("/universities/standings/");
  const work = useApi("/universities/registrations/coursework/", { student: "me" });
  const tt = useApi("/universities/timetable/");
  const inv = useApi("/fees/invoices/", { page_size: 50 });
  const s = standing.data?.results?.[0];
  const courses = work.data?.courses || [];
  const credits = courses.filter((c) => c.status === "approved").reduce((n, c) => n + c.credit_hours, 0);
  return (
    <>
      <div className="grid grid--stats">
        <StatCard icon={LuTrendingUp} label="CGPA" value={s?.cgpa ?? "—"} />
        <StatCard icon={LuGraduationCap} label="Credits earned" value={s ? `${s.credits_earned}` : "—"} />
        <StatCard icon={LuBookOpen} label="Credits this semester" value={work.data ? credits : "…"} />
        <FeeBalance invoices={inv.data?.results} currency={user.tenant?.currency} />
      </div>
      {s?.standing === "probation" && (
        <Card><p style={{ margin: 0 }}><Badge tone="danger">Academic probation</Badge> Your CGPA is below the required minimum. Meet your adviser{ s.adviser_name ? ` (${s.adviser_name})` : ""} to plan your courses.</p></Card>
      )}
      <div className="grid grid--3-1">
        <Card title="My courses this semester" subtitle={work.data?.semester?.name}
          actions={<Link to={`/${mode}/my-courses`} className="btn btn--ghost btn--sm">Marks</Link>}>
          {!work.data ? <Spinner /> : courses.length === 0 ? (
            <EmptyState title="No courses yet">Register for this semester's courses under <Link to={`/${mode}/registration`}>Course registration</Link>.</EmptyState>
          ) : (
            <ul className="list">
              {courses.map((c) => (
                <li className="list__item" key={c.registration}>
                  <span className="list__dot" />
                  <div style={{ flex: 1 }}>
                    <div className="list__title">{c.course_code} {c.course_title} {c.status === "pending" && <Badge tone="warning">Awaiting adviser</Badge>}
                      {c.letter && <Badge tone="success">{c.letter}</Badge>}</div>
                    <div className="list__meta">{c.lecturer || "Lecturer TBA"} · {c.credit_hours} credits ·{" "}
                      {c.percent_so_far != null ? `${c.percent_so_far}% so far on ${c.weight_marked}% marked` : "no marks yet"}</div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <TodayClasses items={tt.data?.meetings?.map((m) => ({ ...m, title: `${m.course_code} ${m.course_title}`, sub: m.lecturer }))} />
      </div>
      <div className="grid grid--2"><Announcements /><QuickLinks /></div>
    </>
  );
}

/* ---------------------------------------------------------------- lecturer */
function LecturerHome() {
  const { mode } = useAuth();
  const tt = useApi("/universities/timetable/");
  const mine = useApi("/universities/offerings/mine/");
  const semId = tt.data?.semester?.id;
  const current = (mine.data || []).filter((o) => !semId || o.semester === semId);
  const students = current.reduce((n, o) => n + (o.enrolled || 0), 0);
  const toSubmit = current.filter((o) => ["not_started", "in_progress", "draft", "returned", null, undefined].includes(o.grade_status));
  return (
    <>
      <div className="grid grid--stats">
        <StatCard icon={LuBookOpen} label="Sections this semester" value={mine.data ? current.length : "…"} />
        <StatCard icon={LuUsers} label="Students taught" value={mine.data ? students : "…"} />
        <StatCard icon={LuListChecks} label="Grades still to submit" value={mine.data ? toSubmit.length : "…"} />
        <StatCard icon={LuCalendarDays} label="Grades due" value={tt.data?.semester?.grades_due ? shortDate(tt.data.semester.grades_due) : "—"} />
      </div>
      <div className="grid grid--3-1">
        <Card title="My sections" subtitle={tt.data?.semester?.name} bodyClass="">
          {!mine.data ? <Spinner /> : current.length === 0 ? <EmptyState title="No sections assigned this semester" /> : (
            <table className="table">
              <thead><tr><th>Section</th><th className="num">Students</th><th>Grades</th><th /></tr></thead>
              <tbody>
                {current.map((o) => (
                  <tr key={o.id}>
                    <td><strong>{o.course_code}-{o.section}</strong> {o.course_title}</td>
                    <td className="num">{o.enrolled} / {o.capacity}</td>
                    <td><Badge tone={o.grade_status === "approved" ? "success" : o.grade_status === "returned" ? "danger" : undefined}>{(o.grade_status || "not started").replace("_", " ")}</Badge></td>
                    <td className="num"><Link className="btn btn--ghost btn--sm" to={`/${mode}/gradebook?offering=${o.id}`}>Gradebook</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
        <TodayClasses items={tt.data?.meetings?.map((m) => ({ ...m, title: `${m.course_code}-${m.section}`, sub: m.course_title }))} />
      </div>
      <div className="grid grid--2"><Announcements /><QuickLinks /></div>
    </>
  );
}

/* ---------------------------------------------------------------- adviser */
function AdviserHome() {
  const { mode } = useAuth();
  const pending = useApi("/universities/registrations/", { status: "pending", page_size: 8 });
  const advisees = useApi("/universities/standings/", { page_size: 200 });
  const rows = advisees.data?.results || [];
  const probation = rows.filter((r) => r.standing === "probation");
  return (
    <>
      <div className="grid grid--stats">
        <StatCard icon={LuUsers} label="Advisees" value={advisees.data ? advisees.data.count : "…"} />
        <StatCard icon={LuClipboardCheck} label="Requests to approve" value={pending.data ? pending.data.count : "…"} />
        <StatCard icon={LuTrendingUp} label="On probation" value={advisees.data ? probation.length : "…"} />
      </div>
      <div className="grid grid--2">
        <Card title="Registration requests" actions={<Link to={`/${mode}/registration`} className="btn btn--ghost btn--sm">Review</Link>}>
          {!pending.data ? <Spinner /> : pending.data.count === 0 ? <p className="muted">Nothing waiting for you.</p> : (
            <ul className="list">
              {pending.data.results.map((r) => (
                <li className="list__item" key={r.id}><span className="list__dot" />
                  <div><div className="list__title">{r.student_name} · {r.course_code}</div><div className="list__meta">{r.course_title} · {r.credit_hours} credits · {timeAgo(r.created_at)}</div></div></li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Advisees needing attention" subtitle="On academic probation">
          {probation.length === 0 ? <p className="muted">All advisees are in good standing.</p> : (
            <ul className="list">
              {probation.map((r) => (
                <li className="list__item" key={r.id}><span className="list__dot" />
                  <div><div className="list__title"><Link to={`/${mode}/students/${r.student}`}>{r.student_name}</Link></div>
                    <div className="list__meta">{r.program_name} · CGPA {r.cgpa}</div></div></li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      <div className="grid grid--2"><Announcements /><QuickLinks /></div>
    </>
  );
}

/* ---------------------------------------------------------------- pupil */
function PupilHome() {
  const { user, mode } = useAuth();
  const att = useApi("/schools/attendance/summary/", { student: "me" });
  const results = useApi("/schools/results/", { page_size: 10 });
  const hw = useApi("/schools/assessments/", { page_size: 100, ordering: "due_date" });
  const tt = useApi("/schools/timetable/mine/");
  const inv = useApi("/fees/invoices/", { page_size: 50 });
  const latest = (results.data?.results || []).filter((r) => r.status === "published").slice(-1)[0];
  const upcoming = (hw.data?.results || []).filter((a) => a.due_date && a.due_date >= todayISO()).slice(0, 6);
  return (
    <>
      <div className="grid grid--stats">
        <StatCard icon={LuClipboardCheck} label={`Attendance${att.data?.term ? ` · ${att.data.term}` : ""}`} value={att.data?.attendance_rate != null ? `${att.data.attendance_rate}%` : "—"} />
        <StatCard icon={LuTrendingUp} label={latest ? `Average · ${latest.term_name}` : "Latest average"} value={latest ? `${latest.average}%` : "—"} />
        <StatCard icon={LuGraduationCap} label="Class position" value={latest ? `${latest.position} of ${latest.class_size}` : "—"} />
        <FeeBalance invoices={inv.data?.results} currency={user.tenant?.currency} />
      </div>
      <div className="grid grid--3-1">
        <Card title="Homework & tests coming up" actions={<Link to={`/${mode}/assignments`} className="btn btn--ghost btn--sm">All</Link>}>
          {!hw.data ? <Spinner /> : upcoming.length === 0 ? <p className="muted">Nothing due right now.</p> : (
            <ul className="list">
              {upcoming.map((a) => (
                <li className="list__item" key={a.id}><span className="list__dot" />
                  <div><div className="list__title">{a.subject_name}: {a.name}</div><div className="list__meta">Due {shortDate(a.due_date)} · {a.kind}</div></div></li>
              ))}
            </ul>
          )}
        </Card>
        <TodayClasses items={(tt.data || []).map((l) => ({ ...l, title: l.subject_name, sub: l.teacher_name }))} />
      </div>
      <div className="grid grid--2"><Announcements /><QuickLinks /></div>
    </>
  );
}

/* ---------------------------------------------------------------- guardian */
function GuardianHome() {
  const { user, mode } = useAuth();
  const kids = useApi("/students/");
  const children = kids.data?.results || [];
  return (
    <>
      <Card title="My children" actions={<Link to={`/${mode}/children`} className="btn btn--ghost btn--sm">Open</Link>}>
        {!kids.data ? <Spinner /> : children.length === 0 ? <EmptyState title="No children linked to your account">Ask the school office to link your children.</EmptyState> : (
          <div className="grid grid--2">
            {children.map((c) => <ChildCard key={c.id} child={c} currency={user.tenant?.currency} />)}
          </div>
        )}
      </Card>
      <div className="grid grid--2"><Announcements /><QuickLinks /></div>
    </>
  );
}

function ChildCard({ child, currency }) {
  const att = useApi("/schools/attendance/summary/", { student: child.id });
  const results = useApi("/schools/results/", { student: child.id, page_size: 10 });
  const latest = (results.data?.results || []).filter((r) => r.status === "published").slice(-1)[0];
  return (
    <div className="card" style={{ padding: 16 }}>
      <div className="list__title" style={{ fontSize: "var(--fs-md)" }}>{child.first_name} {child.last_name}</div>
      <div className="muted" style={{ fontSize: "var(--fs-xs)", marginBottom: 10 }}>{child.level} {child.section} · {child.student_no}</div>
      <div className="stack-sm">
        <ProgressBar value={att.data?.attendance_rate || 0} label={`Attendance ${att.data?.attendance_rate != null ? `${att.data.attendance_rate}%` : "—"}${att.data?.absent ? ` · ${att.data.absent} absences` : ""}`} />
        <div style={{ fontSize: "var(--fs-sm)" }}>{latest ? <>Latest report: <strong>{latest.average}% ({latest.grade})</strong> · {latest.term_name} · position {latest.position}/{latest.class_size}</> : "No published report yet."}</div>
        <div style={{ fontSize: "var(--fs-sm)" }}>Fee balance: <strong style={{ color: child.balance > 0 ? "var(--danger)" : undefined }}>{money(child.balance, currency)}</strong></div>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- teachers */
function TeacherHome() {
  const { mode } = useAuth();
  const classes = useApi("/schools/classes/mine/");
  const tt = useApi("/schools/timetable/mine/");
  const rows = classes.data || [];
  const homeroom = rows.filter((c) => c.is_homeroom);
  return (
    <>
      <div className="grid grid--stats">
        <StatCard icon={LuUsers} label="Classes I teach" value={classes.data ? rows.length : "…"} />
        <StatCard icon={LuGraduationCap} label="Pupils" value={classes.data ? rows.reduce((n, c) => n + c.pupil_count, 0) : "…"} />
        <StatCard icon={LuCalendarDays} label="Lessons today" value={tt.data ? tt.data.filter((l) => l.day === todayIndex()).length : "…"} />
        <StatCard icon={LuNotebookPen} label="Homeroom" value={homeroom.map((c) => c.label).join(", ") || "—"} />
      </div>
      <div className="grid grid--3-1">
        <Card title="My classes" bodyClass="">
          {!classes.data ? <Spinner /> : rows.length === 0 ? <EmptyState title="No classes assigned yet" /> : (
            <table className="table">
              <thead><tr><th>Class</th><th>My subjects</th><th className="num">Pupils</th><th /></tr></thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.id}>
                    <td><strong>{c.label}</strong> {c.is_homeroom && <Badge tone="brand">Homeroom</Badge>}</td>
                    <td className="muted">{(c.my_subjects?.length ? c.my_subjects : c.assignments || []).map((a) => a.subject_name).join(", ")}</td>
                    <td className="num">{c.pupil_count}</td>
                    <td className="num" style={{ whiteSpace: "nowrap" }}>
                      <Link className="btn btn--ghost btn--sm" to={`/${mode}/attendance?section=${c.id}`}>Attendance</Link>
                      <Link className="btn btn--ghost btn--sm" to={`/${mode}/marks?section=${c.id}`}>Marks</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
        <TodayClasses items={(tt.data || []).map((l) => ({ ...l, title: `${l.subject_name} · ${l.section_label}`, sub: `Period ${l.period_no}` }))} />
      </div>
      <div className="grid grid--2"><Announcements /><QuickLinks /></div>
    </>
  );
}

/** Dashboard for teachers, lecturers, advisers, guardians, pupils and students: their day at a glance. */
export default function PersonalDashboard() {
  const { user } = useAuth();
  const body = {
    [R.STUDENT]: <StudentHome />, [R.LECTURER]: <LecturerHome />, [R.ADVISER]: <AdviserHome />,
    [R.PUPIL]: <PupilHome />, [R.GUARDIAN]: <GuardianHome />, [R.CLASS_TEACHER]: <TeacherHome />, [R.SUBJECT_TEACHER]: <TeacherHome />,
  }[user.role];
  return (
    <>
      <PageHeader eyebrow={ROLE_LABELS[user.role]} title={`Welcome, ${user.first_name}`} description={`${user.tenant.name} · here's your day at a glance.`} />
      <div className="stack">{body || <div className="grid grid--2"><Announcements /><QuickLinks /></div>}</div>
    </>
  );
}
