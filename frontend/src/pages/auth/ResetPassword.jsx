import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { LuKeyRound } from "react-icons/lu";
import { api } from "../../api/client";
import { Alert, Button, Field } from "../../components/ui";
import AuthLayout from "./AuthLayout";

/** Opened from the emailed link: /reset-password?uid=…&token=… */
export default function ResetPassword() {
  const [params] = useSearchParams();
  const [pw, setPw] = useState({ new_password: "", confirm: "" });
  const [state, setState] = useState({ loading: false, error: null, done: false });
  const mismatch = pw.confirm && pw.confirm !== pw.new_password;

  async function submit(e) {
    e.preventDefault();
    if (mismatch) return;
    setState({ loading: true, error: null, done: false });
    try {
      await api.post("/auth/password-reset/confirm/", {
        uid: params.get("uid"), token: params.get("token"), new_password: pw.new_password,
      });
      setState({ loading: false, error: null, done: true });
    } catch (error) {
      setState({ loading: false, error, done: false });
    }
  }

  const err = state.error?.fields;
  return (
    <AuthLayout>
      <form className="auth__form" onSubmit={submit} noValidate>
        <h2>Choose a new password</h2>
        <p>Use at least 8 characters. Avoid common words and your name.</p>
        {state.done ? (
          <>
            <Alert tone="success">Your password has been reset. You've been signed out on all devices.</Alert>
            <Link className="btn btn--primary btn--block" to="/login">Go to sign in</Link>
          </>
        ) : (
          <>
            {err?.token && <Alert tone="error">{err.token[0]} <Link to="/forgot-password">Request a new link</Link></Alert>}
            {state.error && !err?.token && !err?.new_password && <Alert tone="error">{state.error.message}</Alert>}
            <Field label="New password" error={err?.new_password?.join(" ")}>
              {(a) => <input {...a} className="input" type="password" autoComplete="new-password" value={pw.new_password}
                onChange={(e) => setPw({ ...pw, new_password: e.target.value })} required />}
            </Field>
            <Field label="Confirm new password" error={mismatch ? "Passwords don't match." : undefined}>
              {(a) => <input {...a} className="input" type="password" autoComplete="new-password" value={pw.confirm}
                onChange={(e) => setPw({ ...pw, confirm: e.target.value })} required />}
            </Field>
            <Button type="submit" block icon={LuKeyRound} disabled={state.loading || !pw.new_password || mismatch}>
              {state.loading ? "Saving…" : "Reset password"}
            </Button>
          </>
        )}
      </form>
    </AuthLayout>
  );
}
