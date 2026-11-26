"""Set up real email (Gmail) for OmniEducation, test it, and save it to backend/.env.

The App password is typed here, hidden, and only saved after Gmail has accepted it.
Run with setup-email.bat in the project folder.
"""
import getpass
import os
import re
import smtplib
import ssl
import sys

ENV = os.path.join(os.path.dirname(__file__), "..", ".env")


def read_env():
    with open(ENV, encoding="utf-8") as f:
        return f.read().splitlines()


def current(lines, key):
    for line in lines:
        if line.startswith(key + "="):
            return line.split("=", 1)[1]
    return ""


def save(lines, values):
    keys = set(values)
    out = [ln for ln in lines if ln.split("=", 1)[0] not in keys]
    out += [f"{k}={v}" for k, v in values.items()]
    with open(ENV, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")


def pause(code=0):
    input("\nPress Enter to close...")
    sys.exit(code)


lines = read_env()
print("=== OmniEducation: set up real email (Gmail) ===\n")
default_user = current(lines, "EMAIL_HOST_USER") or ""
user = input(f"Gmail address that sends the emails [{default_user}]: ").strip() or default_user
if not re.fullmatch(r"[^@\s]+@(gmail|googlemail)\.com", user, re.I):
    print("\nThis setup is for a @gmail.com address.")
    pause(1)

print(f"""
Create an App password for {user}:
  1. Open this link (it opens the right Google account):
     https://myaccount.google.com/apppasswords?authuser={user}
  2. If Google says the setting is not available, turn on 2-Step Verification first:
     https://myaccount.google.com/signinoptions/two-step-verification?authuser={user}
  3. App name: OmniEducation  ->  Create  ->  copy the 16 letters.
""")
password = getpass.getpass("Paste the App password here (it stays hidden) and press Enter: ")
password = re.sub(r"\s", "", password)
if not re.fullmatch(r"[a-zA-Z]{16}", password):
    print(f"\nThat is {len(password)} characters. An App password is exactly 16 letters - copy it again.")
    pause(1)

print("\nChecking with Gmail...")


def step_login(conn):
    """Sign in one step at a time (AUTH LOGIN) so Gmail gives a clear answer instead of hanging up."""
    conn.ehlo()
    conn.user, conn.password = user, password
    code, resp = conn.auth("LOGIN", conn.auth_login, initial_response_ok=False)
    if code != 235:
        raise smtplib.SMTPAuthenticationError(code, resp)


try:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=20) as s:
        step_login(s)
        s.sendmail(user, [user], f"From: OmniEducation <{user}>\r\nTo: {user}\r\nSubject: OmniEducation email works\r\n\r\n"
                                 "Real email is set up. Invitations and password resets will now be emailed.\r\n")
except smtplib.SMTPAuthenticationError as exc:
    print(f"""
Gmail's answer: {exc.smtp_code} {exc.smtp_error.decode(errors='replace')[:120]}
Gmail did not accept this App password for {user}. Nothing was saved.
Most often the App password was created while a DIFFERENT Google account was selected.
Use the link above (it contains your address), delete the old "OmniEducation" password there,
create a new one and run this again.""")
    pause(1)
except Exception as exc:  # noqa: BLE001
    print(f"\nCould not reach Gmail: {type(exc).__name__}: {exc}\nCheck the internet connection and antivirus email shield.")
    pause(1)

save(lines, {
    "EMAIL_BACKEND": "core.mail.EmailBackend",
    "EMAIL_HOST": "smtp.gmail.com", "EMAIL_PORT": "465", "EMAIL_USE_TLS": "false", "EMAIL_USE_SSL": "true",
    "EMAIL_HOST_USER": user, "EMAIL_HOST_PASSWORD": password,
    "DEFAULT_FROM_EMAIL": f"OmniEducation <{user}>",
})
print(f"""
Gmail accepted it and a test email was sent to {user} - check that inbox.
Saved to backend\\.env.  Now restart the backend (close the Backend tab, run start-backend-tab.bat)
so invitations are sent by real email.""")
pause(0)
