"""The visitor's profile. Pure Python, no Django.

A profile lives in the visitor's browser and arrives with each request. It is
never stored. Every field is optional, and a missing field must never count as
evidence that the visitor is ineligible.
"""
import re
from dataclasses import dataclass

# Keep in sync with Opportunity.EducationLevel (a test checks this).
EDUCATION_ORDER = ("secondary", "undergraduate", "graduate", "postgraduate")
EDUCATION_LABELS = {
    "secondary": "Secondary school",
    "undergraduate": "Undergraduate (in progress)",
    "graduate": "Bachelor's completed",
    "postgraduate": "Master's completed",
}

CATEGORY_VALUES = ("scholarship", "internship", "fellowship", "grant", "job", "training")

LOCATION_CHOICES = (
    ("nigeria", "Nigeria"),
    ("africa", "Africa"),
    ("remote_global", "Remote or global"),
)
LOCATION_VALUES = tuple(v for v, _ in LOCATION_CHOICES)

_STOPWORDS = frozenset(
    """the and for with become want wants like get getting have has had was were
    are not you your our their them they this that from into about who what
    work working job role career start started starts begin build make create
    find company""".split()
)


def split_list(value, limit=20, item_max=60):
    """Turn 'a, b; c' (or a list) into a de-duplicated tuple of short strings."""
    if value is None:
        return ()
    if isinstance(value, str):
        parts = re.split(r"[,;\n]+", value)
    else:
        parts = [str(p) for p in value]
    seen, out = set(), []
    for part in parts:
        item = " ".join(part.split())[:item_max].strip()
        key = item.casefold()
        if item and key not in seen:
            seen.add(key)
            out.append(item)
        if len(out) >= limit:
            break
    return tuple(out)


def keywords(text, limit=8):
    """Content words from free text, for matching against listings."""
    out = []
    for word in re.findall(r"[a-z0-9+#]+", (text or "").lower()):
        if len(word) >= 3 and word not in _STOPWORDS and word not in out:
            out.append(word)
        if len(out) >= limit:
            break
    return tuple(out)


def _text(value, limit):
    return " ".join(str(value or "").split())[:limit]


@dataclass(frozen=True)
class Profile:
    country: str = ""
    education_level: str = ""
    field_of_study: str = ""
    current_qualification: str = ""
    skills: tuple = ()
    experience: str = ""
    interests: tuple = ()
    categories: tuple = ()
    location_preferences: tuple = ()
    career_goals: str = ""

    @classmethod
    def from_mapping(cls, data):
        data = data or {}
        level = _text(data.get("education_level"), 30)
        return cls(
            country=_text(data.get("country"), 100),
            education_level=level if level in EDUCATION_LABELS else "",
            field_of_study=_text(data.get("field_of_study"), 100),
            current_qualification=_text(data.get("current_qualification"), 100),
            skills=split_list(data.get("skills")),
            experience=_text(data.get("experience"), 600),
            interests=split_list(data.get("interests")),
            categories=tuple(
                c for c in split_list(data.get("categories")) if c in CATEGORY_VALUES
            ),
            location_preferences=tuple(
                v for v in split_list(data.get("location_preferences"))
                if v in LOCATION_VALUES
            ),
            career_goals=_text(data.get("career_goals"), 300),
        )

    def is_empty(self):
        return not any(
            (
                self.country, self.education_level, self.field_of_study,
                self.current_qualification, self.skills, self.experience,
                self.interests, self.categories, self.location_preferences,
                self.career_goals,
            )
        )

    @property
    def interest_terms(self):
        """Terms the visitor stated: interests and field of study."""
        terms = list(self.interests)
        if self.field_of_study:
            terms.append(self.field_of_study)
        seen, out = set(), []
        for term in terms:
            key = term.casefold()
            if key not in seen:
                seen.add(key)
                out.append(term)
        return tuple(out)

    @property
    def goal_terms(self):
        """Content words from the career goal. Weaker evidence than stated terms."""
        stated = {t.casefold() for t in self.interest_terms}
        return tuple(w for w in keywords(self.career_goals, 6) if w not in stated)

    def as_text(self):
        """A short text version of the profile, for embedding later."""
        parts = []
        if self.education_level:
            parts.append(EDUCATION_LABELS[self.education_level])
        if self.field_of_study:
            parts.append(self.field_of_study)
        if self.skills:
            parts.append("Skills: " + ", ".join(self.skills))
        if self.interests:
            parts.append("Interests: " + ", ".join(self.interests))
        if self.career_goals:
            parts.append("Goal: " + self.career_goals)
        return ". ".join(parts)
