# Deployment

```
frontend  →  Vercel   (web/ — React/Vite, auto-deploy from main)
backend   →  Render   (FastAPI, free tier — cold starts acceptable)
                ↓
            Supabase  (PostgreSQL, existing project)
```

## Backend (Render)

Configured via `render.yaml` (blueprint). One-time setup:

1. Render dashboard → New → Blueprint → connect this repo
2. Set secret env vars when prompted:
   - `SUPABASE_URL` — Supabase project URL
   - `SUPABASE_PUBLISHABLE_KEY` — Supabase publishable key (`sb_publishable_...`;
     legacy `SUPABASE_ANON_KEY` also supported)
   - `CORS_ORIGINS` — comma-separated, e.g. `https://<your-app>.vercel.app`
   - `AUTH_SECRET` — signs the session tokens, 32 bytes or more (#60).
     `python -c "import secrets; print(secrets.token_urlsafe(48))"`
   - `PICKER_PINS` — every picker's PIN, PBKDF2-hashed. Generate the whole
     object in one go: `uv run python scripts/make_pin.py Griffin 1234 Harry 5678`
3. Deploys automatically on push to `main`

Without `AUTH_SECRET` and `PICKER_PINS` every sign-in fails and no picks can be
saved, which is the intended default for an unconfigured deploy. Rotating
`AUTH_SECRET` signs everyone out.

`requirements.txt` is generated from `uv.lock` (core deps only, no analysis/notebook
tooling) — regenerate after dependency changes:

```bash
make deploy-prep
```

## Frontend (Vercel)

1. Vercel dashboard → New Project → import this repo
2. Set **Root Directory** to `web/`
3. Framework preset: Vite (build `npm run build`, output `dist/`)
4. Env var: `VITE_API_URL` — the Render backend URL, e.g. `https://g-nfl-api.onrender.com`
5. Auto-deploys on push to `main`

## Local development

```bash
make api   # FastAPI on :8000
make web   # Vite dev server on :5173 (proxies /api to :8000)
```

Backend reads `SUPABASE_URL` / `SUPABASE_ANON_KEY` from `.env` (via python-dotenv).

## Notes

- Render free tier sleeps after inactivity — first request after idle takes ~30s.
  Upgrade to Starter ($7/mo) if cold starts become annoying.
- No auth yet: `picker` is passed explicitly by the frontend. When auth lands,
  replace the picker param with session identity in `src/g_nfl/api/main.py`.
- The Streamlit app (`app/`) is the fantasy draft board and nothing else. Its
  picks pages were deleted in #91 once the React app reached parity; picks,
  spreads and standings live in `web/` now.
