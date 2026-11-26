"""Check the email settings in backend/.env step by step (the password is never printed).

Run from the backend folder:  .venv\\Scripts\\python scripts\\test_email.py  [address-to-send-a-test-to]
"""
import base64
import os
import smtplib
import ssl
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
host = os.environ.get("EMAIL_HOST", "")
port = int(os.environ.get("EMAIL_PORT", "587"))
use_ssl = os.environ.get("EMAIL_USE_SSL", "").lower() in {"1", "true", "yes"}
user = os.environ.get("EMAIL_HOST_USER", "")
password = os.environ.get("EMAIL_HOST_PASSWORD", "")
to = sys.argv[1] if len(sys.argv) > 1 else user

print(f"Python {sys.version.split()[0]}  server {host}:{port}  {'SSL' if use_ssl else 'STARTTLS'}  user {user}")
print(f"Password: {len(password)} characters, spaces: {'yes' if ' ' in password else 'no'}")


def step(label, fn, expect=None):
    try:
        result = fn()
        if expect and isinstance(result, tuple) and result[0] != expect:
            raise RuntimeError(f"server replied {result[0]}: {result[1].decode(errors='replace')}")
        print(f"  OK   {label}: {result}")
        return result
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL {label}: {type(exc).__name__}: {exc}")
        input("\nPress Enter to close...")
        sys.exit(1)


ctx = ssl.create_default_context()
if use_ssl:
    s = step("connect (SSL)", lambda: smtplib.SMTP_SSL(host, port, context=ctx, timeout=20))
else:
    s = step("connect", lambda: smtplib.SMTP(host, port, timeout=20))
    step("hello", lambda: s.ehlo()[0])
    step("start TLS", lambda: s.starttls(context=ctx)[0])
step("hello (encrypted)", lambda: s.ehlo()[0])
step("server offers sign-in methods", lambda: s.esmtp_features.get("auth", "none"))
# Sign in one step at a time with AUTH LOGIN, printing only the server's replies.
step("AUTH LOGIN", lambda: s.docmd("AUTH", "LOGIN"), 334)
step("send user name", lambda: s.docmd(base64.b64encode(user.encode()).decode()), 334)
step("send password", lambda: s.docmd(base64.b64encode(password.encode()).decode()), 235)
step("send test email", lambda: s.sendmail(user, [to], f"From: {user}\r\nTo: {to}\r\nSubject: OmniEducation test\r\n\r\n"
                                                         "If you can read this, email from OmniEducation works.\r\n") or "sent")
s.quit()
print(f"\nAll good: a test email was sent to {to}.")
input("\nPress Enter to close...")
