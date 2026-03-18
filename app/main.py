from fastapi import FastAPI

from .routers import (
    academies as academies_router,
    auth as auth_router,
    billing as billing_router,
    chat as chat_router,
    leads as leads_router,
    policies as policies_router,
    rules as rules_router,
    sessions as sessions_router,
    users as users_router,
)

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Sports Posture API")

# allow frontend during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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

@app.get("/")
def read_root():
    return {"message": "Sports Posture API"}
