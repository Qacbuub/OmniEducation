import { useEffect, useState } from "react";
import { LuPlus, LuSave, LuTrash2 } from "react-icons/lu";
import { api } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { useAction, useApi } from "../../utils/hooks";
import { titleCase } from "../../utils/format";
import { Alert, Button, Card, Field, PageHeader, Spinner } from "../../components/ui";
import { ActionFeedback } from "../../components/ui/extra";

const POLICY_HELP = {
  pass_mark: "Term average needed to pass (%)",
  promotion_min_average: "Year average needed for a promotion recommendation (%)",
  attendance_alert_absences: "Unexplained absences per term before staff are alerted",
  min_credits: "Minimum semester credit load", max_credits: "Maximum semester credit load",
  overload_max_credits: "Maximum load for high-CGPA students", overload_min_cgpa: "CGPA needed for the overload limit",
  probation_cgpa: "CGPA below which a student is on probation", graduation_min_cgpa: "Minimum CGPA to graduate",
  pass_grade_points: "Grade points needed to pass a course", repeat_policy: "Which attempt of a repeated course counts",
  max_course_attempts: "Maximum attempts per course", registration_requires_approval: "Student registrations need adviser approval",
};

export default function Settings() {
  const { user } = useAuth();
  const { data, error, reload } = useApi("/tenants/current/");
  const [f, setF] = useState(null);
  const [logo, setLogo] = useState(null);
  const act = useAction();
  useEffect(() => { if (data) setF(structuredClone(data)); }, [data]);
  if (error) return <Alert tone="error">{error.message}</Alert>;
  if (!f) return <Spinner />;
  const isUni = f.type === "university";
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  const err = (k) => act.error?.fields?.[k]?.[0];
  const setBand = (i, k, v) => setF((x) => ({ ...x, grading_scale: x.grading_scale.map((b, j) => (j === i ? { ...b, [k]: v } : b)) }));
  const setPolicy = (k, v) => setF((x) => ({ ...x, policies: { ...x.policies, [k]: v } }));

  async function save(e) {
    e.preventDefault();
    const body = {
      ...Object.fromEntries(["name", "contact_email", "contact_phone", "address", "city", "country", "accent_color", "currency",
        "timezone", "student_id_prefix"].map((k) => [k, f[k]])),
      grading_scale: f.grading_scale.map((b) => ({ ...b, min: Number(b.min), points: Number(b.points) })),
      policies: Object.fromEntries(Object.entries(f.policies).map(([k, v]) =>
        [k, typeof v === "boolean" || k === "repeat_policy" ? v : Number(v)])),
    };
    const ok = await act.run(() => api.patch("/tenants/current/", body), "Settings saved.");
    if (ok && logo) {
      const form = new FormData();
      form.append("logo", logo);
      await act.run(() => api.patch("/tenants/current/", form), "Settings and logo saved.");
    }
    if (ok) reload();
  }

  return (
    <form onSubmit={save} noValidate>
      <PageHeader title="Institution settings" description={`Branding, contact details, grading scale and policies for ${user.tenant.name}.`}
        actions={<Button type="submit" icon={LuSave} disabled={act.busy}>{act.busy ? "Saving…" : "Save changes"}</Button>} />
      <ActionFeedback act={act} />
      <div className="grid grid--2">
        <Card title="Institution & branding">
          <div className="form-grid">
            <Field label="Name" error={err("name")} className="span-2">{(a) => <input {...a} className="input" value={f.name} onChange={set("name")} />}</Field>
            <Field label="Accent colour" error={err("accent_color")}>{(a) => <input {...a} className="input mono" value={f.accent_color} onChange={set("accent_color")} />}</Field>
            <Field label="Logo" error={err("logo")} hint={f.logo ? "A logo is set; choose a file to replace it." : "PNG or JPG."}>
              {(a) => <input {...a} className="input" type="file" accept="image/png,image/jpeg" onChange={(e) => setLogo(e.target.files[0])} />}
            </Field>
            <Field label="Contact email" error={err("contact_email")}>{(a) => <input {...a} className="input" type="email" value={f.contact_email} onChange={set("contact_email")} />}</Field>
            <Field label="Contact phone">{(a) => <input {...a} className="input" value={f.contact_phone} onChange={set("contact_phone")} />}</Field>
            <Field label="Address" className="span-2">{(a) => <input {...a} className="input" value={f.address} onChange={set("address")} />}</Field>
            <Field label="City">{(a) => <input {...a} className="input" value={f.city} onChange={set("city")} />}</Field>
            <Field label="Country">{(a) => <input {...a} className="input" value={f.country} onChange={set("country")} />}</Field>
            <Field label="Currency" error={err("currency")}>{(a) => <input {...a} className="input mono" maxLength={3} value={f.currency} onChange={set("currency")} />}</Field>
            <Field label="Time zone">{(a) => <input {...a} className="input" value={f.timezone} onChange={set("timezone")} />}</Field>
            <Field label="Student ID prefix" error={err("student_id_prefix")}>{(a) => <input {...a} className="input mono" value={f.student_id_prefix} onChange={set("student_id_prefix")} />}</Field>
            <Field label="Workspace">{(a) => <input {...a} className="input mono" value={`${f.slug} · ${titleCase(f.type)}`} disabled />}</Field>
          </div>
        </Card>
        <Card title="Grading scale" subtitle={isUni ? "Minimum percentage, letter grade and grade points" : "Minimum percentage, grade and remark"}
          actions={<Button size="sm" variant="secondary" icon={LuPlus}
            onClick={() => setF((x) => ({ ...x, grading_scale: [...x.grading_scale, { min: 0, grade: "", points: 0, remark: "" }] }))}>Add band</Button>}>
          {err("grading_scale") && <Alert tone="error">{err("grading_scale")}</Alert>}
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Min %</th><th>Grade</th><th>Points</th>{!isUni && <th>Remark</th>}<th /></tr></thead>
            <tbody>
              {f.grading_scale.map((b, i) => (
                <tr key={i}>
                  <td><input aria-label="Minimum percentage" className="input score-input" type="number" value={b.min} onChange={(e) => setBand(i, "min", e.target.value)} /></td>
                  <td><input aria-label="Grade" className="input score-input" value={b.grade} onChange={(e) => setBand(i, "grade", e.target.value)} /></td>
                  <td><input aria-label="Grade points" className="input score-input" type="number" step="0.1" value={b.points} onChange={(e) => setBand(i, "points", e.target.value)} /></td>
                  {!isUni && <td><input aria-label="Remark" className="input" value={b.remark || ""} onChange={(e) => setBand(i, "remark", e.target.value)} /></td>}
                  <td><Button size="sm" variant="ghost" icon={LuTrash2} aria-label="Remove band"
                    onClick={() => setF((x) => ({ ...x, grading_scale: x.grading_scale.filter((_, j) => j !== i) }))} /></td>
                </tr>
              ))}
            </tbody>
          </table></div>
        </Card>
        <Card title="Academic policies" className="span-2" subtitle="Enforced by the server for every request.">
          {err("policies") && <Alert tone="error">{err("policies")}</Alert>}
          <div className="form-grid">
            {Object.entries(f.policies).map(([k, v]) => (
              <Field key={k} label={POLICY_HELP[k] || titleCase(k)}>
                {(a) => k === "repeat_policy" ? (
                  <select {...a} className="select" value={v} onChange={(e) => setPolicy(k, e.target.value)}>
                    <option value="latest_attempt">Latest attempt counts</option>
                    <option value="highest_attempt">Highest attempt counts</option>
                    <option value="all_attempts">All attempts count</option>
                  </select>
                ) : typeof v === "boolean" ? (
                  <select {...a} className="select" value={String(v)} onChange={(e) => setPolicy(k, e.target.value === "true")}>
                    <option value="true">Yes</option><option value="false">No</option>
                  </select>
                ) : <input {...a} className="input" type="number" step="0.1" value={v} onChange={(e) => setPolicy(k, e.target.value)} />}
              </Field>
            ))}
          </div>
        </Card>
      </div>
    </form>
  );
}
