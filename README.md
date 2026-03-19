# Backend Service

This directory contains the FastAPI backend for the sports posture analysis
application.

## Setup

```bash
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

Copy or edit `.env` with your MongoDB URI and SECRET_KEY.
For live pose tracking, also configure the pose model file:

```bash
POSE_MODEL_PATH=E:\path\to\pose_landmarker_full.task
```

If `POSE_MODEL_PATH` is not set, backend will look for `pose_landmarker_full.task`
under common project paths like `backend/` and `backend/app/`.

## Email verification setup

Verification and password-reset flows use SMTP. Add these environment variables:

```bash
EMAIL_ENABLED=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_TLS=true
SMTP_USER=your-account@gmail.com
SMTP_PASSWORD=your-16-char-app-password
SMTP_FROM=your-account@gmail.com
SUPPORT_EMAIL=your-account@gmail.com
APP_URL=http://localhost:5173
```

Important for Gmail:

- Do not use your normal Gmail password.
- Use a Google App Password from a Google account with 2-Step Verification enabled.
- If you are developing locally and do not want email delivery yet, set `EMAIL_ENABLED=false`.

## Running

```bash
uvicorn app.main:app --reload
```

Endpoints include authentication, user & academy management, sport rules,
session recording, etc. See `app/main.py` for the full API surface.

Utility modules live in `app/utils` and are shared with example scripts.

## Frontend

A simple React + Vite frontend lives in `../frontend`. After starting the
backend, open a separate shell and run:

```bash
cd ../frontend
npm install    # or yarn
npm run dev     # starts on http://localhost:5173
```

The dev server proxies `/api` requests to the backend so both pieces work
together.
