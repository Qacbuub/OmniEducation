import { useState } from "react";
import { useApi } from "../../utils/hooks";
import { shortDate, timeAgo } from "../../utils/format";
import { Badge, Card, PageHeader } from "../../components/ui";
import { DataTable } from "../../components/ui/DataTable";
import { CopyLink } from "../../components/ui/extra";

/** Institution-administrator invitations sent by the platform. */
export default function PlatformInvitations() {
  const [page, setPage] = useState(1);
  const { data, loading, error } = useApi("/platform/invitations/", { page });
  const columns = [
    { key: "email", header: "Email", render: (i) => <strong>{i.email}</strong> },
    { key: "tenant", header: "Institution", render: (i) => i.tenant_name || "—" },
    { key: "role_name", header: "Role" },
    { key: "status", header: "Status", render: (i) => <Badge>{i.status}</Badge> },
    { key: "created_at", header: "Sent", render: (i) => <span className="muted">{timeAgo(i.created_at)}</span> },
    { key: "expires_at", header: "Expires", render: (i) => shortDate(i.expires_at) },
    { key: "link", header: "", className: "num", render: (i) => i.status === "pending" && <CopyLink href={i.invite_link} /> },
  ];
  return (
    <>
      <PageHeader eyebrow="Platform" title="Admin invitations" description="Invitations sent to institution administrators. Links are single-use and expire after 7 days." />
      <Card bodyClass="">
        <DataTable caption="Invitations" columns={columns} data={data} loading={loading} error={error} page={page} onPage={setPage}
          emptyTitle="No invitations yet" emptyText="Creating an institution sends its administrator an invitation." />
      </Card>
    </>
  );
}
