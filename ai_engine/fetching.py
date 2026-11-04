"""Fetching public web pages safely. Pure Python, standard library only.

Rules, because the URLs can come from an AI search and so are untrusted:
- http and https only, on the standard ports;
- the host must resolve only to public addresses (no localhost, private
  ranges, link-local or cloud metadata addresses), and every redirect hop is
  checked again;
- robots.txt is honoured;
- small, slow and capped: a size limit, a timeout, an honest user agent.
"""
import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser

USER_AGENT = "OppScoutBot/1.0 (opportunity research; respects robots.txt)"
MAX_BYTES = 1_500_000
TIMEOUT = 15
MAX_REDIRECTS = 4
TEXT_LIMIT = 30_000


class FetchError(Exception):
    """`reason` is a short, safe message for the admin."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def check_public_url(url, resolver=None):
    """Raise FetchError unless the URL is http(s) to a public address."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise FetchError("Only http and https links are allowed.")
    if not parts.hostname:
        raise FetchError("The link has no host.")
    try:
        port = parts.port
    except ValueError:
        raise FetchError("The link has an invalid port.") from None
    if port not in (None, 80, 443):
        raise FetchError("Only the standard web ports are allowed.")
    if parts.username or parts.password:
        raise FetchError("Links with a username or password are not allowed.")
    resolve = resolver or (lambda host: [i[4][0] for i in socket.getaddrinfo(host, None)])
    try:
        addresses = resolve(parts.hostname)
    except OSError:
        raise FetchError("The site could not be found.") from None
    if not addresses:
        raise FetchError("The site could not be found.")
    for raw in addresses:
        ip = ipaddress.ip_address(raw.split("%")[0])
        if not ip.is_global:
            raise FetchError("That address is not a public website.")
    return url


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Fetcher:
    """Fetches one page at a time. `opener` and `resolver` are injectable for tests."""

    def __init__(self, opener=None, resolver=None, check_robots=True):
        self._opener = opener or urllib.request.build_opener(_NoRedirect).open
        self._resolver = resolver
        self._check_robots = check_robots
        self._robots = {}

    def _get(self, url, limit):
        check_public_url(url, self._resolver)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain;q=0.9,*/*;q=0.5"})
        try:
            response = self._opener(request, timeout=TIMEOUT)
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308):
                return exc.code, exc.headers.get("Location", ""), b"", ""
            raise FetchError(f"The site answered with HTTP {exc.code}.") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise FetchError("The site could not be reached.") from None
        with response:
            ctype = response.headers.get("Content-Type", "")
            body = response.read(limit + 1)
        if len(body) > limit:
            raise FetchError("The page is too large.")
        return 200, "", body, ctype

    def _allowed(self, url):
        if not self._check_robots:
            return True
        parts = urllib.parse.urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        rp = self._robots.get(base)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            try:
                status, _, body, _ = self._get(base + "/robots.txt", 200_000)
                rp.parse(body.decode("utf-8", "replace").splitlines())
            except FetchError:
                rp.parse([])  # no readable robots.txt: nothing is disallowed
            self._robots[base] = rp
        return rp.can_fetch(USER_AGENT, url)

    def fetch(self, url):
        """Return (final_url, text). Raises FetchError."""
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            check_public_url(current, self._resolver)
            if not self._allowed(current):
                raise FetchError("The site's robots.txt does not allow automated reading of this page.")
            status, location, body, ctype = self._get(current, MAX_BYTES)
            if status != 200:
                current = urllib.parse.urljoin(current, location)
                continue
            if ctype and not any(t in ctype.lower() for t in ("html", "text/plain", "xml")):
                raise FetchError("The page is not a web page (for example a PDF or image).")
            return current, html_to_text(body.decode("utf-8", "replace"))
        raise FetchError("Too many redirects.")


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer", "form", "iframe"}
    BLOCK = {"p", "div", "li", "br", "tr", "h1", "h2", "h3", "h4", "h5", "section", "article", "ul", "ol", "table"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag in self.SKIP:
            self._skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def html_to_text(html):
    """Visible text only, with blank runs collapsed and a hard length cap."""
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # malformed markup should not stop a scouting run
        pass
    lines = [" ".join(line.split()) for line in "".join(parser.parts).splitlines()]
    text = "\n".join(line for line in lines if line)
    title = " ".join(parser.title.split())
    if title:
        text = f"Page title: {title}\n{text}"
    return text[:TEXT_LIMIT]
