from .email import build_verification_email, build_welcome_email, send_email
from .verification import create_email_verification


async def send_verification_email(user_doc: dict) -> None:
    email = user_doc.get("email")
    if not email:
        return
    username = user_doc.get("username") or "there"
    display_name = user_doc.get("full_name") or username
    if user_doc.get("email_verified", False):
        return
    code = await create_email_verification(username, email)
    subject, html, text = build_verification_email(code, display_name)
    send_email(email, subject, html, text)


def send_welcome_email(user_doc: dict) -> None:
    email = user_doc.get("email")
    if not email:
        return
    display_name = user_doc.get("full_name") or user_doc.get("username") or "there"
    subject, html, text = build_welcome_email(display_name)
    send_email(email, subject, html, text)


async def send_onboarding_emails(user_doc: dict) -> None:
    await send_verification_email(user_doc)
    send_welcome_email(user_doc)
