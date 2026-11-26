import { useState } from "react";
import { LuPlus } from "react-icons/lu";
import { api } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { can } from "../../config/roles";
import { useAction, useApi, useDebounced } from "../../utils/hooks";
import { Badge, Button, Card, Field, Modal, PageHeader, Spinner } from "../../components/ui";
import { DataTable } from "../../components/ui/DataTable";
import { ActionFeedback, KeyValues, SelectBox, Tabs } from "../../components/ui/extra";

function NewCourse({ departments, onClose, onDone }) {
  const [f, setF] = useState({ department: departments[0]?.id || "", code: "", title: "", credit_hours: 3, level: 100, description: "" });
  const act = useAction();
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  const err = (k) => act.error?.fields?.[k]?.[0];
  async function submit(e) { e.preventDefault(); if (await act.run(() => api.post("/universities/courses/", f))) onDone(); }
  return (
    <Modal title="New course" onClose={onClose}>
      <form onSubmit={submit} noValidate>
        <ActionFeedback act={act} />
        <div className="form-grid">
          <Field label="Code" error={err("code")}>{(a) => <input {...a} className="input mono" value={f.code} onChange={set("code")} placeholder="CS310" />}</Field>
          <Field label="Credit hours" error={err("credit_hours")}>{(a) => <input {...a} className="input" type="number" min="1" max="12" value={f.credit_hours} onChange={set("credit_hours")} />}</Field>
          <Field label="Title" error={err("title")} className="span-2">{(a) => <input {...a} className="input" value={f.title} onChange={set("title")} />}</Field>
          <Field label="Department" error={err("department")}>
            {(a) => <select {...a} className="select" value={f.department} onChange={set("department")}>{departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select>}
          </Field>
          <Field label="Level">{(a) => <select {...a} className="select" value={f.level} onChange={set("level")}>{[100, 200, 300, 400, 500].map((l) => <option key={l} value={l}>{l}</option>)}</select>}</Field>
          <Field label="Description" className="span-2">{(a) => <textarea {...a} className="textarea" rows={3} value={f.description} onChange={set("description")} />}</Field>
        </div>
        <div className="form-actions"><Button variant="secondary" onClick={onClose}>Cancel</Button><Button type="submit" disabled={act.busy}>Create course</Button></div>
      </form>
    </Modal>
  );
}

function AddPrerequisite({ course, onClose, onDone }) {
  const all = useApi("/universities/courses/", { page_size: 100 });
  const [pre, setPre] = useState("");
  const [minPoints, setMinPoints] = useState("1.0");
  const act = useAction();
  async function submit(e) {
    e.preventDefault();
    if (await act.run(() => api.post("/universities/prerequisites/", { course: course.id, prerequisite: pre, min_grade_points: minPoints }))) onDone();
  }
  return (
    <Modal title={`Prerequisite for ${course.code}`} onClose={onClose}>
      <form onSubmit={submit} noValidate>
        <ActionFeedback act={act} />
        <Field label="Required course" error={act.error?.fields?.prerequisite?.[0]}>
          {(a) => <select {...a} className="select" value={pre} onChange={(e) => setPre(e.target.value)}>
            <option value="">Choose…</option>
            {(all.data?.results || []).filter((c) => c.id !== course.id).map((c) => <option key={c.id} value={c.id}>{c.code} {c.title}</option>)}
          </select>}
        </Field>
        <Field label="Minimum grade points" hint="1.0 = a pass (D). Circular chains are rejected.">
          {(a) => <input {...a} className="input" type="number" step="0.1" min="0" max="4" value={minPoints} onChange={(e) => setMinPoints(e.target.value)} />}
        </Field>
        <div className="form-actions"><Button variant="secondary" onClick={onClose}>Cancel</Button><Button type="submit" disabled={!pre || act.busy}>Add prerequisite</Button></div>
      </form>
    </Modal>
  );
}

function Courses({ manage }) {
  const [search, setSearch] = useState("");
  const [dept, setDept] = useState("");
  const [page, setPage] = useState(1);
  const [modal, setModal] = useState(null);
  const q = useDebounced(search);
  const departments = useApi("/universities/departments/", { page_size: 100 });
  const { data, loading, error, reload } = useApi("/universities/courses/", { search: q, department: dept, page });
  const columns = [
    { key: "code", header: "Code", render: (c) => <span className="mono" style={{ fontWeight: 600 }}>{c.code}</span> },
    { key: "title", header: "Title", render: (c) => <>{c.title}{!c.is_active && <> <Badge>inactive</Badge></>}</> },
    { key: "credit_hours", header: "Credits", className: "num" },
    { key: "level", header: "Level", className: "num" },
    { key: "department_name", header: "Department" },
    { key: "prerequisites", header: "Prerequisites", render: (c) => c.prerequisites.length
      ? c.prerequisites.map((p) => <Badge key={p.id} tone="neutral">{p.code}{Number(p.min_grade_points) > 1 ? ` ≥ ${p.min_grade_points}` : ""}</Badge>) : <span className="muted">None</span> },
    manage && { key: "a", header: "", className: "num", render: (c) => <Button size="sm" variant="secondary" onClick={() => setModal({ kind: "pre", course: c })}>Add prerequisite</Button> },
  ].filter(Boolean);
  return (
    <>
      <Card bodyClass="" title="Course catalogue" actions={manage && <Button size="sm" icon={LuPlus} onClick={() => setModal({ kind: "new" })}>New course</Button>}>
        <DataTable caption="Courses" columns={columns} data={data} loading={loading} error={error} search={search}
          onSearch={(v) => { setSearch(v); setPage(1); }} searchPlaceholder="Search code or title…" page={page} onPage={setPage}
          filters={<SelectBox id="c-dept" label="Department" hideLabel value={dept} onChange={(v) => { setDept(v); setPage(1); }} placeholder="All departments"
            options={(departments.data?.results || []).map((d) => ({ value: d.id, label: d.name }))} />} />
      </Card>
      {modal?.kind === "new" && <NewCourse departments={departments.data?.results || []} onClose={() => setModal(null)} onDone={() => { setModal(null); reload(); }} />}
      {modal?.kind === "pre" && <AddPrerequisite course={modal.course} onClose={() => setModal(null)} onDone={() => { setModal(null); reload(); }} />}
    </>
  );
}

function ProgramsList() {
  const { data } = useApi("/universities/programs/", { page_size: 100 });
  const [open, setOpen] = useState(null);
  const program = (data?.results || []).find((p) => p.id === open) || data?.results?.[0];
  const curriculum = useApi(program?.current_curriculum ? `/universities/curricula/${program.current_curriculum.id}/` : null);
  if (!data) return <Spinner />;
  const items = curriculum.data?.items || [];
  const years = [...new Set(items.map((i) => i.recommended_year))].sort();
  return (
    <div className="grid grid--3-1" style={{ gridTemplateColumns: "300px 1fr" }}>
      <Card title="Programs" bodyClass="">
        <ul className="list" style={{ padding: "0 12px" }}>
          {data.results.map((p) => (
            <li key={p.id} className="list__item" style={{ padding: 0 }}>
              <button type="button" className={`picker__item${p.id === program?.id ? " is-active" : ""}`} onClick={() => setOpen(p.id)}>
                <strong>{p.name}</strong><div className="muted" style={{ fontSize: "var(--fs-xs)" }}>{p.code} · {p.student_count} students</div>
              </button>
            </li>
          ))}
        </ul>
      </Card>
      {program && (
        <Card title={program.name} subtitle={`${program.award} · ${program.faculty_name} · ${program.department_name}`}>
          <KeyValues items={[["Code", program.code], ["Duration", `${program.duration_years} years`], ["Credits to graduate", program.total_credits_required],
            ["Curriculum", program.current_curriculum ? `Version ${program.current_curriculum.version}` : "None"],
            ["Elective credits required", curriculum.data?.elective_credits_required], ["Active students", program.student_count]]} />
          <h3 className="card__title" style={{ margin: "20px 0 8px" }}>Curriculum map</h3>
          {years.map((y) => (
            <div key={y} style={{ marginBottom: 12 }}>
              <div className="select-label" style={{ marginBottom: 4 }}>Year {y}</div>
              <table className="table">
                <tbody>
                  {items.filter((i) => i.recommended_year === y).map((i) => (
                    <tr key={i.id}><td className="mono" style={{ width: 100 }}>{i.code}</td><td>{i.title}</td><td className="num">{i.credits} cr</td>
                      <td><Badge tone={i.category === "core" ? "dark" : "neutral"}>{i.category}</Badge></td><td className="muted">Semester {i.recommended_semester}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}

function Structure() {
  const faculties = useApi("/universities/faculties/", { page_size: 100 });
  const departments = useApi("/universities/departments/", { page_size: 100 });
  return (
    <div className="grid grid--2">
      {(faculties.data?.results || []).map((f) => (
        <Card key={f.id} title={f.name} subtitle={`${f.code} · Dean: ${f.dean_name || "not assigned"}`}>
          <ul className="list">
            {(departments.data?.results || []).filter((d) => d.faculty === f.id).map((d) => (
              <li key={d.id} className="list__item"><span className="list__dot" />
                <div><div className="list__title">{d.name} <span className="muted mono">{d.code}</span></div><div className="list__meta">Head: {d.head_name || "not assigned"}</div></div></li>
            ))}
          </ul>
        </Card>
      ))}
    </div>
  );
}

export default function Programs() {
  const { user } = useAuth();
  const [tab, setTab] = useState("programs");
  const manage = can(user, "uni.programs.manage");
  return (
    <>
      <PageHeader title="Programs & courses" description="Faculties, departments, degree programs, curriculum maps, courses, credit hours and prerequisites." />
      <Tabs value={tab} onChange={setTab} tabs={[{ value: "programs", label: "Programs & curricula" }, { value: "courses", label: "Courses" },
        { value: "structure", label: "Faculties & departments" }]} />
      {tab === "programs" && <ProgramsList />}
      {tab === "courses" && <Courses manage={manage} />}
      {tab === "structure" && <Structure />}
    </>
  );
}
