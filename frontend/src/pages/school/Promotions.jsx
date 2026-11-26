import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { useAction, useApi } from "../../utils/hooks";
import { titleCase } from "../../utils/format";
import { Alert, Badge, Button, Card, Field, Modal, PageHeader, Spinner } from "../../components/ui";
import { ActionFeedback, SelectBox } from "../../components/ui/extra";
import { classOptions, useMyClasses } from "./common";

const LABEL = { promote: "Promote", repeat: "Repeat year", complete: "Complete school" };

function Decide({ row, section, decision, onClose, onDone }) {
  const [reason, setReason] = useState("");
  const act = useAction();
  const against = decision !== row.recommended;
  async function submit(e) {
    e.preventDefault();
    if (await act.run(() => api.post("/schools/promotions/decide/", { student: row.student, section: section.id, decision, reason }))) onDone();
  }
  return (
    <Modal title={`${LABEL[decision]}: ${row.name}`} onClose={onClose}>
      <form onSubmit={submit} noValidate>
        <ActionFeedback act={act} />
        <p style={{ marginTop: 0 }}>Year average <strong>{row.average}%</strong> (promotion needs {row.min_average}%). Recommendation: <strong>{LABEL[row.recommended]}</strong>.</p>
        {against && <Alert tone="info">This goes against the recommendation, so a reason is required and will be recorded in the audit log.</Alert>}
        <Field label={against ? "Reason (required)" : "Note (optional)"} error={act.error?.fields?.reason?.[0]}>
          {(a) => <input {...a} className="input" value={reason} onChange={(e) => setReason(e.target.value)} />}
        </Field>
        <p className="muted" style={{ fontSize: "var(--fs-sm)" }}>This closes the pupil's class placement and enrollment for this year, opens next year's enrollment
          {decision === "complete" ? " (or marks them as completed)" : ""} and notifies their guardians. It can't be undone here.</p>
        <div className="form-actions">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={act.busy || (against && !reason.trim())}>{act.busy ? "Saving…" : `Confirm: ${LABEL[decision]}`}</Button>
        </div>
      </form>
    </Modal>
  );
}

export default function Promotions() {
  const { classes, loading } = useMyClasses();
  const [section, setSection] = useState("");
  const [open, setOpen] = useState(null);
  const sec = classes.find((c) => String(c.id) === String(section)) || classes[0];
  const recs = useApi(sec ? "/schools/promotions/recommendations/" : null, { section: sec?.id });
  const d = recs.data;
  const choices = d?.is_final_grade ? ["complete", "repeat"] : ["promote", "repeat"];
  return (
    <>
      <PageHeader title="Promotions" description="End-of-year decisions: promote, repeat or complete school. Every term's results must be finalized first." />
      {loading ? <Spinner /> : !sec ? <Alert tone="info">No classes this year.</Alert> : (
        <>
          <div className="toolbar">
            <SelectBox id="pr-class" label="Class" value={sec.id} onChange={setSection} options={classOptions(classes)} width={150} />
          </div>
          {!d ? <Spinner /> : (
            <Card title={`${d.section}${d.next_level ? ` → ${d.next_level}` : " (final grade)"}`} bodyClass=""
              subtitle="Year average = mean of the finalized term averages.">
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>Pupil</th>{d.rows[0]?.terms.map((t) => <th key={t.term} className="num">{t.term}</th>)}<th className="num">Year avg.</th><th>Recommended</th><th>Decision</th></tr></thead>
                  <tbody>
                    {d.rows.map((r) => (
                      <tr key={r.student}>
                        <td><Link to={`/school/students/${r.student}`}>{r.name}</Link></td>
                        {r.terms.map((t) => <td key={t.term} className="num">{t.average != null ? `${t.average}%` : <Badge tone="warning">{titleCase(t.status)}</Badge>}</td>)}
                        <td className="num"><strong>{r.average != null ? `${r.average}%` : "—"}</strong></td>
                        <td>{r.recommended ? <Badge tone={r.recommended === "repeat" ? "warning" : "success"}>{LABEL[r.recommended]}</Badge> : "—"}</td>
                        <td>{r.decision ? (
                          <span><Badge tone="dark">{LABEL[r.decision.decision]}</Badge>{r.decision.reason && <span className="muted" style={{ fontSize: "var(--fs-xs)" }}> · {r.decision.reason}</span>}</span>
                        ) : r.missing.length ? (
                          <span className="muted" style={{ fontSize: "var(--fs-xs)" }}>Waiting for {r.missing.join(", ")}</span>
                        ) : (
                          <div className="row-actions" style={{ justifyContent: "flex-start" }}>
                            {choices.map((c) => (
                              <Button key={c} size="sm" variant={c === r.recommended ? "primary" : "secondary"} onClick={() => setOpen({ row: r, decision: c })}>{LABEL[c]}</Button>
                            ))}
                          </div>
                        )}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}
      {open && <Decide {...open} section={sec} onClose={() => setOpen(null)} onDone={() => { setOpen(null); recs.reload(); }} />}
    </>
  );
}
