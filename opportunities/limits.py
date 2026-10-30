"""Caps on AI calls, kept in the database so every worker shares them.

Three limits, checked before any call to the provider:
- per visitor per hour (a hashed IP, never stored raw),
- per minute across the whole site (stays under the provider's RPM),
- per day across the whole site (stays under the provider's RPD).
A refused request is not counted. Directory and matching never touch this.
"""
import hashlib
import hmac
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .models import AIUsage


class LimitExceeded(Exception):
    def __init__(self, scope):
        super().__init__(scope)
        self.scope = scope

    @property
    def public_message(self):
        return {
            "visitor": "You have used your AI checks for this hour. Please try again later.",
            "minute": "Many people are using AI checks right now. Please try again in a minute.",
            "day": "AI checks have reached today's limit. Browsing and matching still work. Try again tomorrow.",
        }[self.scope]


def client_ip(request):
    # Behind Render's proxy the last X-Forwarded-For entry is the one the
    # proxy added; earlier entries can be forged by the client.
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.META.get("REMOTE_ADDR", "")


def _visitor_token(ip):
    digest = hmac.new(settings.SECRET_KEY.encode(), ip.encode(), hashlib.sha256)
    return digest.hexdigest()[:20]


def _bump(key):
    """Add one and return the new count. Safe if two requests race."""
    if AIUsage.objects.filter(key=key).update(count=F("count") + 1):
        return AIUsage.objects.get(key=key).count
    try:
        with transaction.atomic():
            AIUsage.objects.create(key=key, count=1)
        return 1
    except IntegrityError:
        AIUsage.objects.filter(key=key).update(count=F("count") + 1)
        return AIUsage.objects.get(key=key).count


def reserve(request, now=None):
    """Count one AI call or raise LimitExceeded. Nothing is counted on refusal."""
    now = now or timezone.localtime()
    ip = client_ip(request)
    keys = [
        ("visitor", f"v:{_visitor_token(ip)}:{now:%Y%m%d%H}", settings.AI_VISITOR_HOURLY_CAP),
        ("minute", f"m:{now:%Y%m%d%H%M}", settings.AI_MINUTE_CAP),
        ("day", f"d:{now:%Y%m%d}", settings.AI_DAILY_CAP),
    ]
    exceeded = None
    with transaction.atomic():
        for scope, key, cap in keys:
            if _bump(key) > cap:
                exceeded = scope
                transaction.set_rollback(True)
                break
        else:
            AIUsage.objects.filter(created__lt=now - timedelta(days=2)).delete()
    if exceeded:
        raise LimitExceeded(exceeded)


def within_limit(request, name, cap, per="hour", now=None):
    """Count one use of a named action for this visitor. Return False (and do not
    count it) when the visitor is over `cap` for the current hour or day."""
    now = now or timezone.localtime()
    stamp = f"{now:%Y%m%d%H}" if per == "hour" else f"{now:%Y%m%d}"
    key = f"{name}:{_visitor_token(client_ip(request))}:{stamp}"
    allowed = True
    with transaction.atomic():
        if _bump(key) > cap:
            allowed = False
            transaction.set_rollback(True)
    return allowed
