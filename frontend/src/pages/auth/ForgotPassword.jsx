import { useState } from "react";
import { Link } from "react-router-dom";
import { LuMail, LuArrowLeft } from "react-icons/lu";
import { api } from "../../api/client";
import { Alert, Button, Field } from "../../components/ui";
import AuthLayout from "./AuthLayout";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState({ sent: false, error: null, loading: false });

  async function onSubmit(e) {
    e.preventDefault();
    setStatus({ sent: false, error: null, loading: true });
    try {
      // The backend always answers the same way, so this can't be used to discover accounts.
      await api.post("/auth/password-reset/", { email });
      setStatus({ sent: true, error: null, loading: false });
    } catch (error) {
      setStatus({ sent: false, error, loading: false });
    }
  }

  return (
    <AuthLayout>
      <form className="auth__form" onSubmit={onSubmit}>
        <h2>Reset your password</h2>
        <p>Enter your account email and we'll send a secure, single-use reset link.</p>
        {status.sent && <Alert tone="success">If an account exists for that email, a reset link has been sent. It expires in 1 hour.</Alert>}
        {status.error && <Alert tone="error">{status.error.message}</Alert>}
        <Field label="Email address">
          {(a) => <input {...a} className="input" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />}
        </Field>
        <Button type="submit" block icon={LuMail} disabled={status.loading}>
          {status.loading ? "Sending…" : "Send reset link"}
        </Button>
        <p style={{ marginTop: 20, textAlign: "center" }}>
          <Link to="/login"><LuArrowLeft style={{ verticalAlign: -2 }} aria-hidden="true" /> Back to sign in</Link>
        </p>
      </form>
    </AuthLayout>
  );
}
