import { useState } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { homePathForUser } from "../config/roles";
import { Alert, Button, Spinner } from "../components/ui";
import AuthLayout from "../pages/auth/AuthLayout";

/** Requires a logged-in user. Optionally restricts to one navigation mode. */
export function RequireAuth({ mode }) {
  const { user, loading, mode: userMode } = useAuth();
  const location = useLocation();
  if (loading) return <Spinner label="Restoring your session" />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  // A school user must never land in the university shell (and vice versa).
  if (mode && userMode !== mode) return <Navigate to={homePathForUser(user)} replace />;
  return <Outlet />;
}

/** Redirects logged-in users away from the login page. */
export function GuestOnly() {
  const { user, loading } = useAuth();
  if (loading) return <Spinner label="Loading" />;
  if (user) return <Navigate to={homePathForUser(user)} replace />;
  return <Outlet />;
}

export function HomeRedirect() {
  const { user, loading } = useAuth();
  if (loading) return <Spinner label="Loading" />;
  return <Navigate to={user ? homePathForUser(user) : "/login"} replace />;
}

/**
 * For links sent to someone by email (invitation, password reset). If the browser is signed in as another
 * account – typically the admin who copied the link – say so and offer to sign out, instead of silently
 * sending them to their own dashboard.
 */
export function SignedOutLink() {
  const { user, loading, logout } = useAuth();
  const [busy, setBusy] = useState(false);
  if (loading) return <Spinner label="Loading" />;
  if (!user) return <Outlet />;
  const signOut = async () => { setBusy(true); await logout(); setBusy(false); };
  return (
    <AuthLayout>
      <div className="auth__form">
        <h2>This link is for another account</h2>
        <Alert tone="info">
          This tab is already signed in to an account. Sign out to continue with this link, or open the link
          in a new tab or a private window to stay signed in here.
        </Alert>
        <Button block onClick={signOut} disabled={busy}>{busy ? "Signing out…" : "Sign out and continue"}</Button>
        <Button block variant="secondary" onClick={() => window.location.assign(homePathForUser(user))}>Back to my dashboard</Button>
      </div>
    </AuthLayout>
  );
}
