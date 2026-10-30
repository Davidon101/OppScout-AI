"""Score the matcher against hand-labelled profiles.

Usage: python manage.py evaluate_matching [path] [--k 5]

Reads data/eval_profiles.json: a list of {name, profile, relevant: [slugs]}.
Every non-draft, non-archived listing is ranked, whatever its deadline, so the
result measures relevance and does not drift as deadlines pass.
"""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ai_engine.evaluation import precision_at_k, recall_at_k, reciprocal_rank
from ai_engine.matching import rank_opportunities
from ai_engine.profile import Profile
from opportunities.models import Opportunity


class Command(BaseCommand):
    help = "Report precision@k, recall@k and reciprocal rank for labelled profiles."

    def add_arguments(self, parser):
        parser.add_argument(
            "path",
            nargs="?",
            default=str(settings.BASE_DIR / "data" / "eval_profiles.json"),
        )
        parser.add_argument("--k", type=int, default=5)

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.exists():
            raise CommandError(f"File not found: {path}")
        cases = json.loads(path.read_text(encoding="utf-8"))
        k = options["k"]

        opportunities = list(
            Opportunity.objects.filter(
                status__in=[Opportunity.Status.PUBLISHED, Opportunity.Status.EXPIRED]
            ).prefetch_related("requirements")
        )
        if not opportunities:
            raise CommandError("No listings to rank. Run load_opportunities first.")

        totals = {"p": 0.0, "r": 0.0, "rr": 0.0}
        for case in cases:
            result = rank_opportunities(Profile.from_mapping(case["profile"]), opportunities)
            ranked = [m.opportunity.slug for m in result.matches]
            relevant = case["relevant"]
            p = precision_at_k(ranked, relevant, k)
            r = recall_at_k(ranked, relevant, k)
            rr = reciprocal_rank(ranked, relevant)
            totals["p"] += p
            totals["r"] += r
            totals["rr"] += rr

            self.stdout.write(self.style.MIGRATE_HEADING(f"\n{case['name']}"))
            self.stdout.write(
                f"  P@{k}={p:.0%}  R@{k}={r:.0%}  reciprocal rank={rr:.2f}  "
                f"(hidden by region: {result.hidden_region})"
            )
            for match in result.matches[:k]:
                mark = "*" if match.opportunity.slug in relevant else " "
                self.stdout.write(f"  {mark} {match.score:5.1f}  {match.opportunity.slug}")

        n = len(cases)
        self.stdout.write(
            self.style.SUCCESS(
                f"\nMean over {n} profile(s): P@{k}={totals['p'] / n:.0%}  "
                f"R@{k}={totals['r'] / n:.0%}  MRR={totals['rr'] / n:.2f}"
            )
        )
        self.stdout.write(
            "* = labelled relevant. Labels are judgements: review them. "
            "P@k is capped when fewer than k listings are relevant."
        )
