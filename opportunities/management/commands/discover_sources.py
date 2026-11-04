from django.core.management.base import BaseCommand

from ai_engine.fetching import Fetcher
from ai_engine.providers import ProviderError
from opportunities import scouting
from opportunities.services import get_provider


class Command(BaseCommand):
    help = "Ask the AI (with web search) for official opportunity pages and propose them as sources."

    def add_arguments(self, parser):
        parser.add_argument("topic")
        parser.add_argument("--max", type=int, default=5)

    def handle(self, *args, topic="", max=5, **opts):
        try:
            provider = get_provider()
        except ProviderError:
            self.stderr.write("GEMINI_API_KEY is not set. Nothing was done.")
            return
        try:
            added, checked, messages = scouting.discover(topic, provider, Fetcher(), max_new=max)
        except ProviderError as exc:
            self.stderr.write(getattr(exc, "public_message", "The AI service had a problem."))
            return
        for s in added:
            self.stdout.write(f"Proposed: {s.name} {s.url}")
        for m in messages:
            self.stdout.write(m)
        self.stdout.write(f"Checked {checked} pages, proposed {len(added)}. Approve them in Django Admin > Sources.")
