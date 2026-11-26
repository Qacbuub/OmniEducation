import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { LuUserPlus } from "react-icons/lu";
import { useAuth } from "../../auth/AuthContext";
import { useApi, useDebounced } from "../../utils/hooks";
import { money } from "../../utils/format";
import { Badge, Card, PageHeader, PersonCell } from "../../components/ui";
import { DownloadButton } from "../../components/ui/extra";
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
  const { data, loading, error } = useApi("/students/", { search: q, status, page });
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
