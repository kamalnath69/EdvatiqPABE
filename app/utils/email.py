import os
import ssl
import smtplib
from email.message import EmailMessage

APP_NAME = os.getenv("APP_NAME", "Edvatiq")
APP_URL = os.getenv("APP_URL") or os.getenv("FRONTEND_URL") or "http://localhost:5173"
SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "support@edvatiq.com")

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or SUPPORT_EMAIL)
SMTP_TLS = os.getenv("SMTP_TLS", "true").lower() in ("1", "true", "yes")
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "true").lower() in ("1", "true", "yes")


def _is_gmail_host(host: str) -> bool:
    value = (host or "").strip().lower()
    return "gmail.com" in value or "googlemail.com" in value


def _email_shell(title: str, preheader: str, body_html: str, cta_text: str | None = None, cta_url: str | None = None) -> str:
    cta_block = ""
    if cta_text and cta_url:
        cta_block = f"""
          <div style="margin:24px 0;">
            <a href="{cta_url}" style="display:inline-block;background:#111111;color:#ffffff;text-decoration:none;padding:12px 22px;border-radius:999px;font-weight:600;">
              {cta_text}
            </a>
          </div>
        """
    return f"""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>{title}</title>
      </head>
      <body style="margin:0;background:#f7f8fb;font-family:Arial,Helvetica,sans-serif;color:#111111;">
        <span style="display:none;visibility:hidden;opacity:0;height:0;width:0;">{preheader}</span>
        <div style="max-width:600px;margin:0 auto;padding:32px 20px;">
          <div style="background:#ffffff;border:1px solid #e6e9f0;border-radius:20px;padding:28px;">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;">
              <div style="width:36px;height:36px;border-radius:12px;background:#f7c948;color:#111111;font-weight:700;display:grid;place-items:center;">
                E
              </div>
              <div>
                <div style="font-size:12px;text-transform:uppercase;letter-spacing:0.12em;color:#5e6472;">Performance Intelligence</div>
                <div style="font-size:18px;font-weight:700;">{APP_NAME}</div>
              </div>
            </div>
            <h2 style="margin:0 0 12px;font-size:24px;">{title}</h2>
            {body_html}
            {cta_block}
            <p style="margin:24px 0 0;font-size:13px;color:#5e6472;">
              Need help? Contact us at <a href="mailto:{SUPPORT_EMAIL}" style="color:#111111;">{SUPPORT_EMAIL}</a>.
            </p>
          </div>
          <p style="font-size:12px;color:#8b90a0;margin-top:16px;text-align:center;">
            {APP_NAME} • {APP_URL}
          </p>
        </div>
      </body>
    </html>
    """


def send_email(to_email: str, subject: str, html: str, text: str | None = None) -> None:
    if not EMAIL_ENABLED:
        return
    if not SMTP_HOST:
        raise RuntimeError("SMTP_HOST is not configured.")
    if not SMTP_USER or not SMTP_PASSWORD:
        raise RuntimeError("SMTP_USER and SMTP_PASSWORD must be configured when EMAIL_ENABLED=true.")
    if _is_gmail_host(SMTP_HOST) and len(SMTP_PASSWORD.replace(" ", "")) < 16:
        raise RuntimeError(
            "Gmail SMTP requires a Google App Password. Set SMTP_USER to your Gmail address and "
            "SMTP_PASSWORD to a 16-character App Password."
        )

    message = EmailMessage()
    message["From"] = SMTP_FROM
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(text or "Please view this email in HTML format.")
    message.add_alternative(html, subtype="html")

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
            if SMTP_TLS:
                smtp.starttls(context=context)
            smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        if _is_gmail_host(SMTP_HOST):
            raise RuntimeError(
                "Gmail SMTP authentication failed. Use a Google App Password instead of your normal Gmail password, "
                "or set EMAIL_ENABLED=false for local development."
            ) from exc
        raise RuntimeError("SMTP authentication failed. Check SMTP_USER, SMTP_PASSWORD, and provider settings.") from exc


def build_verification_email(code: str, recipient_name: str) -> tuple[str, str, str]:
    title = "Verify your Edvatiq email"
    preheader = "Use this code to verify your Edvatiq account."
    body_html = f"""
      <p style="margin:0 0 12px;color:#2b2f3a;">Hi {recipient_name},</p>
      <p style="margin:0 0 16px;color:#2b2f3a;">
        Use the verification code below to confirm your email address.
      </p>
      <div style="font-size:28px;letter-spacing:6px;font-weight:700;background:#fdf4cf;border:1px dashed #f7c948;border-radius:16px;padding:16px;text-align:center;">
        {code}
      </div>
      <p style="margin:16px 0 0;color:#5e6472;font-size:13px;">
        This code expires in 15 minutes.
      </p>
    """
    html = _email_shell(title, preheader, body_html, "Verify account", f"{APP_URL}/verify-email")
    text = f"Your Edvatiq verification code is {code}. It expires in 15 minutes."
    return subject_for(title), html, text


def build_signup_verification_email(code: str, recipient_name: str) -> tuple[str, str, str]:
    title = "Verify your email to start checkout"
    preheader = "Use this code to continue with your Edvatiq plan."
    body_html = f"""
      <p style="margin:0 0 12px;color:#2b2f3a;">Hi {recipient_name},</p>
      <p style="margin:0 0 16px;color:#2b2f3a;">
        Use the verification code below to confirm your email and continue checkout.
      </p>
      <div style="font-size:28px;letter-spacing:6px;font-weight:700;background:#fdf4cf;border:1px dashed #f7c948;border-radius:16px;padding:16px;text-align:center;">
        {code}
      </div>
      <p style="margin:16px 0 0;color:#5e6472;font-size:13px;">
        This code expires in 15 minutes.
      </p>
    """
    html = _email_shell(title, preheader, body_html, "Continue checkout", f"{APP_URL}/signup")
    text = f"Your Edvatiq checkout verification code is {code}. It expires in 15 minutes."
    return subject_for(title), html, text


def build_password_reset_email(code: str, recipient_name: str) -> tuple[str, str, str]:
    title = "Reset your Edvatiq password"
    preheader = "Use this code to reset your Edvatiq password."
    body_html = f"""
      <p style="margin:0 0 12px;color:#2b2f3a;">Hi {recipient_name},</p>
      <p style="margin:0 0 16px;color:#2b2f3a;">
        We received a request to reset your password. Use the code below to continue.
      </p>
      <div style="font-size:28px;letter-spacing:6px;font-weight:700;background:#fdf4cf;border:1px dashed #f7c948;border-radius:16px;padding:16px;text-align:center;">
        {code}
      </div>
      <p style="margin:16px 0 0;color:#5e6472;font-size:13px;">
        If you did not request a reset, you can ignore this email.
      </p>
    """
    html = _email_shell(title, preheader, body_html, "Reset password", f"{APP_URL}/reset-password")
    text = f"Your Edvatiq password reset code is {code}. It expires in 15 minutes."
    return subject_for(title), html, text


def build_welcome_email(recipient_name: str) -> tuple[str, str, str]:
    title = "Welcome to Edvatiq"
    preheader = "Your Edvatiq workspace is ready."
    body_html = f"""
      <p style="margin:0 0 12px;color:#2b2f3a;">Hi {recipient_name},</p>
      <p style="margin:0 0 16px;color:#2b2f3a;">
        Welcome to Edvatiq. Your workspace is ready to track performance, analyze sessions, and drive improvements.
      </p>
      <ul style="margin:0 0 16px;padding-left:18px;color:#5e6472;">
        <li>Launch live coaching sessions with posture intelligence.</li>
        <li>Review session scores and best reps instantly.</li>
        <li>Ask the AI coach for targeted guidance.</li>
      </ul>
    """
    html = _email_shell(title, preheader, body_html, "Go to login", f"{APP_URL}/login")
    text = "Welcome to Edvatiq. Your workspace is ready."
    return subject_for(title), html, text


def build_invite_email(token: str, recipient_name: str, role: str) -> tuple[str, str, str]:
    title = "You have been invited to Edvatiq"
    preheader = "Accept your invitation and activate your workspace."
    invite_url = f"{APP_URL}/signup?invite={token}"
    body_html = f"""
      <p style="margin:0 0 12px;color:#2b2f3a;">Hi {recipient_name},</p>
      <p style="margin:0 0 16px;color:#2b2f3a;">
        You've been invited to join Edvatiq as <strong>{role}</strong>. Accept the invite to access your workspace.
      </p>
      <p style="margin:0 0 16px;color:#5e6472;">
        If the button does not work, open the signup page and use this invite token:
      </p>
      <div style="font-size:18px;letter-spacing:1px;font-weight:700;background:#f7f8fb;border:1px solid #dfe4ee;border-radius:12px;padding:14px;text-align:center;">
        {token}
      </div>
    """
    html = _email_shell(title, preheader, body_html, "Accept invite", invite_url)
    text = f"You have been invited to Edvatiq as {role}. Use invite token {token} or visit {invite_url}."
    return subject_for(title), html, text


def subject_for(title: str) -> str:
    return f"{APP_NAME} — {title}"
