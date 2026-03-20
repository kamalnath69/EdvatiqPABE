import os

from fastapi import FastAPI

from .routers import (
    academies as academies_router,
    attachments as attachments_router,
    audit as audit_router,
    auth as auth_router,
    billing as billing_router,
    calendar as calendar_router,
    chat as chat_router,
    coach_reviews as coach_reviews_router,
    favorites as favorites_router,
    help_docs as help_docs_router,
    invites as invites_router,
    leads as leads_router,
    notifications as notifications_router,
    policies as policies_router,
    reports as reports_router,
    rules as rules_router,
    search as search_router,
    sessions as sessions_router,
    settings as settings_router,
    system as system_router,
    training_plans as training_plans_router,
    users as users_router,
    wallet as wallet_router,
)

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Sports Posture API")


def _parse_cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "").strip()
    if raw:
        return [origin.strip() for origin in raw.split(",") if origin.strip()]
    return [
        "http://localhost:5173",
        "http://localhost:4173",
        "https://edvatiq.vercel.app",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# include all modular routers
app.include_router(auth_router.router)
app.include_router(billing_router.router)
app.include_router(users_router.router)
app.include_router(academies_router.router)
app.include_router(sessions_router.router)
app.include_router(rules_router.router)
app.include_router(chat_router.router)
app.include_router(leads_router.router)
app.include_router(policies_router.router)
app.include_router(settings_router.router)
app.include_router(notifications_router.router)
app.include_router(reports_router.router)
app.include_router(training_plans_router.router)
app.include_router(coach_reviews_router.router)
app.include_router(calendar_router.router)
app.include_router(audit_router.router)
app.include_router(help_docs_router.router)
app.include_router(invites_router.router)
app.include_router(favorites_router.router)
app.include_router(attachments_router.router)
app.include_router(search_router.router)
app.include_router(system_router.router)
app.include_router(wallet_router.router)

@app.get("/")
def read_root():
    return {"message": "Sports Posture API"}
