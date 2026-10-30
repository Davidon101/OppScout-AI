"""Lightweight stand-ins for Opportunity, so ai_engine tests need no database."""
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def opps_from_seed():
    """Every seed listing as a fake Opportunity, regardless of status or deadline."""
    items = json.loads((DATA_DIR / "seed_opportunities.json").read_text(encoding="utf-8"))
    out = []
    for pk, item in enumerate(items, start=1):
        out.append(
            make_opp(
                pk=pk,
                slug=item["slug"],
                title=item["title"],
                provider=item["provider"],
                category=item["category"],
                description=item["description"],
                benefits=item["benefits"],
                country=item["country"],
                work_mode=item["work_mode"],
                education_levels=item["education_levels"],
                eligible_regions=item["eligible_regions"],
                excluded_regions=item["excluded_regions"],
                deadline=date.fromisoformat(item["deadline"]) if item["deadline"] else None,
                last_verified=date.fromisoformat(item["last_verified"]),
                requirements=[
                    make_requirement(r["text"], r["type"]) for r in item["requirements"]
                ],
            )
        )
    return out


def eval_cases():
    return json.loads((DATA_DIR / "eval_profiles.json").read_text(encoding="utf-8"))


class _Requirements:
    def __init__(self, items):
        self._items = list(items)

    def all(self):
        return self._items


def make_requirement(text, kind="mandatory"):
    return SimpleNamespace(text=text, requirement_type=kind)


def make_opp(
    pk=1,
    title="Test listing",
    provider="Acme",
    category="scholarship",
    description="",
    benefits="",
    country="",
    work_mode="physical",
    education_levels=(),
    eligible_regions=(),
    excluded_regions=(),
    deadline=None,
    last_verified=date(2026, 10, 1),
    requirements=(),
    slug=None,
):
    return SimpleNamespace(
        pk=pk,
        slug=slug or f"opp-{pk}",
        title=title,
        provider=provider,
        category=category,
        description=description,
        benefits=benefits,
        country=country,
        work_mode=work_mode,
        education_levels=list(education_levels),
        eligible_regions=list(eligible_regions),
        excluded_regions=list(excluded_regions),
        deadline=deadline,
        last_verified=last_verified,
        requirements=_Requirements(requirements),
    )
