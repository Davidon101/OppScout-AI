# Deploying OppScout AI (Render + Neon)

Everything below is free-tier. Keep your passwords, the Neon connection string and the Gemini key out of chat, screenshots and git. Paste them only into Render's environment settings and your local `.env`.

## 1. Put the project on GitHub

1. Create an empty **private** repository on GitHub.
2. In the project folder:
   ```
   git init
   git add .
   git commit -m "OppScout AI"
   git branch -M main
   git remote add origin <your repo URL>
   git push -u origin main
   ```
3. Check that `.env` and `db.sqlite3` are NOT in the repo (`.gitignore` already excludes them).

## 2. Neon database (already created)

1. Neon dashboard > your project > **Connect**.
2. Choose the **pooled** connection and copy the string. It looks like `postgresql://user:password@ep-...-pooler.<region>.aws.neon.tech/neondb?sslmode=require`.
3. Keep it for step 3. If a connection error mentions `channel_binding`, delete `&channel_binding=require` from the string.

## 3. Render

1. render.com > **New** > **Blueprint** > connect the GitHub repo. Render reads `render.yaml`.
2. It asks for the values marked "sync: false". Fill in:

| Variable | Value |
|---|---|
| `DATABASE_URL` | the Neon string from step 2 |
| `GEMINI_API_KEY` | your key from AI Studio |
| `DJANGO_SUPERUSER_USERNAME` | admin login name of your choice |
| `DJANGO_SUPERUSER_EMAIL` | your email |
| `DJANGO_SUPERUSER_PASSWORD` | a long password you have not used elsewhere |

   `SECRET_KEY` is generated for you. `GEMINI_MODEL` is preset to `gemini-3.1-flash-lite`.
3. Create the service. The first build installs packages, collects static files, migrates the Neon database, loads the 9 seed listings and creates your admin user. It takes a few minutes.
4. Your site is at `https://oppscout-xxxx.onrender.com` (Render shows the exact address).

## 4. First-run checklist

1. `/healthz/` returns OK.
2. Home page loads, `/opportunities/` shows 9 listings (some marked closed).
3. `/profile/`: fill in a profile, press Find. MLH should rank first for a Python/AI profile.
4. Open a listing, press **Check my eligibility**. This is the first real Gemini call.
   - Works: you see a verdict and per-requirement rows.
   - "AI checks are not available right now": the key is missing or wrong. Check `GEMINI_API_KEY` in Render.
   - "The AI service had a problem": open Render > Logs and look for the HTTP code (400 means a request-format problem; send me that line, not the key).
5. Press **Show what to work on** on the same listing.
6. `/admin/`: log in with the superuser. Check you can edit a listing.
7. Press Save on two listings and open `/saved/`.

## 4b. Approving organization listings

Organizations post at `/for-organizations/`. Their listings arrive as **Pending review**.

1. `/admin/` > Opportunities > filter Status = Pending review.
2. Open each one. Check the organization is real (Organizations list: website, email domain) and that the official link and requirements look genuine.
3. Select it > action **Publish selected**. Tick **Verified** on the organization once you have checked it.
4. A lost management key can be replaced: Organizations > select one > "Issue a new management key". The new key is shown once in the admin message. Send it to them privately.

## 5. Things to know

- **Sleeping:** the free web service sleeps after 15 minutes idle and takes about a minute to wake. Open the site before a demo.
- **Seed data:** every deploy re-runs `load_opportunities`, which overwrites seed listings with the file's contents. Once you edit listings in the admin, remove `python manage.py load_opportunities &&` from `buildCommand` in `render.yaml` and push.
- **Deadlines:** re-check ESOP (30 Nov 2026) and Gates Cambridge (8 Dec 2026) before you demo.
- **Limits:** per-visitor 6 AI checks per hour, 12 per minute and 400 per day for the site. Change them with `AI_VISITOR_HOURLY_CAP`, `AI_MINUTE_CAP`, `AI_DAILY_CAP` in Render.
- **HTTPS:** the site redirects http to https and sends HSTS for one hour. Raise `SECURE_HSTS_SECONDS` once everything is stable.
- **Privacy:** profiles are never stored or logged. Gemini's free tier may use inputs to improve Google products, so tell users in your demo.
- **Cold-start on Neon:** Neon pauses idle databases, so the first request after a quiet period can be slow.

## 6. If something fails

- Build fails on `migrate`: the `DATABASE_URL` is wrong or the Neon project is paused. Open Neon and retry.
- `DisallowedHost` or 400: Render sets the host automatically; if you add a custom domain, add it to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`.
- Matching works but AI buttons do not: see checklist item 4.
