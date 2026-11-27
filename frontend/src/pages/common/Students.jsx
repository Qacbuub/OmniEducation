import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { LuUserPlus } from "react-icons/lu";
import { useAuth } from "../../auth/AuthContext";
import { useApi, useDebounced } from "../../utils/hooks";
import { money } from "../../utils/format";
import { api } from "../../api/client";
import { Alert, Badge, Card, PageHeader, PersonCell } from "../../components/ui";
import { ConfirmDelete, DownloadButton, RowActions } from "../../components/ui/extra";
import { can } from "../../config/roles";
import { DataTable } from "../../components/ui/DataTable";

/** Shared student register. Column set differs by mode (school pupils vs university students). */
export default function Students() {
  const { mode, user } = useAuth();
  const isUni = mode === "university";
  const [params] = useSearchParams();
  const [search, setSearch] = useState(params.get("search") || "");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const q = useDebounced(search);
  const { data, loading, error, reload } = useApi("/students/", { search: q, status, page });
  const navigate = useNavigate();
  const [removing, setRemoving] = useState(null);
  const [notice, setNotice] = useState(null);
  const manage = can(user, "students.manage");
  const currency = user.tenant?.currency || (isUni ? "USD" : "KES");

  const columns = [
    { key: "name", header: isUni ? "Student" : "Pupil", render: (s) => (
      <Link to={`/${mode}/students/${s.id}`} style={{ color: "inherit", textDecoration: "none" }}>
        <PersonCell name={`${s.first_name} ${s.last_name}`} sub={isUni ? null : `Guardian: ${s.guardian || "—"}`} />
      </Link>
    ) },
    { key: "student_no", header: "ID", render: (s) => <span className="mono">{s.student_no}</span> },
    { key: "level", header: isUni ? "Program" : "Grade" },
    { key: "section", header: isUni ? "Year" : "Section" },
    ...(isUni ? [{ key: "cgpa", header: "CGPA", className: "num", render: (s) => (
      <span style={{ color: Number(s.cgpa) < 2 ? "var(--danger)" : undefined, fontWeight: 600 }}>{s.cgpa}</span>
    )}] : []),
    { key: "balance", header: "Balance", className: "num", render: (s) => (
      <span style={{ color: s.balance > 0 ? "var(--danger)" : "var(--success)", fontWeight: 600 }}>{money(s.balance, currency)}</span>
    )},
    { key: "status", header: "Status", render: (s) => <Badge>{s.status}</Badge> },
    ...(manage ? [{ key: "actions", header: "Actions", className: "num", render: (s) => (
      <RowActions name={`${s.first_name} ${s.last_name}`} onEdit={() => navigate(`/${mode}/students/${s.id}?edit=1`)}
        onDelete={() => setRemoving(s)} />
    ) }] : []),
  ];

  return (
    <>
      <PageHeader
        eyebrow={user.tenant.name}
        title={isUni ? "Students" : "Pupils"}
        description="Searchable register of every student profile in this institution."
        actions={<>
          {can(user, "students.view") && <DownloadButton path="/students/export/" filename="students.csv" size={undefined}>Export CSV</DownloadButton>}
          {can(user, "admissions.manage") && (
            <Link className="btn btn--primary" to={`/${mode}/admissions?new=1`}><LuUserPlus aria-hidden="true" /> {isUni ? "New applicant" : "New admission"}</Link>
          )}
        </>}
      />
      {notice && <Alert tone="success">{notice}</Alert>}
      {removing && (
        <ConfirmDelete title={`Delete ${removing.first_name} ${removing.last_name}`}
          onConfirm={(reason) => api.delete(`/students/${removing.id}/`, { reason })}
          onClose={(deleted) => { if (deleted) { setNotice(`${removing.first_name} ${removing.last_name} was deleted.`); reload(); } setRemoving(null); }}>
          <p style={{ marginTop: 0 }}>This removes the profile ({removing.student_no}), the {isUni ? "student's" : "pupil's"} own sign-in, guardian links
            and any unpaid invoices. Use it for a record created by mistake.</p>
          <p className="muted" style={{ fontSize: "var(--fs-sm)", marginBottom: 0 }}>A {isUni ? "student" : "pupil"} who already has payments, attendance, marks or
            results can't be deleted: open the profile and set the status to Withdrawn or Transferred instead, which keeps the history.</p>
        </ConfirmDelete>
      )}
      <Card bodyClass="">
        <DataTable
          caption={isUni ? "Students" : "Pupils"}
          columns={columns} data={data} loading={loading} error={error}
          search={search} onSearch={(v) => { setSearch(v); setPage(1); }} searchPlaceholder="Search name or ID…"
          filters={
            <>
              <label className="sr-only" htmlFor="status-filter">Filter by status</label>
              <select id="status-filter" className="select" style={{ width: 170 }} value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
                <option value="">All statuses</option><option value="active">Active</option><option value="withdrawn">Withdrawn</option><option value="transferred">Transferred</option>{isUni ? <option value="graduated">Graduated</option> : <option value="completed">Completed</option>}
              </select>
            </>
          }
          page={page} onPage={setPage}
        />
      </Card>
    </>
  );
}
