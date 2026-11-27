import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { LuLogIn, LuEye, LuEyeOff } from "react-icons/lu";
import { useAuth } from "../../auth/AuthContext";
import { homePathForUser, ROLE_LABELS } from "../../config/roles";
import { DEMO_ACCOUNTS, DEMO_PASSWORD } from "../../config/demoAccounts";
import { Alert, Button, Field } from "../../components/ui";
import AuthLayout from "./AuthLayout";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ email: "", password: "", otp: "" });
  const [needOtp, setNeedOtp] = useState(false);
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function onSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const user = await login(form.email, form.password, needOtp ? form.otp : undefined);
      const from = location.state?.from;
      navigate(from && from !== "/login" ? from : homePathForUser(user), { replace: true });
    } catch (err) {
      // Accounts with two-factor authentication need a code from the authenticator app as well.
      if (err.code === "mfa_required") { setNeedOtp(true); setError(null); return; }
      setError(err);
    } finally {
      setSubmitting(false);
    }
  }

  const fieldErr = (k) => error?.fields?.[k]?.[0];

  return (
    <AuthLayout>
      <form className="auth__form" onSubmit={onSubmit} noValidate>
        <h2>Sign in</h2>
        <p>Welcome back. Sign in to your institution's workspace.</p>

        {error && !Object.keys(error.fields || {}).length && <Alert tone="error">{error.message}</Alert>}

        <Field label="Email address" error={fieldErr("email")}>
          {(a) => <input {...a} className="input" type="email" autoComplete="username" value={form.email} onChange={set("email")} required />}
        </Field>

        <Field label="Password" error={fieldErr("password")}>
          {(a) => (
            <div style={{ position: "relative" }}>
              <input {...a} className="input" type={showPw ? "text" : "password"} autoComplete="current-password"
                value={form.password} onChange={set("password")} required style={{ paddingRight: 44 }} />
              <button type="button" className="icon-btn" onClick={() => setShowPw((s) => !s)}
                aria-label={showPw ? "Hide password" : "Show password"}
                style={{ position: "absolute", right: 0, top: 0, height: 40 }}>
                {showPw ? <LuEyeOff /> : <LuEye />}
              </button>
            </div>
          )}
        </Field>

        {needOtp && (
          <Field label="Authentication code" hint="Open your authenticator app and enter the 6-digit code." error={fieldErr("otp")}>
            {(a) => <input {...a} className="input mono" inputMode="numeric" autoComplete="one-time-code" maxLength={6}
              value={form.otp} onChange={set("otp")} autoFocus required />}
          </Field>
        )}

        <div className="auth__row">
          <span />
          <Link to="/forgot-password">Forgot password?</Link>
        </div>

        <Button type="submit" block icon={LuLogIn} disabled={submitting}>
          {submitting ? "Signing in…" : "Sign in"}
        </Button>

        <p className="auth__apply">New applicant? <Link to="/apply">Apply online to a school or university</Link></p>

        <div className="demo-box" aria-label="Demo accounts">
          <div className="demo-box__title">Demo accounts · password <span className="mono">{DEMO_PASSWORD}</span></div>
          {DEMO_ACCOUNTS.map((g) => (
            <div key={g.group} style={{ marginBottom: 10 }}>
              <div className="muted" style={{ fontSize: "var(--fs-xs)", marginBottom: 6 }}>{g.group}</div>
              <div className="demo-box__grid">
                {g.accounts.map((a) => (
                  <button key={a.email} type="button" className="chip" title={a.email}
                    onClick={() => { setForm({ email: a.email, password: DEMO_PASSWORD, otp: "" }); setNeedOtp(false); }}>
                    {ROLE_LABELS[a.role]}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </form>
    </AuthLayout>
  );
}
