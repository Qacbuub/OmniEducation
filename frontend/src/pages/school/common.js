import { useAuth } from "../../auth/AuthContext";
import { can } from "../../config/roles";
import { useApi } from "../../utils/hooks";

/** Classes the user works with this year: everything for managers, own classes for teachers. */
export function useMyClasses() {
  const { user } = useAuth();
  const all = can(user, "school.classes.manage", "students.view", "school.results.publish");
  const res = useApi(all ? "/schools/classes/" : "/schools/classes/mine/", all ? { current: 1, page_size: 100 } : undefined);
  const list = Array.isArray(res.data) ? res.data : res.data?.results || [];
  return { ...res, classes: list, all };
}

/** Terms of the current academic year, oldest first, plus the current term's id. */
export function useTerms() {
  const res = useApi("/academic-periods/", { kind: "term", page_size: 50 });
  const terms = (res.data?.results || []).slice().sort((a, b) => a.start_date.localeCompare(b.start_date));
  const current = terms.find((t) => t.is_current) || terms[terms.length - 1];
  return { terms, current, loading: res.loading };
}

export const classOptions = (classes) => classes.map((c) => ({ value: c.id, label: c.label }));
export const termOptions = (terms) => terms.map((t) => ({ value: t.id, label: t.name }));
export const today = () => new Date().toLocaleDateString("en-CA");
