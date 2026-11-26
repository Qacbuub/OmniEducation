"""SMTP email backend that signs in step by step (AUTH LOGIN).

Some Python versions send the whole sign-in in one line (AUTH PLAIN with an initial response) and Gmail
then drops the connection instead of answering, which hides the real reason. Signing in one step at a
time works with every server and, when the password is wrong, returns Gmail's clear "535 Username and
Password not accepted" error.
"""
import smtplib

from django.core.mail.backends.smtp import EmailBackend as DjangoSMTPBackend


class _StepLogin:
    def login(self, user, password, *, initial_response_ok=True):
        self.ehlo_or_helo_if_needed()
        if not self.has_extn("auth"):
            raise smtplib.SMTPNotSupportedError("The mail server does not support sign-in.")
        self.user, self.password = user, password
        code, resp = self.auth("LOGIN", self.auth_login, initial_response_ok=False)
        if code not in (235, 503):
            raise smtplib.SMTPAuthenticationError(code, resp)
        return code, resp


class StepLoginSMTP(_StepLogin, smtplib.SMTP):
    pass


class StepLoginSMTPSSL(_StepLogin, smtplib.SMTP_SSL):
    pass


class EmailBackend(DjangoSMTPBackend):
    @property
    def connection_class(self):
        return StepLoginSMTPSSL if self.use_ssl else StepLoginSMTP
