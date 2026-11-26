import { useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import { useApi, useDebounced } from "../../utils/hooks";
import { timeAgo } from "../../utils/format";
import { Badge, Card, PageHeader } from "../../components/ui";
import { DataTable } from "../../components/ui/DataTable";

/** Append-only activity log. Institution users see their tenant; the platform admin sees platform events. */
export default function AuditLog() {
  const { mode } = useAuth();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const q = useDebounced(search);
  const path = mode === "platform" ? "/platform/audit/" : "/audit/";
  const { data, loading, error } = useApi(path, { search: q, page });
  const columns = [
    { key: "created_at", header: "When", render: (e) => <span className="muted" title={e.created_at}>{timeAgo(e.created_at)}</span> },
    { key: "actor_email", header: "Who", render: (e) => e.actor_email || <span className="muted">System</span> },
    { key: "action", header: "Action", render: (e) => <Badge tone={/deleted|void|rejected|amended/.test(e.action) ? "warning" : "neutral"}>{e.action}</Badge> },
    { key: "target_repr", header: "Record", render: (e) => <span>{e.target_repr || "—"}</span> },
    { key: "changes", header: "Details", render: (e) => {
      const entries = Object.entries(e.changes || {});
      return entries.length ? <span className="mono muted" style={{ fontSize: "var(--fs-xs)" }}>
        {entries.slice(0, 4).map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ").slice(0, 160)}</span> : "—";
    } },
    { key: "ip_address", header: "IP", render: (e) => <span className="mono muted">{e.ip_address || "—"}</span> },
  ];
  return (
    <>
      <PageHeader title="Audit history" description="Every sign-in, data change, payment, grade decision, export and download. Entries can't be edited or deleted." />
      <Card bodyClass="">
        <DataTable caption="Audit events" columns={columns} data={data} loading={loading} error={error}
          search={search} onSearch={(v) => { setSearch(v); setPage(1); }} searchPlaceholder="Search action, user or record…"
          page={page} onPage={setPage} />
      </Card>
    </>
  );
}
