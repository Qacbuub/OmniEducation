import { useState } from "react";
import { LuCheck, LuUndo2 } from "react-icons/lu";
import { api } from "../../api/client";
import { useAction, useApi } from "../../utils/hooks";
import { timeAgo, titleCase } from "../../utils/format";
import { Alert, Badge, Button, Card, EmptyState, Field, PageHeader, Spinner } from "../../components/ui";
import { ActionFeedback, Tabs } from "../../components/ui/extra";
import { GradebookGrid } from "./Gradebook";

function Moderate({ offering, onDone, onNotice }) {
  const [notes, setNotes] = useState("");
  const act = useAction();
  const decide = async (approve) => {
    const path = `/universities/offerings/${offering.id}/${approve ? "approve" : "return"}-grades/`;
    const msg = approve ? `${offering.course_code}-${offering.section}: grades approved. Transcripts and CGPAs are updated and students notified.`
      : `${offering.course_code}-${offering.section}: grades returned to the lecturer.`;
    if (await act.run(() => api.post(path, { notes }))) { onNotice(msg); onDone(); }
  };
  return (
    <>
      <ActionFeedback act={act} />
      <GradebookGrid key={offering.id} offeringId={offering.id} readOnly />
      <Card title="Decision">
        <Field label="Notes (required when returning)">{(a) => <input {...a} className="input" value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
        <div className="row-actions" style={{ justifyContent: "flex-start" }}>
          <Button icon={LuCheck} disabled={act.busy} onClick={() => decide(true)}>Approve grades</Button>
          <Button variant="secondary" icon={LuUndo2} disabled={act.busy || !notes.trim()} onClick={() => decide(false)}>Return for correction</Button>
        </div>
        <p className="muted" style={{ fontSize: "var(--fs-sm)", marginBottom: 0 }}>Approved grades become permanent transcript entries. Later changes need a registrar amendment, which is audited.</p>
      </Card>
    </>
  );
}

export default function GradeApprovals() {
  const { data, loading, reload } = useApi("/universities/grade-approvals/");
  const [tab, setTab] = useState("pending");
  const [open, setOpen] = useState(null);
  const [notice, setNotice] = useState(null);
  const pending = data?.pending || [];
  const chosen = pending.find((o) => o.id === open) || pending[0];
  return (
    <>
      <PageHeader title="Grade approvals" description="Moderate submitted grades. Department heads see their own department, deans their faculty, the registrar everything. Nobody approves their own grades." />
      {notice && <Alert tone="success">{notice}</Alert>}
      <Tabs value={tab} onChange={setTab} tabs={[{ value: "pending", label: "Waiting for approval", count: pending.length }, { value: "history", label: "History" }]} />
      {loading && !data ? <Spinner /> : tab === "pending" ? (
        pending.length === 0 ? <Card><EmptyState title="No grades waiting for you" /></Card> : (
          <>
            <div className="row-actions" style={{ justifyContent: "flex-start", marginBottom: 16 }}>
              {pending.map((o) => (
                <Button key={o.id} size="sm" variant={o.id === chosen.id ? "primary" : "secondary"} onClick={() => setOpen(o.id)}>
                  {o.course_code}-{o.section} · {o.lecturer_name || "—"}
                </Button>
              ))}
            </div>
            <Moderate key={chosen.id} offering={chosen} onNotice={setNotice} onDone={() => { setOpen(null); reload(); }} />
          </>
        )
      ) : (
        <Card bodyClass="">
          <div className="table-wrap"><table className="table">
            <thead><tr><th>When</th><th>Section</th><th>Action</th><th>By</th><th>Notes</th></tr></thead>
            <tbody>
              {(data?.history || []).map((h) => (
                <tr key={h.id}>
                  <td className="muted">{timeAgo(h.created_at)}</td><td className="mono">{h.course_code}-{h.section}</td>
                  <td><Badge tone={h.action === "approved" ? "success" : h.action === "returned" ? "warning" : h.action === "amended" ? "danger" : "brand"}>{titleCase(h.action)}</Badge></td>
                  <td>{h.actor_name || "—"}</td>
                  <td className="muted">{h.notes}{h.details?.from ? ` (${h.details.from.letter} → ${h.details.to.letter})` : ""}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        </Card>
      )}
    </>
  );
}
