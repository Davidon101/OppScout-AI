"""Glue between the views and the AI engine."""
from django.conf import settings

from ai_engine.providers import GeminiProvider


def get_provider():
    """The configured provider. Raises ProviderUnavailable without a key."""
    return GeminiProvider(settings.GEMINI_API_KEY, settings.GEMINI_MODEL)
