# SpendWise project notes

## Structure
- Root Vite app: `src/main.tsx` mounts the existing SpendWise UI from `frontend/src/App.jsx` inside React Router. The existing page design and feature components stay intact.
- `frontend/src/services/api.js` centralizes API URL, Axios requests, bearer tokens, and validation error formatting.
- `backend/app/` contains the FastAPI application, SQLAlchemy models/session, configuration, and JWT/password utilities.

## Features
- SQLite database, created automatically on API startup.
- Demo account and per-user default categories are seeded when the API starts.
- Registration/login, bcrypt password hashes, expiring JWTs, profile/password updates.
- User-scoped income and expense CRUD/filtering, categories, monthly budgets, recurring items and due processing.
- Dashboard/monthly summaries, trends, category spending, and comparison reports.

## Verification
- Frontend `npm run build` and `npm run lint` are the project checks.
- Backend tests live in `backend/tests`; API integration can be checked with FastAPI's TestClient.
- Local start commands and demo credentials are documented in `README.md`.
