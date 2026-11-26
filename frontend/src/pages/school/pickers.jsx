import { useEffect, useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import { can } from "../../config/roles";
import { SelectBox } from "../../components/ui/extra";
import { classOptions, termOptions, useMyClasses, useTerms } from "./common";

/**
 * Class → subject → term selector for teachers. Teachers only get the subjects they teach in each class;
 * the principal gets every subject. `onUserChange` fires when the user changes the selection; `select()` sets it from code.
 */
export function useClassSubjectTerm({ onUserChange, initialSection = "" } = {}) {
  const { user } = useAuth();
  const { classes, loading } = useMyClasses();
  const { terms, current } = useTerms();
  const [sel, setSel] = useState({ section: initialSection, subject: "", term: "" });
  const everything = can(user, "school.results.publish");
  const section = classes.find((c) => String(c.id) === String(sel.section)) || classes[0];
  const subjects = section ? (everything ? section.assignments : section.my_subjects || section.assignments.filter((a) => a.teacher === user.id)) : [];
  const subject = subjects.find((a) => String(a.subject) === String(sel.subject)) || subjects[0];
  const term = sel.term || current?.id || "";
  useEffect(() => { if (!sel.term && current) setSel((s) => ({ ...s, term: current.id })); }, [current, sel.term]);

  const pick = (patch) => { setSel((s) => ({ ...s, ...patch })); onUserChange?.(); };
  const select = (next) => setSel({ section: next.section ?? "", subject: next.subject ?? "", term: next.term ?? "" });
  const picker = (
    <div className="toolbar">
      <SelectBox id="pick-class" label="Class" value={section?.id || ""} options={classOptions(classes)} width={150}
        onChange={(v) => pick({ section: v, subject: "" })} />
      <SelectBox id="pick-subject" label="Subject" value={subject?.subject || ""} width={190}
        options={subjects.map((a) => ({ value: a.subject, label: a.subject_name }))} onChange={(v) => pick({ subject: v })} />
      <SelectBox id="pick-term" label="Term" value={term} options={termOptions(terms)} width={170}
        onChange={(v) => pick({ term: v })} />
    </div>
  );
  return { picker, section, subject, term, loading, terms, select };
}
