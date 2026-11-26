// Role keys must match the backend Role.code values.
export const ROLES = {
  // Platform
  SUPER_ADMIN: "super_admin",
  // Shared institution roles
  INST_ADMIN: "inst_admin",
  REGISTRAR: "registrar",
  FINANCE: "finance_officer",
  // School (K-12)
  PRINCIPAL: "principal",
  CLASS_TEACHER: "class_teacher",
  SUBJECT_TEACHER: "subject_teacher",
  GUARDIAN: "guardian",
  PUPIL: "pupil",
  // University
  DEAN: "dean",
  DEPT_HEAD: "dept_head",
  LECTURER: "lecturer",
  ADVISER: "adviser",
  STUDENT: "student",
};

export const ROLE_LABELS = {
  super_admin: "Platform Super Admin",
  inst_admin: "Institution Admin",
  registrar: "Registrar",
  finance_officer: "Finance Officer",
  principal: "Principal",
  class_teacher: "Class Teacher",
  subject_teacher: "Subject Teacher",
  guardian: "Parent / Guardian",
  pupil: "Pupil",
  dean: "Dean",
  dept_head: "Department Head",
  lecturer: "Lecturer",
  adviser: "Academic Adviser",
  student: "Student",
};

export const MODE = { PLATFORM: "platform", SCHOOL: "school", UNIVERSITY: "university" };

/** Which navigation shell a user gets. */
export function modeForUser(user) {
  if (!user) return null;
  if (user.role === ROLES.SUPER_ADMIN) return MODE.PLATFORM;
  return user.tenant?.type === "university" ? MODE.UNIVERSITY : MODE.SCHOOL;
}

export function homePathForUser(user) {
  const mode = modeForUser(user);
  if (mode === MODE.PLATFORM) return "/platform";
  if (mode === MODE.UNIVERSITY) return "/university";
  return "/school";
}

/** True if the user's role grants any of the permission codes (UX only; the API enforces them). */
export function can(user, ...codes) {
  const held = user?.permissions || [];
  return codes.some((c) => held.includes(c));
}
