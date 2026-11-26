// Synthetic demo logins. The backend seed script (manage.py seed_demo) creates the same accounts.
export const DEMO_PASSWORD = "Demo@1234";

export const DEMO_ACCOUNTS = [
  { group: "Platform", accounts: [{ email: "superadmin@omniedu.app", role: "super_admin" }] },
  { group: "Sunrise Academy (school)", accounts: [
    { email: "admin@sunrise.edu", role: "inst_admin" },
    { email: "principal@sunrise.edu", role: "principal" },
    { email: "teacher@sunrise.edu", role: "class_teacher" },
    { email: "subject@sunrise.edu", role: "subject_teacher" },
    { email: "parent@sunrise.edu", role: "guardian" },
    { email: "pupil@sunrise.edu", role: "pupil" },
    { email: "finance@sunrise.edu", role: "finance_officer" },
  ]},
  { group: "Omni University", accounts: [
    { email: "registrar@omniu.edu", role: "registrar" },
    { email: "dean@omniu.edu", role: "dean" },
    { email: "hod@omniu.edu", role: "dept_head" },
    { email: "lecturer@omniu.edu", role: "lecturer" },
    { email: "adviser@omniu.edu", role: "adviser" },
    { email: "student@omniu.edu", role: "student" },
    { email: "finance@omniu.edu", role: "finance_officer" },
  ]},
];
