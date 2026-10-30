"""Opportunity matching. Pure Python, no Django, no network.

Stage 1  Explicit filters: chosen categories, and regions that clearly exclude
         the visitor. Anything unknown is kept, never dropped.
Stage 2  Text similarity: embedding similarity when supplied, otherwise a
         lexical overlap between profile terms and the listing text.
Stage 3  Ranking: a weighted average over the signals that are actually
         available. A missing signal is left out, not scored as zero.
Stage 4  Explanations: why it matched, and what to check before applying.

A match score says how relevant a listing looks. It is not an eligibility
decision, and the interface must say so.
"""
import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache

from . import regions
from .profile import EDUCATION_LABELS

WEIGHTS = {
    "text": 0.35,
    "skills": 0.25,
    "interests": 0.15,
    "education": 0.10,
    "location": 0.10,
    "region": 0.05,
}

# Strength of a term match.
EXACT, SYNONYM, WORDS = 1.0, 0.7, 0.5

# Weight of keywords taken from the free-text career goal.
GOAL_WEIGHT = 0.5

_LANGUAGE_FAMILY = ("programming language", "programming", "coding")

SYNONYMS = {
    "ai": ("artificial intelligence", "machine learning"),
    "artificial intelligence": ("ai", "machine learning"),
    "machine learning": ("ml", "artificial intelligence", "ai"),
    "ml": ("machine learning",),
    "ai engineering": ("artificial intelligence", "machine learning", "ai"),
    "cs": ("computer science",),
    "computer science": ("computing", "software engineering", "programming"),
    "software development": ("software engineering", "software engineer", "programming"),
    "software engineering": ("software development", "programming"),
    "web development": ("front-end", "frontend", "web"),
    "data science": ("data analysis", "machine learning", "analytics"),
    "data analysis": ("data science", "analytics"),
    "entrepreneurship": ("entrepreneur", "startup", "founder"),
    "startup": ("entrepreneur", "entrepreneurship", "founder"),
}
for _lang in (
    "python", "java", "javascript", "typescript", "html", "css", "php", "sql",
    "c++", "c#", "kotlin", "dart", "ruby", "swift",
):
    SYNONYMS.setdefault(_lang, _LANGUAGE_FAMILY)


def _saturate(total):
    """Diminishing returns: one strong hit is 0.5, two are 0.75, and so on.
    Two weak hits therefore never look as good as several strong ones."""
    return 1.0 - 0.5 ** max(0.0, total)


@lru_cache(maxsize=2048)
def _pattern(phrase):
    return re.compile(r"(?<![a-z0-9])" + re.escape(phrase) + r"s?(?![a-z0-9])")


def _has(haystack, phrase):
    return bool(phrase) and _pattern(phrase).search(haystack) is not None


def term_score(term, haystack):
    """0 to 1: exact phrase, then a synonym, then all its words somewhere."""
    t = " ".join((term or "").lower().split())
    if len(t) < 2:
        return 0.0
    if _has(haystack, t):
        return EXACT
    for synonym in SYNONYMS.get(t, ()):
        if _has(haystack, synonym):
            return SYNONYM
    words = [w for w in re.findall(r"[a-z0-9+#]+", t) if len(w) > 1]
    if len(words) >= 2 and all(_has(haystack, w) for w in words):
        return WORDS
    return 0.0


def _haystack(opp, requirements):
    parts = [
        opp.title, opp.provider, opp.category,
        getattr(opp, "description", ""), getattr(opp, "benefits", ""),
    ]
    details = getattr(opp, "details", None)
    if isinstance(details, dict):
        parts.extend(str(v) for v in details.values())
    parts.extend(r.text for r in requirements)
    return " ".join(" ".join(str(p) for p in parts if p).lower().split())


def _education_status(opp, profile):
    levels = tuple(getattr(opp, "education_levels", ()) or ())
    if not profile.education_level or not levels:
        return None
    return profile.education_level in levels


def _levels_display(levels):
    return ", ".join(EDUCATION_LABELS[v] for v in levels if v in EDUCATION_LABELS)


def _location_match(opp, preferences):
    """True or False when the listing states a location, None when it cannot tell."""
    country = regions.canonical(opp.country)
    remote = opp.work_mode == "remote"
    if not country and not remote:
        return None
    for pref in preferences:
        if pref == "remote_global" and remote:
            return True
        if pref == "nigeria" and country == "nigeria":
            return True
        if pref == "africa" and country and regions.in_group(opp.country, "africa"):
            return True
    return False


def _region_reason(opp, profile):
    eligible = [regions.canonical(r) for r in (opp.eligible_regions or ())]
    if regions.WORLDWIDE in eligible:
        return "Open to applicants worldwide."
    return (
        f"{profile.country} falls within its stated eligible regions "
        f"({', '.join(opp.eligible_regions)})."
    )


@dataclass
class Match:
    opportunity: object
    score: float
    reasons: list = field(default_factory=list)
    attention: list = field(default_factory=list)
    region_status: str = regions.UNKNOWN
    mandatory_count: int = 0
    unclear_count: int = 0


@dataclass
class MatchResult:
    matches: list
    hidden_region: int = 0
    hidden_category: int = 0
    considered: int = 0


def _score(profile, opp, status, similarities, today):
    requirements = list(opp.requirements.all())
    hay = _haystack(opp, requirements)
    components = []
    reasons, attention = [], []

    similarity = similarities.get(opp.pk)
    if similarity is not None:
        similarity = max(0.0, min(1.0, float(similarity)))
        components.append((WEIGHTS["text"], similarity))
        reasons.append(f"Its text is similar to your profile (similarity {similarity:.2f}).")

    if profile.skills:
        hits = [(s, term_score(s, hay)) for s in profile.skills]
        components.append((WEIGHTS["skills"], _saturate(sum(v for _, v in hits))))
        matched = [s for s, v in hits if v >= WORDS]
        if matched:
            reasons.append("Mentions your skills: " + ", ".join(matched[:5]) + ".")

    # Interests and field of study are stated terms. Words pulled from the
    # career goal are weaker evidence, so they count for half.
    weighted = [(t, 1.0) for t in profile.interest_terms]
    weighted += [(t, GOAL_WEIGHT) for t in profile.goal_terms]
    if weighted:
        hits = [(t, w, term_score(t, hay)) for t, w in weighted]
        components.append((WEIGHTS["interests"], _saturate(sum(w * v for _, w, v in hits))))
        matched = [t for t, _, v in hits if v >= WORDS]
        if matched:
            reasons.append("Matches your interests: " + ", ".join(matched[:5]) + ".")

    education = _education_status(opp, profile)
    if education is not None:
        components.append((WEIGHTS["education"], 1.0 if education else 0.0))
        label = EDUCATION_LABELS[profile.education_level]
        if education:
            reasons.append(f"Accepts your education level ({label}).")
        else:
            attention.append(
                f"It asks for: {_levels_display(opp.education_levels)}. "
                f"Your profile says: {label}."
            )

    if status == regions.ELIGIBLE:
        components.append((WEIGHTS["region"], 1.0))
        reasons.append(_region_reason(opp, profile))
    elif status == regions.UNKNOWN and profile.country:
        if not (opp.eligible_regions or opp.excluded_regions):
            attention.append("It does not state who can apply. Check the official page.")
        else:
            attention.append(
                "Your country could not be checked against its eligible regions. "
                "Check the official page."
            )

    if profile.location_preferences:
        located = _location_match(opp, profile.location_preferences)
        if located is not None:
            components.append((WEIGHTS["location"], 1.0 if located else 0.2))
            if located:
                reasons.append("Fits your location preference.")

    total_weight = sum(w for w, _ in components)
    score = 0.0
    if total_weight:
        score = round(100 * sum(w * v for w, v in components) / total_weight, 1)

    if opp.deadline is not None:
        days = (opp.deadline - today).days
        if days < 0:
            attention.append("The deadline has passed.")
        elif days == 0:
            attention.append("Closes today.")
        elif days <= 14:
            attention.append(f"Closes in {days} day{'s' if days != 1 else ''}.")

    verified = getattr(opp, "last_verified", None)
    if verified is None:
        attention.append("Details have not been verified yet. Check the official page.")
    elif (today - verified).days > 90:
        attention.append(
            f"Last verified on {verified.strftime('%d %b %Y')}. Re-check the official page."
        )

    if not reasons:
        reasons.append("Included because nothing in its published details rules you out.")

    return Match(
        opportunity=opp,
        score=score,
        reasons=reasons,
        attention=attention,
        region_status=status,
        mandatory_count=sum(1 for r in requirements if r.requirement_type == "mandatory"),
        unclear_count=sum(1 for r in requirements if r.requirement_type == "unclear"),
    )


def rank_opportunities(profile, opportunities, similarities=None, today=None):
    """Filter and rank opportunities for a profile. Callers decide which listings
    are eligible to appear (published, not past deadline)."""
    today = today or date.today()
    similarities = similarities or {}
    matches = []
    hidden_region = hidden_category = considered = 0

    for opp in opportunities:
        considered += 1
        if profile.categories and opp.category not in profile.categories:
            hidden_category += 1
            continue
        status = regions.region_status(opp.eligible_regions, opp.excluded_regions, profile.country)
        if status == regions.INELIGIBLE:
            hidden_region += 1
            continue
        matches.append(_score(profile, opp, status, similarities, today))

    matches.sort(
        key=lambda m: (
            -m.score,
            m.opportunity.deadline is None,
            m.opportunity.deadline or date.max,
            m.opportunity.title.lower(),
        )
    )
    return MatchResult(
        matches=matches,
        hidden_region=hidden_region,
        hidden_category=hidden_category,
        considered=considered,
    )
