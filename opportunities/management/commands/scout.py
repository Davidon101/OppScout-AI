from django.core.management.base import BaseCommand

from ai_engine.fetching import Fetcher
from ai_engine.providers import ProviderError
from opportunities import scouting
from opportunities.services import get_provider


class Command(BaseCommand):
    help = "Check approved sources and draft listings or propose changes. Never publishes."

    def add_arguments(self, parser):
        parser.add_argument("--max", type=int, default=6, help="Most AI calls this run (default 6).")
        parser.add_argument("--force", action="store_true", help="Re-read pages even if unchanged.")

    def handle(self, *args, max=6, force=False, **opts):
        try:
            provider = get_provider()
        except ProviderError:
            self.stderr.write("GEMINI_API_KEY is not set. Nothing was done.")
            return
        fetcher, used = Fetcher(), 0
        for source in scouting.due_sources(limit=max * 3):
            if used >= max:
                break
            outcome, used_ai = scouting.scout_source(source, provider, fetcher, force=force)
            used += 1 if used_ai else 0
            self.stdout.write(f"{outcome:14} {source.url}")
        self.stdout.write(f"Done. AI calls used: {used}.")
