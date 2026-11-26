import { useState } from "react";
import { Link } from "react-router-dom";
import { LuPencil, LuPlus, LuReceipt, LuSend, LuTrash2, LuWallet } from "react-icons/lu";
import { api } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { can } from "../../config/roles";
import { useAction, useApi, useDebounced } from "../../utils/hooks";
import { compactMoney, money, shortDate, timeAgo } from "../../utils/format";
import { Alert, Badge, Button, Card, EmptyState, Field, Modal, PageHeader, StatCard } from "../../components/ui";
import { DataTable } from "../../components/ui/DataTable";
import { ActionFeedback, DownloadButton, SelectBox, Tabs } from "../../components/ui/extra";

const METHODS = [["cash", "Cash"], ["bank_transfer", "Bank transfer"], ["mobile_money", "Mobile money"]];

function InvoiceAction({ invoice, kind, currency, onClose, onDone }) {
  const [f, setF] = useState({ amount: kind === "pay" || kind === "mock" ? invoice.balance : "", method: "bank_transfer", reference: "", reason: "" });
  const act = useAction();
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  const err = (k) => act.error?.fields?.[k]?.[0];
  const titles = { pay: "Record payment", mock: "Pay online (demo)", discount: "Apply discount or scholarship", void: "Void invoice" };
  async function submit(e) {
    e.preventDefault();
    const calls = {
      pay: () => api.post("/fees/payments/", { invoice: invoice.id, amount: f.amount, method: f.method, reference: f.reference }),
      mock: () => api.post(`/fees/invoices/${invoice.id}/pay-online/`, { amount: f.amount }),
      discount: () => api.post(`/fees/invoices/${invoice.id}/discount/`, { amount: f.amount, reason: f.reason }),
      void: () => api.post(`/fees/invoices/${invoice.id}/void/`, { reason: f.reason }),
    };
    const r = await act.run(calls[kind]);
    if (r) onDone(kind === "pay" || kind === "mock" ? `Payment recorded. Receipt ${r.receipt_no}.` : "Invoice updated.");
  }
  return (
    <Modal title={`${titles[kind]} · ${invoice.number}`} onClose={onClose}>
      <form onSubmit={submit} noValidate>
        <ActionFeedback act={act} />
        <p className="muted" style={{ marginTop: 0 }}>{invoice.student_name} · balance <strong>{money(invoice.balance, currency)}</strong> of {money(invoice.total, currency)}</p>
        {kind === "mock" && <Alert tone="info">This is a mock payment for the demo. No card details are requested and no real money moves.</Alert>}
        {kind !== "void" && (
          <Field label="Amount" error={err("amount")} hint={kind === "pay" || kind === "mock" ? "Partial payments are allowed." : undefined}>
            {(a) => <input {...a} className="input" type="number" min="0" step="0.01" value={f.amount} onChange={set("amount")} required />}
          </Field>
        )}
        {kind === "pay" && <>
          <Field label="Method" error={err("method")}>
            {(a) => <select {...a} className="select" value={f.method} onChange={set("method")}>{METHODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>}
          </Field>
          <Field label="Reference" hint="Bank or mobile-money transaction ID.">{(a) => <input {...a} className="input" value={f.reference} onChange={set("reference")} />}</Field>
        </>}
        {(kind === "discount" || kind === "void") && (
          <Field label="Reason" error={err("reason")}>{(a) => <input {...a} className="input" value={f.reason} onChange={set("reason")} required />}</Field>
        )}
        <div className="form-actions">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant={kind === "void" ? "danger" : "primary"} disabled={act.busy}>{act.busy ? "Saving…" : titles[kind]}</Button>
        </div>
      </form>
    </Modal>
  );
}

function Invoices({ staff, currency, mode }) {
  const { user } = useAuth();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [action, setAction] = useState(null);
  const [notice, setNotice] = useState(null);
  const q = useDebounced(search);
  const { data, loading, error, reload } = useApi("/fees/invoices/", { search: q, status, page });
  const columns = [
    { key: "number", header: "Invoice", render: (i) => <span className="mono">{i.number}</span> },
    { key: "student_name", header: "Student", render: (i) => staff
      ? <Link to={`/${mode}/students/${i.student}`}>{i.student_name}</Link> : i.student_name },
    { key: "due_date", header: "Due", render: (i) => shortDate(i.due_date) },
    { key: "total", header: "Total", className: "num", render: (i) => money(i.total, currency) },
    { key: "discount_amount", header: "Discount", className: "num", render: (i) => Number(i.discount_amount) ? <span title={i.discount_reason}>−{money(i.discount_amount, currency)}</span> : "—" },
    { key: "amount_paid", header: "Paid", className: "num", render: (i) => money(i.amount_paid, currency) },
    { key: "balance", header: "Balance", className: "num", render: (i) => <strong style={{ color: Number(i.balance) > 0 ? "var(--danger)" : "var(--success)" }}>{money(i.balance, currency)}</strong> },
    { key: "status", header: "Status", render: (i) => <Badge>{i.is_overdue ? "overdue" : i.status}</Badge> },
    { key: "actions", header: "", className: "num", render: (i) => (
      <div className="row-actions">
        {Number(i.balance) > 0 && i.status !== "void" && (staff
          ? can(user, "payments.record") && <Button size="sm" onClick={() => setAction({ invoice: i, kind: "pay" })}>Record payment</Button>
          : <Button size="sm" onClick={() => setAction({ invoice: i, kind: "mock" })}>Pay online</Button>)}
        {staff && can(user, "fees.manage") && i.status !== "void" && Number(i.balance) > 0 && <>
          <Button size="sm" variant="secondary" onClick={() => setAction({ invoice: i, kind: "discount" })}>Discount</Button>
          {Number(i.amount_paid) === 0 && <Button size="sm" variant="ghost" onClick={() => setAction({ invoice: i, kind: "void" })}>Void</Button>}
        </>}
        {i.payments?.slice(-1).map((p) => <DownloadButton key={p.id} path={`/fees/payments/${p.id}/receipt/`} icon={LuReceipt}>Receipt</DownloadButton>)}
      </div>
    ) },
  ];
  return (
    <>
      {notice && <Alert tone="success">{notice}</Alert>}
      <Card bodyClass="">
        <DataTable caption="Invoices" columns={columns} data={data} loading={loading} error={error}
          search={staff ? search : undefined} onSearch={staff ? (v) => { setSearch(v); setPage(1); } : undefined}
          searchPlaceholder="Search invoice, name or ID…"
          filters={<SelectBox id="inv-status" label="Status" hideLabel value={status} onChange={(v) => { setStatus(v); setPage(1); }}
            placeholder="All statuses" options={["issued", "partial", "paid", "void"].map((s) => ({ value: s, label: s[0].toUpperCase() + s.slice(1) }))} />}
          page={page} onPage={setPage} emptyTitle="No invoices" />
      </Card>
      {action && <InvoiceAction {...action} currency={currency} onClose={() => setAction(null)}
        onDone={(msg) => { setAction(null); setNotice(msg); reload(); }} />}
    </>
  );
}

function Payments({ currency }) {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const q = useDebounced(search);
  const { data, loading, error } = useApi("/fees/payments/", { page, search: q });
  const columns = [
    { key: "receipt_no", header: "Receipt", render: (p) => <span className="mono">{p.receipt_no}</span> },
    { key: "student_name", header: "Student" },
    { key: "invoice_number", header: "Invoice", render: (p) => <span className="mono">{p.invoice_number}</span> },
    { key: "amount", header: "Amount", className: "num", render: (p) => <strong>{money(p.amount, currency)}</strong> },
    { key: "method_label", header: "Method", render: (p) => <>{p.method_label}{p.method === "mock_online" && <> <Badge tone="warning">Mock</Badge></>}</> },
    { key: "reference", header: "Reference", render: (p) => <span className="mono muted">{p.reference || "—"}</span> },
    { key: "paid_at", header: "Paid", render: (p) => <span className="muted">{timeAgo(p.paid_at)}</span> },
    { key: "r", header: "", className: "num", render: (p) => <DownloadButton path={`/fees/payments/${p.id}/receipt/`} icon={LuReceipt}>Receipt</DownloadButton> },
  ];
  return (
    <Card bodyClass="">
      <DataTable caption="Payments" columns={columns} data={data} loading={loading} error={error} page={page} onPage={setPage}
        search={search} onSearch={(v) => { setSearch(v); setPage(1); }} searchPlaceholder="Search receipt, reference…" />
    </Card>
  );
}

function PlanForm({ plan, currency, onClose, onDone }) {
  const { mode } = useAuth();
  const isUni = mode === "university";
  const periods = useApi("/academic-periods/", { kind: isUni ? "semester" : "term", page_size: 50 });
  const targets = useApi(isUni ? "/universities/programs/" : "/schools/grade-levels/", { page_size: 100 });
  const locked = (plan.invoices_issued || 0) > 0;
  const [f, setF] = useState({
    name: plan.name || "", period: plan.period || "", applies_to: plan.applies_to || "", due_days: plan.due_days ?? 30,
    is_active: plan.is_active ?? true,
    items: plan.items?.length ? plan.items.map((i) => ({ description: i.description, amount: i.amount })) : [{ description: "", amount: "" }],
  });
  const act = useAction();
  const err = (k) => act.error?.fields?.[k]?.[0] || act.error?.fields?.[k];
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));
  const setItem = (i, k, v) => setF((x) => ({ ...x, items: x.items.map((it, j) => (j === i ? { ...it, [k]: v } : it)) }));
  const total = f.items.reduce((sum, i) => sum + (Number(i.amount) || 0), 0);
  async function submit(e) {
    e.preventDefault();
    const body = { name: f.name, period: f.period || null, applies_to: f.applies_to, due_days: Number(f.due_days), is_active: f.is_active,
      ...(locked ? {} : { items: f.items.filter((i) => i.description || i.amount).map((i) => ({ description: i.description, amount: i.amount })) }) };
    const r = await act.run(() => (plan.id ? api.patch(`/fees/plans/${plan.id}/`, body) : api.post("/fees/plans/", body)));
    if (r) onDone();
  }
  const itemErrors = act.error?.fields?.items;
  return (
    <Modal title={plan.id ? `Edit ${plan.name}` : "New fee plan"} onClose={onClose}>
      <form onSubmit={submit} noValidate>
        <ActionFeedback act={act} />
        <div className="form-grid">
          <Field label="Name" required error={err("name")} className="span-2">{(a) => <input {...a} className="input" value={f.name} onChange={set("name")} placeholder={isUni ? "Tuition – Semester 2" : "Term 1 fees – Grade 4"} />}</Field>
          <Field label={isUni ? "Semester" : "Term"} error={err("period")}>
            {(a) => (
              <select {...a} className="select" value={f.period} onChange={set("period")}>
                <option value="">Not tied to a {isUni ? "semester" : "term"}</option>
                {(periods.data?.results || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            )}
          </Field>
          <Field label="Applies to" error={err("applies_to")} hint="Invoices go to active students in this group.">
            {(a) => (
              <select {...a} className="select" value={f.applies_to} onChange={set("applies_to")}>
                <option value="">Every active student</option>
                {(targets.data?.results || []).map((t) => <option key={t.id} value={t.name}>{t.name}</option>)}
              </select>
            )}
          </Field>
          <Field label="Payment due (days after issue)" error={err("due_days")}>{(a) => <input {...a} className="input" type="number" min={0} value={f.due_days} onChange={set("due_days")} />}</Field>
          <div className="field"><label className="check"><input type="checkbox" checked={f.is_active} onChange={set("is_active")} /> Active (can be issued)</label></div>
        </div>
        <h3 className="form-section">Fee items</h3>
        {locked && <p className="muted" style={{ fontSize: "var(--fs-xs)" }}>Items are locked because invoices were already issued from this plan.</p>}
        <table className="table">
          <thead><tr><th>Description</th><th className="num">Amount ({currency})</th><th /></tr></thead>
          <tbody>
            {f.items.map((it, i) => (
              <tr key={i}>
                <td><input className="input" aria-label={`Item ${i + 1} description`} value={it.description} disabled={locked}
                  onChange={(e) => setItem(i, "description", e.target.value)} placeholder="Tuition" /></td>
                <td className="num"><input className="input" style={{ textAlign: "right" }} aria-label={`Item ${i + 1} amount`} type="number" min="0" step="0.01"
                  value={it.amount} disabled={locked} onChange={(e) => setItem(i, "amount", e.target.value)} /></td>
                <td className="num">{!locked && f.items.length > 1 && (
                  <Button size="sm" variant="ghost" aria-label={`Remove item ${i + 1}`} onClick={() => setF((x) => ({ ...x, items: x.items.filter((_, j) => j !== i) }))}>Remove</Button>
                )}</td>
              </tr>
            ))}
            <tr><td><strong>Total</strong></td><td className="num"><strong>{money(total, currency)}</strong></td><td /></tr>
          </tbody>
        </table>
        {itemErrors && <p className="field__error">{[].concat(itemErrors).map((x) => (typeof x === "string" ? x : Object.values(x).flat().join(" "))).filter(Boolean).join(" ")}</p>}
        {!locked && <Button size="sm" variant="secondary" onClick={() => setF((x) => ({ ...x, items: [...x.items, { description: "", amount: "" }] }))}>Add item</Button>}
        <div className="form-actions">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={act.busy}>{act.busy ? "Saving…" : plan.id ? "Save plan" : "Create plan"}</Button>
        </div>
      </form>
    </Modal>
  );
}

function Plans({ currency }) {
  const { user } = useAuth();
  const { data, reload } = useApi("/fees/plans/", { page_size: 50 });
  const [editing, setEditing] = useState(null);
  const manage = can(user, "fees.manage");
  const act = useAction();
  const remove = async (p) => {
    if (window.confirm(`Delete the fee plan "${p.name}"? No invoices have been issued from it.`)
      && (await act.run(() => api.delete(`/fees/plans/${p.id}/`), "Fee plan deleted.")) !== undefined) reload();
  };
  const issue = async (p) => {
    if (await act.run(() => api.post(`/fees/plans/${p.id}/issue/`, {}), (r) =>
      `${p.name}: ${r.issued} invoice(s) issued, ${r.skipped} already billed.`)) reload();
  };
  return (
    <>
      <ActionFeedback act={act} />
      <Card bodyClass="" title="Fee plans" subtitle="A fee plan lists the charges for a term or semester; issuing it creates one invoice per student."
        actions={manage && <Button size="sm" icon={LuPlus} onClick={() => setEditing({})}>New fee plan</Button>}>
        <table className="table">
          <thead><tr><th>Fee plan</th><th>Period</th><th>Applies to</th><th>Items</th><th className="num">Total</th><th className="num">Invoices</th><th /></tr></thead>
          <tbody>
            {(data?.results || []).map((p) => (
              <tr key={p.id}>
                <td><strong>{p.name}</strong> {!p.is_active && <Badge>inactive</Badge>}</td><td>{p.period_name || "—"}</td><td>{p.applies_to || "Everyone"}</td>
                <td className="muted">{p.items.map((i) => `${i.description} ${money(i.amount, currency)}`).join(" · ")}</td>
                <td className="num"><strong>{money(p.total, currency)}</strong></td><td className="num">{p.invoices_issued}</td>
                <td className="num" style={{ whiteSpace: "nowrap" }}>
                  {manage && p.is_active && <Button size="sm" variant="secondary" icon={LuSend} disabled={act.busy} onClick={() => issue(p)}>Issue to students</Button>}
                  {manage && <Button size="sm" variant="ghost" icon={LuPencil} onClick={() => setEditing(p)}>Edit</Button>}
                  {manage && p.invoices_issued === 0 && <Button size="sm" variant="ghost" icon={LuTrash2} aria-label={`Delete ${p.name}`} onClick={() => remove(p)} />}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data?.results?.length === 0 && <EmptyState title="No fee plans yet" />}
      </Card>
      {editing && <PlanForm plan={editing} currency={currency} onClose={() => setEditing(null)} onDone={() => { setEditing(null); reload(); }} />}
    </>
  );
}

function Arrears({ mode }) {
  const { data } = useApi("/fees/arrears/");
  const cur = data?.currency;
  return data ? (
    <>
      <div className="grid grid--stats" style={{ marginBottom: 16 }}>
        <StatCard icon={LuWallet} label="Billed" value={compactMoney(data.totals.billed, cur)} />
        <StatCard icon={LuWallet} label="Collected" value={compactMoney(data.totals.collected, cur)} />
        <StatCard icon={LuWallet} label="Outstanding" value={compactMoney(data.totals.outstanding, cur)} />
        <StatCard icon={LuWallet} label="Overdue 30+ days" value={compactMoney(Number(data.ageing["31_60"]) + Number(data.ageing.over_60), cur)} />
      </div>
      <Card title="Ageing" subtitle="Outstanding balances by days past due">
        <div className="grid grid--stats">
          {[["current", "Not yet due"], ["1_30", "1–30 days"], ["31_60", "31–60 days"], ["over_60", "Over 60 days"]].map(([k, l]) => (
            <div key={k}><div className="stat__label">{l}</div><div className="stat__value" style={{ fontSize: "var(--fs-lg)" }}>{money(data.ageing[k], cur)}</div></div>
          ))}
        </div>
      </Card>
      <Card title="Students with balances" bodyClass="">
        <table className="table">
          <thead><tr><th>Student</th><th>ID</th><th>{mode === "university" ? "Program" : "Grade"}</th><th className="num">Invoices</th><th className="num">Outstanding</th><th className="num">Overdue</th></tr></thead>
          <tbody>
            {data.results.map((r) => (
              <tr key={r.student_id}>
                <td><Link to={`/${mode}/students/${r.student_id}`}>{r.name}</Link></td><td className="mono">{r.student_no}</td><td>{r.level}</td>
                <td className="num">{r.invoices}</td><td className="num"><strong>{money(r.outstanding, cur)}</strong></td>
                <td className="num" style={{ color: Number(r.overdue) > 0 ? "var(--danger)" : undefined }}>{money(r.overdue, cur)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  ) : null;
}

export default function FeeLedger() {
  const { user, mode } = useAuth();
  const staff = can(user, "fees.view");
  const currency = user.tenant?.currency;
  const [tab, setTab] = useState("invoices");
  return (
    <>
      <PageHeader title="Fee ledger" description={staff
        ? "Invoices, partial payments, discounts and scholarships, receipts and arrears."
        : "Your invoices, payments and receipts."} />
      <Tabs value={tab} onChange={setTab} tabs={[
        { value: "invoices", label: "Invoices" }, { value: "payments", label: "Payments & receipts" },
        staff && { value: "plans", label: "Fee plans" }, staff && { value: "arrears", label: "Arrears report" },
      ]} />
      {tab === "invoices" && <Invoices staff={staff} currency={currency} mode={mode} />}
      {tab === "payments" && <Payments currency={currency} />}
      {tab === "plans" && staff && <Plans currency={currency} />}
      {tab === "arrears" && staff && <Arrears mode={mode} />}
    </>
  );
}
