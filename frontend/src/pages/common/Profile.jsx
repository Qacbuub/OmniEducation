import { useState } from "react";
import { LuKeyRound, LuShieldCheck, LuShieldOff } from "react-icons/lu";
import { api, tokens } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { ROLE_LABELS } from "../../config/roles";
import { useAction } from "../../utils/hooks";
import { shortDate } from "../../utils/format";
import { Alert, Badge, Button, Card, Field, PageHeader } from "../../components/ui";
import { ActionFeedback, KeyValues } from "../../components/ui/extra";

function Details() {
  const { user, refreshUser } = useAuth();
  const [f, setF] = useState({ first_name: user.first_name, last_name: user.last_name, phone: user.phone || "" });
  const act = useAction();
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  const err = (k) => act.error?.fields?.[k]?.[0];
  async function save(e) {
    e.preventDefault();
    if (await act.run(() => api.patch("/auth/me/", f), "Your details were saved.")) refreshUser();
  }
  return (
    <Card title="My details">
      <form onSubmit={save} noValidate>
        <ActionFeedback act={act} />
        <div className="form-grid">
          <Field label="First name" required error={err("first_name")}>{(a) => <input {...a} className="input" value={f.first_name} onChange={set("first_name")} />}</Field>
          <Field label="Last name" required error={err("last_name")}>{(a) => <input {...a} className="input" value={f.last_name} onChange={set("last_name")} />}</Field>
          <Field label="Phone" error={err("phone")}>{(a) => <input {...a} className="input" type="tel" value={f.phone} onChange={set("phone")} />}</Field>
          <Field label="Email" hint="Ask an administrator to change your sign-in email.">{(a) => <input {...a} className="input" value={user.email} readOnly disabled />}</Field>
        </div>
        <KeyValues items={[
          ["Role", ROLE_LABELS[user.role] || user.role_name], ["Institution", user.tenant?.name || "OmniEducation platform"],
          ["Last sign-in", user.last_login ? shortDate(user.last_login) : "—"],
        ]} />
        <div className="form-actions"><Button type="submit" disabled={act.busy}>{act.busy ? "Saving…" : "Save details"}</Button></div>
      </form>
    </Card>
  );
}

function PasswordChange() {
  const [f, setF] = useState({ current_password: "", new_password: "", confirm: "" });
  const [mismatch, setMismatch] = useState(false);
  const act = useAction();
  const set = (k) => (e) => { setF((x) => ({ ...x, [k]: e.target.value })); setMismatch(false); };
  const err = (k) => act.error?.fields?.[k]?.[0];
  async function save(e) {
    e.preventDefault();
    if (f.new_password !== f.confirm) { setMismatch(true); return; }
    const r = await act.run(() => api.post("/auth/password/", { current_password: f.current_password, new_password: f.new_password }),
      "Password changed. You stay signed in here; other devices are signed out.");
    if (r) {
      tokens.set({ access: r.access, refresh: r.refresh }); // the old tokens were revoked
      setF({ current_password: "", new_password: "", confirm: "" });
    }
  }
  return (
    <Card title="Change password">
      <form onSubmit={save} noValidate>
        <ActionFeedback act={act} />
        <Field label="Current password" required error={err("current_password")}>
          {(a) => <input {...a} className="input" type="password" autoComplete="current-password" value={f.current_password} onChange={set("current_password")} />}
        </Field>
        <Field label="New password" required error={err("new_password")} hint="At least 8 characters; not too common or similar to your name or email.">
          {(a) => <input {...a} className="input" type="password" autoComplete="new-password" value={f.new_password} onChange={set("new_password")} />}
        </Field>
        <Field label="Confirm new password" required error={mismatch ? "The two passwords do not match." : undefined}>
          {(a) => <input {...a} className="input" type="password" autoComplete="new-password" value={f.confirm} onChange={set("confirm")} />}
        </Field>
        <div className="form-actions">
          <Button type="submit" icon={LuKeyRound} disabled={act.busy || !f.current_password || !f.new_password}>{act.busy ? "Saving…" : "Change password"}</Button>
        </div>
      </form>
    </Card>
  );
}

function TwoFactor() {
  const { user, refreshUser } = useAuth();
  const [setup, setSetup] = useState(null);
  const [code, setCode] = useState("");
  const act = useAction();
  const start = async () => { const r = await act.run(() => api.get("/auth/mfa/")); if (r) { setSetup(r); setCode(""); } };
  const confirm = async (e) => {
    e.preventDefault();
    if (await act.run(() => api.post("/auth/mfa/", { secret: setup.secret, code }), "Two-factor authentication is on.")) {
      setSetup(null); setCode(""); refreshUser();
    }
  };
  const disable = async (e) => {
    e.preventDefault();
    if (await act.run(() => api.delete("/auth/mfa/", { code }), "Two-factor authentication is off.")) { setCode(""); refreshUser(); }
  };
  return (
    <Card title="Two-factor authentication" subtitle="A 6-digit code from an authenticator app (Google Authenticator, Microsoft Authenticator, Authy…) at every sign-in."
      actions={<Badge tone={user.mfa_enabled ? "success" : undefined}>{user.mfa_enabled ? "On" : "Off"}</Badge>}>
      <ActionFeedback act={act} />
      {user.mfa_enabled ? (
        <form onSubmit={disable} noValidate>
          <Field label="Code from your app, or your password" error={act.error?.fields?.code?.[0]}>
            {(a) => <input {...a} className="input" type="password" value={code} onChange={(e) => setCode(e.target.value)} />}
          </Field>
          <div className="form-actions"><Button type="submit" variant="secondary" icon={LuShieldOff} disabled={act.busy || !code}>Turn off</Button></div>
        </form>
      ) : setup ? (
        <form onSubmit={confirm} noValidate>
          <ol className="stack-sm" style={{ paddingLeft: 18 }}>
            <li>In your authenticator app, add an account with this key (or open the link on your phone):
              <div className="mono" style={{ margin: "6px 0", padding: 8, background: "var(--bg)", borderRadius: 6, wordBreak: "break-all" }}>{setup.secret}</div>
              <a href={setup.otpauth_uri}>Open in authenticator app</a>
            </li>
            <li>Enter the 6-digit code it shows.</li>
          </ol>
          <Field label="Code" error={act.error?.fields?.code?.[0]}>
            {(a) => <input {...a} className="input mono" inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value)} />}
          </Field>
          <div className="form-actions">
            <Button variant="secondary" onClick={() => setSetup(null)}>Cancel</Button>
            <Button type="submit" icon={LuShieldCheck} disabled={act.busy || code.length < 6}>Turn on</Button>
          </div>
        </form>
      ) : (
        <>
          <Alert tone="info">Recommended for staff accounts that can see student records or approve grades and payments.</Alert>
          <div className="form-actions"><Button icon={LuShieldCheck} onClick={start} disabled={act.busy}>Set up two-factor authentication</Button></div>
        </>
      )}
    </Card>
  );
}

export default function Profile() {
  return (
    <>
      <PageHeader title="My profile" description="Your details, password and sign-in security." />
      <div className="grid grid--2">
        <Details />
        <div className="stack"><PasswordChange /><TwoFactor /></div>
      </div>
    </>
  );
}
