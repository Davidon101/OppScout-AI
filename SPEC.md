# OppScout AI: specification and build status

Find What Fits. Become What's Next.

Last updated: 2026-10-28. Source: the final technical specification (database schema, structure, seven-day plan) plus the revised scope.

## Agreed decisions

| Area | Decision |
|---|---|
| Frontend | HTML, CSS, HTMX |
| Backend | Python, Django |
| Database | PostgreSQL on Neon in production. SQLite locally when `DATABASE_URL` is unset. |
| Visitor authentication | None. Login and register are labelled demo screens, with a guest path as the real route. |
| Admin | Django Admin, with real admin authentication |
| Profiles | Browser storage. Sent per request, never logged, not stored. |
| Saved opportunities | Browser storage |
| Opportunity data | Curated by hand, loaded through Admin or `load_opportunities` |
| Matching | Explicit Python filters, then embedding similarity, then ranking, then explanations |
| Eligibility | LLM call with validated structured output, assessing only the stored requirements |
| LLM training | None |
| Budget | 0 naira, subject to verified free-tier limits |

## Schema as built, compared with the final spec

The spec's field names were adapted in a few places. These are the differences.

### Opportunity

| Spec field | Built as | Note |
|---|---|---|
| title, slug, provider, category, description, benefits, country | same | |
| location_type | `work_mode` | Same values: remote, physical, hybrid |
| education_levels (plural) | `education_levels` (JSON list) | Empty list means any level is accepted. Values: secondary, undergraduate, graduate (bachelor's completed), postgraduate (master's completed). |
| deadline | `deadline` | Null means no fixed deadline |
| application_url | `official_url` | |
| source_url | `source_url` | |
| status: draft, active, expired, archived | `status`: draft, published, expired, archived | "published" is used instead of "active" |
| last_verified_at | `last_verified` (date) | A date is enough for this project |
| created_at, updated_at | same | |
| not in spec | `eligible_regions` (JSON list) | Who may apply: countries or groups (Africa, Commonwealth, Worldwide). Empty means the provider does not say, not "nobody". |
| not in spec | `excluded_regions` (JSON list) | Who may not apply, e.g. United Kingdom |
| not in spec | `embedding` (JSON, nullable) | Replaces the optional OpportunityEmbedding model |

### OpportunityRequirement

| Spec field | Built as |
|---|---|
| requirement_text | `text` |
| requirement_type: mandatory, preferred | `requirement_type`: mandatory, preferred, **unclear** |
| requirement_category | `category` |
| source_reference | `source_reference` |
| created_at | `created_at` |
| not in spec | `order` |

The extra `unclear` type is deliberate. Some published requirements cannot be classed as mandatory or preferred without guessing, and the assessment must not invent that.

### Not stored in the database

Profiles, saved opportunities and assessment results. This follows the spec.

## Project structure, compared with the spec

Built: `config/`, `opportunities/`, `ai_engine/` (`regions.py`, `profile.py`, `matching.py`, `embeddings.py`, `evaluation.py`), `templates/`, `static/`, `tests/`, `data/`, `render.yaml`.

Not built yet, and expected in the order of the plan:

- `ai_engine/`: none outstanding (eligibility, gap analysis and providers are built)
- `opportunities/`: `services.py`
- Templates: `dashboard/` (not needed; saved page covers it)

Shared partials are in `templates/partials/`; page-specific ones sit next to their pages.

## Plan and status

| Day | Focus | Status |
|---|---|---|
| 1 | Setup, models, admin, deployment files | Done. Runs, migrates, tested. |
| 2 | Directory, search, filters, detail pages, seed loader | Done. Tested. |
| 2+ | 9 verified seed listings | Done. Needs a deadline re-check before launch. |
| 3 | Profile form, matching, ranked results, explanations | Done. 131 Django tests plus a 24-check Chromium run (storage, HTMX, clear, blocked storage, no-JS fallback, mobile). |
| 4 | Eligibility checker with real AI | Built and tested with a fake provider. **Not yet run against live Gemini**: needs your key. |
| 5 | Skill-gap analysis, saved opportunities | Built and tested with a fake provider (204 tests, 14-check Chromium run). Gap analysis not yet run against live Gemini. |
| 7a | Organization portal | Built: 250 tests, 17-check Chromium run. Needs migration 0003. |
| 6 | Tests, error handling, deployment hardening | Done locally: `check --deploy` clean apart from two deliberate HSTS warnings, gunicorn smoke test with DEBUG off (redirect, static, 404 page, CSRF, headers), 206 tests. **Not deployed yet.** See `DEPLOY.md`. |
| 7b | UI redesign | Done (v11). All pages restyled, checked in Chromium at 1280 and 390 px, no horizontal overflow. |
| 7 | Evaluation, README, demo | |

If time runs short, keep in this order: directory, matching, eligibility, deployment, then gap analysis and saves.

## Organization portal (added Day 7, no logins)

Organizations register, post and manage opportunities without accounts.

- **Access:** registration returns a management key, shown once. Only its SHA-256 hash is stored. Entering the key starts an 8-hour session. A key lost is not recoverable; an admin can issue a new one (Organizations > action), which ends old sessions.
- **Moderation:** new and edited listings go to `pending`. An admin publishes them in Django Admin (filter status = Pending review > action "Publish selected"). Editing a published or paused listing sends it back to pending, so a leaked key cannot quietly swap an approved listing.
- **Org actions:** submit, withdraw, take offline (paused), put back online, close applications, mark filled, archive. Anything else is refused (409).
- **Public side:** published listings join the same directory, matching and AI tools. Closed and filled listings stay viewable by link (and in Saved) with a clear notice, but leave the directory and AI tools. Listings show who posted them and whether the organization is verified (admin tick). Changing name, website or email clears verified.
- **Abuse limits:** honeypot field, 3 registrations per visitor per day, 20 key attempts per hour, 30 form submissions per day, URL scheme check, output escaping.
- **AI safety:** requirement text is now third-party content, so both AI prompts treat it as data, and a claim without applicant evidence can never count as met.
- **Category fields:** scholarship, job, internship, fellowship, grant and training each have extra fields (`opportunities/categories.py`), stored in `Opportunity.details`.
- **Limits of the prototype:** no email verification, so the contact email is unconfirmed. Deadline is a date, not a time. Do not claim this is secure for unrestricted public use. Anyone holding a key controls that organization's listings.

## Open items

1. ~~Multiple education levels.~~ Done in v5: a JSON list, filtered in Python.
2. ~~Who can apply.~~ Done in v6: `ai_engine/regions.py` maps countries to groups. Clearly excluded regions hide a listing (and are counted); unknown or unstated never disqualifies. An education mismatch is flagged and scored lower, not hidden.
3. ~~Gemini model and limits.~~ Model `gemini-3.1-flash-lite` (stable per Google's model page); limits 15 RPM, 500 RPD. Only country, education, field, qualification, skills and experience are sent. **Check on first live run:** the REST field names (`responseJsonSchema`, `systemInstruction`) were taken from memory of the generateContent API and could not be tested from the build sandbox.
4. **Embeddings (matching is lexical for now).** Day 3 ranks with keyword and synonym matching. The embedding slot exists (`similarities`, weight .35) and is unused until vectors are precomputed. Plan: precompute offline and store on `Opportunity.embedding`. Embed only the user's profile at request time. Do not run a local model on a 512 MB host.
5. ~~Public AI endpoints.~~ Done: caps per visitor/hour (6), site/minute (12), site/day (400), stored in the `AIUsage` table with hashed visitor ids. Directory and matching keep working when capped. Check Render's X-Forwarded-For behaviour after deploy.
6. ~~HTMX script.~~ Done in v6: self-hosted 2.0.4 (see `static/js/VENDORED.md`).
7. **Development environment.** Built and tested in a cloud sandbox. The README commands also work on your PC.
8. **Review before launch.** Eval labels in `data/eval_profiles.json` are the author's judgements. Re-check seed deadlines (ESOP 2026-11-30, Gates 2026-12-08).

## Hosting facts checked on 2026-10-28

- Render free web service: 512 MB RAM, sleeps after 15 minutes idle, about a minute to wake. Do not use Render's free Postgres, which expires after 30 days.
- Neon free plan: permanent, 0.5 GB storage per project. Compute-hour allowance was reported as both 50 and 100 on Neon's own pages, so check your console.
- Gemini API: Nigeria is on the supported-regions list. Limits are shown per project in AI Studio.
