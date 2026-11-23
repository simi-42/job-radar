"""Search-engine angle: Brave or Serper (API keys), DuckDuckGo HTML as a small fallback."""
import html
import re
import time
from urllib.parse import quote_plus, unquote, urlparse, parse_qs

from .. import http
from ..classify import title_family
from ..detect import parse_ats_url
from ..model import make_job


def provider():
    if http.secret("BRAVE_API_KEY"):
        return "brave"
    if http.secret("SERPER_API_KEY"):
        return "serper"
    return "duckduckgo"


def query(q, freshness_days=7):
    p = provider()
    if p == "brave":
        fr = "pd" if freshness_days <= 1 else ("pw" if freshness_days <= 7 else "pm")
        d = http.get_json(f"https://api.search.brave.com/res/v1/web/search?q={quote_plus(q)}&count=20&freshness={fr}",
                          headers={"X-Subscription-Token": http.secret("BRAVE_API_KEY"), "Accept": "application/json"}, retries=1)
        return [{"title": r.get("title", ""), "url": r.get("url", ""), "snippet": html.unescape(re.sub("<[^>]+>", "", r.get("description", "")))}
                for r in (d.get("web") or {}).get("results", [])]
    if p == "serper":
        tbs = "qdr:d" if freshness_days <= 1 else ("qdr:w" if freshness_days <= 7 else "qdr:m")
        d = http.get_json("https://google.serper.dev/search", method="POST", data={"q": q, "num": 20, "tbs": tbs},
                          headers={"X-API-KEY": http.secret("SERPER_API_KEY")}, retries=1)
        return [{"title": r.get("title", ""), "url": r.get("link", ""), "snippet": r.get("snippet", "")} for r in d.get("organic", [])]
    # DuckDuckGo HTML endpoint: best effort, low volume
    time.sleep(2.5)
    df = "d" if freshness_days <= 1 else ("w" if freshness_days <= 7 else "m")
    text = http.get_text(f"https://html.duckduckgo.com/html/?q={quote_plus(q)}&df={df}", retries=0)
    out = []
    for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?(?:class="result__snippet"[^>]*>(.*?)</a>)?', text, re.S):
        href = html.unescape(m.group(1))
        if "uddg=" in href:
            href = unquote(parse_qs(urlparse(href).query).get("uddg", [href])[0])
        out.append({"title": html.unescape(re.sub("<[^>]+>", "", m.group(2))).strip(),
                    "url": href, "snippet": html.unescape(re.sub("<[^>]+>", "", m.group(3) or "")).strip()})
    return out


_LI = [
    re.compile(r"^(?P<company>.+?) hiring (?P<title>.+?) in (?P<loc>.+?)(?: \| LinkedIn)?$", re.I),
    re.compile(r"^(?P<title>.+?) - (?P<company>.+?) - (?P<loc>.+?)(?: \| LinkedIn| - LinkedIn)?$", re.I),
    re.compile(r"^(?P<title>.+?) at (?P<company>.+?)(?: \| LinkedIn| - LinkedIn)?$", re.I),
]


def to_job(r):
    """Turn a search result into (board_key or None, job or None)."""
    url, title = r["url"], r["title"]
    key = parse_ats_url(url)
    if key:
        return key, None
    host = urlparse(url).netloc.lower()
    if "linkedin.com" in host and "/jobs/view" in url:
        for pat in _LI:
            m = pat.match(title)
            if m and title_family(m.group("title")):
                loc = m.groupdict().get("loc") or ""
                return None, make_job(title=m.group("title"), company=m.group("company"), url=url.split("?")[0], source="linkedin",
                                      kind="search", board="LinkedIn", locations=[loc], description=r.get("snippet", ""))
        return None, None
    t = re.split(r" \| | – | — | - ", title)[0]
    if title_family(t):
        return None, make_job(title=t, company="", url=url, source=host.replace("www.", ""), kind="search", board=host,
                              description=r.get("snippet", ""))
    return None, None
