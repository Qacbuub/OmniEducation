import { useState } from "react";
import { Link } from "react-router-dom";
import { LuCheckCheck } from "react-icons/lu";
import { api } from "../../api/client";
import { useAction, useApi } from "../../utils/hooks";
import { timeAgo, titleCase } from "../../utils/format";
import { Badge, Button, Card, EmptyState, PageHeader, Spinner } from "../../components/ui";
import { ActionFeedback, SelectBox } from "../../components/ui/extra";

const KINDS = ["attendance", "results", "homework", "grade", "registration", "fee", "admission", "announcement", "general"];

export default function Notifications() {
  const [kind, setKind] = useState("");
  const [page, setPage] = useState(1);
  const { data, loading, reload } = useApi("/notifications/", { kind, page });
  const act = useAction();
  const markAll = async () => { if (await act.run(() => api.post("/notifications/read-all/"), "All notifications marked as read.")) reload(); };
  const open = async (n) => { if (!n.read) { await api.post(`/notifications/${n.id}/read/`).catch(() => {}); reload(); } };
  const items = data?.results || [];

  return (
    <>
      <PageHeader title="Notifications" description="Attendance alerts, results, grades, fees and other updates for you."
        actions={<Button variant="secondary" icon={LuCheckCheck} onClick={markAll} disabled={act.busy || !data?.unread}>Mark all as read</Button>} />
      <ActionFeedback act={act} />
      <Card bodyClass="card__body">
        <div className="toolbar">
          <SelectBox id="kind" label="Type" value={kind} onChange={(v) => { setKind(v); setPage(1); }} placeholder="All types"
            options={KINDS.map((k) => ({ value: k, label: titleCase(k) }))} />
          <span className="muted" style={{ fontSize: "var(--fs-sm)" }}>{data?.unread ?? 0} unread</span>
        </div>
        {loading && !data ? <Spinner /> : items.length === 0 ? <EmptyState title="You're all caught up" /> : (
          <ul className="list">
            {items.map((n) => (
              <li className="list__item" key={n.id}>
                <span className="list__dot" style={{ background: n.read ? "var(--border-strong)" : undefined }} />
                <div style={{ flex: 1 }}>
                  <div className="list__title">{n.title} <Badge tone="neutral">{titleCase(n.kind)}</Badge></div>
                  {n.body && <div className="list__meta">{n.body}</div>}
                  <div className="list__meta">{timeAgo(n.created_at)}</div>
                </div>
                <div className="row-actions">
                  {n.link && <Link className="btn btn--ghost btn--sm" to={n.link} onClick={() => open(n)}>Open</Link>}
                  {!n.read && <Button size="sm" variant="secondary" onClick={() => open(n)}>Mark read</Button>}
                </div>
              </li>
            ))}
          </ul>
        )}
        {data && data.total_pages > 1 && (
          <div className="table-footer">
            <span>Page {data.page} of {data.total_pages}</span>
            <div className="pager">
              <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
              <Button size="sm" variant="secondary" disabled={page >= data.total_pages} onClick={() => setPage(page + 1)}>Next</Button>
            </div>
          </div>
        )}
      </Card>
    </>
  );
}
