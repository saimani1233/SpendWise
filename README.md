# SpendWise

SpendWise is a full-stack personal finance application built with React, TypeScript, Vite, FastAPI, SQLAlchemy, and SQLite. It tracks income and expenses, supports expense categories and budgets, and provides monthly summaries, trends, and reports. It can be used as a public portfolio project; do not include private user data in the repository.

## Requirements

- Node.js and npm
- Python 3.12

## Windows setup

Open PowerShell in the project root (`Smart-Expence-Tracker`) and install frontend dependencies:

```powershell
npm install
```

Create the backend environment file and Python environment:

```powershell
Copy-Item backend\.env.example backend\.env
py -3.12 -m venv backend\.venv
.\backend\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
```

Edit `backend\.env` and set `JWT_SECRET_KEY` to a private random value at least 32 characters long. Keep `backend\.env` private and untracked. PowerShell activation can be enabled for the current terminal with `Set-ExecutionPolicy -Scope Process Bypass` if needed.

## Run the application

From the project root, start the API in one PowerShell terminal:

```powershell
.\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

Start Vite in a second terminal:

```powershell
npm run dev -- --host 127.0.0.1 --port 5173
```

Open the URL printed by Vite. FastAPI documentation is at `http://127.0.0.1:8000/docs`; the health check is `http://127.0.0.1:8000/api/health`.

The backend creates the SQLite database and tables on startup. Existing databases are migrated without deleting transaction records. Income records have no category; expenses retain their category links. Register an account in the app to sign in. To provision a local demo account instead, set both `DEMO_EMAIL` and `DEMO_PASSWORD` in your private `backend\.env` before startup. Do not publish or commit those values; this repository does not contain a shared demo password.

## Configuration

`backend\.env` supports these settings:

- `JWT_SECRET_KEY`: required private random value, at least 32 characters.
- `ACCESS_TOKEN_EXPIRE_MINUTES`: token lifetime (default `60`).
- `FRONTEND_ORIGINS`: comma-separated CORS origins (defaults include localhost and 127.0.0.1 on ports 5173 and 5174).
- `DATABASE_URL`: SQLAlchemy URL (defaults to the SQLite file under `backend`).
- `DEMO_EMAIL` and `DEMO_PASSWORD`: optional pair for locally provisioning a demo account.

## Features

JWT registration, login, and session lookup; bcrypt password hashing; profile and password updates; user-isolated expense and income CRUD and filters; expense category management; monthly summaries, trends, and category reports; monthly budgets; and recurring income and expense rules with idempotent due processing.
