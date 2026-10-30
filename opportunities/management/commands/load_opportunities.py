"""Load or update curated opportunities from a JSON file.

Usage: python manage.py load_opportunities [path]

Each item is matched on its "slug", so re-running updates instead of
duplicating. Requirements listed in an item replace the existing ones.
"""
import json
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from opportunities.models import Opportunity, OpportunityRequirement

FIELDS = [
    "title",
    "provider",
    "category",
    "description",
    "benefits",
    "country",
    "work_mode",
    "education_levels",
    "eligible_regions",
    "excluded_regions",
    "deadline",
    "official_url",
    "source_url",
    "status",
    "last_verified",
]
DATE_FIELDS = ("deadline", "last_verified")


class Command(BaseCommand):
    help = "Load or update curated opportunities from a JSON file."

    def add_arguments(self, parser):
        parser.add_argument(
            "path",
            nargs="?",
            default=str(settings.BASE_DIR / "data" / "seed_opportunities.json"),
        )

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.exists():
            raise CommandError(f"File not found: {path}")
        try:
            items = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON: {exc}") from exc
        if not isinstance(items, list):
            raise CommandError("The top level of the file must be a list.")

        created = updated = 0
        for index, item in enumerate(items, start=1):
            label = item.get("title", "?") if isinstance(item, dict) else "?"
            try:
                with transaction.atomic():
                    if self._load(item):
                        created += 1
                    else:
                        updated += 1
            except (ValidationError, KeyError, ValueError, TypeError) as exc:
                raise CommandError(f"Item {index} ({label}): {exc!r}") from exc

        self.stdout.write(self.style.SUCCESS(f"Done: {created} created, {updated} updated."))

    def _load(self, item):
        slug = item["slug"]
        obj = Opportunity.objects.filter(slug=slug).first()
        created = obj is None
        if created:
            obj = Opportunity(slug=slug)

        for field in FIELDS:
            if field not in item:
                continue
            value = item[field]
            if field in DATE_FIELDS:
                value = date.fromisoformat(value) if value else None
            setattr(obj, field, value)

        # Text may have changed, so any stored embedding is stale.
        obj.embedding = None
        obj.full_clean()
        obj.save()

        if "requirements" in item:
            obj.requirements.all().delete()
            for order, req in enumerate(item["requirements"]):
                requirement = OpportunityRequirement(
                    opportunity=obj,
                    text=req["text"],
                    requirement_type=req.get("type", "unclear"),
                    category=req.get("category", ""),
                    source_reference=req.get("source_reference", ""),
                    order=order,
                )
                requirement.full_clean()
                requirement.save()
        return created
