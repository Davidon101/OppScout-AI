# OppScout AI

Find What Fits. Become What's Next.

AI-assisted opportunity discovery for students, graduates and young professionals. Django, HTMX, PostgreSQL, Gemini.

## Run locally (Windows PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python manage.py makemigrations opportunities
python manage.py migrate
python manage.py createsuperuser
python manage.py test
python manage.py runserver
```

Open http://127.0.0.1:8000/ and add listings at http://127.0.0.1:8000/admin/.

Without `DATABASE_URL`, local development uses SQLite. Production uses Neon Postgres.

## Deploy (Render + Neon)

1. Push to GitHub.
2. Create a Neon project and copy its connection string.
3. In Render, create a Blueprint from the repo (`render.yaml`).
4. Set `DATABASE_URL`, `GEMINI_API_KEY` and `GEMINI_MODEL` in the Render dashboard.
5. Create the admin account with the Render shell, or run `createsuperuser` locally against the Neon URL.

## Adding listings

Use the admin, or edit `data/seed_opportunities.json` and run:

```powershell
python manage.py load_opportunities
```

The loader matches on `slug`, so re-running updates instead of duplicating. Only listings with `"status": "published"` appear publicly. Verify every deadline and requirement against the official page and set `last_verified`.

## Status

- Day 1: settings, models, admin, base layout, health check.
- Day 2: public directory with search and filters (HTMX), detail pages, seed loader.
- Day 3: profile form (kept in your browser, sent per request, never stored), matching with explanations, demo login/register screens, self-hosted HTMX.

Evaluate matching quality against the labelled profiles: `python manage.py evaluate_matching`.
- Day 4: eligibility check on each listing page (AI compares your saved profile with the stored requirements; region and education are checked by code). Needs `GEMINI_API_KEY` in `.env`; without it the button explains that AI is unavailable.
- Day 5: "What am I missing?" gap analysis on each listing (same caps and privacy as the eligibility check), and Save buttons with a Saved page (slugs kept in this browser only).
- Day 6: production settings (HTTPS redirect, HSTS, logging), 404/500 pages, `render.yaml` with seed load and superuser creation. Follow `DEPLOY.md`.
- Day 7a: organization portal at `/for-organizations/` (key-based, no logins; listings are approved by an admin). Run `python manage.py migrate` for migration 0003.
