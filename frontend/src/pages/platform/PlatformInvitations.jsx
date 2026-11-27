import { useState } from "react";
import { api } from "../../api/client";
import { useApi } from "../../utils/hooks";
import { shortDate, timeAgo } from "../../utils/format";
import { Alert, Badge, Card, PageHeader } from "../../components/ui";
import { DataTable } from "../../components/ui/DataTable";
import { ConfirmDelete, CopyLink, RowActions } from "../../components/ui/extra";

/** Institution-administrator invitations sent by the platform. */
export default function PlatformInvitations() {
  const [page, setPage] = useState(1);
  const { data, loading, error, reload } = useApi("/platform/invitations/", { page });
  const [removing, setRemoving] = useState(null);
  const [notice, setNotice] = useState(null);
  const columns = [
    { key: "email", header: "Email", render: (i) => <strong>{i.email}</strong> },
    { key: "tenant", header: "Institution", render: (i) => i.tenant_name || "—" },
    { key: "role_name", header: "Role" },
    { key: "status", header: "Status", render: (i) => <Badge>{i.status}</Badge> },
    { key: "created_at", header: "Sent", render: (i) => <span className="muted">{timeAgo(i.created_at)}</span> },
    { key: "expires_at", header: "Expires", render: (i) => shortDate(i.expires_at) },
    { key: "link", header: "Actions", className: "num", render: (i) => i.status === "pending" && (
      <RowActions name={i.email} extra={<CopyLink href={i.invite_link} />} deleteLabel="Cancel" onDelete={() => setRemoving(i)} />
    ) },
  ];
  return (
    <>
      <PageHeader eyebrow="Platform" title="Admin invitations" description="Invitations sent to institution administrators. Links are single-use and expire after 7 days." />
      {notice && <Alert tone="success">{notice}</Alert>}
      {removing && (
        <ConfirmDelete title={`Cancel the invitation for ${removing.email}`} confirmLabel="Cancel invitation"
          onConfirm={(reason) => api.delete(`/platform/invitations/${removing.id}/`, { reason })}
          onClose={(done) => { if (done) { setNotice(`The invitation for ${removing.email} was cancelled; its link no longer works.`); reload(); } setRemoving(null); }}>
          <p style={{ margin: 0 }}>The sign-up link sent to {removing.email} for {removing.tenant_name || "the institution"} will stop working.
            You can send a new one from the institution's page.</p>
        </ConfirmDelete>
      )}
      <Card bodyClass="">
        <DataTable caption="Invitations" columns={columns} data={data} loading={loading} error={error} page={page} onPage={setPage}
          emptyTitle="No invitations yet" emptyText="Creating an institution sends its administrator an invitation." />
      </Card>
    </>
  );
}
