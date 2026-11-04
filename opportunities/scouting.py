"""The scouting job: read approved source pages, draft listings, spot changes.

Nothing here publishes anything. New finds become drafts, and differences on
live listings are stored beside them as proposed changes for an admin to apply
or dismiss. The AI may propose sources, but only an approved source is read
again automatically.
"""
import logging
from datetime import date, datetime, timezone as dt_timezone

from django.db import transaction
from django.utils import timezone

from ai_engine import scout
from ai_engine.fetching import FetchError
from ai_engine.providers import ProviderError

from .models import Opportunity, OpportunityRequirement, ScoutLog, Source

log = logging.getLogger(__name__)
MAX_FAILS = 3


def _log(source, outcome, detail=""):
    ScoutLog.objects.create(source=source, outcome=outcome, detail=detail[:2000])


def read_page(source_url, provider, fetcher):
    """Fetch and extract. Returns (final_url, page_text, clean, notes). Raises FetchError or ProviderError."""
    final_url, text = fetcher.fetch(source_url)
    if len(text) < 200:
        raise FetchError("The page has almost no readable text (it may need JavaScript).")
    raw = provider.generate_json(scout.EXTRACT_SYSTEM, scout.build_extract_prompt(final_url, text), scout.EXTRACT_SCHEMA)
    clean, notes = scout.validate_extraction(raw, final_url, text, today=timezone.localdate())
    return final_url, text, clean, notes


def snapshot(opp):
    return {
        "deadline": opp.deadline.isoformat() if opp.deadline else None,
        "eligible_regions": list(opp.eligible_regions or []),
        "education_levels": list(opp.education_levels or []),
        "requirements": [{"text": r.text, "type": r.requirement_type} for r in opp.requirements.all()],
    }


def find_existing(source, url):
    return (
        Opportunity.objects.filter(scout_source=source).first()
        or Opportunity.objects.filter(official_url=url).first()
        or Opportunity.objects.filter(source_url=url).first()
    )


def _write_fields(opp, clean, source):
    opp.title, opp.provider, opp.category = clean["title"], clean["provider"], clean["category"]
    opp.description, opp.benefits = clean["description"], clean["benefits"]
    opp.country, opp.work_mode = clean["country"], clean["work_mode"]
    opp.education_levels = clean["education_levels"]
    opp.eligible_regions, opp.excluded_regions = clean["eligible_regions"], clean["excluded_regions"]
    opp.deadline = date.fromisoformat(clean["deadline"]) if clean["deadline"] else None
    opp.official_url = clean["official_url"]
    opp.source_url = source.url
    opp.how_to_apply = clean["how_to_apply"]


def _write_requirements(opp, clean, source):
    opp.requirements.all().delete()
    OpportunityRequirement.objects.bulk_create([
        OpportunityRequirement(opportunity=opp, text=r["text"], requirement_type=r["type"], order=i, source_reference=source.url)
        for i, r in enumerate(clean["requirements"])
    ])


@transaction.atomic
def create_draft(source, clean):
    opp = Opportunity(status=Opportunity.Status.DRAFT, scouted=True, scout_source=source)
    _write_fields(opp, clean, source)
    opp.save()
    _write_requirements(opp, clean, source)
    return opp


def scout_source(source, provider, fetcher, force=False):
    """Check one source. Returns (outcome, used_ai). Outcomes: unchanged, drafted,
    updated_draft, changes_found, no_changes, skipped, failed."""
    now = timezone.now()
    try:
        final_url, text = fetcher.fetch(source.url)
    except FetchError as exc:
        return _fail(source, exc.reason, now), False
    digest = scout.text_hash(text)
    if digest == source.last_hash and not force:
        source.last_checked, source.last_error, source.fail_count = now, "", 0
        source.save(update_fields=["last_checked", "last_error", "fail_count"])
        _log(source, "unchanged")
        return "unchanged", False
    if len(text) < 200:
        return _fail(source, "The page has almost no readable text (it may need JavaScript).", now), False
    try:
        raw = provider.generate_json(scout.EXTRACT_SYSTEM, scout.build_extract_prompt(final_url, text), scout.EXTRACT_SCHEMA)
    except ProviderError as exc:
        # Not the source's fault: do not count it as a failure of the page.
        _log(source, "ai_error", getattr(exc, "public_message", str(exc)))
        return "failed", True
    clean, notes = scout.validate_extraction(raw, final_url, text, today=timezone.localdate())
    if clean is None:
        return _fail(source, " ".join(notes), now, used_ai=True), True

    existing = find_existing(source, final_url)
    if existing is None:
        opp = create_draft(source, clean)
        outcome, detail = "drafted", f"Draft created: {opp.title}. " + " ".join(notes)
    elif existing.scouted and existing.status == Opportunity.Status.DRAFT:
        with transaction.atomic():
            _write_fields(existing, clean, source)
            existing.scout_source = source
            existing.save()
            _write_requirements(existing, clean, source)
        outcome, detail = "updated_draft", f"Draft refreshed: {existing.title}. " + " ".join(notes)
    else:
        diff = scout.diff_extraction(snapshot(existing), clean)
        if diff:
            existing.pending_changes = diff
            existing.changes_noted_at = now
            existing.scout_source = existing.scout_source or source
            existing.save(update_fields=["pending_changes", "changes_noted_at", "scout_source", "updated_at"])
            outcome, detail = "changes_found", f"Changes proposed for {existing.title}: {', '.join(diff)}."
        else:
            outcome, detail = "no_changes", f"Page changed but nothing important differs for {existing.title}."
    source.last_checked, source.last_hash, source.last_error, source.fail_count = now, digest, "", 0
    source.cache = {"title": clean["title"]}
    source.save(update_fields=["last_checked", "last_hash", "last_error", "fail_count", "cache"])
    _log(source, outcome, detail)
    return outcome, True


def _fail(source, reason, now, used_ai=False):
    source.last_checked, source.last_error = now, reason[:300]
    source.fail_count = min(source.fail_count + 1, 250)
    source.save(update_fields=["last_checked", "last_error", "fail_count"])
    _log(source, "failed", reason)
    return "failed"


def due_sources(limit):
    """Approved sources, least recently checked first, skipping ones that keep failing."""
    return list(
        Source.objects.filter(status=Source.Status.APPROVED, fail_count__lt=MAX_FAILS)
        .order_by("last_checked")[:limit]
    )


def discover(topic, provider, fetcher, max_new=5):
    """Ask Gemini (with search) for official pages, check each one, and store the
    ones that really are a single opportunity as PROPOSED sources. Returns
    (added, checked, messages)."""
    text, uris = provider.search_text(scout.DISCOVER_SYSTEM, scout.discover_prompt(topic))
    added, checked, messages = [], 0, []
    for url in scout.candidate_urls(text, uris, limit=max_new * 2):
        if len(added) >= max_new:
            break
        if Source.objects.filter(url=url).exists():
            continue
        checked += 1
        try:
            final_url, _text, clean, notes = read_page(url, provider, fetcher)
        except FetchError as exc:
            messages.append(f"Skipped a link: {exc.reason}")
            continue
        except ProviderError as exc:
            messages.append(getattr(exc, "public_message", "The AI service had a problem."))
            break
        if clean is None:
            messages.append("Skipped a page: " + " ".join(notes))
            continue
        if Source.objects.filter(url=final_url).exists():
            continue
        added.append(Source.objects.create(
            url=final_url, name=clean["title"][:200], found_by="ai",
            note=f"{clean['provider']}. {clean['category'].title()}. Found for: {topic[:150]}"))
    _log(None, "discover", f"{topic[:150]}: {len(added)} proposed, {checked} checked. " + " | ".join(messages[:5]))
    return added, checked, messages


# ---- reviewing proposed changes ----

@transaction.atomic
def apply_changes(opp):
    changes = opp.pending_changes or {}
    if "deadline" in changes:
        value = changes["deadline"]["new"]
        opp.deadline = date.fromisoformat(value) if value else None
    for key in ("eligible_regions", "education_levels"):
        if key in changes:
            setattr(opp, key, changes[key]["new"])
    if changes.get("requirements_removed"):
        from ai_engine.scout import _similar
        for req in opp.requirements.all():
            if any(_similar(req.text, t) for t in changes["requirements_removed"]):
                req.delete()
    start = opp.requirements.count()
    for i, text in enumerate(changes.get("requirements_added", [])):
        OpportunityRequirement.objects.create(
            opportunity=opp, text=text[:500], requirement_type="unclear", order=start + i,
            source_reference=opp.source_url or opp.official_url)
    opp.pending_changes, opp.changes_noted_at = {}, None
    opp.last_verified = timezone.localdate()
    opp.save()


def dismiss_changes(opp):
    opp.pending_changes, opp.changes_noted_at = {}, None
    opp.save(update_fields=["pending_changes", "changes_noted_at", "updated_at"])
