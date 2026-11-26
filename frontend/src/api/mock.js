/**
 * Demo-mode API. Mirrors the Django REST endpoints so the UI can be developed
 * before the backend exists. Enabled with VITE_USE_MOCK=true.
 * All data is synthetic. Results are scoped by the logged-in user's tenant,
 * just as the real backend does server-side.
 */

const DEMO_PASSWORD = "Demo@1234";

const TENANTS = [
  { id: 1, name: "Sunrise Academy", slug: "sunrise", type: "school", city: "Nairobi", country: "Kenya",
    domain: "sunrise.omniedu.app", plan: "Standard", status: "active", students: 412, staff: 38, created_at: "2026-09-01" },
  { id: 2, name: "Omni University", slug: "omniu", type: "university", city: "Bellevue", country: "USA",
    domain: "omniu.omniedu.app", plan: "Enterprise", status: "active", students: 1860, staff: 164, created_at: "2026-08-15" },
  { id: 3, name: "Lakeside Primary", slug: "lakeside", type: "school", city: "Kisumu", country: "Kenya",
    domain: "lakeside.omniedu.app", plan: "Starter", status: "trial", students: 0, staff: 2, created_at: "2026-11-20" },
];

const USERS = [
  { id: 1, email: "superadmin@omniedu.app", first_name: "Platform", last_name: "Admin", role: "super_admin", tenant: null },
  // School
  { id: 10, email: "admin@sunrise.edu", first_name: "Grace", last_name: "Wanjiru", role: "inst_admin", tenant: 1 },
  { id: 11, email: "principal@sunrise.edu", first_name: "Daniel", last_name: "Otieno", role: "principal", tenant: 1 },
  { id: 12, email: "teacher@sunrise.edu", first_name: "Mary", last_name: "Achieng", role: "class_teacher", tenant: 1 },
  { id: 13, email: "subject@sunrise.edu", first_name: "Peter", last_name: "Kamau", role: "subject_teacher", tenant: 1 },
  { id: 14, email: "parent@sunrise.edu", first_name: "Ruth", last_name: "Mwangi", role: "guardian", tenant: 1 },
  { id: 15, email: "pupil@sunrise.edu", first_name: "Brian", last_name: "Mwangi", role: "pupil", tenant: 1 },
  { id: 16, email: "finance@sunrise.edu", first_name: "Joseph", last_name: "Njoroge", role: "finance_officer", tenant: 1 },
  // University
  { id: 20, email: "registrar@omniu.edu", first_name: "Sarah", last_name: "Collins", role: "registrar", tenant: 2 },
  { id: 21, email: "dean@omniu.edu", first_name: "Michael", last_name: "Hart", role: "dean", tenant: 2 },
  { id: 22, email: "hod@omniu.edu", first_name: "Aisha", last_name: "Bello", role: "dept_head", tenant: 2 },
  { id: 23, email: "lecturer@omniu.edu", first_name: "James", last_name: "Okafor", role: "lecturer", tenant: 2 },
  { id: 24, email: "adviser@omniu.edu", first_name: "Linda", last_name: "Park", role: "adviser", tenant: 2 },
  { id: 25, email: "student@omniu.edu", first_name: "Kevin", last_name: "Mutua", role: "student", tenant: 2 },
  { id: 26, email: "finance@omniu.edu", first_name: "Helen", last_name: "Ross", role: "finance_officer", tenant: 2 },
];

// ---- Synthetic students -------------------------------------------------
const FIRST = ["Amani", "Baraka", "Chloe", "David", "Esther", "Faith", "George", "Hannah", "Ian", "Joy", "Kevin", "Lucy", "Moses", "Naomi", "Oscar", "Purity", "Quinn", "Rose", "Samuel", "Tina", "Victor", "Wendy", "Yusuf", "Zawadi"];
const LAST = ["Kariuki", "Odhiambo", "Wambui", "Mutua", "Chebet", "Kiptoo", "Njeri", "Omondi", "Barasa", "Atieno", "Smith", "Garcia", "Nguyen", "Patel"];
const GRADES = ["Grade 1", "Grade 2", "Grade 3", "Grade 4", "Grade 5", "Grade 6", "Grade 7", "Grade 8"];
const PROGRAMS = ["BSc Computer Science", "BSc Cybersecurity", "BBA Finance", "BEng Electrical", "BA Economics"];

function seeded(n) { const x = Math.sin(n * 9301 + 49297) * 233280; return x - Math.floor(x); }

const STUDENTS = [];
for (let i = 0; i < 64; i++) {
  const school = i % 2 === 0;
  const fn = FIRST[Math.floor(seeded(i) * FIRST.length)];
  const ln = LAST[Math.floor(seeded(i + 100) * LAST.length)];
  const status = seeded(i + 7) > 0.92 ? "withdrawn" : seeded(i + 3) > 0.85 ? "pending" : "active";
  STUDENTS.push(school
    ? { id: i + 1, tenant: 1, student_no: `SUN-2026-${String(i + 1).padStart(4, "0")}`, first_name: fn, last_name: ln,
        level: GRADES[Math.floor(seeded(i + 5) * GRADES.length)], section: ["A", "B"][i % 4 < 2 ? 0 : 1],
        guardian: `${FIRST[(i + 3) % FIRST.length]} ${ln}`, status, balance: Math.round(seeded(i + 11) * 4) * 2500 }
    : { id: i + 1, tenant: 2, student_no: `OMU-26-${String(i + 1).padStart(5, "0")}`, first_name: fn, last_name: ln,
        level: PROGRAMS[Math.floor(seeded(i + 5) * PROGRAMS.length)], section: `Year ${1 + Math.floor(seeded(i + 9) * 4)}`,
        cgpa: (2 + seeded(i + 13) * 2).toFixed(2), status, balance: Math.round(seeded(i + 11) * 5) * 450 });
}

const NOTIFICATIONS = {
  1: [
    { id: 1, title: "Mid-term exams start Monday", body: "Timetable published for Grades 4–8.", created_at: "2h ago", read: false },
    { id: 2, title: "3 new admission applications", body: "Awaiting review by the registrar.", created_at: "5h ago", read: false },
    { id: 3, title: "Fee reminder sent", body: "Term 3 reminders sent to 58 guardians.", created_at: "Yesterday", read: true },
  ],
  2: [
    { id: 4, title: "Add/drop window closes Friday", body: "Semester 1 2026/27 registration changes end 28 Nov.", created_at: "1h ago", read: false },
    { id: 5, title: "12 grade sheets awaiting approval", body: "Department of Computing.", created_at: "3h ago", read: false },
    { id: 6, title: "Graduation clearance opened", body: "Final-year students can now apply.", created_at: "2 days ago", read: true },
  ],
};

// ---- Helpers --------------------------------------------------------------
const delay = (ms = 250) => new Promise((r) => setTimeout(r, ms));
const clone = (v) => JSON.parse(JSON.stringify(v));

function fail(status, message, code = "error", fields = {}) {
  const err = new Error(message);
  err.status = status; err.code = code; err.fields = fields;
  throw err;
}

function publicUser(u) {
  const tenant = u.tenant ? TENANTS.find((t) => t.id === u.tenant) : null;
  return { ...u, tenant: tenant ? { id: tenant.id, name: tenant.name, type: tenant.type, slug: tenant.slug } : null };
}

function currentUser() {
  let access = null;
  try { access = JSON.parse(localStorage.getItem("omniedu.tokens"))?.access; } catch { /* ignore */ }
  const id = Number(String(access || "").replace("mock-access-", ""));
  const user = USERS.find((u) => u.id === id);
  if (!user) fail(401, "Authentication credentials were not provided.", "not_authenticated");
  return user;
}

function paginate(rows, params) {
  const page = Math.max(1, Number(params.get("page") || 1));
  const size = Number(params.get("page_size") || 10);
  return { count: rows.length, page, page_size: size, results: rows.slice((page - 1) * size, page * size) };
}

// ---- Routes ---------------------------------------------------------------
const routes = [
  ["POST", /^\/auth\/login\/$/, (_m, body) => {
    const errors = {};
    if (!body?.email) errors.email = ["Email is required."];
    if (!body?.password) errors.password = ["Password is required."];
    if (Object.keys(errors).length) fail(400, "Please correct the highlighted fields.", "validation_error", errors);
    const user = USERS.find((u) => u.email.toLowerCase() === body.email.trim().toLowerCase());
    if (!user || body.password !== DEMO_PASSWORD) fail(401, "Invalid email or password.", "invalid_credentials");
    return { access: `mock-access-${user.id}`, refresh: `mock-refresh-${user.id}`, user: publicUser(user) };
  }],

  ["POST", /^\/auth\/password-reset\/$/, () => ({
    message: "If an account exists for that email, a reset link has been sent.",
  })],

  ["POST", /^\/auth\/password-reset\/confirm\/$/, (_p, body) => {
    if (!body?.new_password || body.new_password.length < 8) fail(400, "Please correct the highlighted fields.", "validation_error", { new_password: ["This password is too short. It must contain at least 8 characters."] });
    return { message: "Your password has been reset." };
  }],

  ["GET", /^\/auth\/invitations\/[^/]+\/$/, () => ({
    email: "new.teacher@sunrise.edu", first_name: "", last_name: "", role: "Class Teacher", institution: "Sunrise Academy",
  })],

  ["GET", /^\/auth\/me\/$/, () => publicUser(currentUser())],

  ["GET", /^\/notifications\/$/, () => {
    const u = currentUser();
    return { count: 0, results: clone(NOTIFICATIONS[u.tenant] || []) };
  }],

  // Platform (super admin only)
  ["GET", /^\/platform\/stats\/$/, () => {
    if (currentUser().role !== "super_admin") fail(403, "You do not have permission to perform this action.", "permission_denied");
    return {
      institutions: TENANTS.length,
      schools: TENANTS.filter((t) => t.type === "school").length,
      universities: TENANTS.filter((t) => t.type === "university").length,
      active_users: 2024,
      pending_invitations: 2,
      recent_activity: [
        { id: 1, action: "tenant.created", actor: "superadmin@omniedu.app", target: "Lakeside Primary", at: "2026-11-20 09:12" },
        { id: 2, action: "invitation.sent", actor: "superadmin@omniedu.app", target: "admin@lakeside.edu", at: "2026-11-20 09:15" },
        { id: 3, action: "tenant.settings.updated", actor: "registrar@omniu.edu", target: "Omni University", at: "2026-11-19 16:40" },
      ],
    };
  }],

  ["GET", /^\/tenants\/$/, (params) => {
    if (currentUser().role !== "super_admin") fail(403, "You do not have permission to perform this action.", "permission_denied");
    const q = (params.get("search") || "").toLowerCase();
    const type = params.get("type") || "";
    const rows = TENANTS.filter((t) => (!q || t.name.toLowerCase().includes(q)) && (!type || t.type === type));
    return paginate(clone(rows), params);
  }],

  ["POST", /^\/tenants\/$/, (_p, body) => {
    if (currentUser().role !== "super_admin") fail(403, "You do not have permission to perform this action.", "permission_denied");
    const errors = {};
    if (!body?.name?.trim()) errors.name = ["Institution name is required."];
    if (!["school", "university"].includes(body?.type)) errors.type = ["Choose school or university."];
    if (!/^[a-z0-9-]{3,30}$/.test(body?.slug || "")) errors.slug = ["3–30 lowercase letters, numbers or hyphens."];
    if (TENANTS.some((t) => t.slug === body?.slug)) errors.slug = ["This short name is already taken."];
    if (!/^\S+@\S+\.\S+$/.test(body?.admin_email || "")) errors.admin_email = ["Enter a valid email address."];
    if (Object.keys(errors).length) fail(400, "Please correct the highlighted fields.", "validation_error", errors);
    const t = { id: TENANTS.length + 1, name: body.name.trim(), slug: body.slug, type: body.type,
      city: body.city || "", country: body.country || "", domain: `${body.slug}.omniedu.app`,
      plan: body.plan || "Starter", status: "trial", students: 0, staff: 1, created_at: new Date().toISOString().slice(0, 10) };
    TENANTS.push(t);
    return clone(t);
  }],

  // Students (tenant scoped)
  ["GET", /^\/students\/$/, (params) => {
    const u = currentUser();
    if (u.role === "super_admin") fail(403, "Platform administrators cannot browse private student records.", "permission_denied");
    if (["guardian", "pupil", "student"].includes(u.role)) fail(403, "You do not have permission to perform this action.", "permission_denied");
    const q = (params.get("search") || "").toLowerCase();
    const status = params.get("status") || "";
    const rows = STUDENTS.filter((s) => s.tenant === u.tenant
      && (!q || `${s.first_name} ${s.last_name} ${s.student_no}`.toLowerCase().includes(q))
      && (!status || s.status === status));
    return paginate(clone(rows), params);
  }],

  // Dashboards
  ["GET", /^\/schools\/dashboard\/$/, () => {
    const u = currentUser();
    if (u.tenant !== 1) fail(404, "Not found.", "not_found");
    return {
      term: "Term 3 · 2026",
      stats: { pupils: 412, attendance_today: 94.2, fees_collected: 3120000, fees_outstanding: 845000, pass_rate: 87.5 },
      enrollment_by_grade: GRADES.map((g, i) => ({ label: g.replace("Grade ", "G"), value: [58, 55, 52, 54, 50, 49, 47, 47][i] })),
      attendance_trend: [
        { label: "Wk 1", value: 95.1 }, { label: "Wk 2", value: 94.6 }, { label: "Wk 3", value: 92.8 }, { label: "Wk 4", value: 93.9 },
        { label: "Wk 5", value: 95.4 }, { label: "Wk 6", value: 94.2 }, { label: "Wk 7", value: 93.1 }, { label: "Wk 8", value: 94.2 },
      ],
      pass_rate_by_term: [
        { label: "T1 '25", value: 81 }, { label: "T2 '25", value: 83 }, { label: "T3 '25", value: 84 },
        { label: "T1 '26", value: 85 }, { label: "T2 '26", value: 86 }, { label: "T3 '26", value: 87.5 },
      ],
      fee_collection: [
        { label: "Collected", value: 3120000 }, { label: "Outstanding", value: 845000 },
      ],
      upcoming: [
        { title: "Mid-term exams", meta: "Mon 30 Nov – Fri 4 Dec" },
        { title: "Parents' meeting", meta: "Sat 5 Dec · 10:00" },
        { title: "Term 3 report cards published", meta: "Fri 11 Dec" },
      ],
    };
  }],

  ["GET", /^\/universities\/dashboard\/$/, () => {
    const u = currentUser();
    if (u.tenant !== 2) fail(404, "Not found.", "not_found");
    return {
      semester: "Semester 1 · 2026/27",
      stats: { students: 1860, registrations: 9214, avg_cgpa: 3.12, fee_arrears: 418500, on_probation: 74 },
      enrollment_by_program: PROGRAMS.map((p, i) => ({ label: p.replace(/^B\w+ /, ""), value: [612, 388, 341, 297, 222][i] })),
      course_demand: [
        { label: "CS201 Data Structures", value: 96, capacity: 100 },
        { label: "CY210 Network Security", value: 80, capacity: 80 },
        { label: "FN220 Corporate Finance", value: 71, capacity: 90 },
        { label: "EE230 Circuits II", value: 54, capacity: 60 },
        { label: "EC101 Microeconomics", value: 118, capacity: 150 },
      ],
      gpa_distribution: [
        { label: "<2.0", value: 74 }, { label: "2.0–2.49", value: 213 }, { label: "2.5–2.99", value: 402 },
        { label: "3.0–3.49", value: 611 }, { label: "3.5–4.0", value: 560 },
      ],
      upcoming: [
        { title: "Add/drop window closes", meta: "Fri 28 Nov · 23:59" },
        { title: "Mid-semester grade submission", meta: "Mon 7 Dec" },
        { title: "Graduation clearance deadline", meta: "Fri 18 Dec" },
      ],
    };
  }],
];

export async function mockRequest(method, pathWithQuery, body) {
  await delay();
  const [path, qs = ""] = pathWithQuery.split("?");
  const params = new URLSearchParams(qs);
  const route = routes.find(([m, re]) => m === method && re.test(path));
  try {
    if (!route) fail(404, `Demo mode: no mock for ${method} ${path}`, "not_found");
    return route[2](params, body, path);
  } catch (e) {
    const { ApiError } = await import("./client");
    if (e.status === 401) {
      try { localStorage.removeItem("omniedu.tokens"); } catch { /* ignore */ }
      window.dispatchEvent(new Event("omniedu:logout"));
    }
    throw new ApiError(e.status || 500, { code: e.code, message: e.message, fields: e.fields });
  }
}

