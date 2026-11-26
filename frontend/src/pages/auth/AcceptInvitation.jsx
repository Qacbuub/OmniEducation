import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { LuUserCheck } from "react-icons/lu";
import { api, tokens } from "../../api/client";
import { Alert, Button, Field, Spinner } from "../../components/ui";
import AuthLayout from "./AuthLayout";

/** Opened from the invitation email: /accept-invitation?token=… */
export default function AcceptInvitation() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const navigate = useNavigate();
  const [invite, setInvite] = useState(null);
  const [lookupError, setLookupError] = useState(null);
  const [form, setForm] = useState({ first_name: "", last_name: "", new_password: "" });
  const [state, setState] = useState({ loading: false, error: null });

  useEffect(() => {
    api.get(`/auth/invitations/${encodeURIComponent(token)}/`)
      .then((d) => { setInvite(d); setForm((f) => ({ ...f, first_name: d.first_name || "", last_name: d.last_name || "" })); })
      .catch(setLookupError);
  }, [token]);

  async function submit(e) {
    e.preventDefault();
    setState({ loading: true, error: null });
    try {
      const data = await api.post("/auth/invitations/accept/", { token, ...form });
      tokens.set({ access: data.access, refresh: data.refresh });
      window.location.assign("/"); // reload so the session starts cleanly
    } catch (error) {
      setState({ loading: false, error });
    }
  }

  const f = state.error?.fields || {};
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  return (
    <AuthLayout>
      <div className="auth__form">
        {lookupError ? (
          <>
            <h2>Invitation unavailable</h2>
            <Alert tone="error">{lookupError.fields?.token?.[0] || "This invitation link is invalid."}</Alert>
            <Button variant="secondary" block onClick={() => navigate("/login")}>Back to sign in</Button>
          </>
        ) : !invite ? <Spinner /> : (
          <form onSubmit={submit} noValidate>
            <h2>Join {invite.institution || "OmniEducation"}</h2>
            <p>You've been invited as <strong>{invite.role}</strong> using <strong>{invite.email}</strong>.</p>
            {state.error && !Object.keys(f).length && <Alert tone="error">{state.error.message}</Alert>}
            {f.token && <Alert tone="error">{f.token[0]}</Alert>}
            <div className="form-grid">
              <Field label="First name" error={f.first_name?.[0]}>
                {(a) => <input {...a} className="input" autoComplete="given-name" value={form.first_name} onChange={set("first_name")} required />}
              </Field>
              <Field label="Last name" error={f.last_name?.[0]}>
                {(a) => <input {...a} className="input" autoComplete="family-name" value={form.last_name} onChange={set("last_name")} required />}
              </Field>
            </div>
            <Field label="Create a password" error={f.new_password?.join(" ")} hint="At least 8 characters; not a common password.">
              {(a) => <input {...a} className="input" type="password" autoComplete="new-password" value={form.new_password} onChange={set("new_password")} required />}
            </Field>
            <Button type="submit" block icon={LuUserCheck} disabled={state.loading}>
              {state.loading ? "Creating account…" : "Accept invitation"}
            </Button>
            <p style={{ marginTop: 16, textAlign: "center" }}><Link to="/login">Already have an account? Sign in</Link></p>
          </form>
        )}
      </div>
    </AuthLayout>
  );
}
