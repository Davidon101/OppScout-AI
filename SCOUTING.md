# Scouting: finding and watching opportunities

The AI proposes sources. You approve them once. An approved source is re-read on a schedule, and the AI turns what it finds into drafts for you to review. **Nothing is ever published or changed on a live listing automatically.**

## The flow

1. **Find sources.** Django Admin > Sources > "Find sources with AI". Type what to look for (for example "fully funded master's scholarships for Nigerian graduates"). Gemini searches the web. Each page it finds is opened and read, and only pages that describe one real opportunity are saved, as **Proposed** sources. (Command line: `python manage.py discover_sources "topic"`.)
2. **Approve.** Tick the proposed sources you trust, choose "Approve selected". Reject the rest.
3. **Scout.** `python manage.py scout` (the weekly job does this) re-reads approved sources, least recently checked first:
   - a page that is unchanged costs no AI call;
   - a new page becomes a **Draft** listing (hidden from the public) with its requirements;
   - a page that changed for a **live** listing never edits it. The differences (deadline, who can apply, requirements added or removed) are stored as **proposed changes**.
4. **Review.** In Admin > Opportunities, filter by "Scouted" or look for the "Changes to review" column. Open a draft, compare it with the source page, fix anything, then "Publish selected" (this also stamps today as the verification date). For proposed changes use "Apply the proposed changes" or "Dismiss the proposed changes".
5. **Watch the log.** Admin > Scout logs shows what each check did. A source that fails 3 times in a row is paused until you approve it again.

## Safeguards built in

- The model only sees the page text, which is treated as untrusted data. Its answer is validated by code: unknown categories, bad dates, non-web links and over-long text are rejected.
- A deadline is kept only if the exact quoted wording appears in the page text. Otherwise it is dropped and the draft says so.
- A page whose title the model reports but that does not appear in the page text is discarded.
- Fetching: http and https only, standard ports only, public addresses only (no localhost, private ranges or cloud metadata addresses), every redirect re-checked, `robots.txt` honoured, 1.5 MB and 15 second limits, an honest bot name. Pages that need JavaScript to show their content, and PDFs, cannot be read.
- Changes are compared by meaning-similarity, so a reworded requirement is not flagged as a change.

## Run it weekly for free (GitHub Actions)

`.github/workflows/scout.yml` runs the scout every Monday and on demand. It needs two repository secrets (GitHub > repo > Settings > Secrets and variables > Actions):

- `DATABASE_URL`: the same Neon connection string Render uses.
- `GEMINI_API_KEY`: your Gemini key.

Add them there only, never in chat. From the Actions tab you can also "Run workflow" and type a topic to find new sources.

Render's free tier sleeps and has no scheduled jobs, which is why this runs on GitHub instead.

## Limits to know

- The Gemini free tier allows about 500 requests a day for the whole project, shared with the live site. A scout run uses at most `--max` AI calls (default 6; the workflow uses 8). Finding sources uses one search call plus one read per page it checks.
- **Not tested against live services:** the sandbox this was built in cannot reach general websites or Gemini. The fetching and parsing were tested against a local test server, and the AI parts with a stand-in. Gemini's Google Search tool (used only to find sources), its response format, and the real behaviour on real sites are untried. Expect to adjust after the first real runs. Check Google's current free-tier terms for the Search tool.
- The address safety check resolves a site's address before connecting, so a site that deliberately changes its address in between could slip through. The job runs on GitHub's servers with only your database and Gemini secrets, so the risk is small, but do not point it at untrusted sites you do not understand.
- Respect each site's terms. If a provider asks you to stop, reject the source.

## Report an error

Every listing has "Report incorrect or out-of-date information". Reports appear in Admin > Reports. Listings not verified in the last 30 days show a "not checked recently" notice.
