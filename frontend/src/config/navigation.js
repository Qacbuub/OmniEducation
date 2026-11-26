import {
  LuLayoutDashboard, LuBuilding2, LuSettings, LuUserPlus, LuUsers, LuClipboardCheck,
  LuCalendarDays, LuBookOpen, LuFileText, LuWallet, LuBell, LuChartBar, LuHistory,
  LuGraduationCap, LuLayers, LuNotebookPen, LuListChecks, LuScrollText, LuBadgeCheck,
  LuShieldCheck, LuSchool, LuBookMarked, LuIdCard, LuMegaphone, LuSlidersHorizontal,
} from "react-icons/lu";
import { ROLES as R, MODE } from "./roles";

/**
 * Role-aware navigation. Each item lists the roles that may see it.
 * The backend enforces the same permissions; hiding a menu item is only UX.
 */
const ALL_SCHOOL_STAFF = [R.INST_ADMIN, R.REGISTRAR, R.PRINCIPAL, R.CLASS_TEACHER, R.SUBJECT_TEACHER, R.FINANCE];
const ALL_UNI_STAFF = [R.INST_ADMIN, R.REGISTRAR, R.DEAN, R.DEPT_HEAD, R.LECTURER, R.ADVISER, R.FINANCE];

const NAV = {
  [MODE.PLATFORM]: [
    { group: "Platform", items: [
      { to: "/platform", label: "Overview", icon: LuLayoutDashboard, end: true },
      { to: "/platform/institutions", label: "Institutions", icon: LuBuilding2 },
      { to: "/platform/invitations", label: "Admin invitations", icon: LuUserPlus },
      { to: "/platform/audit", label: "Audit history", icon: LuHistory },
    ]},
  ],

  [MODE.SCHOOL]: [
    { group: "Overview", items: [
      { to: "/school", label: "Dashboard", icon: LuLayoutDashboard, end: true },
      { to: "/school/announcements", label: "Announcements", icon: LuMegaphone },
    ]},
    { group: "Students", items: [
      { to: "/school/admissions", label: "Admissions", icon: LuUserPlus, roles: [R.INST_ADMIN, R.REGISTRAR, R.PRINCIPAL] },
      { to: "/school/students", label: "Pupils", icon: LuUsers, roles: ALL_SCHOOL_STAFF },
      { to: "/school/children", label: "My children", icon: LuUsers, roles: [R.GUARDIAN] },
      { to: "/school/children", label: "My school", icon: LuUsers, roles: [R.PUPIL] },
    ]},
    { group: "Academics", items: [
      { to: "/school/classes", label: "Classes & roster", icon: LuSchool, roles: [R.INST_ADMIN, R.PRINCIPAL, R.CLASS_TEACHER, R.SUBJECT_TEACHER] },
      { to: "/school/timetable", label: "Timetable", icon: LuCalendarDays },
      { to: "/school/attendance", label: "Attendance", icon: LuClipboardCheck, roles: [R.INST_ADMIN, R.PRINCIPAL, R.CLASS_TEACHER, R.SUBJECT_TEACHER] },
      { to: "/school/assignments", label: "Homework", icon: LuNotebookPen, roles: [R.PRINCIPAL, R.CLASS_TEACHER, R.SUBJECT_TEACHER, R.PUPIL, R.GUARDIAN] },
      { to: "/school/marks", label: "Marks entry", icon: LuListChecks, roles: [R.CLASS_TEACHER, R.SUBJECT_TEACHER, R.PRINCIPAL] },
      { to: "/school/report-cards", label: "Report cards", icon: LuFileText },
      { to: "/school/promotions", label: "Promotions", icon: LuBadgeCheck, roles: [R.INST_ADMIN, R.PRINCIPAL] },
    ]},
    { group: "Finance", items: [
      { to: "/school/fees", label: "Fee ledger", icon: LuWallet, roles: [R.INST_ADMIN, R.FINANCE, R.PRINCIPAL, R.GUARDIAN, R.PUPIL] },
    ]},
    { group: "Administration", items: [
      { to: "/school/setup", label: "Academic setup", icon: LuSlidersHorizontal, roles: [R.INST_ADMIN, R.PRINCIPAL] },
      { to: "/school/staff", label: "Staff", icon: LuIdCard, roles: [R.INST_ADMIN, R.PRINCIPAL] },
      { to: "/school/reports", label: "Reports", icon: LuChartBar, roles: [R.INST_ADMIN, R.PRINCIPAL, R.FINANCE] },
      { to: "/school/audit", label: "Audit history", icon: LuHistory, roles: [R.INST_ADMIN, R.PRINCIPAL] },
      { to: "/school/settings", label: "Settings", icon: LuSettings, roles: [R.INST_ADMIN] },
    ]},
  ],

  [MODE.UNIVERSITY]: [
    { group: "Overview", items: [
      { to: "/university", label: "Dashboard", icon: LuLayoutDashboard, end: true },
      { to: "/university/announcements", label: "Announcements", icon: LuMegaphone },
    ]},
    { group: "Students", items: [
      { to: "/university/admissions", label: "Admissions", icon: LuUserPlus, roles: [R.INST_ADMIN, R.REGISTRAR, R.DEAN] },
      { to: "/university/students", label: "Students", icon: LuUsers, roles: ALL_UNI_STAFF },
    ]},
    { group: "Academics", items: [
      { to: "/university/programs", label: "Programs & courses", icon: LuLayers, roles: [R.INST_ADMIN, R.REGISTRAR, R.DEAN, R.DEPT_HEAD] },
      { to: "/university/offerings", label: "Course offerings", icon: LuBookOpen, roles: [R.INST_ADMIN, R.REGISTRAR, R.DEAN, R.DEPT_HEAD] },
      { to: "/university/my-courses", label: "My courses & marks", icon: LuNotebookPen, roles: [R.STUDENT] },
      { to: "/university/registration", label: "Course registration", icon: LuBookMarked, roles: [R.STUDENT, R.ADVISER, R.REGISTRAR] },
      { to: "/university/timetable", label: "Timetable", icon: LuCalendarDays, roles: [R.STUDENT, R.LECTURER, R.ADVISER, R.REGISTRAR] },
      { to: "/university/gradebook", label: "Gradebook", icon: LuListChecks, roles: [R.LECTURER] },
      { to: "/university/grade-approvals", label: "Grade approvals", icon: LuShieldCheck, roles: [R.DEPT_HEAD, R.DEAN, R.REGISTRAR] },
      { to: "/university/transcript", label: "Transcript", icon: LuScrollText, roles: [R.STUDENT, R.REGISTRAR, R.ADVISER] },
      { to: "/university/degree-audit", label: "Degree audit", icon: LuGraduationCap, roles: [R.STUDENT, R.ADVISER, R.REGISTRAR] },
    ]},
    { group: "Finance", items: [
      { to: "/university/fees", label: "Fee ledger", icon: LuWallet, roles: [R.INST_ADMIN, R.FINANCE, R.REGISTRAR, R.STUDENT] },
    ]},
    { group: "Administration", items: [
      { to: "/university/setup", label: "Academic setup", icon: LuSlidersHorizontal, roles: [R.INST_ADMIN, R.REGISTRAR, R.DEAN, R.DEPT_HEAD] },
      { to: "/university/staff", label: "Staff", icon: LuIdCard, roles: [R.INST_ADMIN, R.REGISTRAR, R.DEAN] },
      { to: "/university/reports", label: "Reports", icon: LuChartBar, roles: [R.INST_ADMIN, R.REGISTRAR, R.DEAN, R.FINANCE] },
      { to: "/university/audit", label: "Audit history", icon: LuHistory, roles: [R.INST_ADMIN, R.REGISTRAR] },
      { to: "/university/settings", label: "Settings", icon: LuSettings, roles: [R.INST_ADMIN] },
    ]},
  ],
};

export const NOTIFICATIONS_ITEM = { label: "Notifications", icon: LuBell };

/** Navigation groups filtered for a role; empty groups are dropped. */
export function navForUser(mode, role) {
  return (NAV[mode] || [])
    .map((g) => ({ ...g, items: g.items.filter((i) => !i.roles || i.roles.includes(role)) }))
    .filter((g) => g.items.length > 0);
}
