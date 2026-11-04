"""AI providers. Pure Python, no Django. Standard library only.

A provider turns (system prompt, user text, JSON schema) into a decoded JSON
value, or raises ProviderError. Callers must treat the value as untrusted.
"""
import json
import urllib.error
import urllib.request

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class ProviderError(Exception):
    """Base class. `public_message` is safe to show to a visitor."""

    public_message = "The AI service had a problem. Please try again later."


class ProviderUnavailable(ProviderError):
    public_message = "AI checks are not available right now. Browsing and matching still work."


class ProviderBusy(ProviderError):
    public_message = "The AI service is busy. Please try again in a minute."


class ProviderBadResponse(ProviderError):
    public_message = "The AI service returned something we could not use. Please try again."


class GeminiProvider:
    def __init__(self, api_key, model, timeout=25, opener=None):
        if not api_key or not model:
            raise ProviderUnavailable("Gemini is not configured.")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._open = opener or urllib.request.urlopen

    def generate_json(self, system, user, schema):
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": schema,
                "temperature": 0.1,
                "maxOutputTokens": 4096,
            },
        }
        request = urllib.request.Request(
            GEMINI_URL.format(model=self.model),
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                # The key travels in a header, never in the URL, so it cannot
                # end up in access logs.
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )
        try:
            with self._open(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise ProviderBusy(f"Gemini returned {exc.code}") from None
            raise ProviderError(f"Gemini returned HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ProviderError("Could not reach Gemini.") from None
        except ValueError:
            raise ProviderBadResponse("Gemini sent invalid JSON.") from None

        try:
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except (KeyError, IndexError, TypeError, ValueError):
            raise ProviderBadResponse("Unexpected Gemini response shape.") from None


    def search_text(self, system, user):
        """Ask with Google Search switched on. Returns (answer_text, source_uris).

        Not combined with a JSON schema: the answer is plain text and the
        grounding metadata carries the pages the search used. Callers must
        re-check every address before trusting it.
        """
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048},
        }
        request = urllib.request.Request(
            GEMINI_URL.format(model=self.model),
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
            method="POST",
        )
        try:
            with self._open(request, timeout=max(self.timeout, 40)) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise ProviderBusy(f"Gemini returned {exc.code}") from None
            raise ProviderError(f"Gemini returned HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ProviderError("Could not reach Gemini.") from None
        except ValueError:
            raise ProviderBadResponse("Gemini sent invalid JSON.") from None
        try:
            candidate = payload["candidates"][0]
            text = "".join(p.get("text", "") for p in candidate["content"]["parts"])
        except (KeyError, IndexError, TypeError):
            raise ProviderBadResponse("Unexpected Gemini response shape.") from None
        chunks = (candidate.get("groundingMetadata") or {}).get("groundingChunks") or []
        uris = [c["web"]["uri"] for c in chunks if isinstance(c, dict) and isinstance(c.get("web"), dict) and c["web"].get("uri")]
        return text, uris


class FakeProvider:
    """For tests and offline demos. Returns a canned value or raises an error."""

    def __init__(self, result=None, error=None, results=None, search=("", [])):
        self.result = result
        self.error = error
        self.results = list(results) if results is not None else None
        self.search = search
        self.calls = []

    def generate_json(self, system, user, schema):
        self.calls.append((system, user, schema))
        if self.error:
            raise self.error
        if self.results is not None:
            item = self.results.pop(0) if self.results else None
            if isinstance(item, Exception):
                raise item
            return item
        return self.result

    def search_text(self, system, user):
        self.calls.append((system, user, "search"))
        if self.error:
            raise self.error
        return self.search
